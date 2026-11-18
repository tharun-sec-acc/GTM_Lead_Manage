"""Tests for DENSO Solwer TWMS automated draft population, mailbox sync, and received analytics."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import bedrock, mailer
from app.database import Base, get_db
from app.main import app
from app.models import Campaign, Contact, EmailMessage, EmailReply, Enrollment, Lead, MailboxState


@pytest.fixture
def denso_workflow(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'denso.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    monkeypatch.setattr(mailer, "SessionLocal", factory)
    monkeypatch.setattr("app.mailbox.poll_mailbox", lambda session: True)
    monkeypatch.setattr(mailer.settings, "mail_send_enabled", True)
    monkeypatch.setattr(mailer.settings, "gmail_address", "tharunjs012003@gmail.com")
    monkeypatch.setattr(mailer.settings, "gmail_app_password", "secret")

    with factory.begin() as session:
        lead = Lead(company_name="VRL Logistics", company_key="vrl_logistics", extra={})
        session.add(lead)
        session.flush()
        lead_id = lead.id

        contact = Contact(lead_id=lead_id, name="Vijay Sankeshwar", email="vijay@vrl.example")
        session.add(contact)
        session.flush()
        contact_id = contact.id

    with TestClient(app) as client:
        yield client, factory, lead_id, contact_id

    app.dependency_overrides.clear()
    engine.dispose()


def test_build_denso_solwer_twms_sequence_structure():
    seq = bedrock.build_denso_solwer_twms_sequence(
        company="VRL Logistics", contact_first_name="Vijay", steps=4
    )
    assert len(seq) == 4
    # Email 1
    assert "VRL Logistics" in seq[0]["subject"]
    assert "logistics costs" in seq[0]["subject"]
    assert "Hi Vijay" in seq[0]["body"]
    assert "Solwer TWMS" in seq[0]["body"]
    assert "20–30%" in seq[0]["body"]
    assert "15-minute discussion" in seq[0]["body"]

    # Email 2
    assert "Re:" in seq[1]["subject"]
    assert "reduce transportation costs" in seq[1]["body"]
    assert "truck capacity utilization" in seq[1]["body"]

    # Email 3
    assert "Re:" in seq[2]["subject"]
    assert "SAP" in seq[2]["body"]
    assert "ERP" in seq[2]["body"]

    # Email 4
    assert "Re:" in seq[3]["subject"]
    assert "5–25%" in seq[3]["body"]
    assert "10–30%" in seq[3]["body"]


def test_enrollment_auto_populates_visible_drafts(denso_workflow):
    client, _, lead_id, contact_id = denso_workflow
    camp = client.post("/campaigns", json={"name": "Solwer Outreach", "mode": "manual", "delays": [2, 4, 7]}).json()
    camp_id = camp["id"]

    enroll = client.post(f"/campaigns/{camp_id}/enrollments", json={
        "lead_id": lead_id, "contact_id": contact_id, "recipient": "vijay@vrl.example"
    })
    assert enroll.status_code == 201

    detail = client.get(f"/campaigns/{camp_id}").json()
    enr = detail["enrollments"][0]
    msgs = enr["messages"]
    assert len(msgs) == 4  # Step 0 + 3 follow-ups

    # Verify drafts are pre-populated and visible right away
    assert msgs[0]["subject"] == "VRL Logistics’s logistics costs"
    assert "Hi Vijay" in msgs[0]["body"]
    assert "Solwer TWMS" in msgs[0]["body"]
    assert msgs[0]["status"] == "draft"

    assert "Re: VRL Logistics’s logistics costs" in msgs[1]["subject"]
    assert "reduce transportation costs" in msgs[1]["body"]


def test_mailbox_analytics_and_sync(denso_workflow, monkeypatch):
    client, factory, lead_id, contact_id = denso_workflow

    with factory.begin() as session:
        # Create a mock reply
        session.add(EmailReply(
            mailbox_uid="uid-test-1",
            sender="vijay@vrl.example",
            subject="Re: VRL Logistics’s logistics costs",
            body="We are interested in Solwer TWMS. Can we schedule a demo call on Thursday at 2 PM?",
            classification="meeting_requested",
        ))

    analytics_resp = client.get("/mailbox/analytics")
    assert analytics_resp.status_code == 200
    data = analytics_resp.json()
    assert data["mailbox_address"] == "tharunjs012003@gmail.com"
    assert data["total_received"] >= 1
    assert data["classification_counts"]["meeting_requested"] == 1
    assert len(data["recent_received"]) >= 1
    assert data["recent_received"][0]["classification"] == "meeting_requested"

    # Test sync endpoint
    sync_resp = client.post("/mailbox/sync")
    assert sync_resp.status_code == 200
    assert sync_resp.json()["success"] is True


def test_direct_outreach_flow_without_campaign(denso_workflow, monkeypatch):
    client, factory, lead_id, contact_id = denso_workflow

    # Upload attachment via standalone upload endpoint
    upload_resp = client.post(
        "/attachments/upload",
        files={"file": ("TWMS_Presentation.pdf", b"%PDF-1.4 sample content", "application/pdf")},
    )
    assert upload_resp.status_code == 201
    att_data = upload_resp.json()
    assert att_data["filename_safe"] == "TWMS_Presentation.pdf"
    assert att_data["id"]

    # Send direct outreach to contact
    direct_resp = client.post(
        f"/leads/{lead_id}/direct-outreach",
        json={
            "contact_ids": [contact_id],
            "subject": "{{company}}’s logistics costs",
            "body": "Hi {{First Name}},\n\nDENSO Solwer TWMS presentation attached.",
            "attachment_ids": [att_data["id"]],
            "send_now": True,
        },
    )
    assert direct_resp.status_code == 200
    res = direct_resp.json()
    assert res["success"] is True
    assert res["count"] == 1
    assert res["dispatched"][0]["recipient"] == "vijay@vrl.example"

    # Verify lead profile includes email with attachment in history
    prof_resp = client.get(f"/leads/{lead_id}/profile")
    assert prof_resp.status_code == 200
    prof = prof_resp.json()
    assert prof["overview"]["email_count"] >= 1
    emails = prof["email_history"]
    assert len(emails) >= 1
    sent_email = emails[0]
    assert "VRL Logistics" in sent_email["subject"]
    assert "Hi Vijay" in sent_email["body"]
    assert len(sent_email["attachments"]) == 1
    assert sent_email["attachments"][0]["filename"] == "TWMS_Presentation.pdf"


def test_bulk_outreach_recipients_and_send(denso_workflow):
    client, factory, lead_id, contact_id = denso_workflow

    # 1. Test GET /outreach/recipients
    rec_resp = client.get("/outreach/recipients")
    assert rec_resp.status_code == 200
    data = rec_resp.json()
    assert data["count"] >= 1
    recipients = data["recipients"]
    assert any(r["email"] == "vijay@vrl.example" for r in recipients)

    # 2. Test POST /outreach/bulk-send
    send_resp = client.post(
        "/outreach/bulk-send",
        json={
            "recipients": [
                {
                    "lead_id": lead_id,
                    "contact_id": contact_id,
                    "email": "vijay@vrl.example",
                    "recipient_name": "Vijay Sankeshwar",
                    "company_name": "VRL Logistics",
                }
            ],
            "subject": "{{company}}'s fleet efficiency",
            "body": "Hi {{First Name}},\n\nCustomized bulk message for {{company}}.",
            "attachment_ids": [],
            "send_now": True,
        },
    )
    assert send_resp.status_code == 200
    send_data = send_resp.json()
    assert send_data["success"] is True
    assert send_data["count"] == 1
    assert send_data["dispatched"][0]["recipient"] == "vijay@vrl.example"


def test_single_email_has_body_and_collateral_together(denso_workflow):
    client, factory, lead_id, contact_id = denso_workflow

    # 1. Upload collateral attachment
    file_bytes = b"%PDF-1.7 DENSO SOLWER TWMS Collateral Document"
    files = {"file": ("Solwer_TWMS_Overview.pdf", file_bytes, "application/pdf")}
    up_resp = client.post("/attachments/upload", files=files)
    assert up_resp.status_code == 201
    att_id = up_resp.json()["id"]

    # 2. Capture the actual MIME message passed to smtplib.send_message
    sent_mimes = []

    class MockSMTP:
        def __init__(self, host, port, timeout=15):
            pass
        def starttls(self, context=None):
            pass
        def login(self, user, pwd):
            pass
        def send_message(self, mime):
            sent_mimes.append(mime)
        def close(self):
            pass

    from app import mailer
    orig_smtp = mailer.smtplib.SMTP
    orig_unsub = mailer.settings.mail_unsubscribe_enabled
    mailer.smtplib.SMTP = MockSMTP
    mailer.settings.mail_unsubscribe_enabled = False
    try:
        send_resp = client.post(
            "/outreach/bulk-send",
            json={
                "recipients": [
                    {
                        "lead_id": lead_id,
                        "contact_id": contact_id,
                        "email": "single_mail_test@vrl.example",
                        "recipient_name": "Vijay Sankeshwar",
                        "company_name": "VRL Logistics",
                    }
                ],
                "subject": "DENSO Solwer TWMS for {{company}}",
                "body": "Hi {{First Name}},\n\nPlease find attached the official Solwer TWMS brief.",
                "attachment_ids": [att_id],
                "send_now": True,
            },
        )
        assert send_resp.status_code == 200
    finally:
        mailer.smtplib.SMTP = orig_smtp
        mailer.settings.mail_unsubscribe_enabled = orig_unsub

    # 3. Verify exactly ONE email was sent, and it contains BOTH the body and the attachment
    assert len(sent_mimes) == 1, f"Expected 1 email sent, but got {len(sent_mimes)}"
    mime = sent_mimes[0]
    assert mime["Subject"] == "DENSO Solwer TWMS for VRL Logistics"
    assert mime["To"] == "single_mail_test@vrl.example"
    assert mime.get_content_type() == "multipart/mixed"

    parts = list(mime.walk())
    part_types = [p.get_content_type() for p in parts]
    assert "text/plain" in part_types
    assert "text/html" in part_types
    assert "application/pdf" in part_types

    # Find the pdf attachment part and check filename
    pdf_part = next(p for p in parts if p.get_content_type() == "application/pdf")
    assert pdf_part.get_filename() == "Solwer_TWMS_Overview.pdf"
    assert pdf_part.get_content_disposition() == "attachment"
    assert pdf_part.get_payload(decode=True) == file_bytes

    # Find the text part and check body
    text_part = next(p for p in parts if p.get_content_type() == "text/plain")
    assert "Please find attached the official Solwer TWMS brief" in text_part.get_content()



