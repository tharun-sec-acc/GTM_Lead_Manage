import pytest
from starlette.testclient import TestClient

from app.database import Base
from app.main import app
from app.models import Contact, EmailMessage, EmailReply, Enrollment, Lead, SalesTask, now
from app import mailer


@pytest.fixture
def conv_client(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    db_path = tmp_path / "conv_test.db"
    test_engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(test_engine)
    TestingSession = sessionmaker(bind=test_engine, expire_on_commit=False, autoflush=False)

    from app import database
    monkeypatch.setattr(database, "engine", test_engine)
    monkeypatch.setattr(database, "SessionLocal", TestingSession)

    def override_get_db():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[database.get_db] = override_get_db
    monkeypatch.setattr(mailer.settings, "mail_send_enabled", False)
    monkeypatch.setattr(mailer.settings, "tracking_enabled", False)
    monkeypatch.setattr(mailer.settings, "gmail_address", "sales@denso.example")
    monkeypatch.setattr(mailer.settings, "gmail_app_password", "testapppass123")

    with TestClient(app) as c:
        yield c, TestingSession

    app.dependency_overrides.clear()


def test_conversations_segregation_and_intelligence(conv_client):
    client, Session = conv_client

    with Session.begin() as s:
        # Create Lead & Contact
        lead = Lead(company_name="Tata Motors Extended Care", company_key="tata_motors", domain="tatamotors.test")
        s.add(lead)
        s.flush()

        contact = Contact(
            lead_id=lead.id,
            name="Rajesh Sharma",
            title="VP Supply Chain & Operations",
            email="rajesh.sharma@tatamotors.test",
        )
        s.add(contact)
        s.flush()

        # Create Enrollment
        from app.models import Campaign
        camp = Campaign(name="Test Campaign", mode="manual", delays=[3, 5, 7], status="active")
        s.add(camp)
        s.flush()

        enr = Enrollment(
            campaign_id=camp.id,
            lead_id=lead.id,
            contact_id=contact.id,
            recipient="rajesh.sharma@tatamotors.test",
            status="active",
            reply_blocked=False,
            unsubscribe_token="unsub_test_123",
        )
        s.add(enr)
        s.flush()

        # Add outbound outreach email
        msg = EmailMessage(
            enrollment_id=enr.id,
            step_number=0,
            subject="Tata Motors logistics costs",
            body="Hi Rajesh,\n\nAre transport and warehouse costs increasing?\n\nDENSO Solwer TWMS helps optimize operations.",
            status="sent",
            sent_at=now(),
            due_at=now(),
            message_id="<msg-001@denso.example>",
            open_token="token_001",
        )
        s.add(msg)
        s.flush()

        # Add real prospect reply
        reply = EmailReply(
            mailbox_uid="uid-1001",
            incoming_message_id="<reply-001@tatamotors.test>",
            enrollment_id=enr.id,
            original_email_id=msg.id,
            sender="rajesh.sharma@tatamotors.test",
            subject="Re: Tata Motors logistics costs",
            body="Hi, we are very interested in seeing a demo of Solwer TWMS. Does it integrate with SAP ERP? Can we connect next Tuesday at 2 PM?",
            classification="meeting_requested",
            received_at=now(),
        )
        s.add(reply)
        s.flush()

        # Add an automated bounce (NDR with enrollment_id None)
        orphan_bounce = EmailReply(
            mailbox_uid="uid-9999",
            incoming_message_id="<bounce-9999@iamneo.ai>",
            enrollment_id=None,
            original_email_id=None,
            sender="microsoftexchange329e@iamneo.ai",
            subject="Delivery Status Notification (Failure)",
            body="Diagnostic-Code: smtp; 550 5.1.1 User unknown",
            classification="hard_bounce",
            received_at=now(),
        )
        s.add(orphan_bounce)
        s.flush()

        enr_id = enr.id

    # 1. Test GET /conversations with default category=sales
    resp = client.get("/conversations?category=sales")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["conversations"][0]["id"] == enr_id
    assert data["conversations"][0]["company_name"] == "Tata Motors Extended Care"
    assert data["conversations"][0]["is_sales_conversation"] is True
    assert data["conversations"][0]["interest_level"] in ("VERY_HIGH", "HIGH", "MEDIUM")
    assert len(data["conversations"][0]["timeline"]) == 2  # 1 outbound + 1 inbound

    # 2. Test GET /conversations?category=automated (should contain only the bounce)
    resp_bounces = client.get("/conversations?category=automated")
    assert resp_bounces.status_code == 200
    b_data = resp_bounces.json()
    assert b_data["total"] == 1
    assert "iamneo.ai" in b_data["conversations"][0]["recipient_email"]
    assert b_data["conversations"][0]["is_sales_conversation"] is False

    # 3. Test GET /conversations/{conversation_id}
    detail_resp = client.get(f"/conversations/{enr_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["contact_name"] == "Rajesh Sharma"
    assert detail["intelligence"]["classification"] in ("MEETING_REQUESTED", "DEMO_REQUESTED", "INTERESTED")
    assert "recommended_action" in detail["intelligence"]

    # 4. Test POST /conversations/{conversation_id}/generate-draft
    draft_resp = client.post(f"/conversations/{enr_id}/generate-draft")
    assert draft_resp.status_code == 200
    draft = draft_resp.json()
    assert "subject" in draft and "body" in draft
    assert len(draft["body"]) > 10

    # 5. Test POST /conversations/{conversation_id}/reply
    reply_resp = client.post(
        f"/conversations/{enr_id}/reply",
        json={
            "subject": "Re: Tata Motors logistics costs",
            "body": "Hi Rajesh,\n\n**Yes, Solwer integrates directly with SAP!**\n\nTuesday at 2 PM works great. Looking forward to our discussion.",
            "attachment_ids": [],
            "send_now": True,
        },
    )
    assert reply_resp.status_code == 200
    updated = reply_resp.json()
    assert len(updated["timeline"]) == 3  # now 3 messages
    last_msg = updated["timeline"][-1]
    assert last_msg["type"] == "outbound"
    assert "integrates directly with SAP" in last_msg["body"]

    # 6. Test POST /conversations/{conversation_id}/followup-status
    status_resp = client.post(
        f"/conversations/{enr_id}/followup-status",
        json={"status": "FOLLOW_UP_COMPLETED", "note": "Meeting scheduled for Tuesday"},
    )
    assert status_resp.status_code == 200
