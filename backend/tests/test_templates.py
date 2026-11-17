"""Tests for email template CRUD, versioning, variable validation, and preview."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.email_templates import ALLOWED_TEMPLATE_VARIABLES, validate_variables
from app.main import app
from app.models import EmailTemplate, EmailTemplateVersion, Product, now


@pytest.fixture
def db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        yield client, factory
    app.dependency_overrides.clear()
    engine.dispose()


def _make_product(factory, name="Prod", slug="test-prod"):
    with factory() as s:
        p = Product(name=name, slug=slug, status="active",
                    target_industries=[], created_at=now(), updated_at=now())
        s.add(p)
        s.commit()
        return p.id


# ---- Variable validation unit tests (no DB) ----

def test_validate_variables_all_allowed():
    unknown = validate_variables("Hi {{contact_first_name}}", "From {{company_name}}")
    assert unknown == []


def test_validate_variables_unknown_flagged():
    unknown = validate_variables("{{unknown_var}}", "{{company_name}}")
    assert "unknown_var" in unknown


def test_every_allowed_variable_passes():
    for v in ALLOWED_TEMPLATE_VARIABLES:
        assert validate_variables(f"{{{{{v}}}}}", "") == []


# ---- Template CRUD ----

def test_create_global_template(db):
    client, _ = db
    resp = client.post("/templates", json={
        "name": "Initial Outreach",
        "type": "initial",
        "subject_template": "Hello {{contact_first_name}}",
        "body_template": "We work with {{company_name}} clients.",
    })
    assert resp.status_code == 201
    t = resp.json()
    assert t["product_id"] is None
    assert t["version"] == 1
    assert "contact_first_name" in t["variables"]


def test_create_product_template(db):
    client, factory = db
    pid = _make_product(factory)
    resp = client.post("/templates", json={
        "name": "VDI Intro",
        "type": "product_intro",
        "product_id": pid,
        "subject_template": "{{product_name}} for {{company_name}}",
        "body_template": "Hi {{contact_first_name}}, our {{product_value_proposition}}",
    })
    assert resp.status_code == 201
    assert resp.json()["product_id"] == pid


def test_unknown_variable_rejected(db):
    client, _ = db
    resp = client.post("/templates", json={
        "name": "Bad Template",
        "subject_template": "{{nonexistent_var}} hello",
        "body_template": "text",
    })
    assert resp.status_code == 422
    # Must NOT have persisted anything
    resp2 = client.get("/templates")
    assert all("nonexistent_var" not in str(t) for t in resp2.json())


def test_product_override_does_not_mutate_parent(db):
    client, factory = db
    # Create global template
    parent = client.post("/templates", json={
        "name": "Global Base",
        "subject_template": "Hello {{contact_first_name}}",
        "body_template": "Global body",
    }).json()
    parent_id = parent["id"]
    original_body = parent["body_template"]

    pid = _make_product(factory, slug="override-prod")
    # Create product override
    override = client.post("/templates", json={
        "name": "Product Override",
        "product_id": pid,
        "parent_template_id": parent_id,
        "subject_template": "Hello {{contact_first_name}} - override",
        "body_template": "Override body for {{product_name}}",
    })
    assert override.status_code == 201

    # Parent unchanged
    parent_after = client.get(f"/templates/{parent_id}").json()
    assert parent_after["body_template"] == original_body
    assert parent_after["product_id"] is None


def test_version_increments_monotonically(db):
    client, _ = db
    resp = client.post("/templates", json={
        "name": "Versioned",
        "subject_template": "v1 {{company_name}}",
        "body_template": "body v1",
    })
    tid = resp.json()["id"]
    # 4 more updates
    for i in range(2, 6):
        client.put(f"/templates/{tid}", json={"body_template": f"body v{i} {{{{company_name}}}}"})
    t = client.get(f"/templates/{tid}").json()
    assert t["version"] == 5
    versions = client.get(f"/templates/{tid}/versions").json()
    nums = [v["version"] for v in versions]
    assert sorted(nums) == list(range(1, 6))


def test_version_history_immutable(db):
    client, _ = db
    tid = client.post("/templates", json={
        "name": "Hist",
        "subject_template": "s1 {{company_name}}",
        "body_template": "b1",
    }).json()["id"]
    # Save v1 body
    v1_body = client.get(f"/templates/{tid}/versions").json()[-1]["body_template"]
    # Update to v2
    client.put(f"/templates/{tid}", json={"body_template": "b2 {{company_name}}"})
    # v1 still has original body
    versions = {v["version"]: v for v in client.get(f"/templates/{tid}/versions").json()}
    assert versions[1]["body_template"] == v1_body


def test_preview_resolves_variables(db):
    client, _ = db
    tid = client.post("/templates", json={
        "name": "Preview Test",
        "subject_template": "Dear {{contact_first_name}}",
        "body_template": "Company: {{company_name}}",
    }).json()["id"]
    resp = client.post(f"/templates/{tid}/preview").json()
    assert "Jane" in resp["subject"]
    assert "Acme" in resp["body"]


def test_template_list_filter_by_product(db):
    client, factory = db
    pid = _make_product(factory, slug="filter-prod")
    client.post("/templates", json={"name": "Global", "subject_template": "{{company_name}}", "body_template": ""})
    client.post("/templates", json={"name": "Product T", "product_id": pid, "subject_template": "{{product_name}}", "body_template": ""})
    global_list = client.get("/templates?product_id=global").json()
    assert all(t["product_id"] is None for t in global_list)
    product_list = client.get(f"/templates?product_id={pid}").json()
    assert all(t["product_id"] == pid for t in product_list)