import io

import pytest
import httpx
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app import apollo
from app.imports import process_batch
from app.main import app
from app.models import Batch, Contact, EmailEvent, EmailMessage, EmailReply, ImportRow, Lead, SalesTask, now


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
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


def multi_xlsx(sheets):
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, rows in sheets:
        sheet = workbook.create_sheet(name)
        for row in rows:
            sheet.append(row)
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def upload(client, rows):
    return client.post("/batches", files={
        "file": ("leads.xlsx", xlsx(rows), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    })


def upload_content(client, content):
    return client.post("/batches", files={
        "file": ("leads.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    })


def test_import_preserves_extra_and_reports_invalid_and_duplicates(db):
    client, factory = db
    response = upload(client, [
        ["Company Name", "Email id", "Remarks", "Region"],
        ["Example", "person@example.com", "Potential", "India"],
        ["Other", "not-an-email", "", "US"],
        ["Example", "", "another row", "UK"],
        ["", "person@other.com", "", "EU"],
    ])
    assert response.status_code == 201
    batch = response.json()
    assert batch["row_count"] == 4
    mapping = {"company_name": "Company Name", "email": "Email id", "remarks": "Remarks"}
    assert client.post(f"/batches/{batch['id']}/start", json={"mapping": mapping}).status_code == 200
    with factory.begin() as session:
        process_batch(session, batch["id"])
        process_batch(session, batch["id"])
    result = client.get(f"/batches/{batch['id']}").json()
    assert result["status"] == "completed"
    assert result["counts"] == {"imported": 1, "invalid": 2, "duplicate": 1}
    assert result["rows"][2]["original"]["Region"] == "UK"
    leads = client.get("/leads").json()
    assert len(leads) == 1
    assert leads[0]["extra"] == {"Region": "India"}
    assert leads[0]["remarks"] == "Potential"


def test_mapping_validation_and_bad_upload(db):
    client, _ = db
    assert client.post("/batches", files={"file": ("bad.xlsx", b"bad")}).status_code == 400
    batch = upload(client, [["Company", "Email"], ["Test", ""]]).json()
    invalid = client.post(f"/batches/{batch['id']}/start", json={
        "mapping": {"company_name": "Company", "email": "Company"}
    })
    assert invalid.status_code == 400
    assert client.get(f"/batches/{batch['id']}").json()["status"] == "draft"


def test_multisheet_mapping_imports_valid_rows_and_records_sheet_provenance(db):
    client, factory = db
    content = multi_xlsx([
        ("Companies", [
            ["Company", "Domain", "Industry", "City"],
            ["Acme", "acme.example", "Manufacturing", "Nagoya"],
            ["", "invalid.example", "", ""],
        ]),
        ("People", [
            ["Organization", "Business email", "Job title"],
            ["Acme", "sales@acme.example", "VP Sales"],
            ["Beta Corp", "sales@beta.example", "VP Sales"],
            ["Beta Corp", "ceo@beta.example", "CEO"],
        ]),
        ("Empty", []),
    ])
    uploaded = upload_content(client, content)
    assert uploaded.status_code == 201
    batch = uploaded.json()
    assert [(sheet["name"], sheet["row_count"]) for sheet in batch["sheets"]] == [
        ("Companies", 2), ("People", 3), ("Empty", 0),
    ]
    mappings = {
        "Companies": {"company_name": "Company", "domain": "Domain",
                      "industry": "Industry", "location": "City"},
        "People": {"company_name": "Organization", "email": "Business email",
                   "designation": "Job title"},
    }
    assert client.post(f"/batches/{batch['id']}/start", json={"mapping": mappings}).status_code == 200
    with factory.begin() as session:
        process_batch(session, batch["id"])
    result = client.get(f"/batches/{batch['id']}").json()
    assert result["counts"] == {"imported": 2, "invalid": 1, "duplicate": 2}
    assert [(row["sheet_name"], row["row_number"], row["status"]) for row in result["rows"]] == [
        ("Companies", 2, "imported"), ("Companies", 3, "invalid"),
        ("People", 2, "duplicate"), ("People", 3, "imported"),
        ("People", 4, "duplicate"),
    ]
    leads = client.get("/leads").json()
    acme = next(lead for lead in leads if lead["industry"])
    assert (acme["domain"], acme["industry"], acme["location"]) == (
        "acme.example", "Manufacturing", "Nagoya",
    )
    assert acme["extra"] == {}
    beta = next(lead for lead in leads if lead["company_name"] == "Beta Corp")
    assert beta["designation"] == "VP Sales"


def test_multisheet_preview_and_selection_preserve_active_sheet_legacy_contract(db):
    client, factory = db
    content = multi_xlsx([
        ("Archive", [["Old Company"], ["Old Inc"]]),
        ("Current", [["Company", "Notes"], ["Current Inc", "New"]]),
    ])
    batch = upload_content(client, content).json()
    assert batch["headers"] == ["Old Company"]
    assert [sheet["name"] for sheet in client.get(f"/batches/{batch['id']}/preview").json()["sheets"]] == [
        "Archive", "Current",
    ]
    response = client.post(f"/batches/{batch['id']}/start", json={
        "mapping": {"Current": {"company_name": "Company", "remarks": "Notes"}}
    })
    assert response.status_code == 200
    with factory.begin() as session:
        process_batch(session, batch["id"])
    assert [lead["company_name"] for lead in client.get("/leads").json()] == ["Current Inc"]


def test_repeated_import_is_reviewed_not_silently_duplicated(db):
    client, factory = db
    for _ in range(2):
        batch = upload(client, [["Company", "Email"], ["Example", "sales@example.com"]]).json()
        client.post(f"/batches/{batch['id']}/start", json={
            "mapping": {"company_name": "Company", "email": "Email"}
        })
        with factory.begin() as session:
            process_batch(session, batch["id"])
    assert len(client.get("/leads").json()) == 1
    assert client.get(f"/batches/{batch['id']}").json()["counts"] == {"duplicate": 1}


def test_apollo_requires_confirmed_domain_and_saves_selected_contact(db, monkeypatch):
    client, factory = db
    with factory.begin() as session:
        lead = Lead(company_name="Example", company_key="example", extra={})
        session.add(lead)
        session.flush()
        lead_id = lead.id
    assert client.post(f"/leads/{lead_id}/apollo/search").status_code == 400
    response = client.put(f"/leads/{lead_id}/domain", json={
        "domain": "https://www.example.com/company/about/",
    })
    assert response.status_code == 200
    assert response.json()["domain"] == "example.com"
    with factory() as session:
        assert session.get(Lead, lead_id).domain == "example.com"
    monkeypatch.setattr("app.apollo.search_people", lambda domain: [
        {"id": "p1", "first_name": "Alex", "last_name_obfuscated": "Sm***", "has_email": True,
         "title": "Director", "organization": {"name": "Example", "primary_domain": "example.com"}}
    ])
    monkeypatch.setattr("app.apollo.enrich_person", lambda person_id: {
        "name": "Alex", "title": "Director", "email": "alex@example.com",
        "organization": {"primary_domain": "example.com"},
    })
    candidate = client.post(f"/leads/{lead_id}/apollo/search").json()[0]
    assert candidate["id"] == "p1"
    assert candidate["name"] == "Alex Sm***"
    assert candidate["has_email"] is True
    result = client.post(f"/leads/{lead_id}/apollo/enrich", json={"apollo_id": "p1"})
    assert result.status_code == 200
    assert result.json()["email"] == "alex@example.com"
    assert client.post(f"/leads/{lead_id}/apollo/enrich", json={"apollo_id": "p1"}).status_code == 409
    assert len(client.get(f"/leads/{lead_id}/contacts").json()) == 1


def test_apollo_wrong_organization_is_not_enriched_without_sales_confirmation(db, monkeypatch):
    client, factory = db
    with factory.begin() as session:
        lead = Lead(company_name="Example", company_key="example", domain="example.com", extra={})
        session.add(lead)
        session.flush()
        lead_id = lead.id
    monkeypatch.setattr("app.apollo.search_people", lambda domain: [{
        "id": "p1", "name": "Past employee", "organization": {
            "name": "Other Corp", "primary_domain": "other.example",
        },
    }])
    enrich_calls = []
    monkeypatch.setattr("app.apollo.enrich_person", lambda person_id: (
        enrich_calls.append(person_id) or {
            "name": "Past employee", "email": "person@other.example",
            "organization": {"primary_domain": "other.example"},
        }
    ))
    result = client.post(f"/leads/{lead_id}/apollo/search").json()[0]
    assert result["organization_matches"] is False
    response = client.post(f"/leads/{lead_id}/apollo/enrich", json={"apollo_id": "p1"})
    assert response.status_code == 409
    assert enrich_calls == []
    response = client.post(f"/leads/{lead_id}/apollo/enrich", json={
        "apollo_id": "p1", "organization_confirmed": True,
    })
    assert response.status_code == 200
    assert response.json()["verification_status"] == "manually_verified"
    assert response.json()["email"] is None
    assert len(enrich_calls) == 1
    assert len(client.get(f"/leads/{lead_id}/contacts").json()) == 1


def test_apollo_enrich_preserves_email_when_organization_matches_or_domain_variant(db, monkeypatch):
    client, factory = db
    with factory.begin() as session:
        lead = Lead(company_name="VRL Logistics", company_key="vrl logistics", domain="vrlgroup.in", extra={})
        session.add(lead)
        session.flush()
        lead_id = lead.id

    monkeypatch.setattr("app.apollo.search_people", lambda domain: [{
        "id": "p_vrl", "name": "Surendra Nayak", "organization": {
            "name": "VRL Logistics",
        },
        "has_email": True,
    }])
    monkeypatch.setattr("app.apollo.enrich_person", lambda person_id: {
        "name": "Surendra Nayak",
        "email": "surendra.nayak@vrllogistics.com",
        "organization": {"name": "VRL Logistics", "primary_domain": "vrllogistics.com"},
    })

    search_res = client.post(f"/leads/{lead_id}/apollo/search").json()
    assert len(search_res) == 1
    assert search_res[0]["organization_matches"] is True
    assert search_res[0]["organization_domain"] == "vrlgroup.in"

    enrich_res = client.post(f"/leads/{lead_id}/apollo/enrich", json={"apollo_id": "p_vrl"})
    assert enrich_res.status_code == 200
    assert enrich_res.json()["email"] == "surendra.nayak@vrllogistics.com"
    assert enrich_res.json()["verification_status"] == "organization_verified"


def test_manual_contact_create_update_and_soft_remove(db):
    client, factory = db
    with factory.begin() as session:
        lead = Lead(company_name="Example", company_key="example", extra={})
        session.add(lead)
        session.flush()
        lead_id = lead.id
    created = client.post(f"/leads/{lead_id}/contacts", json={
        "name": "Sam Example", "email": "sam@example.com", "title": "Director",
        "is_key_decision_maker": True,
    })
    assert created.status_code == 201
    contact = created.json()
    assert contact["apollo_id"] is None
    assert contact["source"] == "Manual"
    assert contact["verification_status"] == "unverified"
    updated = client.put(f"/leads/{lead_id}/contacts/{contact['id']}", json={"title": "VP"})
    assert updated.status_code == 200 and updated.json()["title"] == "VP"
    assert client.delete(f"/leads/{lead_id}/contacts/{contact['id']}").status_code == 204
    assert client.get(f"/leads/{lead_id}/contacts").json() == []
    with factory() as session:
        assert session.get(Contact, contact["id"]).is_active is False


def test_lead_profile_exposes_existing_outreach_history_without_claiming_delivery(db):
    client, factory = db
    with factory.begin() as session:
        lead = Lead(company_name="Profile Co", company_key="profile co", extra={})
        session.add(lead)
        session.flush()
        lead_id = lead.id
    client.post(f"/leads/{lead_id}/contacts", json={"name": "Taylor Contact"})
    campaign = client.post("/campaigns", json={"name": "Profile campaign", "delays": []}).json()
    enrollment = client.post(f"/campaigns/{campaign['id']}/enrollments", json={
        "lead_id": lead_id, "recipient": "taylor@profile.example",
    }).json()
    message = client.get(f"/campaigns/{campaign['id']}").json()["enrollments"][0]["messages"][0]
    with factory.begin() as session:
        record = session.get(EmailMessage, message["id"])
        record.subject, record.body, record.status = "Demo", "Invite body", "sent"
        record.sent_at = now()
        reply = EmailReply(
            mailbox_uid="profile-mailbox:1", enrollment_id=enrollment["id"],
            sender="taylor@profile.example", subject="Re: Demo", body="Interested.",
            classification="meeting_requested",
        )
        session.add(reply)
        session.flush()
        session.add_all([
            EmailEvent(email_id=record.id, event_type="smtp_accepted", event_time=record.sent_at),
            SalesTask(reply_id=reply.id, title="Arrange a meeting", status="open"),
        ])
    profile = client.get(f"/leads/{lead_id}/profile").json()
    assert profile["overview"]["contact_count"] == 1
    assert profile["overview"]["email_count"] == 1
    assert profile["overview"]["reply_count"] == 1
    assert profile["meetings"] == {"implemented": True, "items": []}
    assert profile["email_history"][0]["status"] == "sent"
    assert profile["email_history"][0]["events"][0]["type"] == "smtp_accepted"
    assert profile["email_history"][0]["delivery_confirmed"] is False
    assert any(event["type"] == "sales_task_created" for event in profile["timeline"])


def test_apollo_uses_documented_query_parameters(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path.endswith("/api_search"):
            return httpx.Response(200, json={"people": [{"id": "p1"}]})
        return httpx.Response(200, json={"person": {"id": "p1"}})

    real_client = httpx.Client
    monkeypatch.setattr(apollo.settings, "apollo_api_key", "test-key")
    monkeypatch.setattr(apollo.httpx, "Client", lambda **kwargs: real_client(
        transport=httpx.MockTransport(handler), **kwargs
    ))
    assert apollo.search_people("example.com") == [{"id": "p1"}]
    assert apollo.enrich_person("p1") == {"id": "p1"}
    assert seen[0].method == "POST"
    assert seen[0].url.path == "/api/v1/mixed_people/api_search"
    assert seen[0].url.params.get_list("q_organization_domains_list[]") == ["example.com"]
    assert "director" in seen[0].url.params.get_list("person_seniorities[]")
    assert seen[1].url.params["id"] == "p1"
    assert seen[0].headers["x-api-key"] == "test-key"


@pytest.mark.parametrize("value", [
    "ftp://example.com",
    "https://example.com:8443",
    "https://user@example.com",
    "https://",
])
def test_apollo_company_domain_rejects_unsafe_or_invalid_urls(db, value):
    client, factory = db
    with factory.begin() as session:
        lead = Lead(company_name="Example", company_key="example", extra={})
        session.add(lead)
        session.flush()
        lead_id = lead.id
    response = client.put(f"/leads/{lead_id}/domain", json={"domain": value})
    assert response.status_code == 400
    with factory() as session:
        assert session.get(Lead, lead_id).domain is None


def test_cross_origin_mutation_is_rejected(db):
    client, _ = db
    response = client.post("/batches", headers={"Origin": "https://untrusted.example"})
    assert response.status_code == 403
