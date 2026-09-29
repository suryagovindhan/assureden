import hashlib
import io
import uuid
import zipfile
from datetime import timedelta
from sqlalchemy import select
from test_execution_contract import execution_data
from app.db.base import utcnow
from app.models.agent_control import AgentEnrollment, BrowserRecording
from app.models.drafts import DraftAsset
from app.models.foundation import Agent
from app.models.executions import TestRun as Run


def ready(client, d):
    response = client.post('/api/agents/heartbeat-extended', headers=d.agent_headers,
                           json={'recording': True, 'protocol_version': 2, 'supported_actions': ['NAVIGATE']})
    assert response.status_code == 204


def start(client, d):
    ready(client, d)
    response = client.post('/api/agent-control/recordings', headers=d.headers,
                           json={'agent_id': str(d.agent.id), 'name': 'Record test', 'url': 'https://example.test'})
    assert response.status_code == 201, response.text
    return response.json()['id']


def test_enrollment_claim_is_one_time_and_device_retry_safe(client, db, execution_data):
    d = execution_data
    response = client.post('/api/agent-control/enroll', headers=d.headers, json={'name': 'Desktop'})
    assert response.status_code == 200, response.text
    data = response.json()
    body = {'code': data['code'], 'key_hash': hashlib.sha256(b'device-key').hexdigest()}
    for _ in range(2):
        assert client.post('/api/agent-control/claim', json=body).status_code == 200
    agent = db.get(Agent, uuid.UUID(data['agent_id']))
    assert agent.org_id == d.org.id and agent.api_key_hash == body['key_hash']
    assert client.post('/api/agent-control/claim', json={**body, 'key_hash': 'a' * 64}).status_code == 409
    enrollment = db.scalar(select(AgentEnrollment).where(AgentEnrollment.agent_id == agent.id))
    enrollment.expires_at = utcnow() - timedelta(seconds=1); db.flush()
    assert client.post('/api/agent-control/claim', json=body).status_code == 401
    d.user.role = 'TESTER'; db.flush()
    assert client.post('/api/agent-control/enroll', headers=d.headers, json={'name': 'Denied'}).status_code == 403


def test_recording_stops_completes_once_and_prevents_run_claim(client, db, execution_data):
    d = execution_data
    rid = start(client, d)
    response = client.post('/api/runs', headers=d.headers, json={'test_case_id': str(d.case.id)})
    assert response.status_code == 201
    assert client.post('/api/agents/poll', headers=d.agent_headers).json() == {'status': 'no_work'}
    request = client.post('/api/agent-control/poll', headers=d.agent_headers).json()
    assert request['id'] == rid and request['status'] == 'RECORDING'
    assert client.post('/api/agent-control/poll', headers=d.agent_headers).json() is None
    assert client.post(f'/api/agent-control/recordings/{rid}/stop', headers=d.headers).json()['status'] == 'STOP_REQUESTED'
    body = {'name': 'Untrusted name', 'steps': [{'action': 'NAVIGATE', 'input_value': 'https://example.test'}]}
    results = [client.post(f'/api/agent-control/recordings/{rid}/complete', headers=d.agent_headers, json=body) for _ in range(2)]
    assert all(r.status_code == 200 for r in results), results[0].text
    assert results[0].json()['draft_id'] == results[1].json()['draft_id']
    draft = db.get(DraftAsset, uuid.UUID(results[0].json()['draft_id']))
    assert draft.name == 'Record test' and draft.created_by == d.user.id
    assert client.post('/api/agents/poll', headers=d.agent_headers).json()['execute_request']
    assert client.get('/api/agents/', headers=d.headers).status_code == 200


def test_recording_access_busy_expiry_and_validation(client, db, execution_data):
    d = execution_data
    body = {'agent_id': str(d.agent.id), 'name': 'Test', 'url': 'https://example.test'}
    assert client.post('/api/agent-control/recordings', headers=d.headers, json=body).status_code == 409
    rid = start(client, d)
    assert client.post('/api/agent-control/recordings', headers=d.headers, json=body).status_code == 409
    for patch in ({'url': 'file:///private'}, {'url': 'https://user:password@example.test'}, {'agent_id': str(uuid.uuid4())}):
        assert client.post('/api/agent-control/recordings', headers=d.headers, json={**body, **patch}).status_code in (404, 422)
    assert client.get(f'/api/agent-control/recordings/{uuid.uuid4()}/state', headers=d.agent_headers).status_code == 404
    assert client.post(f'/api/agent-control/recordings/{rid}/stop', headers=d.headers).json()['status'] == 'CANCELLED'
    rid = start(client, d)
    row = db.get(BrowserRecording, uuid.UUID(rid)); row.expires_at = utcnow() - timedelta(seconds=1); db.flush()
    assert client.post('/api/agent-control/poll', headers=d.agent_headers).json() is None
    assert client.get('/api/agent-control/recordings', headers=d.headers).json()[0]['status'] == 'EXPIRED'
    d.user.role = 'VIEWER'; db.flush()
    assert client.post('/api/agent-control/recordings', headers=d.headers, json=body).status_code == 403


def test_requested_agent_scoping_and_routing(client, db, execution_data):
    d = execution_data
    ready(client, d)
    other = Agent(org_id=d.org.id, name='Other', api_key_hash=hashlib.sha256(b'other').hexdigest(),
                  capabilities={'protocol_version': 2, 'supported_actions': ['NAVIGATE']})
    db.add(other); db.flush()
    body = {'test_case_id': str(d.case.id), 'requested_agent_id': str(other.id)}
    response = client.post('/api/runs', headers=d.headers, json=body)
    assert response.status_code == 201, response.text
    assert client.post('/api/agents/poll', headers=d.agent_headers).json() == {'status': 'no_work'}
    assert client.post('/api/agents/poll', headers={'X-Agent-Api-Key': 'other'}).json()['execute_request']
    assert client.post('/api/runs', headers=d.headers, json={**body, 'requested_agent_id': str(uuid.uuid4())}).status_code == 422


def test_download_contains_companion_and_installer(client, execution_data):
    response = client.get('/api/agent-control/download', headers=execution_data.headers)
    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert {'Install.cmd', 'Install.ps1', 'execution_agent/desktop.py', 'execution_agent/worker.py'} <= set(archive.namelist())
        assert not any('.env' in name or 'connection.bin' in name for name in archive.namelist())


def test_cancelled_recording_cannot_upload_and_empty_case_cannot_run(client, db, execution_data):
    d = execution_data
    rid = start(client, d)
    client.post('/api/agent-control/poll', headers=d.agent_headers)
    response = client.post(f'/api/agent-control/recordings/{rid}/cancel', headers=d.headers)
    assert response.status_code == 200 and response.json()['status'] == 'CANCELLED'
    response = client.post(f'/api/agent-control/recordings/{rid}/complete', headers=d.agent_headers,
                           json={'name': 'Discarded', 'steps': [{'action': 'NAVIGATE', 'input_value': 'about:blank'}]})
    assert response.status_code == 409
    d.step.is_enabled = False; db.flush()
    response = client.post('/api/runs', headers=d.headers, json={'test_case_id': str(d.case.id)})
    assert response.status_code == 422 and 'enabled test step' in response.text
