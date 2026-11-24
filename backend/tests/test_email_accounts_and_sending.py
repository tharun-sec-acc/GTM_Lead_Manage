import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.auth.models import Organization, User, OrganizationMember, OAuthConnection
from app.auth.security import hash_password, encrypt_token, create_access_token


@pytest.fixture
def email_system(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'email_test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override

    with factory.begin() as session:
        # Create Org 1 & User 1
        org1 = Organization(id="org-1", name="Alpha Corp", slug="alpha-corp", plan="pro")
        user1 = User(id="user-1", email="alice@alpha.com", full_name="Alice Alpha", hashed_password=hash_password("Pass123!"))
        member1 = OrganizationMember(organization_id="org-1", user_id="user-1", role="owner")
        session.add_all([org1, user1, member1])

        # Create Org 2 & User 2
        org2 = Organization(id="org-2", name="Beta Corp", slug="beta-corp", plan="pro")
        user2 = User(id="user-2", email="bob@beta.com", full_name="Bob Beta", hashed_password=hash_password("Pass123!"))
        member2 = OrganizationMember(organization_id="org-2", user_id="user-2", role="owner")
        session.add_all([org2, user2, member2])

        # Org 1 Gmail Connection
        conn1 = OAuthConnection(
            id="conn-google-1",
            organization_id="org-1",
            user_id="user-1",
            provider="google",
            account_email="alice@alpha.com",
            refresh_token_encrypted=encrypt_token("fake-refresh-token"),
            scopes=["https://www.googleapis.com/auth/gmail.send"],
            status="connected",
            connection_metadata={"is_default": True},
        )
        session.add(conn1)

        # Org 2 Outlook Connection
        conn2 = OAuthConnection(
            id="conn-ms-2",
            organization_id="org-2",
            user_id="user-2",
            provider="microsoft",
            account_email="bob@beta.com",
            refresh_token_encrypted=encrypt_token("fake-refresh-token-2"),
            scopes=["Mail.Send"],
            status="connected",
            connection_metadata={"is_default": True},
        )
        session.add(conn2)

    client = TestClient(app)
    token1, _, _ = create_access_token(user_id="user-1", org_id="org-1", role="owner")
    token2, _, _ = create_access_token(user_id="user-2", org_id="org-2", role="owner")

    yield client, factory, token1, token2

    app.dependency_overrides.clear()
    engine.dispose()


def test_list_email_accounts_tenant_isolation(email_system):
    client, _, token1, token2 = email_system

    # User 1 should only see Alice's Gmail
    res1 = client.get("/api/email-accounts", headers={"Authorization": f"Bearer {token1}"})
    assert res1.status_code == 200
    data1 = res1.json()
    assert len(data1) == 1
    assert data1[0]["account_email"] == "alice@alpha.com"
    assert data1[0]["provider"] == "google"
    assert data1[0]["is_default"] is True

    # User 2 should only see Bob's Outlook
    res2 = client.get("/api/email-accounts", headers={"Authorization": f"Bearer {token2}"})
    assert res2.status_code == 200
    data2 = res2.json()
    assert len(data2) == 1
    assert data2[0]["account_email"] == "bob@beta.com"
    assert data2[0]["provider"] == "microsoft"


def test_email_account_default_and_disconnect(email_system):
    client, factory, token1, _ = email_system

    # Disconnect account
    res = client.post("/api/email-accounts/conn-google-1/disconnect", headers={"Authorization": f"Bearer {token1}"})
    assert res.status_code == 200

    # Verify status is disconnected
    with factory() as session:
        conn = session.get(OAuthConnection, "conn-google-1")
        assert conn.status == "disconnected"


def test_cross_tenant_email_sending_prevention(email_system):
    client, _, token1, token2 = email_system

    # User 1 attempts to send email using User 2's connection ID -> 404
    payload = {
        "account_id": "conn-ms-2",
        "recipient": "customer@example.com",
        "subject": "Hello",
        "body_html": "<p>Hi</p>",
    }
    res = client.post("/api/email-accounts/send", json=payload, headers={"Authorization": f"Bearer {token1}"})
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_direct_email_send_via_mocked_provider(email_system, monkeypatch):
    client, _, token1, _ = email_system
    from app import email_sender

    # Mock Gmail API send
    monkeypatch.setattr(
        email_sender,
        "send_email_via_gmail",
        lambda **kwargs: {"provider": "google", "message_id": "msg-12345", "from_email": "alice@alpha.com", "to_email": kwargs["recipient"]},
    )

    payload = {
        "recipient": "customer@example.com",
        "subject": "New Proposition",
        "body_html": "<p>Hello customer</p>",
        "cc": ["manager@alpha.com"],
    }
    res = client.post("/api/email-accounts/send", json=payload, headers={"Authorization": f"Bearer {token1}"})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["provider"] == "google"
    assert data["sender_email"] == "alice@alpha.com"
    assert data["message_id"] == "msg-12345"


def test_email_account_manual_sync(email_system, monkeypatch):
    client, factory, token1, token2 = email_system
    from app.email_provider import GmailAPIProvider

    monkeypatch.setattr(
        GmailAPIProvider,
        "sync_inbox",
        lambda self, session, max_messages=50: {"synced_count": 12, "matched_replies": 3, "provider": "google"},
    )

    # User 1 syncs their own connected Gmail account
    res = client.post("/api/email-accounts/conn-google-1/sync", headers={"Authorization": f"Bearer {token1}"})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["synced_count"] == 12
    assert data["matched_replies"] == 3

    # Cross-tenant check: User 2 cannot sync User 1's account -> 404
    res_cross = client.post("/api/email-accounts/conn-google-1/sync", headers={"Authorization": f"Bearer {token2}"})
    assert res_cross.status_code == 404


def test_oauth_campaign_dispatch(email_system, monkeypatch):
    _, factory, _, _ = email_system
    from app.mailer import send_claimed
    from app.models import Campaign, Enrollment, EmailMessage, EmailEvent, Lead
    from app.email_provider import GmailAPIProvider

    # Mock provider inbox sync and send
    monkeypatch.setattr(
        GmailAPIProvider,
        "sync_inbox",
        lambda self, session, max_messages=25: {"synced_count": 0, "matched_replies": 0},
    )
    monkeypatch.setattr(
        GmailAPIProvider,
        "send_email",
        lambda self, session, recipient, subject, body_html, **kwargs: {
            "provider": "google",
            "message_id": "oauth-msg-999",
            "from_email": "alice@alpha.com",
            "to_email": recipient,
        },
    )

    # Enable mail sending and wire SessionLocal
    from app.config import settings
    monkeypatch.setattr(settings, "mail_send_enabled", True)
    monkeypatch.setattr("app.mailer.SessionLocal", factory)

    with factory.begin() as session:
        lead = Lead(id="lead-test-1", organization_id="org-1", company_name="Target Corp", company_key="target_corp")
        campaign = Campaign(id="camp-test-1", organization_id="org-1", name="Alpha Outreach", mode="manual", delays=[2], status="active")
        enrollment = Enrollment(
            id="enr-test-1",
            lead_id="lead-test-1",
            campaign_id="camp-test-1",
            recipient="target@example.com",
            status="active",
            unsubscribe_token="unsub-token-claim-1",
        )
        message = EmailMessage(
            id="msg-claim-1",
            enrollment_id="enr-test-1",
            step_number=0,
            subject="Intro to Alpha",
            body="Hello Target Corp",
            status="sending",
            message_id="<msg-claim-1@alpha.com>",
            open_token="open-token-claim-1",
            approved_at=datetime.now(timezone.utc),
        )
        session.add_all([lead, campaign, enrollment, message])

    # Run dispatch
    send_claimed("msg-claim-1")

    with factory() as session:
        msg = session.get(EmailMessage, "msg-claim-1")
        assert msg.status == "sent"
        event = session.scalar(select(EmailEvent).where(EmailEvent.email_id == "msg-claim-1"))
        assert event is not None
        assert event.event_type == "google_accepted"


def test_celery_sync_connected_mailboxes_task(email_system, monkeypatch):
    _, factory, _, _ = email_system
    from app.tasks import sync_single_connected_mailbox
    from app.email_provider import GmailAPIProvider
    from app import tasks

    monkeypatch.setattr(tasks, "SessionLocal", factory)
    monkeypatch.setattr(
        GmailAPIProvider,
        "sync_inbox",
        lambda self, session, max_messages=25: {"synced_count": 4, "matched_replies": 1, "provider": "google"},
    )

    res = sync_single_connected_mailbox("conn-google-1")
    assert res is not None
    assert res.get("synced_count") == 4
    assert res.get("matched_replies") == 1

