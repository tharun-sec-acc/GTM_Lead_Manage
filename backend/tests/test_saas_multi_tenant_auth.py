import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.models import (
    AuditLog,
    OAuthConnection,
    Organization,
    OrganizationInvitation,
    OrganizationMember,
    PasswordResetToken,
    User,
    now,
)
from app.auth.security import create_access_token, hash_password, verify_password
from app.database import Base, get_db
from app.main import app
from app.models import Batch, Campaign, Contact, Lead, Product


@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestingSession
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(test_db):
    return TestClient(app)


def test_password_hashing():
    pw = "SuperSecurePassword123!"
    h = hash_password(pw)
    assert h != pw
    assert verify_password(pw, h) is True
    assert verify_password("WrongPassword!", h) is False


def test_user_registration_and_org_creation(client):
    res = client.post(
        "/auth/register",
        json={
            "email": "owner@company-a.com",
            "password": "Password12345!",
            "full_name": "Alice Smith",
            "organization_name": "Company A Inc",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert "access_token" in data
    assert data["user"]["email"] == "owner@company-a.com"
    assert data["user"]["role"] == "owner"
    assert data["organization"]["name"] == "Company A Inc"
    assert data["organization"]["plan"] == "pro"


def test_user_login_and_token_refresh(client):
    # Register user
    client.post(
        "/auth/register",
        json={
            "email": "bob@company-b.com",
            "password": "SecurePassword99!",
            "full_name": "Bob Jones",
            "organization_name": "Company B Corp",
        },
    )

    # Login
    login_res = client.post(
        "/auth/login",
        json={"email": "bob@company-b.com", "password": "SecurePassword99!"},
    )
    assert login_res.status_code == 200
    login_data = login_res.json()
    token = login_data["access_token"]

    # Access /auth/me
    me_res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["email"] == "bob@company-b.com"
    assert me_data["active_organization"]["name"] == "Company B Corp"

    # Refresh token
    refresh_cookie = login_res.cookies.get("refresh_token")
    ref_res = client.post("/auth/refresh", cookies={"refresh_token": refresh_cookie})
    assert ref_res.status_code == 200
    assert "access_token" in ref_res.json()


def test_login_lockout_after_failed_attempts(client):
    client.post(
        "/auth/register",
        json={
            "email": "target@acme.com",
            "password": "CorrectPassword123!",
            "full_name": "Target User",
        },
    )

    # Attempt 5 wrong passwords
    for _ in range(5):
        fail_res = client.post(
            "/auth/login",
            json={"email": "target@acme.com", "password": "WrongPassword!"},
        )
        assert fail_res.status_code == 401

    # 6th attempt -> 429 Too Many Requests (Lockout)
    lock_res = client.post(
        "/auth/login",
        json={"email": "target@acme.com", "password": "CorrectPassword123!"},
    )
    assert lock_res.status_code == 429
    assert "locked" in lock_res.json()["detail"].lower()


def test_organization_member_invitation_flow(client):
    # 1. Register Owner
    reg = client.post(
        "/auth/register",
        json={
            "email": "owner@titan.com",
            "password": "Password12345!",
            "full_name": "Titan Owner",
            "organization_name": "Titan Logistics",
        },
    )
    owner_token = reg.json()["access_token"]

    # 2. Invite Member as 'rep'
    invite_res = client.post(
        "/organizations/members/invite",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": "rep@titan.com", "role": "rep"},
    )
    assert invite_res.status_code == 201
    invite_data = invite_res.json()
    assert invite_data["email"] == "rep@titan.com"
    assert invite_data["role"] == "rep"
    invite_url = invite_data["invite_url"]
    raw_token = invite_url.split("/invite/")[-1]

    # 3. Public check invitation
    chk_res = client.get(f"/public/invitations/{raw_token}")
    assert chk_res.status_code == 200
    assert chk_res.json()["email"] == "rep@titan.com"

    # 4. Accept invitation
    accept_res = client.post(
        "/public/invitations/accept",
        json={
            "token": raw_token,
            "full_name": "Titan Sales Rep",
            "password": "RepPassword123!",
        },
    )
    assert accept_res.status_code == 200

    # 5. Rep logs in
    rep_login = client.post(
        "/auth/login",
        json={"email": "rep@titan.com", "password": "RepPassword123!"},
    )
    assert rep_login.status_code == 200
    rep_data = rep_login.json()
    assert rep_data["user"]["role"] == "rep"
    assert rep_data["organization"]["name"] == "Titan Logistics"


def test_multi_tenant_isolation_leads_and_campaigns(client):
    # Register Company A
    reg_a = client.post(
        "/auth/register",
        json={
            "email": "ceo@companya.com",
            "password": "Password12345!",
            "full_name": "Alice A",
            "organization_name": "Company A",
        },
    )
    token_a = reg_a.json()["access_token"]
    org_a_id = reg_a.json()["organization"]["id"]

    # Register Company B
    reg_b = client.post(
        "/auth/register",
        json={
            "email": "ceo@companyb.com",
            "password": "Password12345!",
            "full_name": "Bob B",
            "organization_name": "Company B",
        },
    )
    token_b = reg_b.json()["access_token"]
    org_b_id = reg_b.json()["organization"]["id"]

    assert org_a_id != org_b_id

    # Company A creates a campaign
    camp_a_res = client.post(
        "/campaigns",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Company A Private Campaign", "mode": "manual", "delays": [3, 7]},
    )
    assert camp_a_res.status_code == 201

    # Company B lists campaigns -> Must NOT see Company A's campaign
    list_b = client.get(
        "/campaigns",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert list_b.status_code == 200
    camps_b = list_b.json()
    assert len(camps_b) == 0  # Completely isolated!

    # Company A lists campaigns -> Sees its campaign
    list_a = client.get(
        "/campaigns",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert list_a.status_code == 200
    assert len(list_a.json()) == 1
    assert list_a.json()[0]["name"] == "Company A Private Campaign"


def test_rbac_endpoint_authorization(client):
    # Register owner
    reg_owner = client.post(
        "/auth/register",
        json={
            "email": "owner@rbac.com",
            "password": "Password12345!",
            "full_name": "RBAC Owner",
            "organization_name": "RBAC Corp",
        },
    )
    owner_token = reg_owner.json()["access_token"]

    # Invite read_only user
    inv = client.post(
        "/organizations/members/invite",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": "viewer@rbac.com", "role": "read_only"},
    )
    raw_token = inv.json()["invite_url"].split("/invite/")[-1]

    client.post(
        "/public/invitations/accept",
        json={
            "token": raw_token,
            "full_name": "Viewer User",
            "password": "ViewerPassword123!",
        },
    )

    viewer_login = client.post(
        "/auth/login",
        json={"email": "viewer@rbac.com", "password": "ViewerPassword123!"},
    )
    viewer_token = viewer_login.json()["access_token"]

    # Read_only user tries to invite another member -> 403 Forbidden (requires admin)
    forbidden_invite = client.post(
        "/organizations/members/invite",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={"email": "intruder@rbac.com", "role": "admin"},
    )
    assert forbidden_invite.status_code == 403
    assert "access denied" in forbidden_invite.json()["detail"].lower()


def test_integrations_status_and_disconnect(client):
    reg = client.post(
        "/auth/register",
        json={
            "email": "admin@integrations.com",
            "password": "Password12345!",
            "full_name": "Integration Admin",
            "organization_name": "Cloud Integrations",
        },
    )
    token = reg.json()["access_token"]

    # Check integrations status
    status_res = client.get(
        "/api/integrations/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert status_res.status_code == 200
    data = status_res.json()
    assert "integrations" in data
    providers = [i["provider"] for i in data["integrations"]]
    assert "google" in providers
    assert "microsoft" in providers
    assert "zoho" in providers

    # Disconnect google
    dc_res = client.post(
        "/api/integrations/google/disconnect",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert dc_res.status_code == 200
    assert "disconnected" in dc_res.json()["message"].lower()
