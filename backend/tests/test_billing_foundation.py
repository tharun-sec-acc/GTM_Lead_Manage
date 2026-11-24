import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.models import AuditLog, Organization
from app.billing.models import UsageRecord
from app.billing.service import record_usage
from app.database import Base, get_db
from app.main import app
from app.models import Batch, Lead


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


def register(client, email: str, organization_name: str) -> dict:
    res = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "Password12345!",
            "full_name": email.split("@")[0].title(),
            "organization_name": organization_name,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_plan_catalogue_and_subscription_defaults(client):
    reg = register(client, "billing-owner@alpha.com", "Alpha Billing")

    plans_res = client.get("/billing/plans", headers=auth(reg["access_token"]))
    assert plans_res.status_code == 200
    codes = [plan["code"] for plan in plans_res.json()]
    assert codes == ["free", "starter", "growth", "business", "enterprise"]

    state_res = client.get("/billing/subscription", headers=auth(reg["access_token"]))
    assert state_res.status_code == 200
    state = state_res.json()
    # Legacy "pro" label maps onto the growth catalogue plan.
    assert state["plan"]["code"] == "growth"
    assert state["subscription"]["status"] == "trialing"
    assert state["active"] is True
    assert state["limits"]["seats"] == 15
    assert state["usage"]["seats"] == 1
    assert "crm" in state["features"]


def test_plan_change_is_role_gated_and_audited(client, test_db):
    owner = register(client, "owner@beta.com", "Beta Corp")
    invite = client.post(
        "/organizations/members/invite",
        headers=auth(owner["access_token"]),
        json={"email": "viewer@beta.com", "role": "read_only"},
    )
    assert invite.status_code == 201
    raw_token = invite.json()["invite_url"].split("/invite/")[-1]
    client.post(
        "/public/invitations/accept",
        json={"token": raw_token, "full_name": "Viewer", "password": "ViewerPassword123!"},
    )
    viewer = client.post(
        "/auth/login",
        json={"email": "viewer@beta.com", "password": "ViewerPassword123!"},
    ).json()

    forbidden = client.post(
        "/billing/subscription/change",
        headers=auth(viewer["access_token"]),
        json={"plan_code": "free"},
    )
    assert forbidden.status_code == 403

    changed = client.post(
        "/billing/subscription/change",
        headers=auth(owner["access_token"]),
        json={"plan_code": "free"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["plan"]["code"] == "free"
    assert changed.json()["limits"]["seats"] == 3

    current = client.get("/organizations/current", headers=auth(owner["access_token"]))
    assert current.json()["plan"] == "free"

    session = test_db()
    try:
        audit = session.scalar(
            select(AuditLog).where(AuditLog.action == "billing_plan_changed")
        )
        assert audit is not None
        assert audit.details["from"] == "growth"
        assert audit.details["to"] == "free"
    finally:
        session.close()


def test_seat_limit_enforced_on_invitation(client):
    owner = register(client, "seat-owner@gamma.com", "Gamma Seats")
    client.post(
        "/billing/subscription/change",
        headers=auth(owner["access_token"]),
        json={"plan_code": "free"},
    )

    first = client.post(
        "/organizations/members/invite",
        headers=auth(owner["access_token"]),
        json={"email": "first@gamma.com", "role": "rep"},
    )
    second = client.post(
        "/organizations/members/invite",
        headers=auth(owner["access_token"]),
        json={"email": "second@gamma.com", "role": "rep"},
    )
    third = client.post(
        "/organizations/members/invite",
        headers=auth(owner["access_token"]),
        json={"email": "third@gamma.com", "role": "rep"},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert third.status_code == 402
    assert "seats" in third.json()["detail"]


def test_usage_metering_and_snapshot(client, test_db):
    reg = register(client, "usage-owner@delta.com", "Delta Usage")
    session = test_db()
    try:
        organization = session.get(Organization, reg["organization"]["id"])
        record_usage(session, organization, "email_sends_monthly", 4)
    finally:
        session.close()

    usage_res = client.get("/billing/usage", headers=auth(reg["access_token"]))
    assert usage_res.status_code == 200
    usage = usage_res.json()
    assert usage["usage"]["email_sends_monthly"] == 4
    assert usage["remaining"]["email_sends_monthly"] == 20000 - 4

    session = test_db()
    try:
        record = session.scalar(
            select(UsageRecord).where(UsageRecord.metric == "email_sends_monthly")
        )
        assert record is not None and record.quantity == 4
    finally:
        session.close()


def test_cancel_and_resume_subscription(client):
    reg = register(client, "cancel-owner@epsilon.com", "Epsilon")
    token = reg["access_token"]

    canceled = client.post("/billing/subscription/cancel", headers=auth(token))
    assert canceled.status_code == 200
    assert canceled.json()["subscription"]["cancel_at_period_end"] is True

    resumed = client.post("/billing/subscription/resume", headers=auth(token))
    assert resumed.status_code == 200
    assert resumed.json()["subscription"]["cancel_at_period_end"] is False


def test_cross_tenant_lead_and_batch_access_is_blocked(client, test_db):
    alpha = register(client, "alpha@isolation.com", "Isolation Alpha")
    beta = register(client, "beta@isolation.com", "Isolation Beta")

    session = test_db()
    try:
        lead = Lead(
            organization_id=alpha["organization"]["id"],
            company_name="Alpha Only Company",
            company_key="alpha only company",
            domain="alpha-only.example",
        )
        batch = Batch(
            organization_id=alpha["organization"]["id"],
            filename="alpha.xlsx",
            content=b"",
            headers=[],
            status="draft",
        )
        session.add_all([lead, batch])
        session.commit()
        lead_id, batch_id = lead.id, batch.id
    finally:
        session.close()

    own_profile = client.get(f"/leads/{lead_id}/profile", headers=auth(alpha["access_token"]))
    assert own_profile.status_code == 200

    foreign_profile = client.get(f"/leads/{lead_id}/profile", headers=auth(beta["access_token"]))
    assert foreign_profile.status_code == 404

    foreign_domain = client.put(
        f"/leads/{lead_id}/domain",
        headers=auth(beta["access_token"]),
        json={"domain": "hijacked.example"},
    )
    assert foreign_domain.status_code == 404

    foreign_contacts = client.get(
        f"/leads/{lead_id}/contacts", headers=auth(beta["access_token"])
    )
    assert foreign_contacts.status_code == 404

    own_batch = client.get(f"/batches/{batch_id}", headers=auth(alpha["access_token"]))
    assert own_batch.status_code == 200

    foreign_batch = client.get(f"/batches/{batch_id}", headers=auth(beta["access_token"]))
    assert foreign_batch.status_code == 404
