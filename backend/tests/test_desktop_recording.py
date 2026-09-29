"""Exercise the actual desktop capture loop against browser and authenticated API."""
import asyncio
import json
import os
from pathlib import Path
import sys
import uuid
import httpx
import pytest
from test_execution_contract import execution_data
from app.main import app
from app.models.drafts import DraftAsset

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from execution_agent import desktop


@pytest.mark.skipif(os.name != 'nt', reason='DPAPI is Windows-only')
def test_windows_credential_storage_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(desktop, 'CONFIG', tmp_path / 'connection.bin')
    config = {'server': 'http://127.0.0.1:8000', 'key': 'test-only-device-secret'}
    try:
        desktop.save_config(config)
    except OSError as exc:
        # Codex's impersonated sandbox account has no loaded Windows DPAPI profile.
        # Keep failures fatal for ordinary Windows users, including installer users.
        import subprocess
        identity = subprocess.check_output(['whoami'], text=True).strip().lower()
        if getattr(exc, 'winerror', None) == 2 and '\\codexsandbox' in identity:
            pytest.skip('Impersonated Codex sandbox has no loaded DPAPI user profile; verify pairing under the interactive Windows user')
        raise
    encrypted = desktop.CONFIG.read_bytes()
    assert b'test-only-device-secret' not in encrypted
    assert json.loads(desktop.protect(encrypted, decrypt=True)) == config


@pytest.mark.skipif(os.getenv('RUN_BROWSER_TESTS') != '1', reason='Requires browser runtime')
def test_desktop_stop_upload_review_promote_run(client, db, execution_data, monkeypatch):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from execution_agent.worker import AgentWorker
    d = execution_data
    sessions = []
    class ObservedSession(desktop.RecordingSession):
        async def attach(self, context):
            self.context = context
            await super().attach(context)
            sessions.append(self)
    monkeypatch.setattr(desktop, 'RecordingSession', ObservedSession)
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.send_header('Content-Type', 'text/html'); self.end_headers()
            self.wfile.write(b'<title>Desktop acceptance</title><input id="name"><button id="save">Save</button>')
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        client.post('/api/agents/heartbeat-extended', headers=d.agent_headers, json=desktop.DESKTOP_CAPABILITIES)
        result = client.post('/api/agent-control/recordings', headers=d.headers, json={
            'agent_id': str(d.agent.id), 'name': 'Desktop acceptance', 'url': f'http://127.0.0.1:{server.server_port}'})
        assert result.status_code == 201, result.text
        rid = result.json()['id']
        request = client.post('/api/agent-control/poll', headers=d.agent_headers).json()
        async def exercise():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=d.agent_headers) as api:
                task = asyncio.create_task(desktop.capture(api, request, channel=os.getenv('ASSUREDEN_BROWSER_CHANNEL'), headless=True))
                try:
                    async with asyncio.timeout(20):
                        while not sessions or not sessions[0].context.pages:
                            await asyncio.sleep(.02)
                        page = sessions[0].context.pages[0]
                        await page.locator('#name').fill('Ada')
                        # Keep focus in the field: Stop must blur and capture the final value.
                        response = await api.post(f'/api/agent-control/recordings/{rid}/stop', headers=d.headers)
                        assert response.status_code == 200, response.text
                        return await task
                finally:
                    if not task.done(): task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
        completed = asyncio.run(exercise())
        draft = db.get(DraftAsset, uuid.UUID(completed['draft_id']))
        assert [s['action'] for s in draft.recording['steps']] == ['NAVIGATE', 'TYPE']
        assert draft.recording['steps'][1]['input_value'] == 'Ada'
        promoted = client.post(f'/api/drafts/{draft.id}/promote', headers=d.headers,
                               json={'expected_version': 1, 'page_id': str(d.obj.page_id)})
        assert promoted.status_code == 200, promoted.text
        case_id = promoted.json()['test_case_id']
        case = client.get(f'/api/cases/{case_id}', headers=d.headers).json()
        step_id = case['steps'][1]['id']
        response = client.post(f'/api/steps/{step_id}/assertions', headers=d.headers,
                               json={'assertion_type': 'VALUE_EQUALS', 'expected_value': 'Ada'})
        assert response.status_code == 201, response.text
        async def replay(run_id):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=d.agent_headers) as api:
                assert await AgentWorker(api, channel=os.getenv('ASSUREDEN_BROWSER_CHANNEL')).poll_once() == run_id
        # Both initial Run and Rerun use a fresh saved-case snapshot.
        for _ in range(2):
            queued = client.post('/api/runs', headers=d.headers, json={'test_case_id': case_id, 'requested_agent_id': str(d.agent.id)})
            assert queued.status_code == 201, queued.text
            run_id = queued.json()['id']; asyncio.run(replay(run_id))
            assert client.get(f'/api/runs/{run_id}', headers=d.headers).json()['status'] == 'COMPLETED'
    finally:
        server.shutdown(); thread.join(); server.server_close()
