import pytest
from uuid import uuid4, UUID
from fastapi import status

from app.core.security import create_access_token, create_refresh_token, hash_password
from app.db.repositories.foundation import (
    OrganizationRepository, UserRepository, AgentRepository, AuditEventRepository
)
from app.models.foundation import User, Organization, Agent, AuditEvent

def create_headers(user_id: UUID, org_id: UUID, role: str) -> dict:
    token = create_access_token(user_id, org_id, role)
    return {"Authorization": f"Bearer {token}"}

def test_org_scope_enforced(db, client):
    org_repo = OrganizationRepository(db)
    user_repo = UserRepository(db)
    
    # Create two organizations
    org_a = org_repo.create_org(name="Org A", slug="org-a")
    org_b = org_repo.create_org(name="Org B", slug="org-b")
    db.flush()
    
    # Create users in different orgs
    user_a = user_repo.create_user(
        org_id=org_a.id,
        username="user_a",
        email="user_a@assureden.com",
        hashed_password=hash_password("password123"),
        role="TESTER"
    )
    user_b = user_repo.create_user(
        org_id=org_b.id,
        username="user_b",
        email="user_b@assureden.com",
        hashed_password=hash_password("password123"),
        role="TESTER"
    )
    db.flush()
    
    # Repository scope enforcement: querying Org B user with Org A's ID context returns None
    retrieved = user_repo.get(user_b.id, org_a.id)
    assert retrieved is None
    
    # Listing users for Org A only returns User A, not User B
    users_list = user_repo.list(org_a.id)
    assert user_a in users_list
    assert user_b not in users_list

    # API scope enforcement
    headers_a = create_headers(user_a.id, org_a.id, "TESTER")
    
    # Org A user should be able to get themselves
    resp_self = client.get(f"/api/users/{user_a.id}", headers=headers_a)
    assert resp_self.status_code == status.HTTP_200_OK
    assert resp_self.json()["username"] == "user_a"
    
    # Org A user trying to fetch Org B user gets 404
    resp_other = client.get(f"/api/users/{user_b.id}", headers=headers_a)
    assert resp_other.status_code == status.HTTP_404_NOT_FOUND

def test_soft_delete_excluded(db, client):
    org_repo = OrganizationRepository(db)
    user_repo = UserRepository(db)
    
    org = org_repo.create_org(name="Org Delete Test", slug="org-del-test")
    db.flush()
    
    admin_user = user_repo.create_user(
        org_id=org.id,
        username="admin_del",
        email="admin_del@assureden.com",
        hashed_password=hash_password("password123"),
        role="ADMIN"
    )
    target_user = user_repo.create_user(
        org_id=org.id,
        username="tester_del",
        email="tester_del@assureden.com",
        hashed_password=hash_password("password123"),
        role="TESTER"
    )
    db.flush()
    
    # Soft delete the target user
    user_repo.soft_delete(target_user.id, org.id, admin_user.id)
    db.flush()
    
    # Verify repository get and list exclude the soft-deleted user
    assert user_repo.get(target_user.id, org.id) is None
    users_list = user_repo.list(org.id)
    assert target_user not in users_list

    # Verify API excludes the soft-deleted user
    headers = create_headers(admin_user.id, org.id, "ADMIN")
    resp_get = client.get(f"/api/users/{target_user.id}", headers=headers)
    assert resp_get.status_code == status.HTTP_404_NOT_FOUND
    
    resp_list = client.get("/api/users/", headers=headers)
    assert resp_list.status_code == status.HTTP_200_OK
    user_ids = [u["id"] for u in resp_list.json()]
    assert str(target_user.id) not in user_ids

def test_agent_registration(db, client):
    org_repo = OrganizationRepository(db)
    user_repo = UserRepository(db)
    
    org = org_repo.create_org(name="Agent Org", slug="agent-org")
    db.flush()
    
    admin_user = user_repo.create_user(
        org_id=org.id,
        username="admin_agent",
        email="admin_agent@assureden.com",
        hashed_password=hash_password("password123"),
        role="ADMIN"
    )
    db.flush()
    
    headers = create_headers(admin_user.id, org.id, "ADMIN")
    
    # Register agent
    payload = {
        "name": "agent-01",
        "max_parallel_sessions": 2
    }
    resp_register = client.post("/api/agents/register", json=payload, headers=headers)
    assert resp_register.status_code == status.HTTP_200_OK
    data = resp_register.json()
    assert "api_key" in data
    agent_id = UUID(data["id"])
    raw_key = data["api_key"]
    
    # Verify agent was created in database
    agent_repo = AgentRepository(db)
    agent = agent_repo.get(agent_id, org.id)
    assert agent is not None
    assert agent.name == "agent-01"
    assert agent.max_parallel_sessions == 2
    
    # Verify heartbeat works with X-Agent-Api-Key
    heartbeat_payload = {
        "status": "ONLINE",
        "current_parallel_sessions": 1,
        "agent_version": "1.0.0",
        "browser_versions": {"chrome": "120.0"},
        "tags": ["windows", "chrome"]
    }
    hb_headers = {"X-Agent-Api-Key": raw_key}
    resp_hb = client.post("/api/agents/heartbeat", json=heartbeat_payload, headers=hb_headers)
    assert resp_hb.status_code == status.HTTP_204_NO_CONTENT
    
    # Verify database status updated
    db.refresh(agent)
    assert agent.status == "ONLINE"
    assert agent.current_parallel_sessions == 1
    assert agent.agent_version == "1.0.0"
    assert "windows" in agent.tags

def test_jwt_refresh(db, client):
    org_repo = OrganizationRepository(db)
    user_repo = UserRepository(db)
    
    org = org_repo.create_org(name="Refresh Org", slug="refresh-org")
    db.flush()
    
    user = user_repo.create_user(
        org_id=org.id,
        username="refresh_user",
        email="refresh_user@assureden.com",
        hashed_password=hash_password("password123"),
        role="TESTER"
    )
    db.flush()
    
    # Perform login
    login_payload = {
        "email": "refresh_user@assureden.com",
        "password": "password123",
        "org_slug": "refresh-org"
    }
    resp_login = client.post("/api/auth/login", json=login_payload)
    assert resp_login.status_code == status.HTTP_200_OK
    tokens = resp_login.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    
    # Call refresh endpoint with refresh token
    refresh_payload = {
        "refresh_token": tokens["refresh_token"]
    }
    resp_refresh = client.post("/api/auth/refresh", json=refresh_payload)
    assert resp_refresh.status_code == status.HTTP_200_OK
    new_tokens = resp_refresh.json()
    assert "access_token" in new_tokens
    
    # Verify the new access token is valid and works
    new_headers = {"Authorization": f"Bearer {new_tokens['access_token']}"}
    resp_me = client.get("/api/auth/me", headers=new_headers)
    assert resp_me.status_code == status.HTTP_200_OK
    assert resp_me.json()["email"] == "refresh_user@assureden.com"

def test_require_role_admin(db, client):
    org_repo = OrganizationRepository(db)
    user_repo = UserRepository(db)
    
    org = org_repo.create_org(name="Role Org", slug="role-org")
    db.flush()
    
    tester_user = user_repo.create_user(
        org_id=org.id,
        username="tester_user",
        email="tester_user@assureden.com",
        hashed_password=hash_password("password123"),
        role="TESTER"
    )
    db.flush()
    
    # Generate token for TESTER user
    headers = create_headers(tester_user.id, org.id, "TESTER")
    
    # Try to register agent (ADMIN only)
    payload = {
        "name": "unauthorized-agent",
        "max_parallel_sessions": 1
    }
    resp = client.post("/api/agents/register", json=payload, headers=headers)
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    
    # Try to create organization (ADMIN only)
    resp_org = client.post("/api/organizations/", json={"name": "New Org", "slug": "new-org"}, headers=headers)
    assert resp_org.status_code == status.HTTP_403_FORBIDDEN
