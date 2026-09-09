"""
api/realtime/router.py — Phase 5: SSE live execution updates.

## Authentication

The app uses JWT Bearer tokens stored in memory/localStorage. Browser-native
EventSource cannot send Authorization headers, so we use a short-lived
SSE ticket pattern:

  Step 1: Client calls POST /realtime/token to exchange their Bearer token
          for a 60-second SSE ticket scoped to a specific run.

  Step 2: Client opens  GET /sse/runs/{run_id}?token=<ticket>

The SSE ticket:
  - is signed with the same JWT_SECRET_KEY
  - has type="sse" (rejected by the regular token validators)
  - optionally scoped to a single run_id
  - expires in SSE_TICKET_EXPIRE_SECONDS (default 60s)
  - single-use only within its validity window (server does NOT track usage,
    but the 60s window and run_id scope makes reuse impractical)

## SSE Stream

GET /sse/runs/{run_id}

Streams RunEvent rows as Server-Sent Events in the stable schema:

  data: {"sequence": 42, "timestamp": "...", "severity": "INFO",
         "event": "RUN_STARTED", "message": "...", "metadata": {}}

Query parameters:
  token           Required. Short-lived SSE ticket from POST /realtime/token.
  last_sequence   Optional. Resume from this sequence number (default: 0).

The stream polls the RunEvent table every 1 second for new rows.
It closes automatically when the run reaches a terminal status.

## Event Schema (stable)

All RunEvent emissions use:
  sequence  — monotone integer per run
  timestamp — ISO-8601 UTC
  severity  — INFO | WARNING | ERROR | DEBUG
  event     — string identifier (e.g. QUEUED, RUN_STARTED, SCHEDULE_TRIGGERED)
  message   — human-readable description
  metadata  — arbitrary JSON object (≤ RUN_EVENT_MAX_METADATA_BYTES)

This schema is shared by: Event Log UI, SSE stream, Webhook payloads, Audit export.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import CurrentUser
from app.core.security import create_sse_ticket, decode_sse_ticket
from app.db.session import get_db
from app.db.repositories.foundation import UserRepository
from app.db.repositories.executions import TestRunRepository
from app.models.executions import RunStatus

router = APIRouter(tags=["realtime"])

# Terminal run states — stream closes once reached
TERMINAL_STATUSES = {
    RunStatus.COMPLETED,
    RunStatus.FAILED,
    RunStatus.ABORTED,
    RunStatus.CANCELLED,
    RunStatus.TIMED_OUT,
}

# ── Ticket Endpoint ───────────────────────────────────────────────────────────

@router.post("/realtime/token", status_code=status.HTTP_201_CREATED)
def issue_sse_ticket(
    run_id: Optional[UUID] = None,
    current_user: CurrentUser = None,
):
    """
    Exchange a Bearer access token for a short-lived SSE ticket.

    POST /realtime/token?run_id=<uuid>   (optional: scope to a single run)

    Response:
      { "token": "<ticket>", "expires_in": 60 }

    The returned token:
    - is valid for SSE_TICKET_EXPIRE_SECONDS seconds
    - is scoped to the given run_id if provided (prevents use on other runs)
    - is usable only on the SSE endpoint (type="sse"; access/refresh routes reject it)
    """
    ticket = create_sse_ticket(
        user_id=current_user.id,
        org_id=current_user.org_id,
        run_id=str(run_id) if run_id else None,
    )
    return {
        "token":      ticket,
        "expires_in": settings.SSE_TICKET_EXPIRE_SECONDS,
    }


# ── SSE Stream ────────────────────────────────────────────────────────────────

def _fmt_sse(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data)}\n\n"


def _get_run_events_since(db: Session, run_id: UUID, org_id: UUID, after_seq: int):
    """Return RunEvent rows for run_id with sequence > after_seq, ordered ascending."""
    from app.models.executions import RunEvent
    return (
        db.query(RunEvent)
        .filter(
            RunEvent.run_id == run_id,
            RunEvent.sequence > after_seq,
        )
        .order_by(RunEvent.sequence.asc())
        .all()
    )


def _get_run_status(db: Session, run_id: UUID, org_id: UUID):
    from app.models.executions import TestRun
    run = db.query(TestRun).filter(TestRun.id == run_id, TestRun.org_id == org_id).first()
    return run.status if run else None


async def _event_stream(
    run_id: UUID,
    org_id: UUID,
    last_sequence: int,
    db: Session,
) -> AsyncGenerator[str, None]:
    """
    Async generator yielding SSE-formatted strings.

    Polls the RunEvent table every 1 second. Closes when the run
    reaches a terminal status AND all pending events have been flushed.
    """
    current_seq = last_sequence

    # Send an initial connection confirmation
    yield _fmt_sse({
        "sequence":  -1,
        "event":     "SSE_CONNECTED",
        "severity":  "INFO",
        "message":   f"Connected to run {run_id}. Resuming from sequence {last_sequence}.",
        "metadata":  {"run_id": str(run_id), "last_sequence": last_sequence},
        "timestamp": None,
    })

    while True:
        await asyncio.sleep(1)

        # Fetch new events
        try:
            new_events = _get_run_events_since(db, run_id, org_id, current_seq)
        except Exception:
            # DB error — yield warning and continue
            yield _fmt_sse({"event": "SSE_ERROR", "message": "DB read error"})
            continue

        for ev in new_events:
            current_seq = ev.sequence
            yield _fmt_sse({
                "sequence":  ev.sequence,
                "timestamp": ev.timestamp.isoformat() if ev.timestamp else None,
                "severity":  ev.severity,
                "event":     ev.event,
                "message":   ev.message,
                "metadata":  ev.event_metadata or {},
            })

        # Check if run has reached a terminal state
        run_status = _get_run_status(db, run_id, org_id)
        if run_status in TERMINAL_STATUSES:
            yield _fmt_sse({
                "sequence":  current_seq + 1,
                "event":     "SSE_CLOSED",
                "severity":  "INFO",
                "message":   f"Run reached terminal status: {run_status}. Stream closing.",
                "metadata":  {"final_status": run_status},
                "timestamp": None,
            })
            break


@router.get("/sse/runs/{run_id}")
async def sse_run_events(
    run_id: UUID,
    token: str = Query(..., description="Short-lived SSE ticket from POST /realtime/token"),
    last_sequence: int = Query(0, description="Resume from this sequence (exclusive)"),
    db: Session = Depends(get_db),
):
    """
    Stream RunEvents for a run as Server-Sent Events.

    Authentication: `?token=<sse_ticket>` from POST /realtime/token.

    The stream closes automatically when the run reaches a terminal status.
    Clients should reconnect with `?last_sequence=N` using the last
    received sequence number to resume without duplicate events.

    Event format:
      data: {"sequence":N,"timestamp":"...","severity":"INFO","event":"...","message":"...","metadata":{}}
    """
    # ── Authenticate via SSE ticket ───────────────────────────────────────────
    payload = decode_sse_ticket(token, run_id=str(run_id))
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or misscoped SSE ticket",
        )

    org_id = UUID(payload["org_id"])

    # ── Verify run access ─────────────────────────────────────────────────────
    repo = TestRunRepository(db)
    run = repo.get_run(run_id, org_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    # ── Stream ────────────────────────────────────────────────────────────────
    return StreamingResponse(
        _event_stream(run_id, org_id, last_sequence, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control":   "no-cache",
            "X-Accel-Buffering": "no",   # Disable nginx buffering
        },
    )
