"""
core/dependencies.py — FastAPI injectable dependencies

  get_current_user  → validates JWT, returns User model
  get_current_org   → returns org_id from token (no extra DB hit)
  require_role      → factory that asserts the user has a minimum role
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.db.repositories.foundation import UserRepository
from app.models.foundation import User

bearer = HTTPBearer(auto_error=True)

ROLE_ORDER = {"VIEWER": 0, "TESTER": 1, "LEAD": 2, "ADMIN": 3}


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Security(bearer)],
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials
    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id  = UUID(payload["sub"])
    org_id   = UUID(payload["org_id"])

    repo = UserRepository(db)
    user = repo.get(user_id, org_id)

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(minimum_role: str):
    """Factory — returns a dependency that asserts role >= minimum_role."""
    def _check(user: CurrentUser) -> User:
        if ROLE_ORDER.get(user.role, -1) < ROLE_ORDER.get(minimum_role, 99):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role {minimum_role} or higher",
            )
        return user
    return _check
