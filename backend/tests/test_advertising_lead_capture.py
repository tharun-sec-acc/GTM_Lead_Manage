"""Release 3 tests: advertising connectors, lead capture, attribution."""

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.advertising.models import (
    AdCampaign,
    AdConnection,
    AttributionTouchpoint,
    CapturedSubmission,
)
from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import Lead


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


def add_read_only_member(client, owner: dict, email: str) -> dict:
    invite = client.post(
        "/organizations/members/invite",
        headers=auth(owner["access_token"]),
        json={"email": email, "role": "read_only"},
    )
    assert invite.status_code == 201, invite.text
    token = invite.json()["invite_url"].split("/invite/")[-1]
    accept = client.post(
        "/public/invitations/accept",
        json={"token": token, "full_name": "Viewer", "password": "ViewerPassword123!"},
    )
    assert accept.status_code in (200, 201), accept.text
    login = client.post(
        "/auth/login", json={"email": email, "password": "ViewerPassword123!"}
    )
    assert login.status_code == 200, login.text
    return login.json()


def create_connection(client, owner: dict, provider: str = "meta", account: str = "act_123") -> dict:
    res = client.post(
        "/advertising/connections",
        headers=auth(owner["access_token"]),
        json={
            "provider": provider,
            "external_account_id": account,
            "account_name": "Test account",
            "access_token": "provider-token-value",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def create_form(client, owner: dict, **overrides) -> dict:
    payload = {
        "name": "Website enquiry",
        "slug": overrides.pop("slug", "website-enquiry"),
        "consent_text": "I agree to be contacted.",
    }
    payload.update(overrides)
    res = client.post(
        "/advertising/forms", headers=auth(owner["access_token"]), json=payload
    )
    assert res.status_code == 201, res.text
    return res.json()


# ------------------------------- connections ------------------------------


def test_connection_credentials_are_encrypted_and_never_returned(client, test_db):
    owner = register(client, "ads-owner@alpha.com", "Alpha Ads")
    connection = create_connection(client, owner)

    assert connection["has_credentials"] is True
    assert connection["status"] == "connected"
    assert "access_token" not in json.dumps(connection)
    assert "provider-token-value" not in json.dumps(connection)

    session = test_db()
    try:
        stored = session.get(AdConnection, connection["id"])
        assert stored.access_token_encrypted is not None
        assert b"provider-token-value" not in stored.access_token_encrypted
    finally:
        session.close()


def test_connection_writes_require_manager_role(client):
    owner = register(client, "ads-roles@beta.com", "Beta Ads")
    viewer = add_read_only_member(client, owner, "viewer@beta.com")

    res = client.post(
        "/advertising/connections",
        headers=auth(viewer["access_token"]),
        json={"provider": "meta", "external_account_id": "act_9", "access_token": "x"},
    )
    assert res.status_code == 403

    listed = client.get("/advertising/connections", headers=auth(viewer["access_token"]))
    assert listed.status_code == 200
    assert listed.json() == []


def test_sync_reports_missing_credentials_instead_of_fake_data(client):
    owner = register(client, "ads-sync@gamma.com", "Gamma Ads")
    connection = client.post(
        "/advertising/connections",
        headers=auth(owner["access_token"]),
        json={"provider": "meta", "external_account_id": "act_555"},
    ).json()
    assert connection["status"] == "pending_credentials"

    res = client.post(
        f"/advertising/connections/{connection['id']}/sync",
        headers=auth(owner["access_token"]),
    )
    assert res.status_code == 409
    assert "token" in res.json()["detail"].lower()


# -------------------------------- campaigns -------------------------------


def test_campaign_rows_and_metrics_drive_cpl(client, test_db):
    owner = register(client, "ads-campaign@delta.com", "Delta Ads")
    connection = create_connection(client, owner, account="act_777")

    upsert = client.post(
        f"/advertising/connections/{connection['id']}/campaigns",
        headers=auth(owner["access_token"]),
        json={
            "campaigns": [
                {
                    "external_id": "C1",
                    "name": "Spring launch",
                    "status": "ACTIVE",
                    "objective": "OUTCOME_LEADS",
                    "daily_budget_cents": 50000,
                },
                {"external_id": "C2", "name": "Retargeting"},
            ]
        },
    )
    assert upsert.status_code == 200, upsert.text
    assert upsert.json() == {"created": 2, "updated": 0}

    repeated = client.post(
        f"/advertising/connections/{connection['id']}/campaigns",
        headers=auth(owner["access_token"]),
        json={"campaigns": [{"external_id": "C1", "name": "Spring launch v2"}]},
    )
    assert repeated.json() == {"created": 0, "updated": 1}

    session = test_db()
    try:
        campaign = session.scalar(select(AdCampaign).where(AdCampaign.external_id == "C1"))
        campaign_id = campaign.id
        assert session.scalar(
            select(AdCampaign).where(AdCampaign.external_id == "C1")
        ).name == "Spring launch v2"
    finally:
        session.close()

    metrics = client.post(
        f"/advertising/campaigns/{campaign_id}/metrics",
        headers=auth(owner["access_token"]),
        json={
            "rows": [
                {"metric_date": "2026-11-01", "spend_cents": 100000, "impressions": 5000, "clicks": 120, "leads": 10},
                {"metric_date": "2026-11-02", "spend_cents": 60000, "impressions": 2500, "clicks": 60, "leads": 5},
                {"metric_date": "2026-11-02", "spend_cents": 60000, "impressions": 2500, "clicks": 60, "leads": 5},
            ]
        },
    )
    assert metrics.status_code == 200, metrics.text
    # The duplicate day is upserted, not added twice.
    assert metrics.json()["campaign"]["spend_cents"] == 160000
    assert metrics.json()["campaign"]["provider_leads"] == 15
    assert metrics.json()["recorded"] == 2

    report = client.get("/advertising/reports/campaigns", headers=auth(owner["access_token"]))
    assert report.status_code == 200
    body = report.json()
    spring = next(row for row in body["campaigns"] if row["external_id"] == "C1")
    assert spring["cost_per_lead_cents"] == 160000 // 15
    assert spring["crm_leads"] == 0
    assert "not proof" in body["caveat"]
    assert body["attribution_model"]


# ------------------------------ website forms -----------------------------


def test_website_form_creates_attributed_lead(client, test_db):
    owner = register(client, "ads-forms@epsilon.com", "Epsilon Ads")
    form = create_form(client, owner)

    res = client.post(
        f"/public/forms/{form['slug']}/submit",
        json={
            "name": "Priya Sharma",
            "email": "priya@acme.example",
            "company": "Acme Industries",
            "phone": "+919000000001",
            "message": "Need a demo",
            "consent": True,
            "campaign_id": "C1",
            "utm": {
                "utm_source": "google",
                "utm_medium": "cpc",
                "utm_campaign": "spring",
            },
            "landing_page": "https://acme.example/landing?utm_source=google",
            "referrer": "https://google.com",
        },
    )
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "accepted"

    session = test_db()
    try:
        lead = session.scalar(select(Lead).where(Lead.email == "priya@acme.example"))
        assert lead is not None
        assert lead.source == "website_form"
        assert lead.organization_id == owner["organization"]["id"]
        touchpoint = session.scalar(
            select(AttributionTouchpoint).where(AttributionTouchpoint.lead_id == lead.id)
        )
        assert touchpoint.channel == "website"
        assert touchpoint.campaign_external_id == "C1"
        assert touchpoint.medium == "cpc"
        submission = session.scalar(
            select(CapturedSubmission).where(CapturedSubmission.lead_id == lead.id)
        )
        assert submission.status == "accepted"
    finally:
        session.close()

    refreshed = client.get("/advertising/forms", headers=auth(owner["access_token"])).json()
    assert refreshed[0]["submission_count"] == 1


def test_form_requires_consent_and_ignores_bots(client, test_db):
    owner = register(client, "ads-consent@zeta.com", "Zeta Ads")
    form = create_form(client, owner, slug="consent-form")

    no_consent = client.post(
        f"/public/forms/{form['slug']}/submit",
        json={"name": "No Consent", "email": "no@consent.example", "consent": False},
    )
    assert no_consent.status_code == 400

    bot = client.post(
        f"/public/forms/{form['slug']}/submit",
        json={
            "name": "Bot",
            "email": "bot@spam.example",
            "consent": True,
            "honeypot": "http://spam.example",
        },
    )
    assert bot.status_code in (200, 201)
    assert bot.json()["status"] == "accepted"

    session = test_db()
    try:
        assert session.scalar(select(Lead).where(Lead.email == "bot@spam.example")) is None
        assert session.scalar(select(CapturedSubmission)) is None
    finally:
        session.close()


def test_form_submission_without_contact_details_is_rejected(client):
    owner = register(client, "ads-reject@theta.com", "Theta Ads")
    form = create_form(client, owner, slug="empty-form")
    res = client.post(
        f"/public/forms/{form['slug']}/submit",
        json={"name": "Nobody", "consent": True},
    )
    assert res.status_code == 400


# -------------------------------- webhooks --------------------------------


def _meta_body(leadgen_id: str, form_id: str) -> bytes:
    return json.dumps(
        {
            "object": "page",
            "entry": [
                {
                    "id": "page-1",
                    "changes": [
                        {"field": "leadgen", "value": {"leadgen_id": leadgen_id, "form_id": form_id}}
                    ],
                }
            ],
        }
    ).encode()


def test_meta_webhook_requires_signature_and_is_idempotent(client, test_db, monkeypatch):
    monkeypatch.setattr(settings, "meta_app_secret", "app-secret")
    monkeypatch.setattr(settings, "meta_webhook_verify_token", "verify-token")
    owner = register(client, "ads-meta@iota.com", "Iota Ads")
    create_form(
        client,
        owner,
        slug="meta-form",
        provider="meta",
        provider_form_id="FORM_1",
    )

    body = _meta_body("LEAD_1", "FORM_1")
    unsigned = client.post(
        "/public/webhooks/meta", content=body, headers={"Content-Type": "application/json"}
    )
    assert unsigned.status_code == 401

    signature = "sha256=" + hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()
    signed = client.post(
        "/public/webhooks/meta",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
    )
    assert signed.status_code == 200, signed.text
    # No Meta connection is configured, so the delivery is stored for retry.
    assert signed.json()["pending"] == 1

    session = test_db()
    try:
        submission = session.scalar(
            select(CapturedSubmission).where(CapturedSubmission.provider_submission_id == "LEAD_1")
        )
        assert submission.status == "received"
        assert submission.lead_id is None
        assert "meta ad account" in (submission.error or "").lower()
    finally:
        session.close()

    replay = client.post(
        "/public/webhooks/meta",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
    )
    assert replay.status_code == 200
    assert replay.json()["pending"] == 0

    retry = client.post(
        f"/advertising/submissions/{submission.id}/process",
        headers=auth(owner["access_token"]),
    )
    assert retry.status_code == 409


def test_meta_webhook_verification_challenge(client, monkeypatch):
    monkeypatch.setattr(settings, "meta_webhook_verify_token", "verify-token")
    wrong = client.get(
        "/public/webhooks/meta",
        params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "42"},
    )
    assert wrong.status_code == 403

    ok = client.get(
        "/public/webhooks/meta",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "verify-token",
            "hub.challenge": "42",
        },
    )
    assert ok.status_code == 200
    assert ok.json() == 42


def test_google_lead_webhook_creates_lead_once(client, test_db, monkeypatch):
    monkeypatch.setattr(settings, "google_lead_form_key", "google-key")
    owner = register(client, "ads-google@kappa.com", "Kappa Ads")
    create_form(
        client,
        owner,
        slug="google-form",
        provider="google",
        provider_form_id="GFORM_1",
    )

    payload = {
        "lead_id": "GLEAD_1",
        "form_id": "GFORM_1",
        "campaign_id": "G_CAMPAIGN_1",
        "google_key": "google-key",
        "user_column_data": [
            {"column_id": "FULL_NAME", "string_value": "Arjun Rao"},
            {"column_id": "EMAIL", "string_value": "arjun@example.com"},
            {"column_id": "COMPANY_NAME", "string_value": "Rao Traders"},
            {"column_id": "PHONE_NUMBER", "string_value": "+919000000002"},
        ],
    }
    bad_key = client.post(
        "/public/webhooks/google", json={**payload, "google_key": "wrong"}
    )
    assert bad_key.status_code == 401

    first = client.post("/public/webhooks/google", json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "accepted"

    duplicate = client.post("/public/webhooks/google", json=payload)
    assert duplicate.json()["status"] == "duplicate"

    session = test_db()
    try:
        leads = session.scalars(select(Lead).where(Lead.email == "arjun@example.com")).all()
        assert len(leads) == 1
        assert leads[0].source == "google_lead_form"
        touchpoint = session.scalar(
            select(AttributionTouchpoint).where(AttributionTouchpoint.lead_id == leads[0].id)
        )
        assert touchpoint.campaign_external_id == "G_CAMPAIGN_1"
    finally:
        session.close()


# ------------------------------- attribution ------------------------------


def test_campaign_to_won_revenue_attribution(client):
    owner = register(client, "ads-revenue@lambda.com", "Lambda Ads")
    connection = create_connection(client, owner, account="act_rev")
    client.post(
        f"/advertising/connections/{connection['id']}/campaigns",
        headers=auth(owner["access_token"]),
        json={"campaigns": [{"external_id": "C_REV", "name": "Revenue campaign"}]},
    )
    form = create_form(client, owner, slug="revenue-form")
    submit = client.post(
        f"/public/forms/{form['slug']}/submit",
        json={
            "name": "Deal Maker",
            "email": "deal@example.com",
            "company": "Deal Co",
            "consent": True,
            "campaign_id": "C_REV",
        },
    )
    assert submit.status_code == 201

    session = client.get("/advertising/submissions", headers=auth(owner["access_token"])).json()
    lead_id = session[0]["lead_id"]

    qualified = client.patch(
        f"/crm/leads/{lead_id}",
        headers=auth(owner["access_token"]),
        json={"qualification_status": "qualified"},
    )
    assert qualified.status_code == 200, qualified.text

    opportunity = client.post(
        "/crm/opportunities",
        headers=auth(owner["access_token"]),
        json={"lead_id": lead_id, "name": "Deal Co rollout", "amount_cents": 250000},
    )
    assert opportunity.status_code == 201, opportunity.text
    opportunity_id = opportunity.json()["id"]
    closed = client.post(
        f"/crm/opportunities/{opportunity_id}/close",
        headers=auth(owner["access_token"]),
        json={"status": "won"},
    )
    assert closed.status_code == 200, closed.text

    report = client.get("/advertising/reports/campaigns", headers=auth(owner["access_token"])).json()
    row = next(item for item in report["campaigns"] if item["external_id"] == "C_REV")
    assert row["crm_leads"] == 1
    assert row["qualified_leads"] == 1
    assert row["opportunities"] == 1
    assert row["won_deals"] == 1
    assert row["won_value_cents"] == 250000


# ------------------------------ tenant isolation --------------------------


def test_campaigns_and_forms_are_organization_scoped(client):
    alpha = register(client, "ads-iso-a@mu.com", "Mu Ads")
    beta = register(client, "ads-iso-b@nu.com", "Nu Ads")

    connection = create_connection(client, alpha, account="act_iso")
    client.post(
        f"/advertising/connections/{connection['id']}/campaigns",
        headers=auth(alpha["access_token"]),
        json={"campaigns": [{"external_id": "ISO_1", "name": "Alpha only"}]},
    )
    form = create_form(client, alpha, slug="alpha-form")

    beta_campaigns = client.get("/advertising/campaigns", headers=auth(beta["access_token"])).json()
    assert beta_campaigns == []
    beta_forms = client.get("/advertising/forms", headers=auth(beta["access_token"])).json()
    assert beta_forms == []

    session = client.get("/advertising/campaigns", headers=auth(alpha["access_token"])).json()
    campaign_id = session[0]["id"]
    assert client.get(
        f"/advertising/campaigns/{campaign_id}", headers=auth(beta["access_token"])
    ).status_code == 404
    assert client.get(
        f"/advertising/forms/{form['id']}/submissions", headers=auth(beta["access_token"])
    ).status_code == 404
    assert client.post(
        f"/advertising/connections/{connection['id']}/sync",
        headers=auth(beta["access_token"]),
    ).status_code == 404
