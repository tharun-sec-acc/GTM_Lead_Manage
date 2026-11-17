"""Tests for product CRUD, product-lead associations, and overview APIs."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import Campaign, Contact, Lead, Product, ProductLead, now


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


# ---- Product CRUD ----

def test_create_and_list_product(db):
    client, _ = db
    resp = client.post("/products", json={
        "name": "Test Product", "slug": "test-product",
        "short_description": "A test product",
    })
    assert resp.status_code == 201
    p = resp.json()
    assert p["slug"] == "test-product"
    assert p["status"] == "active"

    listing = client.get("/products").json()
    assert any(x["slug"] == "test-product" for x in listing)


def test_slug_uniqueness(db):
    client, _ = db
    client.post("/products", json={"name": "P1", "slug": "my-slug"})
    resp = client.post("/products", json={"name": "P2", "slug": "my-slug"})
    assert resp.status_code == 409


def test_slug_format_rejected(db):
    client, _ = db
    for bad_slug in ["-starts-with-dash", "UPPERCASE", "has space", "ends-with-"]:
        resp = client.post("/products", json={"name": "X", "slug": bad_slug})
        assert resp.status_code == 422, f"Expected 422 for slug '{bad_slug}', got {resp.status_code}"


def test_slug_immutable_on_put(db):
    client, _ = db
    resp = client.post("/products", json={"name": "P", "slug": "original-slug"})
    pid = resp.json()["id"]
    resp2 = client.put(f"/products/{pid}", json={"slug": "changed-slug", "name": "P2"})
    assert resp2.status_code == 422


def test_put_without_slug_change_succeeds(db):
    client, _ = db
    resp = client.post("/products", json={"name": "P", "slug": "my-prod"})
    pid = resp.json()["id"]
    resp2 = client.put(f"/products/{pid}", json={"name": "Updated Name"})
    assert resp2.status_code == 200
    assert resp2.json()["name"] == "Updated Name"
    assert resp2.json()["slug"] == "my-prod"


def test_patch_status_to_archived(db):
    client, _ = db
    pid = client.post("/products", json={"name": "P", "slug": "arch-me"}).json()["id"]
    resp = client.patch(f"/products/{pid}/status", json={"status": "archived"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"


def test_patch_status_invalid_value(db):
    client, _ = db
    pid = client.post("/products", json={"name": "P", "slug": "inv-st"}).json()["id"]
    resp = client.patch(f"/products/{pid}/status", json={"status": "deleted"})
    assert resp.status_code == 422


def test_delete_product_returns_405(db):
    client, _ = db
    pid = client.post("/products", json={"name": "P", "slug": "del-me"}).json()["id"]
    resp = client.delete(f"/products/{pid}")
    assert resp.status_code == 405


def test_get_nonexistent_product_404(db):
    client, _ = db
    resp = client.get("/products/nonexistent-id")
    assert resp.status_code == 404


# ---- Product-lead associations ----

def _make_lead(factory, name="Acme Corp"):
    with factory() as s:
        lead = Lead(company_name=name, company_key=name.lower(), extra={})
        s.add(lead)
        s.commit()
        return lead.id


def _make_product(client, name="Prod", slug=None):
    slug = slug or name.lower().replace(" ", "-")
    return client.post("/products", json={"name": name, "slug": slug}).json()["id"]


def test_associate_lead_to_product(db):
    client, factory = db
    pid = _make_product(client)
    lid = _make_lead(factory)
    resp = client.post(f"/products/{pid}/leads", json={"lead_id": lid})
    assert resp.status_code == 201
    pl = resp.json()
    assert pl["lead_id"] == lid
    assert pl["product_id"] == pid
    assert pl["stage"] == "prospect"
    assert pl["priority"] == "medium"


def test_duplicate_association_rejected(db):
    client, factory = db
    pid = _make_product(client, slug="dup-prod")
    lid = _make_lead(factory)
    client.post(f"/products/{pid}/leads", json={"lead_id": lid})
    resp = client.post(f"/products/{pid}/leads", json={"lead_id": lid})
    assert resp.status_code == 409


def test_association_to_archived_product_rejected(db):
    client, factory = db
    pid = _make_product(client, slug="arch-prod")
    client.patch(f"/products/{pid}/status", json={"status": "archived"})
    lid = _make_lead(factory)
    resp = client.post(f"/products/{pid}/leads", json={"lead_id": lid})
    assert resp.status_code == 422


def test_delete_association_preserves_lead(db):
    client, factory = db
    pid = _make_product(client, slug="del-assoc")
    lid = _make_lead(factory)
    client.post(f"/products/{pid}/leads", json={"lead_id": lid})
    resp = client.delete(f"/products/{pid}/leads/{lid}")
    assert resp.status_code == 204
    # Lead still exists
    with factory() as s:
        assert s.get(Lead, lid) is not None
    # Association gone
    resp2 = client.get(f"/products/{pid}/leads")
    assert not any(x["lead_id"] == lid for x in resp2.json())


def test_product_lead_update(db):
    client, factory = db
    pid = _make_product(client, slug="upd-assoc")
    lid = _make_lead(factory)
    client.post(f"/products/{pid}/leads", json={"lead_id": lid})
    resp = client.put(f"/products/{pid}/leads/{lid}", json={"stage": "qualified", "priority": "high"})
    assert resp.status_code == 200
    pl = resp.json()
    assert pl["stage"] == "qualified"
    assert pl["priority"] == "high"


def test_invalid_stage_rejected(db):
    client, factory = db
    pid = _make_product(client, slug="inv-stage")
    lid = _make_lead(factory)
    resp = client.post(f"/products/{pid}/leads", json={"lead_id": lid, "stage": "INVALID"})
    assert resp.status_code == 422


def test_product_lead_filter_by_stage(db):
    client, factory = db
    pid = _make_product(client, slug="filter-stage")
    lid1 = _make_lead(factory, "Acme")
    lid2 = _make_lead(factory, "Beta")
    client.post(f"/products/{pid}/leads", json={"lead_id": lid1, "stage": "prospect"})
    client.post(f"/products/{pid}/leads", json={"lead_id": lid2, "stage": "qualified"})
    resp = client.get(f"/products/{pid}/leads?stage=qualified").json()
    assert len(resp) == 1
    assert resp[0]["lead_id"] == lid2


# ---- Campaign product scope ----

def test_campaign_stores_product_id(db):
    client, factory = db
    pid = _make_product(client, slug="camp-prod")
    resp = client.post("/campaigns", json={"name": "Test Campaign", "product_id": pid})
    assert resp.status_code == 201
    with factory() as s:
        from app.models import Campaign
        camp = s.scalars(select(Campaign).order_by(Campaign.created_at.desc()).limit(1)).first()
        assert camp.product_id == pid


def test_campaign_without_product_id(db):
    client, factory = db
    resp = client.post("/campaigns", json={"name": "No Product Campaign"})
    assert resp.status_code == 201
    with factory() as s:
        from app.models import Campaign
        camp = s.scalars(select(Campaign).order_by(Campaign.created_at.desc()).limit(1)).first()
        assert camp.product_id is None


# ---- Overview APIs ----

def test_product_overview(db):
    client, factory = db
    pid = _make_product(client, slug="overview-prod")
    lid = _make_lead(factory)
    client.post(f"/products/{pid}/leads", json={"lead_id": lid})
    resp = client.get(f"/products/{pid}/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["associated_companies"] == 1
    assert data["active_contacts"] == 0
    assert data["campaigns_count"] == 0


def test_global_overview(db):
    client, factory = db
    pid1 = _make_product(client, slug="glob-p1")
    pid2 = _make_product(client, slug="glob-p2")
    lid = _make_lead(factory)
    client.post(f"/products/{pid1}/leads", json={"lead_id": lid})
    client.post(f"/products/{pid2}/leads", json={"lead_id": lid})
    resp = client.get("/overview")
    assert resp.status_code == 200
    data = resp.json()
    # Same lead in 2 products = 1 unique company
    assert data["unique_companies"] == 1
    assert len(data["per_product"]) >= 2