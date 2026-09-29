"""Pinned flow behavior through authoring APIs and the execution snapshot."""
import uuid
import pytest
from sqlalchemy import select
from app.models.foundation import AssetRevision
from app.models.flows import Flow
from app.services.snapshot_builder import build_snapshot
from tests.test_execution_contract import execution_data


def create_navigation(client, d):
    response = client.post('/api/flows/', headers=d.headers, json={'name': 'Reusable navigation'})
    assert response.status_code == 201, response.text
    flow_id = response.json()['id']
    response = client.post(f'/api/flows/{flow_id}/steps', headers=d.headers,
                           json={'action': 'NAVIGATE', 'target_url': 'about:blank#old'})
    assert response.status_code == 201, response.text
    return flow_id, response.json()['id']


def test_pinned_revision_survives_edits_and_repeated_expansion(client, db, execution_data):
    d = execution_data
    flow_id, child_id = create_navigation(client, d)
    response = client.put(f'/api/steps/{d.step.id}', headers=d.headers,
                          json={'action': 'FLOW', 'flow_id': flow_id, 'flow_version': 2,
                                'target_url': None, 'input_value': None, 'page_object_id': None})
    assert response.status_code == 200, response.text
    assert response.json()['flow_version'] == 2
    response = client.put(f'/api/flows/steps/{child_id}', headers=d.headers,
                          json={'target_url': 'about:blank#new'})
    assert response.status_code == 200, response.text
    history = client.get(f'/api/flows/{flow_id}/revisions', headers=d.headers).json()
    assert [r['version'] for r in history] == [3, 2, 1]
    old = client.get(f'/api/flows/{flow_id}/revisions/2', headers=d.headers).json()
    assert old['steps'][0]['target_url'] == 'about:blank#old'
    snapshot, report = build_snapshot(test_case=d.case, steps=[d.step, d.step],
                                     env_variables=[], run_variables={}, db=db)
    assert report.valid
    assert [s['display_value'] for s in snapshot['steps']] == ['about:blank#old'] * 2
    assert len({s['execution_step_id'] for s in snapshot['steps']}) == 2
    # Explicit upgrade adopts the edit; switching back to an action clears the pin.
    assert client.put(f'/api/steps/{d.step.id}', headers=d.headers,
                      json={'flow_version': 3}).status_code == 200
    snapshot, _ = build_snapshot(test_case=d.case, steps=[d.step], env_variables=[], run_variables={}, db=db)
    assert snapshot['steps'][0]['display_value'] == 'about:blank#new'
    response = client.put(f'/api/steps/{d.step.id}', headers=d.headers, json={'action': 'NAVIGATE'})
    assert response.status_code == 200
    assert response.json()['flow_id'] is None and response.json()['flow_version'] is None


def test_history_preserves_reorder_delete_duplicate_and_metadata(client, db, execution_data):
    d = execution_data
    fid, first = create_navigation(client, d)
    second = client.post(f'/api/flows/{fid}/steps', headers=d.headers,
                         json={'action': 'NAVIGATE', 'target_url': 'about:blank#second'}).json()['id']
    assert client.put(f'/api/flows/{fid}/steps/reorder', headers=d.headers,
                      json={'step_ids': [second, first]}).status_code == 200
    assert client.delete(f'/api/flows/steps/{first}', headers=d.headers).status_code == 204
    assert client.put(f'/api/flows/{fid}', headers=d.headers,
                      json={'expected_version': 5, 'name': 'Renamed'}).status_code == 200
    assert client.put(f'/api/flows/{fid}', headers=d.headers,
                      json={'expected_version': 5, 'name': 'Stale'}).status_code == 409
    clone = client.post(f'/api/flows/{fid}/duplicate', headers=d.headers,
                        json={'new_name': 'Clone'}).json()
    assert clone['created_from_version'] == 6
    assert client.get(f"/api/flows/{clone['id']}/revisions/1", headers=d.headers).json()['steps'][0]['id'] != second
    rows = db.scalars(select(AssetRevision).where(AssetRevision.asset_id == uuid.UUID(fid),
                                                 AssetRevision.asset_type == 'Flow')).all()
    versions = {r.revision: r.snapshot for r in rows}
    assert sorted(versions) == [1, 2, 3, 4, 5, 6]
    assert [s['id'] for s in versions[3]['steps']] == [first, second]
    assert [s['id'] for s in versions[4]['steps']] == [second, first]
    assert len(versions[5]['steps']) == 1
    assert versions[5]['name'] != versions[6]['name']


def test_flow_scope_roles_and_reference_validation(client, db, execution_data):
    d = execution_data
    fid, child = create_navigation(client, d)
    other = Flow(org_id=uuid.uuid4(), name='Other tenant')
    db.add(other); db.flush()
    for values in ({'flow_id': fid, 'flow_version': 99},
                   {'flow_id': str(other.id), 'flow_version': 1},
                   {'flow_id': fid}, {'flow_id': fid, 'flow_version': 2, 'is_optional': True}):
        response = client.post(f'/api/cases/{d.case.id}/steps', headers=d.headers,
                               json={'action': 'FLOW', **values})
        assert response.status_code == 422, response.text
    assert client.get(f'/api/flows/{other.id}/revisions', headers=d.headers).status_code == 404
    response = client.post(f'/api/cases/{d.case.id}/steps', headers=d.headers,
                           json={'action': 'FLOW', 'flow_id': fid, 'flow_version': 2})
    assert response.status_code == 201, response.text
    step_id = response.json()['id']
    assert client.post(f'/api/steps/{step_id}/assertions', headers=d.headers,
                       json={'assertion_type': 'VISIBLE'}).status_code == 422
    d.user.role = 'VIEWER'; db.flush()
    for method, path, body in [('post', '/api/flows/', {'name': 'Forbidden'}),
                               ('put', f'/api/flows/steps/{child}', {'action': 'CLICK'}),
                               ('delete', f'/api/flows/{fid}', None)]:
        response = client.request(method, path, headers=d.headers, json=body)
        assert response.status_code == 403


@pytest.mark.parametrize('body', [{'action': 'NOT_AN_ACTION'}, {'action': 'FLOW'},
                                 {'action': 'CLICK', 'timeout_ms': 0},
                                 {'action': 'CLICK', 'page_object_id': str(uuid.uuid4())}])
def test_flow_invalid_steps_are_rejected(client, execution_data, body):
    fid, _ = create_navigation(client, execution_data)
    response = client.post(f'/api/flows/{fid}/steps', headers=execution_data.headers, json=body)
    assert response.status_code == 422, response.text


def test_empty_and_deleted_flows_fail_queueing(client, db, execution_data):
    d = execution_data
    fid, _ = create_navigation(client, d)
    response = client.put(f'/api/steps/{d.step.id}', headers=d.headers,
                          json={'action': 'FLOW', 'flow_id': fid, 'flow_version': 1,
                                'target_url': None})
    assert response.status_code == 200, response.text
    response = client.post('/api/runs', headers=d.headers, json={'test_case_id': str(d.case.id)})
    assert response.status_code == 422, response.text
    assert 'no enabled steps' in response.text
    assert client.put(f'/api/steps/{d.step.id}', headers=d.headers, json={'flow_version': 2}).status_code == 200
    assert client.delete(f'/api/flows/{fid}', headers=d.headers).status_code == 204
    response = client.post('/api/runs', headers=d.headers, json={'test_case_id': str(d.case.id)})
    assert response.status_code == 422, response.text
    assert db.scalar(select(AssetRevision).where(AssetRevision.asset_id == uuid.UUID(fid),
                                                AssetRevision.revision == 2)) is not None


def test_locators_freeze_at_queue_time_not_flow_authoring(client, db, execution_data):
    d = execution_data
    fid, _ = create_navigation(client, d)
    response = client.post(f'/api/flows/{fid}/steps', headers=d.headers,
                           json={'action': 'TYPE', 'page_object_id': str(d.obj.id), 'input_value': 'Ada'})
    assert response.status_code == 201, response.text
    assert client.put(f'/api/steps/{d.step.id}', headers=d.headers,
                      json={'action': 'FLOW', 'flow_id': fid, 'flow_version': 3,
                            'target_url': None}).status_code == 200
    args = dict(test_case=d.case, steps=[d.step], env_variables=[], run_variables={}, db=db)
    old, _ = build_snapshot(**args)
    d.obj.locators = [{'type': 'ID', 'value': 'new-target'}]; db.flush()
    new, _ = build_snapshot(**args)
    assert old['steps'][1]['locator_snapshot']['selector'] == 'missing'
    assert new['steps'][1]['locator_snapshot']['selector'] == 'new-target'
