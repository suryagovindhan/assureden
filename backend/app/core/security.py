"""
security.py — Password hashing, JWT access + refresh tokens
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings


# ── Password ─────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ── JWT ───────────────────────────────────────────────────────────────────────

def _encode(payload: dict) -> str:
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _decode(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


def create_access_token(user_id: UUID, org_id: UUID, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return _encode({
        "sub":     str(user_id),
        "org_id":  str(org_id),
        "role":    role,
        "type":    "access",
        "exp":     expire,
    })


def create_refresh_token(user_id: UUID, org_id: UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    return _encode({
        "sub":    str(user_id),
        "org_id": str(org_id),
        "type":   "refresh",
        "exp":    expire,
    })


def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = _decode(token)
        if payload.get("type") != "access":
            return None
        return payload
    except JWTError:
        return None


def decode_refresh_token(token: str) -> Optional[dict]:
    try:
        payload = _decode(token)
        if payload.get("type") != "refresh":
            return None
        return payload
    except JWTError:
        return None


def create_sse_ticket(
    user_id: UUID,
    org_id: UUID,
    *,
    run_id: Optional[str] = None,
) -> str:
    """
    Create a short-lived (SSE_TICKET_EXPIRE_SECONDS) single-purpose token.

    Properties:
    - type = "sse"  → rejected by decode_access_token / decode_refresh_token
    - Optionally scoped to a single run_id to prevent ticket reuse across runs
    - Intended for use as ?token=<ticket> on GET /sse/runs/{id}
    """
    expire = datetime.now(timezone.utc) + timedelta(
        seconds=settings.SSE_TICKET_EXPIRE_SECONDS
    )
    payload: dict = {
        "sub":    str(user_id),
        "org_id": str(org_id),
        "type":   "sse",
        "exp":    expire,
    }
    if run_id:
        payload["run_id"] = str(run_id)
    return _encode(payload)


def decode_sse_ticket(token: str, *, run_id: Optional[str] = None) -> Optional[dict]:
    """
    Validate an SSE ticket. Returns the payload or None.

    If `run_id` is provided, also validates the ticket is scoped to that run
    (when the ticket was issued with a run_id scope).
    """
    try:
        payload = _decode(token)
        if payload.get("type") != "sse":
            return None
        # Validate run_id scope if the ticket was scoped
        ticket_run_id = payload.get("run_id")
        if ticket_run_id and run_id and ticket_run_id != str(run_id):
            return None
        return payload
    except JWTError:
        return None
