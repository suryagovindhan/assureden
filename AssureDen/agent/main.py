"""
agent/main.py — AssureDen Desktop Agent
────────────────────────────────────────
• Connects to the Central Server via WebSocket
• Sends a 'hello' registration payload with OS and IP info
• Maintains a resilient reconnect loop with exponential back-off
• Dispatches received JSON command payloads to executor.py
"""

import asyncio
import json
import os
import platform
import socket
import sys

import websockets

# Allow absolute imports when run as a script
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from agent.executor import execute

# ── Configuration ─────────────────────────────────────────────────────────────
SERVER_HOST = os.getenv("ASSUREDEN_SERVER_HOST", "127.0.0.1")
SERVER_PORT = os.getenv("ASSUREDEN_SERVER_PORT", "8001")
AGENT_ID    = os.getenv("ASSUREDEN_AGENT_ID", socket.gethostname())

WS_URL  = f"ws://{SERVER_HOST}:{SERVER_PORT}/ws/agents/{AGENT_ID}"
RECONNECT_INITIAL = 5    # seconds
RECONNECT_MAX     = 30   # seconds cap


def _get_hello() -> str:
    return json.dumps({
        "type": "hello",
        "os":   platform.system() + " " + platform.release(),
        "ip":   socket.gethostbyname(socket.gethostname()),
    })


async def _connect_and_listen():
    """Single connection attempt — raises on failure so caller can retry."""
    print(f"[Agent] Connecting → {WS_URL}")
    async with websockets.connect(WS_URL) as ws:
        # Send registration
        await ws.send(_get_hello())
        ack = await ws.recv()
        print(f"[Agent] Server ACK: {ack}")

        # Command loop
        async for raw in ws:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                print(f"[Agent] Invalid JSON: {raw!r}")
                continue

            print(f"[Agent] Command received: {payload}")
            result = await execute(payload)
            await ws.send(json.dumps({"type": "result", "result": result}))


async def run():
    """Resilient reconnect loop with exponential back-off."""
    delay = RECONNECT_INITIAL
    while True:
        try:
            await _connect_and_listen()
            delay = RECONNECT_INITIAL   # reset on clean disconnect
        except (websockets.ConnectionClosed, OSError) as e:
            print(f"[Agent] Disconnected: {e}. Retrying in {delay}s…")
        except Exception as e:
            print(f"[Agent] Unexpected error: {e}. Retrying in {delay}s…")
        await asyncio.sleep(delay)
        delay = min(delay * 2, RECONNECT_MAX)


if __name__ == "__main__":
    asyncio.run(run())
