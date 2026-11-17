import base64
import hashlib
from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import google_workspace as google
from app.database import Base, get_db
from app.main import app
from app.models import GoogleOAuthCredential, now


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'google.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    monkeypatch.setattr(google.settings, "google_client_id", "client-id")
    monkeypatch.setattr(google.settings, "google_client_secret", "client-secret")
    monkeypatch.setattr(google.settings, "google_workspace_organizer_email", "organizer@example.com")
    monkeypatch.setattr(google.settings, "google_redirect_uri", "http://localhost:8000/google/oauth/callback")
    monkeypatch.setattr(google.settings, "google_token_encryption_key", Fernet.generate_key().decode())
    with TestClient(app, base_url="http://localhost:8000") as client:
        yield client, factory
    app.dependency_overrides.clear()
    engine.dispose()


def test_oauth_state_pkce_encryption_and_replay(workspace, monkeypatch):
    client, factory = workspace
    start = client.get("/google/oauth/start", follow_redirects=False)
    assert start.status_code == 302
    query = parse_qs(urlsplit(start.headers["location"]).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["access_type"] == ["offline"]
    state = query["state"][0]
    original_cookie = client.cookies.get(google.COOKIE)

    class FakeFlow:
        credentials = SimpleNamespace(refresh_token="secret-refresh-token", id_token="id-token",
                                      granted_scopes=google.SCOPES)
        def fetch_token(self, code):
            assert code == "example-code"

    def fake_flow(state, verifier, booking):
        assert not booking
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        assert query["code_challenge"] == [challenge]
        return FakeFlow()

    monkeypatch.setattr(google, "oauth_flow", fake_flow)
    monkeypatch.setattr(google.id_token, "verify_oauth2_token",
                        lambda *args: {"email": "organizer@example.com", "email_verified": True})
    result = client.get(f"/google/oauth/callback?state={state}&code=example-code", follow_redirects=False)
    assert result.status_code == 303
    with factory() as session:
        credential = session.get(GoogleOAuthCredential, "organizer")
        assert b"secret-refresh-token" not in credential.refresh_token_encrypted
        assert google.cipher().decrypt(credential.refresh_token_encrypted) == b"secret-refresh-token"
    client.cookies.set(google.COOKIE, original_cookie, domain="localhost.local", path="/google/oauth")
    assert client.get(f"/google/oauth/callback?state={state}&code=example-code", follow_redirects=False).status_code == 400


def test_oauth_rejects_wrong_browser_and_organizer(workspace, monkeypatch):
    client, factory = workspace
    start = client.get("/google/oauth/start", follow_redirects=False)
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    original_cookie = client.cookies.get(google.COOKIE)
    client.cookies.set(google.COOKIE, "wrong", domain="localhost.local", path="/google/oauth")
    assert client.get(f"/google/oauth/callback?state={state}&code=x", follow_redirects=False).status_code == 400
    client.cookies.set(google.COOKIE, original_cookie, domain="localhost.local", path="/google/oauth")
    monkeypatch.setattr(google, "oauth_flow", lambda *args: SimpleNamespace(
        fetch_token=lambda **kwargs: None,
        credentials=SimpleNamespace(refresh_token="secret", id_token="id", granted_scopes=google.SCOPES),
    ))
    monkeypatch.setattr(google.id_token, "verify_oauth2_token",
                        lambda *args: {"email": "other@example.com", "email_verified": True})
    assert client.get(f"/google/oauth/callback?state={state}&code=x", follow_redirects=False).status_code == 502
    with factory() as session:
        assert session.get(GoogleOAuthCredential, "organizer") is None


@pytest.mark.parametrize("calendar", [
    {"errors": [{"reason": "notFound"}]},
    [],
    {"busy": [{"start": 10, "end": 20}]},
])
def test_freebusy_errors_do_not_become_free_slots(workspace, monkeypatch, calendar):
    client, _ = workspace
    monkeypatch.setattr(google, "google_access_token", lambda session: "token")
    real_client = httpx.Client
    monkeypatch.setattr(google.httpx, "Client", lambda **kwargs: real_client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
            "calendars": {"organizer@example.com": calendar}
        })), **kwargs))
    start = (now() + timedelta(days=1)).isoformat()
    end = (now() + timedelta(days=2)).isoformat()
    assert client.post("/google/availability", json={"start": start, "end": end}).status_code == 502


def test_availability_excludes_busy_and_obeys_work_hours(workspace, monkeypatch):
    client, _ = workspace
    monkeypatch.setattr(google.settings, "meeting_timezone", "UTC")
    start = (now() + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    while start.weekday() >= 5:
        start += timedelta(days=1)
    busy_start = start + timedelta(minutes=30)
    monkeypatch.setattr(google, "freebusy", lambda session, first, last: [
        (busy_start, busy_start + timedelta(minutes=30))
    ])
    result = client.post("/google/availability", json={"start": start.isoformat(),
                                                       "end": (start + timedelta(hours=2)).isoformat()})
    assert result.status_code == 200
    slots = result.json()["slots"]
    assert len(slots) == 3
    assert all(slot["start"] != busy_start.isoformat() for slot in slots)


def test_refresh_failure_is_reported(workspace, monkeypatch):
    client, factory = workspace
    with factory.begin() as session:
        session.add(GoogleOAuthCredential(
            id="organizer", organizer_email="organizer@example.com",
            refresh_token_encrypted=google.cipher().encrypt(b"refresh"), scopes=google.SCOPES))
    monkeypatch.setattr(google.Credentials, "refresh",
                        lambda *args: (_ for _ in ()).throw(google.GoogleAuthError("revoked")))
    start = now() + timedelta(days=1)
    response = client.post("/google/availability", json={"start": start.isoformat(),
                                                         "end": (start + timedelta(hours=2)).isoformat()})
    assert response.status_code == 502


def test_existing_read_only_connection_requires_reconsent_for_events(workspace):
    client, factory = workspace
    with factory.begin() as session:
        session.add(GoogleOAuthCredential(
            id="organizer", organizer_email="organizer@example.com",
            refresh_token_encrypted=google.cipher().encrypt(b"refresh"),
            scopes=[google.CALENDAR_SCOPE]))
    assert client.get("/google/oauth/status").json()["booking_access"] is False
    with factory() as session:
        with pytest.raises(RuntimeError, match="permission is missing"):
            google.google_access_token(session, google.EVENTS_SCOPE)


@pytest.mark.parametrize("granted,expected", [(True, 303), (False, 502)])
def test_booking_reconsent_does_not_replace_credentials_without_permission(workspace, monkeypatch, granted, expected):
    client, factory = workspace
    with factory.begin() as session:
        session.add(GoogleOAuthCredential(
            id="organizer", organizer_email="organizer@example.com",
            refresh_token_encrypted=google.cipher().encrypt(b"old-refresh"),
            scopes=google.SCOPES))
    start = client.get("/google/oauth/start?booking=true", follow_redirects=False)
    query = parse_qs(urlsplit(start.headers["location"]).query)
    assert google.EVENTS_SCOPE in query["scope"][0].split()
    state = query["state"][0]

    def fake_flow(state, verifier, booking):
        assert booking
        return SimpleNamespace(
            fetch_token=lambda **kwargs: None,
            credentials=SimpleNamespace(refresh_token="new-refresh", id_token="id",
                                        granted_scopes=google.BOOKING_SCOPES if granted else google.SCOPES))

    monkeypatch.setattr(google, "oauth_flow", fake_flow)
    monkeypatch.setattr(google.id_token, "verify_oauth2_token",
                        lambda *args: {"email": "organizer@example.com", "email_verified": True})
    response = client.get(f"/google/oauth/callback?state={state}&code=x", follow_redirects=False)
    assert response.status_code == expected
    with factory() as session:
        credential = session.get(GoogleOAuthCredential, "organizer")
        expected_token = b"new-refresh" if granted else b"old-refresh"
        assert google.cipher().decrypt(credential.refresh_token_encrypted) == expected_token
    assert client.get("/google/oauth/status").json()["booking_access"] is granted
