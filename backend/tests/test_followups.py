from datetime import timedelta
from email.message import EmailMessage as MimeMessage

import pytest
import smtplib
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import mailer
from app.database import Base, get_db
from app import mailbox
from app.mailbox import process_incoming
from app.main import app
from app.models import (Campaign, Contact, EmailEvent, EmailMessage, EmailReply, Enrollment,
                        Lead, MailboxState, Suppression, now)


@pytest.fixture
def workflow(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'followups.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    monkeypatch.setattr(mailer, "SessionLocal", factory)
    monkeypatch.setattr(mailer, "poll_mailbox", lambda session: True)
    monkeypatch.setattr(mailer.settings, "mail_send_enabled", True)
    monkeypatch.setattr(mailer.settings, "mail_unsubscribe_enabled", True)
    monkeypatch.setattr(mailer.settings, "tracking_enabled", False)
    monkeypatch.setattr(mailer.settings, "gmail_address", "sender@gmail.com")
    monkeypatch.setattr(mailer.settings, "gmail_app_password", "test")
    monkeypatch.setattr(mailer.settings, "public_base_url", "https://public.example")
    monkeypatch.setattr(mailer.settings, "daily_send_limit", 50)
    with factory.begin() as session:
        lead = Lead(company_name="Example", company_key="example", extra={})
        session.add(lead)
        session.flush()
        lead_id = lead.id
    with TestClient(app) as client:
        yield client, factory, lead_id
    app.dependency_overrides.clear()
    engine.dispose()


def create_campaign(client, lead_id, mode="manual", delays=None):
    result = client.post("/campaigns", json={"name": "Pilot", "mode": mode, "delays": delays or [3, 4, 5]})
    assert result.status_code == 201
    campaign_id = result.json()["id"]
    result = client.post(f"/campaigns/{campaign_id}/enrollments",
                         json={"lead_id": lead_id, "recipient": "person@example.com"})
    assert result.status_code == 201
    enrollment_id = result.json()["id"]
    detail = client.get(f"/campaigns/{campaign_id}").json()
    return campaign_id, enrollment_id, detail["enrollments"][0]["messages"]


def save_and_approve(client, message_id):
    assert client.put(f"/messages/{message_id}", json={"subject": "Hello", "body": "Hello there."}).status_code == 200
    assert client.post(f"/messages/{message_id}/approve", json={"subject": "Hello", "body": "Hello there."}).status_code == 200


class FakeSMTP:
    sent = []

    def __init__(self, *args, **kwargs):
        pass

    def starttls(self, **kwargs):
        pass

    def login(self, *args):
        pass

    def send_message(self, message):
        self.sent.append(message)

    def close(self):
        pass


def test_approval_and_schedule_after_success(workflow, monkeypatch):
    client, factory, lead_id = workflow
    FakeSMTP.sent = []
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    campaign_id, _, messages = create_campaign(client, lead_id)
    initial, followup = messages[:2]
    client.post(f"/campaigns/{campaign_id}/activate")
    assert not mailer.claim(initial["id"])
    save_and_approve(client, initial["id"])
    assert mailer.claim(initial["id"])
    assert not mailer.claim(initial["id"])
    mailer.send_claimed(initial["id"])
    with factory() as session:
        sent = session.get(EmailMessage, initial["id"])
        next_message = session.get(EmailMessage, followup["id"])
        assert sent.status == "sent"
        assert next_message.due_at - sent.sent_at == timedelta(days=3)
        assert "List-Unsubscribe" in FakeSMTP.sent[0]
    assert len(FakeSMTP.sent) == 1


@pytest.mark.parametrize("tracking_enabled,base_url,tracking_expected", [
    (False, "", False),
    (True, "", False),
    (True, "https://public.example", True),
])
def test_optional_unsubscribe_preserves_sending_and_reports_tracking(
    workflow, monkeypatch, caplog, tracking_enabled, base_url, tracking_expected,
):
    client, factory, lead_id = workflow
    FakeSMTP.sent = []
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(mailer.settings, "mail_unsubscribe_enabled", False)
    monkeypatch.setattr(mailer.settings, "tracking_enabled", tracking_enabled)
    monkeypatch.setattr(mailer.settings, "public_base_url", base_url)
    campaign_id, enrollment_id, messages = create_campaign(client, lead_id)
    message_id = messages[0]["id"]
    body = "See https://example.com/product"
    assert client.put(f"/messages/{message_id}", json={"subject": "Hello", "body": body}).status_code == 200
    link = client.post(f"/messages/{message_id}/tracking-links",
                       json={"destination": "https://example.com/product"}).json()
    assert client.post(f"/messages/{message_id}/approve",
                       json={"subject": "Hello", "body": body}).status_code == 200
    assert client.post(f"/campaigns/{campaign_id}/activate").status_code == 200
    assert mailer.claim(message_id)
    mailer.send_claimed(message_id)
    assert len(FakeSMTP.sent) == 1
    sent = FakeSMTP.sent[0]
    assert "List-Unsubscribe" not in sent
    assert "List-Unsubscribe-Post" not in sent
    assert "To unsubscribe:" not in sent.get_body(preferencelist=("plain",)).get_content()
    assert sent.is_multipart() is tracking_expected
    with factory() as session:
        message = session.get(EmailMessage, message_id)
        assert message.status == "sent"
        assert session.scalar(select(EmailEvent).where(EmailEvent.email_id == message_id)).event_type == "smtp_accepted"
        assert session.get(Enrollment, enrollment_id).unsubscribe_token
        if tracking_expected:
            assert f"https://public.example/public/open/{message.open_token}" in sent.get_body(
                preferencelist=("html",)).get_content()
            assert f"https://public.example/public/r/{link['token']}" in sent.get_body(
                preferencelist=("plain",)).get_content()
        else:
            assert "https://example.com/product" in sent.get_content()
            assert "/public/r/" not in sent.get_content()
    capacity = client.get("/mailbox/capacity").json()
    assert capacity["unsubscribe_enabled"] is False
    assert capacity["tracking_enabled"] is tracking_enabled
    assert capacity["tracking_configured"] is tracking_expected
    if tracking_enabled and not tracking_expected:
        assert "unavailable" in capacity["tracking_note"]
        assert "Sending without tracking pixels or redirects" in caplog.text


def test_required_unsubscribe_still_blocks_sending_without_https(workflow, monkeypatch):
    client, factory, lead_id = workflow
    FakeSMTP.sent = []
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(mailer.settings, "public_base_url", "")
    campaign_id, _, messages = create_campaign(client, lead_id)
    save_and_approve(client, messages[0]["id"])
    client.post(f"/campaigns/{campaign_id}/activate")
    assert mailer.claim(messages[0]["id"])
    mailer.send_claimed(messages[0]["id"])
    assert FakeSMTP.sent == []
    with factory() as session:
        message = session.get(EmailMessage, messages[0]["id"])
        assert message.status == "failed"
        assert "PUBLIC_BASE_URL" in message.last_error


def test_campaign_enrollment_links_only_matching_active_contact(workflow):
    client, factory, lead_id = workflow
    campaign = client.post("/campaigns", json={"name": "Contact outreach", "mode": "manual", "delays": []})
    assert campaign.status_code == 201
    campaign_id = campaign.json()["id"]
    contact = client.post(f"/leads/{lead_id}/contacts", json={
        "name": "Taylor Contact", "email": "person@example.com",
    })
    assert contact.status_code == 201
    contact_id = contact.json()["id"]

    mismatched_email = client.post(f"/campaigns/{campaign_id}/enrollments", json={
        "lead_id": lead_id, "contact_id": contact_id, "recipient": "other@example.com",
    })
    assert mismatched_email.status_code == 409

    with factory.begin() as session:
        other_lead = Lead(company_name="Other", company_key="other", extra={})
        session.add(other_lead)
        session.flush()
        other_contact = Contact(lead_id=other_lead.id, name="Other Contact", email="other@example.com")
        session.add(other_contact)
        session.flush()
        other_contact_id = other_contact.id
    mismatched_lead = client.post(f"/campaigns/{campaign_id}/enrollments", json={
        "lead_id": lead_id, "contact_id": other_contact_id, "recipient": "other@example.com",
    })
    assert mismatched_lead.status_code == 409

    enrolled = client.post(f"/campaigns/{campaign_id}/enrollments", json={
        "lead_id": lead_id, "contact_id": contact_id, "recipient": "person@example.com",
    })
    assert enrolled.status_code == 201
    assert client.delete(f"/leads/{lead_id}/contacts/{contact_id}").status_code == 204
    enrollment = client.get(f"/campaigns/{campaign_id}").json()["enrollments"][0]
    assert enrollment["contact_id"] == contact_id
    assert enrollment["contact_name"] == "Taylor Contact"
    email_history = client.get(f"/leads/{lead_id}/profile").json()["email_history"]
    assert email_history[0]["contact_id"] == contact_id
    assert email_history[0]["contact_name"] == "Taylor Contact"


def test_bulk_recipients_have_independent_threads_and_approval(workflow, monkeypatch):
    client, factory, lead_id = workflow
    campaign_id = client.post("/campaigns", json={"name": "People", "delays": []}).json()["id"]
    contact_id = client.post(f"/leads/{lead_id}/contacts", json={
        "name": "First Person", "email": "first@example.com",
    }).json()["id"]
    result = client.post(f"/campaigns/{campaign_id}/enrollments/bulk", json={"recipients": [
        {"lead_id": lead_id, "contact_id": contact_id, "recipient": "first@example.com"},
        {"lead_id": lead_id, "recipient": "second@example.com"},
    ]})
    assert result.status_code == 201
    assert result.json()["added"] == 2
    enrollments = client.get(f"/campaigns/{campaign_id}").json()["enrollments"]
    first = next(item for item in enrollments if item["contact_id"] == contact_id)
    second = next(item for item in enrollments if item["id"] != first["id"])
    assert first["messages"][0]["id"] != second["messages"][0]["id"]
    with factory() as session:
        assert session.get(Enrollment, first["id"]).unsubscribe_token != session.get(
            Enrollment, second["id"]).unsubscribe_token
    save_and_approve(client, first["messages"][0]["id"])
    assert client.post(f"/campaigns/{campaign_id}/activate").status_code == 200
    FakeSMTP.sent = []
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    assert not mailer.claim(second["messages"][0]["id"])
    assert mailer.claim(first["messages"][0]["id"])
    mailer.send_claimed(first["messages"][0]["id"])
    assert len(FakeSMTP.sent) == 1
    assert FakeSMTP.sent[0]["To"] == "first@example.com"
    assert FakeSMTP.sent[0]["Cc"] is None


@pytest.mark.parametrize("reason", ["duplicate", "suppressed", "invalid", "contact-mismatch", "already-enrolled"])
def test_bulk_enrollment_rejects_whole_batch(workflow, reason):
    client, factory, lead_id = workflow
    campaign_id = client.post("/campaigns", json={"name": "Atomic", "delays": []}).json()["id"]
    invalid = {"lead_id": lead_id, "recipient": "second@example.com"}
    expected_count = 0
    if reason == "duplicate":
        invalid["recipient"] = "FIRST@example.com"
    elif reason == "invalid":
        invalid["recipient"] = "not-an-email"
    elif reason == "suppressed":
        with factory.begin() as session:
            session.add(Suppression(email="second@example.com", reason="unsubscribe"))
    elif reason == "contact-mismatch":
        contact_id = client.post(f"/leads/{lead_id}/contacts", json={
            "name": "Other Person", "email": "other@example.com",
        }).json()["id"]
        invalid["contact_id"] = contact_id
    else:
        assert client.post(f"/campaigns/{campaign_id}/enrollments", json=invalid).status_code == 201
        expected_count = 1
    result = client.post(f"/campaigns/{campaign_id}/enrollments/bulk", json={"recipients": [
        {"lead_id": lead_id, "recipient": "first@example.com"}, invalid,
    ]})
    assert result.status_code in {400, 409}
    enrollments = client.get(f"/campaigns/{campaign_id}").json()["enrollments"]
    assert len(enrollments) == expected_count
    assert all(item["recipient"] != "first@example.com" for item in enrollments)


def test_generated_drafts_can_be_reviewed_and_approved_and_failure_preserves_them(workflow, monkeypatch):
    client, factory, lead_id = workflow
    _, enrollment_id, messages = create_campaign(client, lead_id)
    monkeypatch.setattr("app.followup_api.bedrock.generate_sequence", lambda company, context, count, **kwargs: [
        {"subject": "Approved context", "body": "A factual introduction."} for _ in range(count)
    ])
    result = client.post(f"/enrollments/{enrollment_id}/generate", json={"context": "Approved facts"})
    assert result.status_code == 200
    first = result.json()[0]
    assert first["status"] == "draft"
    assert first["approved_at"] is None
    assert client.post(f"/messages/{first['id']}/approve", json={
        "subject": first["subject"], "body": first["body"],
    }).status_code == 200

    def fail(*args, **kwargs):
        raise RuntimeError("Bedrock AccessDeniedException: Check model access.")

    monkeypatch.setattr("app.followup_api.bedrock.generate_sequence", fail)
    result = client.post(f"/enrollments/{enrollment_id}/generate", json={"context": "Approved facts"})
    assert result.status_code == 502
    assert "AccessDeniedException" in result.json()["detail"]
    with factory() as session:
        saved = session.get(EmailMessage, messages[0]["id"])
        assert saved.status == "approved"
        assert saved.subject == first["subject"]
        assert saved.body == first["body"]


def test_campaign_analytics_use_unique_recipient_denominators(workflow):
    client, factory, lead_id = workflow
    campaign_id, enrollment_id, messages = create_campaign(client, lead_id)
    second = client.post(f"/campaigns/{campaign_id}/enrollments", json={
        "lead_id": lead_id, "recipient": "second@example.com",
    })
    assert second.status_code == 201
    with factory.begin() as session:
        sent = session.get(EmailMessage, messages[0]["id"])
        sent.status = "sent"
        session.add(EmailEvent(email_id=sent.id, event_type="smtp_accepted"))
        session.add_all([
            EmailEvent(email_id=sent.id, event_type="open"),
            EmailEvent(email_id=sent.id, event_type="open"),
            EmailEvent(email_id=sent.id, event_type="click"),
        ])
        session.add(EmailReply(
            mailbox_uid="analytics-reply", enrollment_id=enrollment_id,
            sender="person@example.com", body="Interested.",
        ))

    result = client.get(f"/campaigns/{campaign_id}/analytics")
    assert result.status_code == 200
    analytics = result.json()
    assert analytics["recipient_count"] == 2
    assert analytics["accepted_recipient_count"] == 1
    assert analytics["accepted_email_count"] == 1
    assert analytics["replied_recipient_count"] == 1
    assert analytics["opened_recipient_count"] == 1
    assert analytics["clicked_recipient_count"] == 1
    assert analytics["reply_rate_percent"] == 100
    assert "not delivery" in analytics["engagement_note"]


def test_mailbox_capacity_reports_configured_rolling_budget(workflow):
    client, factory, lead_id = workflow
    _, _, messages = create_campaign(client, lead_id)
    with factory.begin() as session:
        message = session.get(EmailMessage, messages[0]["id"])
        message.status = "unknown"
        message.attempted_at = now()
    capacity = client.get("/mailbox/capacity")
    assert capacity.status_code == 200
    assert capacity.json()["configured_limit"] == 50
    assert capacity.json()["attempts_counted"] == 1
    assert capacity.json()["remaining_application_budget"] == 49
    assert capacity.json()["window_hours"] == 24
    assert "separate account quotas" in capacity.json()["note"]


def test_automatic_sequence_requires_approval_and_edits_invalidate_it(workflow):
    client, _, lead_id = workflow
    campaign_id, _, messages = create_campaign(client, lead_id, "automatic")
    assert client.post(f"/campaigns/{campaign_id}/activate").status_code == 409
    for message in messages:
        assert client.put(f"/messages/{message['id']}", json={"subject": "Hi", "body": "Hello"}).status_code == 200
    sequence = [{"id": message["id"], "subject": "Hi", "body": "Hello"} for message in messages[1:]]
    assert client.post(f"/campaigns/{campaign_id}/approve-sequence", json={"messages": sequence}).status_code == 200
    assert client.post(f"/campaigns/{campaign_id}/activate").status_code == 200
    assert client.put(f"/messages/{messages[1]['id']}", json={"subject": "Changed", "body": "Hello"}).status_code == 200
    assert client.get(f"/campaigns/{campaign_id}").json()["sequence_approved_at"] is None
    assert client.get(f"/campaigns/{campaign_id}").json()["enrollments"][0]["messages"][0]["status"] == "draft"


@pytest.mark.parametrize("unsubscribe_enabled", [True, False])
def test_unsubscribe_and_reply_block_further_sending(workflow, monkeypatch, unsubscribe_enabled):
    client, factory, lead_id = workflow
    FakeSMTP.sent = []
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(mailer.settings, "mail_unsubscribe_enabled", unsubscribe_enabled)
    campaign_id, enrollment_id, messages = create_campaign(client, lead_id)
    save_and_approve(client, messages[0]["id"])
    client.post(f"/campaigns/{campaign_id}/activate")
    assert mailer.claim(messages[0]["id"])
    mailer.send_claimed(messages[0]["id"])
    incoming = MimeMessage()
    incoming["From"] = "person@example.com"
    incoming["In-Reply-To"] = messages[0]["message_id"]
    incoming["Subject"] = "Re: Hello"
    incoming.set_content("Please unsubscribe me.")
    with factory.begin() as session:
        process_incoming(session, incoming.as_bytes(), "uid-1")
        process_incoming(session, incoming.as_bytes(), "uid-1")
    with factory() as session:
        assert session.get(Enrollment, enrollment_id).reply_blocked
        assert session.get(Suppression, "person@example.com").reason == "unsubscribe"
        assert len(session.scalars(select(EmailReply)).all()) == 1
    assert client.post(f"/enrollments/{enrollment_id}/resume").status_code == 409


def test_unknown_smtp_result_is_never_claimed_again(workflow, monkeypatch):
    client, factory, lead_id = workflow

    class Disconnected(FakeSMTP):
        def send_message(self, message):
            raise smtplib.SMTPServerDisconnected("connection lost after DATA")

    monkeypatch.setattr(mailer.smtplib, "SMTP", Disconnected)
    campaign_id, _, messages = create_campaign(client, lead_id)
    save_and_approve(client, messages[0]["id"])
    client.post(f"/campaigns/{campaign_id}/activate")
    assert mailer.claim(messages[0]["id"])
    mailer.send_claimed(messages[0]["id"])
    assert not mailer.claim(messages[0]["id"])
    with factory() as session:
        assert session.get(EmailMessage, messages[0]["id"]).status == "unknown"
    assert client.post(f"/messages/{messages[0]['id']}/approve", json={"subject": "Hello", "body": "Hello there."}).status_code == 409


def test_public_unsubscribe_requires_post_and_blocks_resume(workflow):
    client, factory, lead_id = workflow
    _, enrollment_id, _ = create_campaign(client, lead_id)
    with factory() as session:
        token = session.get(Enrollment, enrollment_id).unsubscribe_token
    assert client.get(f"/public/unsubscribe/{token}").status_code == 200
    with factory() as session:
        assert session.get(Suppression, "person@example.com") is None
    assert client.post(f"/public/unsubscribe/{token}").status_code == 200
    assert client.post(f"/enrollments/{enrollment_id}/resume").status_code == 409


def test_stale_approval_is_rejected(workflow):
    client, _, lead_id = workflow
    campaign_id, _, messages = create_campaign(client, lead_id, "automatic")
    for message in messages:
        client.put(f"/messages/{message['id']}", json={"subject": "Current", "body": "Hello"})
    assert client.post(f"/messages/{messages[0]['id']}/approve",
                       json={"subject": "Old", "body": "Hello"}).status_code == 409
    sequence = [{"id": message["id"], "subject": "Current", "body": "Hello"} for message in messages[1:]]
    sequence[0]["body"] = "Outdated"
    assert client.post(f"/campaigns/{campaign_id}/approve-sequence", json={"messages": sequence}).status_code == 409


@pytest.mark.parametrize("unsubscribe_enabled", [True, False])
def test_unsynchronized_mailbox_prevents_send(workflow, monkeypatch, unsubscribe_enabled):
    client, factory, lead_id = workflow
    FakeSMTP.sent = []
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(mailer.settings, "mail_unsubscribe_enabled", unsubscribe_enabled)
    monkeypatch.setattr(mailer, "poll_mailbox", lambda session: False)
    campaign_id, _, messages = create_campaign(client, lead_id)
    save_and_approve(client, messages[0]["id"])
    client.post(f"/campaigns/{campaign_id}/activate")
    assert mailer.claim(messages[0]["id"])
    mailer.send_claimed(messages[0]["id"])
    assert not FakeSMTP.sent
    with factory() as session:
        message = session.get(EmailMessage, messages[0]["id"])
        assert message.status == "approved"
        assert "sync" in message.last_error


@pytest.mark.parametrize("unsubscribe_enabled", [True, False])
def test_suppression_between_approval_and_send_blocks_delivery(workflow, monkeypatch, unsubscribe_enabled):
    client, factory, lead_id = workflow
    FakeSMTP.sent = []
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(mailer.settings, "mail_unsubscribe_enabled", unsubscribe_enabled)
    campaign_id, _, messages = create_campaign(client, lead_id)
    save_and_approve(client, messages[0]["id"])
    client.post(f"/campaigns/{campaign_id}/activate")
    assert mailer.claim(messages[0]["id"])
    client.post("/suppressions", json={"email": "person@example.com", "reason": "unsubscribe"})
    mailer.send_claimed(messages[0]["id"])
    assert not FakeSMTP.sent
    with factory() as session:
        assert session.get(EmailMessage, messages[0]["id"]).status == "approved"


def test_inbox_backlog_advances_without_marking_it_synchronized(workflow, monkeypatch):
    _, factory, _ = workflow
    message = MimeMessage()
    message["From"] = "unrelated@example.com"
    message.set_content("Not related to a campaign.")

    class FakeIMAP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def login(self, *args): pass
        def select(self, *args, **kwargs): return "OK", []
        def response(self, *args): return "UIDVALIDITY", [b"123"]
        def uid(self, operation, *args):
            if operation == "search":
                return "OK", [" ".join(str(i) for i in range(1, 102)).encode()]
            return "OK", [(b"message", message.as_bytes())]

    monkeypatch.setattr(mailbox.imaplib, "IMAP4_SSL", FakeIMAP)
    with factory.begin() as session:
        assert mailbox.poll_mailbox(session) is False
    with factory() as session:
        assert session.get(MailboxState, 1).last_uid == 100
        assert session.get(MailboxState, 1).last_success_at is None
        assert session.scalars(select(EmailReply)).all() == []
    with factory.begin() as session:
        assert mailbox.poll_mailbox(session) is True
    with factory() as session:
        assert session.get(MailboxState, 1).last_uid == 101
        assert session.get(MailboxState, 1).last_success_at is not None


def test_inbox_connection_timeout_reports_network_blocker(workflow, monkeypatch):
    _, factory, _ = workflow

    def timeout(*args, **kwargs):
        raise TimeoutError("private connection details")

    monkeypatch.setattr(mailbox.imaplib, "IMAP4_SSL", timeout)
    with factory.begin() as session:
        with pytest.raises(RuntimeError, match="network/firewall access to imap.gmail.com:993") as error:
            mailbox.poll_mailbox(session)
    assert "private connection details" not in str(error.value)


def test_tracking_is_opt_in_and_link_changes_revoke_approval(workflow, monkeypatch):
    client, factory, lead_id = workflow
    campaign_id, _, messages = create_campaign(client, lead_id)
    message_id = messages[0]["id"]
    body = "See https://example.com/product"
    client.put(f"/messages/{message_id}", json={"subject": "Hello", "body": body})
    client.post(f"/messages/{message_id}/approve", json={"subject": "Hello", "body": body})
    result = client.post(f"/messages/{message_id}/tracking-links",
                         json={"destination": "https://example.com/product"})
    assert result.status_code == 200
    token = result.json()["token"]
    assert client.get(f"/public/r/{token}", follow_redirects=False).status_code == 404
    with factory.begin() as session:
        message = session.get(EmailMessage, message_id)
        assert message.status == "draft"
        message.status = "sent"
    monkeypatch.setattr(mailer.settings, "tracking_enabled", True)
    response = client.get(f"/public/r/{token}", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "https://example.com/product"


def test_hard_bounce_suppresses_recipient(workflow):
    client, factory, lead_id = workflow
    _, enrollment_id, messages = create_campaign(client, lead_id)
    original_id = messages[0]["message_id"]
    raw = (
        "From: MAILER-DAEMON@example.net\r\n"
        "Subject: Delivery Status Notification\r\n"
        'Content-Type: multipart/report; report-type=delivery-status; boundary="b"\r\n'
        "\r\n--b\r\nContent-Type: text/plain\r\n\r\nDelivery failed.\r\n"
        "--b\r\nContent-Type: message/delivery-status\r\n\r\n"
        "Reporting-MTA: dns; example.net\r\n\r\n"
        "Final-Recipient: rfc822; person@example.com\r\n"
        "Action: failed\r\nStatus: 5.1.1\r\n\r\n"
        "--b\r\nContent-Type: message/rfc822\r\n\r\n"
        f"Message-ID: {original_id}\r\n"
        "To: person@example.com\r\n\r\nHello\r\n--b--\r\n"
    ).encode()
    with factory.begin() as session:
        process_incoming(session, raw, "bounce-1")
    with factory() as session:
        assert session.get(Suppression, "person@example.com").reason == "hard_bounce"
        assert session.get(Enrollment, enrollment_id).reply_blocked
        assert session.scalar(select(EmailReply)).classification == "hard_bounce"


def test_rejected_email_requires_edit_before_approval(workflow):
    client, _, lead_id = workflow
    _, _, messages = create_campaign(client, lead_id)
    message_id = messages[0]["id"]
    save_and_approve(client, message_id)
    assert client.post(f"/messages/{message_id}/reject").status_code == 200
    assert client.post(f"/messages/{message_id}/approve",
                       json={"subject": "Hello", "body": "Hello there."}).status_code == 409
    assert client.put(f"/messages/{message_id}", json={"subject": "Revised", "body": "Hello"}).status_code == 200
    assert client.post(f"/messages/{message_id}/approve",
                       json={"subject": "Revised", "body": "Hello"}).status_code == 200


def test_automatic_followup_checks_sequence_and_preserves_thread(workflow, monkeypatch):
    client, factory, lead_id = workflow
    FakeSMTP.sent = []
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    campaign_id, _, messages = create_campaign(client, lead_id, "automatic")
    for message in messages:
        client.put(f"/messages/{message['id']}", json={"subject": "Hello", "body": "Content"})
    client.post(f"/messages/{messages[0]['id']}/approve", json={"subject": "Hello", "body": "Content"})
    sequence = [{"id": message["id"], "subject": "Hello", "body": "Content"} for message in messages[1:]]
    client.post(f"/campaigns/{campaign_id}/approve-sequence", json={"messages": sequence})
    client.post(f"/campaigns/{campaign_id}/activate")
    assert mailer.claim(messages[0]["id"])
    mailer.send_claimed(messages[0]["id"])
    with factory.begin() as session:
        session.get(EmailMessage, messages[1]["id"]).due_at = now() - timedelta(seconds=1)
        session.get(Campaign, campaign_id).sequence_approved_at = None
    assert mailer.claim(messages[1]["id"])
    mailer.send_claimed(messages[1]["id"])
    assert len(FakeSMTP.sent) == 1
    client.post(f"/campaigns/{campaign_id}/approve-sequence", json={"messages": sequence})
    assert mailer.claim(messages[1]["id"])
    mailer.send_claimed(messages[1]["id"])
    assert len(FakeSMTP.sent) == 2
    assert FakeSMTP.sent[1]["In-Reply-To"] == messages[0]["message_id"]
    with factory() as session:
        second = session.get(EmailMessage, messages[1]["id"])
        third = session.get(EmailMessage, messages[2]["id"])
        assert third.due_at - second.sent_at == timedelta(days=4)


def test_initial_draft_change_invalidates_followup_approvals(workflow):
    client, _, lead_id = workflow
    campaign_id, _, messages = create_campaign(client, lead_id, "automatic")
    for message in messages:
        client.put(f"/messages/{message['id']}", json={"subject": "Original", "body": "Hello"})
    sequence = [{"id": message["id"], "subject": "Original", "body": "Hello"} for message in messages[1:]]
    assert client.post(f"/campaigns/{campaign_id}/approve-sequence", json={"messages": sequence}).status_code == 200
    client.put(f"/messages/{messages[0]['id']}", json={"subject": "Revised", "body": "Hello"})
    detail = client.get(f"/campaigns/{campaign_id}").json()
    assert detail["sequence_approved_at"] is None
    assert all(message["status"] == "draft" for message in detail["enrollments"][0]["messages"][1:])


def test_daily_limit_prevents_second_send(workflow, monkeypatch):
    client, factory, lead_id = workflow
    FakeSMTP.sent = []
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(mailer.settings, "daily_send_limit", 1)
    campaign_id, _, messages = create_campaign(client, lead_id)
    save_and_approve(client, messages[0]["id"])
    save_and_approve(client, messages[1]["id"])
    client.post(f"/campaigns/{campaign_id}/activate")
    assert mailer.claim(messages[0]["id"])
    mailer.send_claimed(messages[0]["id"])
    with factory.begin() as session:
        session.get(EmailMessage, messages[1]["id"]).due_at = now() - timedelta(seconds=1)
    assert mailer.claim(messages[1]["id"])
    mailer.send_claimed(messages[1]["id"])
    assert len(FakeSMTP.sent) == 1
    with factory() as session:
        assert "limit" in session.get(EmailMessage, messages[1]["id"]).last_error


def test_generation_does_not_overwrite_concurrent_edits(workflow, monkeypatch):
    client, factory, lead_id = workflow
    _, enrollment_id, messages = create_campaign(client, lead_id)

    def generate(company, context, count, **kwargs):
        with factory.begin() as session:
            session.get(EmailMessage, messages[0]["id"]).subject = "Sales edit"
        return [{"subject": "AI", "body": "AI content"} for _ in range(count)]

    monkeypatch.setattr("app.followup_api.bedrock.generate_sequence", generate)
    response = client.post(f"/enrollments/{enrollment_id}/generate", json={"context": "Approved facts"})
    assert response.status_code == 409
    with factory() as session:
        assert session.get(EmailMessage, messages[0]["id"]).subject == "Sales edit"


def test_meeting_classification_creates_one_sales_task_and_suggests_draft(workflow, monkeypatch):
    client, factory, lead_id = workflow
    _, enrollment_id, messages = create_campaign(client, lead_id)
    with factory.begin() as session:
        reply = EmailReply(mailbox_uid="meeting-uid", enrollment_id=enrollment_id,
                           original_email_id=messages[0]["id"], sender="person@example.com",
                           subject="Meeting", body="Can we meet?")
        session.add(reply)
        session.flush()
        reply_id = reply.id
    monkeypatch.setattr("app.followup_api.bedrock.classify_reply", lambda body: "meeting_requested")
    monkeypatch.setattr("app.followup_api.bedrock.suggest_response",
                        lambda body, subject, original: {"subject": "Re: Meeting", "body": "Let's discuss."})
    assert client.post(f"/replies/{reply_id}/classify").status_code == 200
    assert client.post(f"/replies/{reply_id}/classify").status_code == 200
    tasks = client.get("/sales-tasks").json()
    assert len(tasks) == 1
    assert tasks[0]["status"] == "open"
    assert client.post(f"/replies/{reply_id}/suggest-response").json()["body"] == "Let's discuss."
    assert client.post(f"/sales-tasks/{tasks[0]['id']}/complete").status_code == 200
    assert client.get("/sales-tasks").json()[0]["status"] == "completed"
