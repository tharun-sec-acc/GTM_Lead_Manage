"""Product-scoped import, campaign isolation, and consolidated overview tests."""

import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.imports import process_batch
from app.main import app
from app.models import (
    Campaign, Contact, EmailMessage, EmailReply, Enrollment, Lead, Product,
    ProductLead, SalesTask, now,
)


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


def xlsx(rows):
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def make_product(client, name="Prod", slug=None):
    slug = slug or name.lower().replace(" ", "-")
    response = client.post("/products", json={"name": name, "slug": slug})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def make_lead(factory, name="Acme Corp", domain=None):
    with factory() as session:
        lead = Lead(company_name=name, company_key=name.lower(), domain=domain, extra={})
        session.add(lead)
        session.commit()
        return lead.id


def upload(client, rows, product_id=None):
    data = {"product_id": product_id} if product_id else None
    return client.post(
        "/batches",
        files={"file": (
            "leads.xlsx",
            xlsx(rows),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )},
        data=data,
    )


def run_import(client, factory, rows, product_id=None, mapping=None):
    response = upload(client, rows, product_id)
    assert response.status_code == 201, response.text
    batch_id = response.json()["id"]
    mapping = mapping or {"company_name": "Company Name"}
    assert client.post(f"/batches/{batch_id}/start", json={"mapping": mapping}).status_code == 200
    with factory.begin() as session:
        process_batch(session, batch_id)
    return client.get(f"/batches/{batch_id}").json()


# ---- Product-scoped import ----


def test_import_requires_active_product(db):
    client, _ = db
    response = upload(client, [["Company Name"], ["Acme"]], product_id="missing-product")
    assert response.status_code == 404


def test_archived_product_rejects_import(db):
    client, _ = db
    product_id = make_product(client, slug="archived-import")
    client.patch(f"/products/{product_id}/status", json={"status": "archived"})
    response = upload(client, [["Company Name"], ["Acme"]], product_id=product_id)
    assert response.status_code == 422


def test_import_creates_master_company_and_association(db):
    client, factory = db
    product_id = make_product(client, slug="import-new")
    result = run_import(client, factory, [["Company Name"], ["Acme Ltd"]], product_id)
    assert result["status"] == "completed"
    assert result["counts"] == {"imported": 1}

    leads = client.get("/leads").json()
    assert [lead["company_name"] for lead in leads] == ["Acme Ltd"]
    product_leads = client.get(f"/products/{product_id}/leads").json()
    assert len(product_leads) == 1
    assert product_leads[0]["lead_id"] == leads[0]["id"]
    assert product_leads[0]["company_name"] == "Acme Ltd"
    assert product_leads[0]["stage"] == "prospect"

    # The batch is visible in the product's import history only.
    assert [b["id"] for b in client.get(f"/products/{product_id}/batches").json()] == [result["id"]]


def test_reimporting_same_company_under_second_product_associates_existing_master(db):
    client, factory = db
    first = make_product(client, name="First", slug="assoc-first")
    second = make_product(client, name="Second", slug="assoc-second")
    run_import(client, factory, [["Company Name"], ["Acme Ltd"]], first)
    result = run_import(client, factory, [["Company Name"], ["Acme Ltd"]], second)

    # No duplicate master company is created; the row is associated, not skipped.
    assert len(client.get("/leads").json()) == 1
    assert result["counts"] == {"imported": 1}
    assert "associated" in (result["rows"][0]["message"] or "").lower()
    assert len(client.get(f"/products/{first}/leads").json()) == 1
    assert len(client.get(f"/products/{second}/leads").json()) == 1


def test_reimporting_same_company_under_same_product_is_duplicate(db):
    client, factory = db
    product_id = make_product(client, slug="dupe-prod")
    run_import(client, factory, [["Company Name"], ["Acme Ltd"]], product_id)
    result = run_import(client, factory, [["Company Name"], ["Acme Ltd"]], product_id)
    assert result["counts"] == {"duplicate": 1}
    assert len(client.get(f"/products/{product_id}/leads").json()) == 1


def test_import_without_product_keeps_legacy_behavior(db):
    client, factory = db
    result = run_import(client, factory, [["Company Name"], ["Legacy Co"]])
    assert result["counts"] == {"imported": 1}
    assert client.get("/products").json() == []
    assert len(client.get("/leads").json()) == 1


# ---- Campaign and enrollment isolation ----


def test_campaign_rejects_unknown_product(db):
    client, _ = db
    response = client.post("/campaigns", json={"name": "Bad", "product_id": "nope"})
    assert response.status_code == 404


def test_campaign_rejects_archived_product(db):
    client, _ = db
    product_id = make_product(client, slug="camp-archived")
    client.patch(f"/products/{product_id}/status", json={"status": "archived"})
    response = client.post("/campaigns", json={"name": "Bad", "product_id": product_id})
    assert response.status_code == 422


def test_enrollment_rejects_company_outside_product(db):
    client, factory = db
    product_id = make_product(client, slug="camp-scope")
    lead_id = make_lead(factory)
    campaign_id = client.post(
        "/campaigns", json={"name": "Scoped", "product_id": product_id}
    ).json()["id"]

    response = client.post(
        f"/campaigns/{campaign_id}/enrollments",
        json={"lead_id": lead_id, "recipient": "person@acme.com"},
    )
    assert response.status_code == 409
    assert "not associated" in response.json()["detail"]
    with factory() as session:
        assert session.scalars(select(Enrollment)).all() == []
        assert session.scalars(select(EmailMessage)).all() == []

    client.post(f"/products/{product_id}/leads", json={"lead_id": lead_id})
    ok = client.post(
        f"/campaigns/{campaign_id}/enrollments",
        json={"lead_id": lead_id, "recipient": "person@acme.com"},
    )
    assert ok.status_code == 201


def test_bulk_enrollment_is_all_or_nothing_across_products(db):
    client, factory = db
    product_id = make_product(client, slug="camp-bulk")
    associated = make_lead(factory, "Associated Co")
    outside = make_lead(factory, "Outside Co")
    client.post(f"/products/{product_id}/leads", json={"lead_id": associated})
    campaign_id = client.post(
        "/campaigns", json={"name": "Bulk", "product_id": product_id}
    ).json()["id"]

    response = client.post(
        f"/campaigns/{campaign_id}/enrollments/bulk",
        json={"recipients": [
            {"lead_id": associated, "recipient": "a@associated.com"},
            {"lead_id": outside, "recipient": "b@outside.com"},
        ]},
    )
    assert response.status_code == 409
    with factory() as session:
        assert session.scalars(select(Enrollment)).all() == []


def test_campaign_listing_is_product_scoped(db):
    client, _ = db
    first = make_product(client, name="One", slug="list-one")
    second = make_product(client, name="Two", slug="list-two")
    client.post("/campaigns", json={"name": "One campaign", "product_id": first})
    client.post("/campaigns", json={"name": "Two campaign", "product_id": second})
    client.post("/campaigns", json={"name": "Unassigned campaign"})

    assert [c["name"] for c in client.get(f"/products/{first}/campaigns").json()] == ["One campaign"]
    assert [c["name"] for c in client.get("/campaigns?product_id=" + second).json()] == ["Two campaign"]
    assert len(client.get("/campaigns").json()) == 3


# ---- Product read models ----


def test_product_contacts_only_include_associated_companies(db):
    client, factory = db
    product_id = make_product(client, slug="contacts-prod")
    inside = make_lead(factory, "Inside Co")
    outside = make_lead(factory, "Outside Co")
    client.post(f"/products/{product_id}/leads", json={"lead_id": inside})
    with factory() as session:
        session.add(Contact(lead_id=inside, name="Inside Person", email="i@inside.com",
                            source="Manual", verification_status="unverified",
                            retrieved_at=now(), updated_at=now()))
        session.add(Contact(lead_id=outside, name="Outside Person", email="o@outside.com",
                            source="Manual", verification_status="unverified",
                            retrieved_at=now(), updated_at=now()))
        session.commit()

    contacts = client.get(f"/products/{product_id}/contacts").json()
    assert [c["name"] for c in contacts] == ["Inside Person"]
    assert contacts[0]["company_name"] == "Inside Co"


def test_product_sales_tasks_are_attributed_through_campaign(db):
    client, factory = db
    product_id = make_product(client, slug="tasks-prod")
    lead_id = make_lead(factory, "Tasked Co")
    client.post(f"/products/{product_id}/leads", json={"lead_id": lead_id})
    campaign_id = client.post(
        "/campaigns", json={"name": "Tasks", "product_id": product_id}
    ).json()["id"]
    enrollment_id = client.post(
        f"/campaigns/{campaign_id}/enrollments",
        json={"lead_id": lead_id, "recipient": "person@tasked.com"},
    ).json()["id"]
    with factory() as session:
        reply = EmailReply(mailbox_uid="uid-1", enrollment_id=enrollment_id,
                           sender="person@tasked.com", body="Can we meet?",
                           classification="meeting_requested", received_at=now())
        session.add(reply)
        session.flush()
        session.add(SalesTask(reply_id=reply.id, title="Arrange meeting", status="open"))
        session.commit()

    tasks = client.get(f"/products/{product_id}/sales-tasks").json()
    assert len(tasks) == 1
    assert tasks[0]["company_name"] == "Tasked Co"
    assert tasks[0]["classification"] == "meeting_requested"

    other = make_product(client, name="Other", slug="tasks-other")
    assert client.get(f"/products/{other}/sales-tasks").json() == []


def test_product_overview_counts_are_product_scoped(db):
    client, factory = db
    product_id = make_product(client, slug="overview-scope")
    lead_id = make_lead(factory, "Counted Co")
    client.post(f"/products/{product_id}/leads", json={"lead_id": lead_id})
    campaign_id = client.post(
        "/campaigns", json={"name": "Counts", "product_id": product_id}
    ).json()["id"]
    enrollment_id = client.post(
        f"/campaigns/{campaign_id}/enrollments",
        json={"lead_id": lead_id, "recipient": "counted@example.com"},
    ).json()["id"]
    with factory() as session:
        message = session.scalars(select(EmailMessage).where(
            EmailMessage.enrollment_id == enrollment_id, EmailMessage.step_number == 0
        )).one()
        message.status = "sent"
        message.sent_at = now()
        session.commit()

    data = client.get(f"/products/{product_id}/overview").json()
    assert data["associated_companies"] == 1
    assert data["campaigns_count"] == 1
    # The default campaign creates the initial message plus three follow-up drafts.
    assert data["messages_by_status"] == {"sent": 1, "draft": 3}
    assert data["contacted_companies"] == 1
    assert data["contacted_company_percent"] == 100.0
    assert data["pipeline"]["prospect"] == 1

    other = make_product(client, name="Empty", slug="overview-empty")
    empty = client.get(f"/products/{other}/overview").json()
    assert empty["associated_companies"] == 0
    assert empty["contacted_company_percent"] is None


def test_product_overview_rejects_invalid_dates(db):
    client, _ = db
    product_id = make_product(client, slug="dates-prod")
    assert client.get(f"/products/{product_id}/overview?start_date=yesterday").status_code == 422


def test_global_overview_distinguishes_companies_from_associations(db):
    client, factory = db
    first = make_product(client, name="Alpha", slug="global-a")
    second = make_product(client, name="Beta", slug="global-b")
    shared = make_lead(factory, "Shared Co")
    client.post(f"/products/{first}/leads", json={"lead_id": shared})
    client.post(f"/products/{second}/leads", json={"lead_id": shared})
    client.post("/campaigns", json={"name": "Global"})

    data = client.get("/overview").json()
    assert data["unique_companies"] == 1
    assert data["product_associations"] == 2
    assert data["product_associated_companies"] == 1
    assert data["products_count"] == 2
    assert data["total_campaigns"] == 1
    assert {item["slug"] for item in data["per_product"]} == {"global-a", "global-b"}
