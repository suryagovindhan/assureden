"""
server/routers/sandbox_ws.py — Sandbox WebSocket endpoint
──────────────────────────────────────────────────────────
Launches recorder_worker.py as a subprocess (separate Python process).
Reads JSON-lines from its stdout in a background thread and streams
them to the browser UI via WebSocket.

This avoids all greenlet/asyncio/thread conflicts that arise when
running sync_playwright inside a FastAPI worker process.
"""

import asyncio
import json
import os
import subprocess
import sys
import threading
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["Sandbox"])

# Path to the standalone recorder worker script
_HERE = os.path.dirname(os.path.abspath(__file__))
_WORKER_SCRIPT = os.path.join(os.path.dirname(_HERE), "recorder_worker.py")


@router.websocket("/ws/sandbox")
async def sandbox_ws(websocket: WebSocket):
    await websocket.accept()
    loop = asyncio.get_running_loop()

    # Initial handshake
    await websocket.send_text(json.dumps({
        "type": "ack",
        "status": "READY",
        "message": "Sandbox ready. Send a codegen command to open the Custom Recorder."
    }))

    proc:      subprocess.Popen | None = None
    all_steps: list = []

    def send_sync(msg: dict):
        """Thread-safe send to the WebSocket from a background thread."""
        try:
            asyncio.run_coroutine_threadsafe(
                websocket.send_text(json.dumps(msg)), loop
            )
        except Exception:
            pass

    def _read_worker_stdout(p: subprocess.Popen):
        """
        Background thread: reads JSON lines from the worker's stdout (and stderr)
        and dispatches them to the browser UI.
        """
        try:
            if not p.stdout:
                return
            for raw in p.stdout:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    msg = json.loads(raw)
                    mtype = msg.get("type")

                    if mtype == "ready":
                        send_sync({"type": "codegen_line",
                                   "line": "[Recorder] Browser launched ✓ — interact with the app. Click Stop when done."})
                    elif mtype == "step":
                        step = msg.get("step", {})
                        seq  = msg.get("sequence", len(all_steps) + 1)
                        all_steps.append(step)
                        send_sync({"type": "recorded_step", "step": step, "sequence": seq})
                    elif mtype == "script":
                        send_sync({"type": "codegen_script", "script": msg.get("script", "")})
                    elif mtype == "all_steps":
                        send_sync({"type": "all_steps", "steps": msg.get("steps", [])})
                    elif mtype == "error":
                        send_sync({"type": "error", "detail": msg.get("detail", "Unknown error")})
                    elif mtype == "closed":
                        send_sync({"type": "codegen_line", "line": "[Recorder] Session closed."})
                except json.JSONDecodeError:
                    # Non-JSON output (tracebacks, prints)
                    send_sync({"type": "codegen_line", "line": f"[Worker Log] {raw}"})

        except Exception as exc:
            send_sync({"type": "error", "detail": f"Worker read error: {exc}"})
        finally:
            if p.poll() is not None:
                all_steps_copy = list(all_steps) # snapshot
                send_sync({"type": "codegen_line",
                           "line": f"[Recorder] Worker exited (code {p.returncode})."})

    try:
        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                break
            except Exception:
                break

            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"type": "error", "detail": "Invalid JSON"}))
                continue

            cmd = payload.get("type", "")

            # ── Launch recorder ─────────────────────────────────────────────
            if cmd == "codegen":
                # Kill existing
                if proc and proc.poll() is None:
                    try: 
                        proc.stdin.write("stop\n")
                        proc.stdin.flush()
                    except Exception: pass
                    try: proc.terminate()
                    except Exception: pass

                all_steps.clear()
                url = payload.get("target_url", "about:blank")

                await websocket.send_text(json.dumps({
                    "type": "codegen_line",
                    "line": f"[Recorder] Opening browser → {url}"
                }))

                # Launch worker in project root for imports
                project_root = os.path.dirname(_HERE)
                
                proc = subprocess.Popen(
                    [sys.executable, _WORKER_SCRIPT, url],
                    stdout=subprocess.PIPE,
                    stdin=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=project_root,
                    text=True,
                    bufsize=1,
                    env=os.environ.copy()
                )

                t = threading.Thread(target=_read_worker_stdout, args=(proc,), daemon=True)
                t.start()

            # ── Stop recording ──────────────────────────────────────────────
            elif cmd == "stop":
                await websocket.send_text(json.dumps({
                    "type": "codegen_line", "line": "[Recorder] Stop signal sent..."
                }))
                if proc and proc.poll() is None:
                    try:
                        proc.stdin.write("stop\n")
                        proc.stdin.flush()
                    except Exception:
                        try: proc.terminate()
                        except Exception: pass

            else:
                await websocket.send_text(json.dumps({"type": "echo", "received": payload}))

    finally:
        # Clean up
        if proc and proc.poll() is None:
            try: 
                proc.stdin.write("stop\n")
                proc.stdin.flush()
            except Exception: pass
            try: proc.terminate()
            except Exception: pass
