import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import Contact, Lead, Product, ProductLead, ProductOpportunity
from app.meetings.models import Meeting, MeetingAnalysis, MeetingActionItem
from app.booking.models import Booking, BookingProfile
from app.zoho.client import ZohoClient, ZohoAPIError, ZohoRateLimitError
from app.zoho.crypto import encrypt_token, decrypt_token
from app.zoho.models import (
    ZohoConnection, ZohoOAuthState, ZohoFieldMapping, ZohoRecordMapping,
    ZohoSyncJob, ZohoSyncLog, ZohoSyncConflict, now as zoho_now
)
from app.zoho.service import ZohoService, DEFAULT_STAGE_MAPPING


# Setup isolated test database for fast, reliable tests
@pytest.fixture
def workspace(tmp_path):
    db_path = tmp_path / "zoho_test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    with factory() as session:
        yield session
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(workspace):
    return TestClient(app)


@pytest.fixture
def mock_connected_zoho(workspace):
    """Sets up an active ZohoConnection in the database."""
    conn = ZohoConnection(
        org_id="zoho_org_12345",
        org_name="DENSO Test Org",
        user_email="sales@denso.test",
        accounts_domain="https://accounts.zoho.in",
        api_domain="https://www.zohoapis.in",
        crm_api_version="v8",
        refresh_token_encrypted=encrypt_token("mock_refresh_token_xyz"),
        access_token_encrypted=encrypt_token("mock_access_token_abc"),
        access_token_expires_at=zoho_now() + timedelta(hours=1),
        is_active=True,
    )
    workspace.add(conn)
    workspace.commit()
    workspace.refresh(conn)
    return conn


# -----------------------------------------------------------------------------
# 1. OAuth & Token Encryption Tests
# -----------------------------------------------------------------------------

def test_crypto_token_encryption():
    raw_token = "1000.secret_refresh_token_string"
    encrypted = encrypt_token(raw_token)
    assert isinstance(encrypted, bytes)
    assert encrypted != raw_token.encode()
    decrypted = decrypt_token(encrypted)
    assert decrypted == raw_token


def test_generate_authorization_url(workspace):
    service = ZohoService(workspace)
    with patch.object(settings, "zoho_client_id", "1000.TEST_CLIENT_ID"):
        auth_url, state = service.generate_authorization_url(browser_hash="mock_hash")
        assert "https://accounts.zoho.in/oauth/v2/auth" in auth_url
        assert "1000.TEST_CLIENT_ID" in auth_url
        assert state in auth_url
        assert "ZohoCRM.modules.ALL" in auth_url


def test_handle_oauth_callback(workspace):
    service = ZohoService(workspace)
    with patch.object(settings, "zoho_client_id", "1000.TEST_CLIENT_ID"), \
         patch.object(settings, "zoho_client_secret", "secret_123"), \
         patch("requests.post") as mock_post, \
         patch.object(ZohoClient, "get_organization") as mock_org:

        # Step 1: Generate state
        _, state = service.generate_authorization_url("browser_abc")
        workspace.commit()

        # Step 2: Mock Zoho Accounts token exchange
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "access_token": "mock_new_access_token",
                "refresh_token": "mock_new_refresh_token",
                "api_domain": "https://www.zohoapis.in",
                "expires_in": 3600,
            },
        )
        mock_org.return_value = {
            "id": "org_998877",
            "company_name": "Test Company India",
            "primary_email": "admin@testcompany.in",
        }

        conn = service.handle_oauth_callback(code="auth_code_xyz", state=state, browser_hash="browser_abc")
        workspace.commit()

        assert conn.is_active is True
        assert conn.org_id == "org_998877"
        assert conn.org_name == "Test Company India"
        assert decrypt_token(conn.refresh_token_encrypted) == "mock_new_refresh_token"


# -----------------------------------------------------------------------------
# 2. Client & Rate Limiting Tests
# -----------------------------------------------------------------------------

def test_client_proactive_token_refresh(workspace, mock_connected_zoho):
    # Expire access token to force refresh
    mock_connected_zoho.access_token_expires_at = zoho_now() - timedelta(minutes=10)
    workspace.commit()

    client = ZohoClient(workspace, mock_connected_zoho)
    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "access_token": "refreshed_access_token_123",
                "expires_in": 3600,
            },
        )
        token = client.get_access_token()
        assert token == "refreshed_access_token_123"


def test_client_rate_limiting_and_retry(workspace, mock_connected_zoho):
    client = ZohoClient(workspace, mock_connected_zoho)
    with patch("requests.request") as mock_req, patch("time.sleep") as mock_sleep:
        # First request hits 429 Rate Limit, second succeeds with 200
        mock_req.side_effect = [
            MagicMock(status_code=429, json=lambda: {"message": "Rate limit exceeded"}),
            MagicMock(status_code=200, json=lambda: {"data": [{"id": "rec_1"}]}),
        ]
        res = client.get("Accounts")
        assert res["data"][0]["id"] == "rec_1"
        assert mock_sleep.called


# -----------------------------------------------------------------------------
# 3. Field Mappings & 17-Stage Lifecycle Tests
# -----------------------------------------------------------------------------

def test_seed_default_field_mappings(workspace):
    service = ZohoService(workspace)
    service.seed_default_field_mappings()
    mappings = service.get_field_mappings()
    assert len(mappings) >= 15
    account_name_map = next(m for m in mappings if m.zoho_module == "Accounts" and m.gtm_field == "company_name")
    assert account_name_map.zoho_field == "Account_Name"
    assert account_name_map.conflict_policy == "crm_wins"


def test_17_stage_sales_lifecycle_mapping():
    assert DEFAULT_STAGE_MAPPING["prospect"] == "Qualification"
    assert DEFAULT_STAGE_MAPPING["outreach_initiated"] == "Needs Analysis"
    assert DEFAULT_STAGE_MAPPING["meeting_scheduled"] == "Proposal/Price Quote"
    assert DEFAULT_STAGE_MAPPING["demo_completed"] == "Negotiation/Review"
    assert DEFAULT_STAGE_MAPPING["won"] == "Closed Won"
    assert DEFAULT_STAGE_MAPPING["closed_lost"] == "Closed Lost"


# -----------------------------------------------------------------------------
# 4. Outbound Synchronization Tests
# -----------------------------------------------------------------------------

def test_sync_account_outbound(workspace, mock_connected_zoho):
    service = ZohoService(workspace)
    lead = Lead(
        company_name="Tata Motors Extended Care",
        company_key="tata_motors",
        domain="tatamotors.com",
        phone="+912266658282",
        industry="Automotive",
    )
    workspace.add(lead)
    workspace.commit()

    with patch.object(ZohoClient, "upsert_records") as mock_upsert:
        mock_upsert.return_value = [{"status": "success", "details": {"id": "zoho_acc_9999"}}]
        mapping = service.sync_account_outbound(lead.id)
        assert mapping is not None
        assert mapping.zoho_record_id == "zoho_acc_9999"
        assert mapping.sync_status == "synced"
        assert mock_upsert.called


def test_sync_contact_outbound(workspace, mock_connected_zoho):
    service = ZohoService(workspace)
    lead = Lead(company_name="VRL Logistics", company_key="vrl_logistics", domain="vrl.in")
    workspace.add(lead)
    workspace.commit()

    contact = Contact(
        lead_id=lead.id,
        name="Suresh Raina",
        email="suresh.raina@vrl.in",
        title="VP Fleet Logistics",
    )
    workspace.add(contact)
    workspace.commit()

    with patch.object(ZohoClient, "upsert_records") as mock_upsert:
        # Returns success for Account and Contact
        mock_upsert.side_effect = [
            [{"status": "success", "details": {"id": "zoho_acc_vrl"}}],
            [{"status": "success", "details": {"id": "zoho_cnt_suresh"}}],
        ]
        mapping = service.sync_contact_outbound(contact.id)
        assert mapping is not None
        assert mapping.zoho_record_id == "zoho_cnt_suresh"


def test_sync_opportunity_to_deal(workspace, mock_connected_zoho):
    service = ZohoService(workspace)
    product = Product(name="TWMS Logistics Solver", slug="twms-solver")
    lead = Lead(company_name="TCI Express", company_key="tci_express", domain="tciexpress.in")
    workspace.add_all([product, lead])
    workspace.commit()

    prod_lead = ProductLead(product_id=product.id, lead_id=lead.id, stage="demo_completed")
    workspace.add(prod_lead)
    workspace.commit()

    opp = ProductOpportunity(
        product_lead_id=prod_lead.id,
        opportunity_summary="Warehouse automation cross-docking deployment",
        status="active",
    )
    workspace.add(opp)
    workspace.commit()

    with patch.object(ZohoClient, "upsert_records") as mock_upsert:
        mock_upsert.side_effect = [
            [{"status": "success", "details": {"id": "zoho_acc_tci"}}],
            [{"status": "success", "details": {"id": "zoho_deal_123"}}],
        ]
        mapping = service.sync_opportunity_to_deal(opp.id)
        assert mapping is not None
        assert mapping.zoho_record_id == "zoho_deal_123"
        # Verify stage mapped from demo_completed to Negotiation/Review
        call_args = mock_upsert.call_args_list[1]
        assert call_args[0][1][0]["Stage"] == "Negotiation/Review"


# -----------------------------------------------------------------------------
# 5. Public Booking to Zoho CRM Event Test
# -----------------------------------------------------------------------------

def test_sync_booking_to_zoho_event(workspace, mock_connected_zoho):
    service = ZohoService(workspace)
    profile = BookingProfile(
        public_slug="denso-test",
        display_name="Discovery",
        company_name="DENSO",
        meeting_title="DENSO Discovery Call",
    )
    workspace.add(profile)
    workspace.commit()

    lead = Lead(company_name="Apollo Tyres", company_key="apollo_tyres", domain="apollotyres.com")
    workspace.add(lead)
    workspace.commit()

    meeting = Meeting(
        provider="google_meet",
        join_url="https://meet.google.com/abc-defg-hij",
        title="DENSO Discovery Call - Apollo Tyres",
    )
    workspace.add(meeting)
    workspace.commit()

    booking = Booking(
        booking_profile_id=profile.id,
        meeting_id=meeting.id,
        lead_id=lead.id,
        customer_name="Vikram Mehta",
        customer_email="vikram@apollotyres.com",
        customer_company="Apollo Tyres",
        start_time=zoho_now() + timedelta(days=1),
        end_time=zoho_now() + timedelta(days=1, minutes=30),
        status="confirmed",
        cancellation_token_hash="hash_cancel_123",
        reschedule_token_hash="hash_reschedule_123",
    )
    workspace.add(booking)
    workspace.commit()

    with patch.object(ZohoClient, "upsert_records") as mock_upsert, \
         patch.object(ZohoClient, "create_records") as mock_create:
        mock_upsert.side_effect = [
            [{"status": "success", "details": {"id": "acc_apollo"}}],
        ]
        mock_create.return_value = [{"status": "success", "details": {"id": "event_apollo_meet"}}]

        map_rec = service.sync_booking_to_zoho(booking.id)
        assert map_rec is not None
        assert map_rec.zoho_record_id == "event_apollo_meet"
        assert map_rec.zoho_module == "Events"

        event_payload = mock_create.call_args[0][1][0]
        assert "Google Meet" in event_payload["Description"]
        assert event_payload["Venue"] == "https://meet.google.com/abc-defg-hij"


# -----------------------------------------------------------------------------
# 6. Meeting Intelligence & MoM Sync Test
# -----------------------------------------------------------------------------

def test_sync_meeting_intelligence_to_zoho(workspace, mock_connected_zoho):
    service = ZohoService(workspace)
    lead = Lead(company_name="Mahindra Logistics", company_key="mahindra_logistics")
    workspace.add(lead)
    workspace.commit()

    meeting = Meeting(
        title="TWMS Platform Demonstration",
        lead_id=lead.id,
        provider="teams",
        join_url="https://teams.microsoft.com/l/meetup-join/123",
    )
    workspace.add(meeting)
    workspace.commit()

    analysis = MeetingAnalysis(
        meeting_id=meeting.id,
        executive_summary="Deep discovery on warehouse slotting and vehicle telematics.",
        customer_requirements=["Real-time truck tracking", "Automated barcode dispatch"],
        customer_pain_points=["Manual paperwork delays in Pune depot"],
        decisions=["Pilot scheduled for next month"],
        meeting_minutes="Meeting convened to review TWMS Platform deployment.",
        recommended_sales_stage="Solution Validation",
    )
    action_item = MeetingActionItem(
        meeting_id=meeting.id,
        lead_id=lead.id,
        title="Send technical architecture deck",
        owner="Sales Rep",
        status="open",
    )
    workspace.add_all([analysis, action_item])
    workspace.commit()

    with patch.object(ZohoClient, "upsert_records") as mock_upsert, \
         patch.object(ZohoClient, "add_note") as mock_note, \
         patch.object(ZohoClient, "create_records") as mock_task:

        mock_upsert.return_value = [{"status": "success", "details": {"id": "acc_mahindra"}}]
        mock_note.return_value = {"id": "note_mom_123"}
        mock_task.return_value = [{"status": "success", "details": {"id": "task_deck_456"}}]

        service.sync_meeting_intelligence_to_zoho(meeting.id)

        assert mock_note.called
        note_content = mock_note.call_args[1]["content"]
        assert "Real-time truck tracking" in note_content
        assert "Manual paperwork delays" in note_content

        assert mock_task.called
        task_payload = mock_task.call_args[0][1][0]
        assert "Send technical architecture deck" in task_payload["Subject"]


# -----------------------------------------------------------------------------
# 7. Inbound Synchronization & Conflict Resolution Test
# -----------------------------------------------------------------------------

def test_run_inbound_sync_and_upsert(workspace, mock_connected_zoho):
    service = ZohoService(workspace)
    with patch.object(ZohoClient, "get_records") as mock_records:
        def _get_records_side_effect(module, **kwargs):
            if module == "Accounts":
                return (
                    [
                        {
                            "id": "zoho_inbound_acc_1",
                            "Account_Name": "Blue Dart Express",
                            "Website": "bluedart.com",
                            "Phone": "+918888888888",
                            "Industry": "Logistics & Supply Chain",
                        }
                    ],
                    {"more_records": False},
                )
            elif module == "Contacts":
                return (
                    [
                        {
                            "id": "zoho_inbound_con_1",
                            "First_Name": "Anand",
                            "Last_Name": "Sharma",
                            "Email": "anand.sharma@bluedart.com",
                            "Phone": "+919999999999",
                            "Title": "Head of Operations",
                            "Department": "Supply Chain",
                            "Account_Name": {"name": "Blue Dart Express", "id": "zoho_inbound_acc_1"},
                        }
                    ],
                    {"more_records": False},
                )
            return ([], {"more_records": False})

        mock_records.side_effect = _get_records_side_effect
        job = service.run_inbound_sync()
        workspace.commit()

        assert job.status == "completed"
        assert job.records_succeeded == 2

        lead = workspace.query(Lead).filter(Lead.domain == "bluedart.com").first()
        assert lead is not None
        assert lead.company_name == "Blue Dart Express"
        assert lead.phone == "+918888888888"

        contact = workspace.query(Contact).filter(Contact.email == "anand.sharma@bluedart.com").first()
        assert contact is not None
        assert contact.name == "Anand Sharma"
        assert contact.lead_id == lead.id
        assert contact.source == "Zoho CRM"


# -----------------------------------------------------------------------------
# 8. API Endpoints Test
# -----------------------------------------------------------------------------

def test_api_zoho_connection_endpoints(client, mock_connected_zoho, monkeypatch):
    res = client.get("/zoho/connection")
    assert res.status_code == 200
    data = res.json()
    assert data["is_connected"] is True
    assert data["connected"] is True
    assert data["org_name"] == "DENSO Test Org"

    # Test verify endpoint
    monkeypatch.setattr(
        "app.zoho.client.ZohoClient.get",
        lambda self, path, params=None: {"org": [{"company_name": "DENSO Test Org", "zgid": "123456", "primary_email": "org@example.com", "time_zone": "Asia/Kolkata"}]}
    )
    res_verify = client.post("/zoho/verify")
    assert res_verify.status_code == 200
    vdata = res_verify.json()
    assert vdata["success"] is True
    assert vdata["is_connected"] is True

    # Disconnect
    res_disc = client.post("/zoho/disconnect")
    assert res_disc.status_code == 200

    res_after = client.get("/zoho/connection")
    assert res_after.json()["is_connected"] is False


def test_api_zoho_mappings_endpoint(client):
    res = client.get("/zoho/mappings")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 15
    first = data[0]
    assert "zoho_module" in first
    assert "gtm_field" in first
    assert "zoho_field" in first
