"""Opt-in real Chromium/Edge acceptance test through authenticated FastAPI routes."""
import asyncio
import os
import sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import httpx
import pytest

from test_execution_contract import execution_data  # noqa: F401
from app.main import app
from app.models.test_cases import TestStep as Step, StepAssertion
from app.core.config import settings
from app.storage import get_storage

pytestmark = pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Set RUN_BROWSER_TESTS=1 with Playwright installed")


@pytest.mark.parametrize("expected,fatal,optional,status,use_flow", [
    ("Hello Ada", True, False, "COMPLETED", False),
    ("Wrong", True, False, "FAILED", False),
    ("Wrong", False, False, "COMPLETED", False),
    ("Wrong", True, True, "COMPLETED", False),
    ("Hello Ada", True, False, "COMPLETED", True),
])
def test_real_browser_execution(client, db, execution_data, tmp_path, monkeypatch, expected, fatal, optional, status, use_flow):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from execution_agent.worker import AgentWorker
    d = execution_data

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'''<!doctype html><title>Agent acceptance</title><input id="name">
            <button onclick="document.querySelector('#result').textContent='Hello '+document.querySelector('#name').value">Greet</button>
            <div id="result"></div>'''
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    monkeypatch.setattr(settings, "ARTIFACT_LOCAL_BASE_PATH", str(tmp_path))
    get_storage.cache_clear()
    try:
        d.step.target_url = f"http://127.0.0.1:{server.server_port}"
        type_step = Step(org_id=d.org.id, test_case_id=d.case.id, position=2, action="TYPE",
                         page_object_id=d.obj.id, input_value="{{NAME}}", timeout_ms=2500)
        # Assertion locator differs from the action locator.
        from app.models.object_repository import PageObject
        button = PageObject(org_id=d.org.id, page_id=d.obj.page_id, name="Greet", object_type="BUTTON",
                            locators=[{"type": "TEXT", "value": "Greet"}])
        output = PageObject(org_id=d.org.id, page_id=d.obj.page_id, name="Result", object_type="TEXT",
                            locators=[{"type": "ID", "value": "result"}])
        db.add_all([type_step, button, output]); db.flush()
        click = Step(org_id=d.org.id, test_case_id=d.case.id, position=3, action="CLICK",
                     page_object_id=button.id, timeout_ms=2500, is_optional=optional)
        db.add(click); db.flush()
        db.add(StepAssertion(org_id=d.org.id, step_id=click.id, position=1, assertion_type="TEXT_EQUALS",
                             target_page_object_id=output.id, expected_value=expected, is_fatal=fatal))
        db.add(Step(org_id=d.org.id, test_case_id=d.case.id, position=4, action="SCREENSHOT"))
        db.flush()
        if use_flow:
            flow = client.post('/api/flows/', headers=d.headers, json={'name': 'Reusable form setup'}).json()
            for body in ({'action': 'NAVIGATE', 'target_url': d.step.target_url},
                         {'action': 'TYPE', 'page_object_id': str(d.obj.id),
                          'input_value': '{{NAME}}', 'timeout_ms': 2500}):
                response = client.post(f"/api/flows/{flow['id']}/steps", headers=d.headers, json=body)
                assert response.status_code == 201, response.text
            typed_child = response.json()['id']
            response = client.put(f'/api/steps/{d.step.id}', headers=d.headers,
                                  json={'action': 'FLOW', 'flow_id': flow['id'], 'flow_version': 3,
                                        'target_url': None})
            assert response.status_code == 200, response.text
            assert client.delete(f'/api/steps/{type_step.id}', headers=d.headers).status_code == 204
            # This edit must not change the test case pinned to revision 3.
            assert client.put(f'/api/flows/steps/{typed_child}', headers=d.headers,
                              json={'input_value': 'Wrong revision'}).status_code == 200
        queued = client.post("/api/runs", headers=d.headers,
                             json={"test_case_id": str(d.case.id), "run_variables": {"NAME": "Ada"}})
        assert queued.status_code == 201, queued.text
        run_id = queued.json()["id"]

        async def run_agent():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url="http://test", headers=d.agent_headers) as api:
                worker = AgentWorker(api, channel=os.getenv("ASSUREDEN_BROWSER_CHANNEL"))
                assert await worker.poll_once() == run_id
        asyncio.run(run_agent())
        run = client.get(f"/api/runs/{run_id}", headers=d.headers).json()
        assert run["status"] == status, run
        results = client.get(f"/api/runs/{run_id}/steps", headers=d.headers).json()
        assert len(results) == 4
        assert results[1]["status"] == "PASSED", results
        assert results[2]["assertions"][0]["status"] == ("PASSED" if expected == "Hello Ada" else "FAILED")
        artifacts = client.get(f"/api/runs/{run_id}/artifacts", headers=d.headers).json()["items"]
        assert artifacts
        screenshot = client.get(artifacts[0]["url"], headers=d.headers)
        assert screenshot.status_code == 200 and screenshot.content.startswith(b"\x89PNG")
        assert client.get(artifacts[0]["url"]).status_code in (401, 403)
        assert artifacts[0]["step_result_id"] in {r["id"] for r in results}
    finally:
        server.shutdown(); thread.join(); server.server_close()
        get_storage.cache_clear()


def test_assertion_library_in_browser():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from execution_agent.worker import check_assertion
    from playwright.async_api import async_playwright

    async def verify():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(channel=os.getenv("ASSUREDEN_BROWSER_CHANNEL"))
            try:
                page = await browser.new_page()
                await page.set_content('<title>Assertions</title><div id="text" data-test="yes">Hello Ada</div>'
                                       '<input id="value" value="Ada"><input id="on" type="checkbox" checked>'
                                       '<input id="off" type="checkbox"><button id="disabled" disabled>Disabled</button>')
                cases = [
                    ("VISIBLE", "text", ""), ("NOT_VISIBLE", "missing", ""),
                    ("TEXT_EQUALS", "text", "Hello Ada"), ("TEXT_CONTAINS", "text", "Ada"),
                    ("TEXT_MATCHES", "text", "Hello.*"), ("VALUE_EQUALS", "value", "Ada"),
                    ("ATTRIBUTE_EQUALS", "text", "yes"), ("URL_EQUALS", None, "about:blank"),
                    ("URL_CONTAINS", None, "blank"), ("TITLE_EQUALS", None, "Assertions"),
                    ("ELEMENT_COUNT", "text", "1"), ("ELEMENT_COUNT", "missing", "0"),
                    ("ENABLED", "value", ""), ("DISABLED", "disabled", ""),
                    ("CHECKED", "on", ""), ("UNCHECKED", "off", ""),
                ]
                for kind, target, expected in cases:
                    assertion = {"assertion_type": kind, "expected_value": expected, "attribute_name": "data-test",
                                 "locator": {"strategy": "ID", "selector": target} if target else None}
                    await check_assertion(page, page, assertion, 1000)
                await check_assertion(page, page, {"assertion_type": "VISIBLE", "is_negated": True,
                                      "locator": {"strategy": "ID", "selector": "missing"}}, 1000)
            finally:
                await browser.close()
    asyncio.run(verify())


def test_record_review_promote_and_replay(client, db, execution_data):
    import uuid
    from sqlalchemy import select
    from app.models.executions import TestRun as Run
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from execution_agent.recorder import RecordingSession
    from execution_agent.worker import AgentWorker
    from playwright.async_api import async_playwright
    d = execution_data

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'<input id="name"><input id="password" type="password"><button id="go">Save</button>'
            self.send_response(200); self.send_header("Content-Type", "text/html")
            self.end_headers(); self.wfile.write(body)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    recorder = RecordingSession("Recorded browser test", url)
    try:
        async def capture():
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(channel=os.getenv("ASSUREDEN_BROWSER_CHANNEL"))
                try:
                    context = await browser.new_context()
                    await recorder.attach(context)
                    page = await context.new_page(); await page.goto(url)
                    await page.locator("#name").fill("Ada")
                    await page.locator("#password").fill("never-export-this-password")
                    await page.locator("#go").click()
                    for _ in range(100):
                        if len(recorder.data["steps"]) >= 4:
                            break
                        await asyncio.sleep(0.02)
                    assert len(recorder.data["steps"]) == 4, recorder.data
                finally:
                    await browser.close()
        asyncio.run(capture())
        assert "never-export-this-password" not in str(recorder.data)
        created = client.post("/api/drafts", headers=d.headers, json=recorder.data)
        assert created.status_code == 201, created.text
        draft = created.json()
        promoted = client.post(f"/api/drafts/{draft['id']}/promote", headers=d.headers,
                               json={"expected_version": 1, "page_id": str(d.obj.page_id)})
        assert promoted.status_code == 200, promoted.text
        case_id = uuid.UUID(promoted.json()["test_case_id"])
        steps = db.scalars(select(Step).where(Step.test_case_id == case_id).order_by(Step.position)).all()
        db.add(StepAssertion(org_id=d.org.id, step_id=steps[1].id, assertion_type="VALUE_EQUALS",
                             expected_value="Ada", position=1))
        db.flush()
        env = client.post("/api/environments", headers=d.headers, json={"name": "Recorder secrets"}).json()
        secret_key = recorder.data["steps"][2]["input_value"][2:-2]
        response = client.post(f"/api/environments/{env['id']}/variables", headers=d.headers,
                               json={"key": secret_key, "value": "replay-test-only", "is_secret": True})
        assert response.status_code == 201, response.text
        queued = client.post("/api/runs", headers=d.headers,
                             json={"test_case_id": str(case_id), "environment_id": env["id"]})
        assert queued.status_code == 201, queued.text
        run_id = queued.json()["id"]
        async def replay():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", headers=d.agent_headers) as api:
                assert await AgentWorker(api, channel=os.getenv("ASSUREDEN_BROWSER_CHANNEL")).poll_once() == run_id
        asyncio.run(replay())
        run = db.get(Run, uuid.UUID(run_id))
        assert run.status == "COMPLETED" and run.passed_steps == 4
        assert "replay-test-only" not in str(run.execution_snapshot)
    finally:
        server.shutdown(); thread.join(); server.server_close()
