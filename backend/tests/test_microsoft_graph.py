from datetime import timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import microsoft_graph as microsoft
from app.database import Base, get_db
from app.main import app
from app.models import MicrosoftOAuthCredential, MicrosoftOAuthState, now


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'microsoft.db'}",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    tenant_id = str(uuid4())
    monkeypatch.setattr(microsoft.settings, "microsoft_tenant_id", tenant_id)
    monkeypatch.setattr(microsoft.settings, "microsoft_client_id", "client-id")
    monkeypatch.setattr(microsoft.settings, "microsoft_client_secret", "client-secret")
    monkeypatch.setattr(microsoft.settings, "microsoft_redirect_uri",
                        "http://localhost:8000/microsoft/oauth/callback")
    monkeypatch.setattr(microsoft.settings, "microsoft_organizer_email", "organizer@example.com")
    monkeypatch.setattr(microsoft.settings, "microsoft_token_encryption_key",
                        Fernet.generate_key().decode())
    monkeypatch.setattr(microsoft.settings, "microsoft_graph_base_url",
                        "https://graph.microsoft.com/v1.0")
    with TestClient(app, base_url="http://localhost:8000") as test_client:
        yield test_client, factory, tenant_id
    app.dependency_overrides.clear()
    engine.dispose()


class FakeTokenCache:
    has_state_changed = True

    def serialize(self):
        return '{"token":"cached"}'

    def deserialize(self, value):
        assert value == '{"token":"cached"}'


class FakeApplication:
    def __init__(self, cache):
        self.cache = cache

    def initiate_auth_code_flow(self, **kwargs):
        return {"auth_uri": "https://login.example/authorize?state=state-123",
                "state": "state-123", "scopes": kwargs["scopes"]}

    def acquire_token_by_auth_code_flow(self, flow, response):
        assert flow["state"] == response["state"] == "state-123"
        self.cache.has_state_changed = True
        return {
            "access_token": "mock-access-token",
            "id_token_claims": {"tid": self.tenant_id, "oid": "organizer-object-id"},
            "scope": ["User.Read", "Calendars.ReadBasic"],
        }


def install_fake_application(monkeypatch, tenant_id):
    def factory(cache=None):
        result = FakeApplication(cache)
        result.tenant_id = tenant_id
        return result
    monkeypatch.setattr(microsoft, "client", factory)
    monkeypatch.setattr(microsoft.msal, "SerializableTokenCache", FakeTokenCache)


def test_oauth_flow_encryption_identity_and_replay(workspace, monkeypatch):
    client, factory, tenant_id = workspace
    install_fake_application(monkeypatch, tenant_id)
    monkeypatch.setattr(microsoft, "graph_request", lambda *args, **kwargs: {
        "mail": "organizer@example.com", "userPrincipalName": "organizer@example.com",
    })

    start = client.get("/microsoft/oauth/start", follow_redirects=False)
    assert start.status_code == 302
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    original_cookie = client.cookies.get(microsoft.COOKIE)
    with factory() as session:
        record = session.get(MicrosoftOAuthState, microsoft.digest(state))
        assert record is not None
        assert b"state-123" not in record.auth_flow_encrypted
        assert microsoft.cipher().decrypt(record.auth_flow_encrypted)

    callback = client.get(f"/microsoft/oauth/callback?state={state}&code=mock-code",
                          follow_redirects=False)
    assert callback.status_code == 303
    with factory() as session:
        credential = session.get(MicrosoftOAuthCredential, "organizer")
        assert credential.organizer_email == "organizer@example.com"
        assert b"cached" not in credential.token_cache_encrypted
        assert microsoft.cipher().decrypt(credential.token_cache_encrypted) == b'{"token":"cached"}'

    client.cookies.set(microsoft.COOKIE, original_cookie, domain="localhost.local",
                       path="/microsoft/oauth")
    replay = client.get(f"/microsoft/oauth/callback?state={state}&code=mock-code",
                        follow_redirects=False)
    assert replay.status_code == 400


def test_oauth_rejects_another_organizer(workspace, monkeypatch):
    client, factory, tenant_id = workspace
    install_fake_application(monkeypatch, tenant_id)
    monkeypatch.setattr(microsoft, "graph_request", lambda *args, **kwargs: {
        "mail": "someone-else@example.com", "userPrincipalName": "someone-else@example.com",
    })
    start = client.get("/microsoft/oauth/start", follow_redirects=False)
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    callback = client.get(f"/microsoft/oauth/callback?state={state}&code=mock-code",
                          follow_redirects=False)
    assert callback.status_code == 403
    with factory() as session:
        assert session.get(MicrosoftOAuthCredential, "organizer") is None


def test_disconnect_removes_only_the_local_token_cache(workspace):
    client, factory, tenant_id = workspace
    with factory.begin() as session:
        session.add(MicrosoftOAuthCredential(
            id="organizer",
            tenant_id=tenant_id,
            organizer_email="organizer@example.com",
            token_cache_encrypted=microsoft.cipher().encrypt(b"cached-token"),
            scopes=["User.Read", "Calendars.ReadBasic"],
        ))
    response = client.post("/microsoft/oauth/disconnect")
    assert response.status_code == 200
    assert response.json() == {"connected": False, "local_tokens_removed": True}
    with factory() as session:
        assert session.get(MicrosoftOAuthCredential, "organizer") is None


def test_availability_uses_graph_schedule_and_fails_closed(workspace, monkeypatch):
    client, _, _ = workspace
    monkeypatch.setattr(microsoft.settings, "meeting_timezone", "UTC")
    monkeypatch.setattr(microsoft, "access_token", lambda session: "mock-access-token")
    start = (now() + timedelta(days=3)).replace(hour=9, minute=0, second=0, microsecond=0)
    while start.weekday() >= 5:
        start += timedelta(days=1)
    calls = []

    def graph_request(token, method, path, *, payload=None, headers=None):
        calls.append((token, method, path, payload, headers))
        return {"value": [{
            "scheduleId": "organizer@example.com",
            "scheduleItems": [],
        }]}

    monkeypatch.setattr(microsoft, "graph_request", graph_request)
    response = client.post("/microsoft/availability", json={
        "start": start.isoformat(), "end": (start + timedelta(hours=2)).isoformat(),
    })
    assert response.status_code == 200
    assert len(response.json()["slots"]) == 4
    token, method, path, payload, headers = calls[0]
    assert (token, method, path) == (
        "mock-access-token", "POST", "/me/calendar/getSchedule")
    assert payload["schedules"] == ["organizer@example.com"]
    assert payload["availabilityViewInterval"] == 30
    assert headers["Prefer"] == 'outlook.timezone="UTC"'

    monkeypatch.setattr(microsoft, "graph_request", lambda *args, **kwargs: {
        "value": [{"scheduleId": "organizer@example.com", "scheduleItems": None}],
    })
    response = client.post("/microsoft/availability", json={
        "start": start.isoformat(), "end": (start + timedelta(hours=2)).isoformat(),
    })
    assert response.status_code == 502


def test_availability_treats_unknown_schedule_status_as_busy_error(workspace, monkeypatch):
    client, _, _ = workspace
    monkeypatch.setattr(microsoft.settings, "meeting_timezone", "UTC")
    monkeypatch.setattr(microsoft, "access_token", lambda session: "mock-access-token")
    start = (now() + timedelta(days=3)).replace(hour=9, minute=0, second=0, microsecond=0)
    while start.weekday() >= 5:
        start += timedelta(days=1)
    monkeypatch.setattr(microsoft, "graph_request", lambda *args, **kwargs: {
        "value": [{
            "scheduleId": "organizer@example.com",
            "scheduleItems": [{
                "status": "futureStatus",
                "start": {"dateTime": start.isoformat(), "timeZone": "UTC"},
                "end": {"dateTime": (start + timedelta(minutes=30)).isoformat(), "timeZone": "UTC"},
            }],
        }],
    })
    response = client.post("/microsoft/availability", json={
        "start": start.isoformat(), "end": (start + timedelta(hours=2)).isoformat(),
    })
    assert response.status_code == 502
