"""
agents_ws.py — /ws/agents/{agent_id}
WebSocket hub for Desktop Agent connections.
On connect  → Agent.status = ONLINE
On disconnect → Agent.status = OFFLINE
"""
import json
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from server.database import SessionLocal
from server.models import Agent

router = APIRouter(tags=["Agents WS"])

# In-memory registry  {agent_id: WebSocket}
_connections: dict[str, WebSocket] = {}


def _get_or_create_agent(db, agent_id: str, host_info: dict) -> Agent:
    agent = db.query(Agent).filter(Agent.name == agent_id).first()
    if not agent:
        agent = Agent(
            name=agent_id,
            host_os=host_info.get("os"),
            host_ip=host_info.get("ip"),
        )
        db.add(agent)
    agent.status    = "ONLINE"
    agent.last_seen = datetime.now(timezone.utc).replace(tzinfo=None)
    if host_info.get("os"):
        agent.host_os = host_info["os"]
    if host_info.get("ip"):
        agent.host_ip = host_info["ip"]
    db.commit()
    return agent


@router.websocket("/ws/agents/{agent_id}")
async def agent_ws(websocket: WebSocket, agent_id: str):
    await websocket.accept()
    _connections[agent_id] = websocket

    db = SessionLocal()
    try:
        # Wait for the agent's hello payload: {"type":"hello","os":"Windows","ip":"x.x.x.x"}
        hello_raw = await websocket.receive_text()
        try:
            hello = json.loads(hello_raw)
        except Exception:
            hello = {}

        agent = _get_or_create_agent(db, agent_id, hello)
        await websocket.send_text(json.dumps({"type": "ack", "status": "ONLINE", "agent_db_id": agent.id}))

        # Main message loop
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except Exception:
                await websocket.send_text(json.dumps({"type": "error", "detail": "Invalid JSON"}))
                continue

            # Broadcast or echo for now
            await websocket.send_text(json.dumps({"type": "echo", "received": payload}))

    except WebSocketDisconnect:
        pass
    finally:
        _connections.pop(agent_id, None)
        # Mark offline
        agent_row = db.query(Agent).filter(Agent.name == agent_id).first()
        if agent_row:
            agent_row.status = "OFFLINE"
            db.commit()
        db.close()


async def broadcast(message: str):
    """Utility: push message to all connected agents."""
    for ws in list(_connections.values()):
        try:
            await ws.send_text(message)
        except Exception:
            pass
