import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.crm.models import Activity, CrmTask, OpportunityStageEvent
from app.database import Base, get_db
from app.main import app
from app.models import Contact, Lead


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


def make_lead(test_db, org_id: str, name: str, domain: str | None = None, email: str | None = None) -> str:
    session = test_db()
    try:
        lead = Lead(
            organization_id=org_id,
            company_name=name,
            company_key=name.lower(),
            domain=domain,
            email=email,
        )
        session.add(lead)
        session.commit()
        return lead.id
    finally:
        session.close()


def test_default_pipeline_is_created(client):
    reg = register(client, "owner@pipe.com", "Pipe Corp")
    res = client.get("/crm/pipelines", headers=auth(reg["access_token"]))
    assert res.status_code == 200
    pipelines = res.json()
    assert len(pipelines) == 1
    pipeline = pipelines[0]
    assert pipeline["is_default"] is True
    assert [stage["name"] for stage in pipeline["stages"]] == [
        "New",
        "Qualified",
        "Meeting",
        "Proposal",
        "Negotiation",
        "Won",
        "Lost",
    ]
    won = next(stage for stage in pipeline["stages"] if stage["is_won"])
    assert won["probability"] == 100


def test_opportunity_lifecycle_and_summary(client, test_db):
    reg = register(client, "owner@life.com", "Lifecycle Corp")
    token = reg["access_token"]
    org_id = reg["organization"]["id"]
    lead_id = make_lead(test_db, org_id, "Acme Industries", domain="acme.example")

    pipeline = client.get("/crm/pipelines", headers=auth(token)).json()[0]
    qualified = next(stage for stage in pipeline["stages"] if stage["name"] == "Qualified")

    created = client.post(
        "/crm/opportunities",
        headers=auth(token),
        json={
            "lead_id": lead_id,
            "name": "Acme annual licence",
            "amount_cents": 100000,
            "expected_close_date": "2026-12-31",
            "source": "referral",
        },
    )
    assert created.status_code == 201, created.text
    opportunity = created.json()
    assert opportunity["status"] == "open"
    assert opportunity["stage_name"] == "New"
    assert opportunity["amount"] == 1000.0
    opportunity_id = opportunity["id"]

    moved = client.post(
        f"/crm/opportunities/{opportunity_id}/stage",
        headers=auth(token),
        json={"stage_id": qualified["id"], "note": "Call completed"},
    )
    assert moved.status_code == 200
    assert moved.json()["stage_name"] == "Qualified"

    won = client.post(
        f"/crm/opportunities/{opportunity_id}/close",
        headers=auth(token),
        json={"status": "won"},
    )
    assert won.status_code == 200, won.text
    assert won.json()["status"] == "won"
    assert won.json()["won_at"] is not None

    detail = client.get(f"/crm/opportunities/{opportunity_id}", headers=auth(token))
    assert detail.status_code == 200
    assert len(detail.json()["history"]) == 3

    summary = client.get("/crm/summary", headers=auth(token))
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["leads"]["total"] == 1
    assert payload["leads"]["customers"] == 1
    assert payload["opportunities"]["won_count"] == 1
    assert payload["opportunities"]["won_value_cents"] == 100000
    assert payload["opportunities"]["win_rate"] == 1.0

    session = test_db()
    try:
        lead = session.get(Lead, lead_id)
        assert lead.lifecycle_stage == "customer"
        assert session.scalar(
            select(OpportunityStageEvent).where(
                OpportunityStageEvent.opportunity_id == opportunity_id
            )
        )
    finally:
        session.close()


def test_lost_opportunity_requires_reason(client, test_db):
    reg = register(client, "owner@lost.com", "Lost Corp")
    token = reg["access_token"]
    lead_id = make_lead(test_db, reg["organization"]["id"], "Beta Ltd")
    created = client.post(
        "/crm/opportunities",
        headers=auth(token),
        json={"lead_id": lead_id, "name": "Beta deal", "amount_cents": 5000},
    )
    opportunity_id = created.json()["id"]

    missing = client.post(
        f"/crm/opportunities/{opportunity_id}/close",
        headers=auth(token),
        json={"status": "lost"},
    )
    assert missing.status_code == 400

    lost = client.post(
        f"/crm/opportunities/{opportunity_id}/close",
        headers=auth(token),
        json={"status": "lost", "lost_reason": "Budget moved to next year"},
    )
    assert lost.status_code == 200
    assert lost.json()["status"] == "lost"
    assert lost.json()["lost_reason"] == "Budget moved to next year"


def test_cross_tenant_crm_access_is_blocked(client, test_db):
    alpha = register(client, "owner@alpha-crm.com", "Alpha CRM")
    beta = register(client, "owner@beta-crm.com", "Beta CRM")
    lead_id = make_lead(test_db, alpha["organization"]["id"], "Alpha Client")

    created = client.post(
        "/crm/opportunities",
        headers=auth(alpha["access_token"]),
        json={"lead_id": lead_id, "name": "Alpha deal", "amount_cents": 1000},
    )
    assert created.status_code == 201
    opportunity_id = created.json()["id"]

    assert client.get("/crm/opportunities", headers=auth(beta["access_token"])).json() == []
    assert (
        client.get(
            f"/crm/opportunities/{opportunity_id}", headers=auth(beta["access_token"])
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/crm/opportunities/{opportunity_id}",
            headers=auth(beta["access_token"]),
            json={"name": "Hijacked"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/crm/opportunities/{opportunity_id}/close",
            headers=auth(beta["access_token"]),
            json={"status": "won"},
        ).status_code
        == 404
    )
    assert (
        client.get(f"/crm/leads/{lead_id}/timeline", headers=auth(beta["access_token"])).status_code
        == 404
    )


def test_stage_deletion_guard(client, test_db):
    reg = register(client, "owner@stage.com", "Stage Corp")
    token = reg["access_token"]
    lead_id = make_lead(test_db, reg["organization"]["id"], "Gamma Co")
    pipeline = client.get("/crm/pipelines", headers=auth(token)).json()[0]
    new_stage = pipeline["stages"][0]

    created = client.post(
        "/crm/opportunities",
        headers=auth(token),
        json={"lead_id": lead_id, "name": "Gamma deal", "amount_cents": 2000},
    )
    assert created.status_code == 201

    blocked = client.delete(f"/crm/stages/{new_stage['id']}", headers=auth(token))
    assert blocked.status_code == 409

    added = client.post(
        f"/crm/pipelines/{pipeline['id']}/stages",
        headers=auth(token),
        json={"name": "Discovery", "position": 15, "probability": 15},
    )
    assert added.status_code == 201
    deleted = client.delete(f"/crm/stages/{added.json()['id']}", headers=auth(token))
    assert deleted.status_code == 204


def test_role_gates_on_crm_writes(client):
    owner = register(client, "owner@roles-crm.com", "Roles CRM")
    invite = client.post(
        "/organizations/members/invite",
        headers=auth(owner["access_token"]),
        json={"email": "viewer@roles-crm.com", "role": "read_only"},
    )
    raw_token = invite.json()["invite_url"].split("/invite/")[-1]
    client.post(
        "/public/invitations/accept",
        json={"token": raw_token, "full_name": "Viewer", "password": "ViewerPassword123!"},
    )
    viewer = client.post(
        "/auth/login",
        json={"email": "viewer@roles-crm.com", "password": "ViewerPassword123!"},
    ).json()

    assert (
        client.post(
            "/crm/pipelines",
            headers=auth(viewer["access_token"]),
            json={"name": "Viewer pipeline"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/crm/opportunities",
            headers=auth(viewer["access_token"]),
            json={"lead_id": "missing", "name": "No"},
        ).status_code
        == 403
    )
    assert client.get("/crm/summary", headers=auth(viewer["access_token"])).status_code == 200


def test_lead_scoring_and_duplicate_merge(client, test_db):
    reg = register(client, "owner@dupe.com", "Dupe Corp")
    token = reg["access_token"]
    org_id = reg["organization"]["id"]
    target_id = make_lead(test_db, org_id, "Same Company", domain="same.example", email="a@same.example")
    duplicate_id = make_lead(test_db, org_id, "Same Company", domain="same.example")

    session = test_db()
    try:
        session.add(
            Contact(
                organization_id=org_id,
                lead_id=duplicate_id,
                name="Dup Contact",
                email="dup@same.example",
                source="Manual",
            )
        )
        session.commit()
    finally:
        session.close()

    score_res = client.post(f"/crm/leads/{target_id}/score", headers=auth(token))
    assert score_res.status_code == 200
    assert score_res.json()["score"] > 0
    assert score_res.json()["factors"]

    duplicates = client.get(f"/crm/leads/{target_id}/duplicates", headers=auth(token))
    assert duplicates.status_code == 200
    assert [item["lead"]["id"] for item in duplicates.json()] == [duplicate_id]

    merged = client.post(
        f"/crm/leads/{target_id}/merge",
        headers=auth(token),
        json={"source_lead_ids": [duplicate_id]},
    )
    assert merged.status_code == 200, merged.text
    assert merged.json()["moved"]["leads"] == 1
    assert merged.json()["moved"]["contacts"] == 1

    assert client.get(f"/crm/leads/{target_id}/duplicates", headers=auth(token)).json() == []

    session = test_db()
    try:
        moved_contact = session.scalar(select(Contact).where(Contact.email == "dup@same.example"))
        assert moved_contact.lead_id == target_id
        assert session.get(Lead, duplicate_id).merged_into_id == target_id
        assert session.scalar(
            select(Activity).where(Activity.subject == "Duplicate leads merged")
        )
    finally:
        session.close()


def test_tasks_custom_fields_and_saved_views(client, test_db):
    reg = register(client, "owner@tasks.com", "Tasks Corp")
    token = reg["access_token"]
    lead_id = make_lead(test_db, reg["organization"]["id"], "Task Co")

    task = client.post(
        "/crm/tasks",
        headers=auth(token),
        json={"title": "Follow up on pricing", "lead_id": lead_id, "priority": "high"},
    )
    assert task.status_code == 201
    task_id = task.json()["id"]

    completed = client.post(f"/crm/tasks/{task_id}/complete", headers=auth(token))
    assert completed.status_code == 200
    assert completed.json()["status"] == "done"
    assert completed.json()["completed_at"] is not None

    session = test_db()
    try:
        assert session.get(CrmTask, task_id).status == "done"
        assert session.scalar(
            select(Activity).where(Activity.subject.like("Task completed%"))
        )
    finally:
        session.close()

    field = client.post(
        "/crm/custom-fields",
        headers=auth(token),
        json={"entity": "lead", "key": "budget_band", "label": "Budget band", "field_type": "select", "options": ["low", "high"]},
    )
    assert field.status_code == 201
    duplicate = client.post(
        "/crm/custom-fields",
        headers=auth(token),
        json={"entity": "lead", "key": "budget_band", "label": "Duplicate"},
    )
    assert duplicate.status_code == 409
    assert len(client.get("/crm/custom-fields", headers=auth(token)).json()) == 1

    view = client.post(
        "/crm/views",
        headers=auth(token),
        json={"name": "My open deals", "entity": "opportunity", "filters": {"status": "open"}},
    )
    assert view.status_code == 201
    assert client.delete(f"/crm/views/{view.json()['id']}", headers=auth(token)).status_code == 204
