import os
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import Lead, Contact, GoogleOAuthCredential, now
from app.meetings.models import (
    Meeting, MeetingParticipant, MeetingRecording,
    MeetingTranscript, MeetingTranscriptEntry, MeetingAnalysis, MeetingActionItem
)
from app.meetings.artifacts.normalization import parse_vtt_content, clean_speaker_name


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    db_path = tmp_path / "meetings.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override

    # Storage dir override
    test_storage_dir = tmp_path / "attachments"
    monkeypatch.setattr("app.meetings.artifacts.storage_service.LOCAL_ARCHIVE_ROOT", test_storage_dir)

    with TestClient(app, base_url="http://localhost:8000") as test_client:
        yield test_client, factory, test_storage_dir

    app.dependency_overrides.clear()
    engine.dispose()


def test_provider_status_endpoint(workspace):
    client, _, _ = workspace
    res = client.get("/meetings/providers/status")
    assert res.status_code == 200
    providers = res.json()
    assert len(providers) == 2
    names = {p["provider"] for p in providers}
    assert "teams" in names
    assert "google_meet" in names
    for p in providers:
        assert p["capabilities"]["instant_meeting"] is True
        assert p["capabilities"]["scheduled_meeting"] is True


def test_vtt_transcript_parser():
    vtt = """WEBVTT

00:00:01.000 --> 00:00:04.500
<v John Doe>Hi everyone, thank you for joining this demo.</v>

00:00:05.000 --> 00:00:09.000
<v Jane Smith>Glad to be here. We are looking for route optimization and e-POD.</v>
"""
    entries = parse_vtt_content(vtt)
    assert len(entries) == 2
    assert entries[0]["speaker_name"] == "John Doe"
    assert "Hi everyone" in entries[0]["text"]
    assert entries[1]["speaker_name"] == "Jane Smith"
    assert "route optimization" in entries[1]["text"]


def test_create_teams_instant_meeting(workspace):
    client, factory, _ = workspace

    with factory() as session:
        lead = Lead(company_name="Acme Corp", company_key="acme", domain="acme.com")
        session.add(lead)
        session.flush()
        contact = Contact(lead_id=lead.id, name="Bob Alice", email="bob@acme.com")
        session.add(contact)
        session.commit()
        lead_id = lead.id
        contact_id = contact.id

    mock_tuple = (
        "teams-online-12345",
        "https://teams.microsoft.com/l/meetup-join/12345",
        {"id": "teams-online-12345"},
    )

    with patch("app.meetings.providers.teams_provider.TeamsMeetingProvider.create_instant_meeting", return_value=mock_tuple):
        payload = {
            "title": "Quick Sync with Acme",
            "provider": "teams",
            "meeting_type": "instant",
            "lead_id": lead_id,
            "contact_id": contact_id,
            "participant_emails": ["bob@acme.com"],
        }
        res = client.post("/meetings", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["provider"] == "teams"
        assert data["meeting_type"] == "instant"
        assert data["join_url"] == "https://teams.microsoft.com/l/meetup-join/12345"
        assert len(data["participants"]) >= 1
        assert any(p["email"] == "bob@acme.com" for p in data["participants"])


def test_create_google_meet_scheduled_meeting(workspace):
    client, factory, _ = workspace

    with factory() as session:
        lead = Lead(company_name="Beta Logistics", company_key="beta", domain="beta.com")
        session.add(lead)
        session.commit()
        lead_id = lead.id

    now_utc = datetime.now(timezone.utc)
    start_time = (now_utc + timedelta(hours=2)).isoformat()
    end_time = (now_utc + timedelta(hours=3)).isoformat()

    mock_tuple = (
        "google-cal-event-987",
        "https://meet.google.com/abc-defg-hij",
        {"id": "google-cal-event-987", "calendar_event_id": "google-cal-event-987"},
    )

    with patch("app.meetings.providers.google_meet_provider.GoogleMeetProvider.schedule_meeting", return_value=mock_tuple):
        payload = {
            "title": "Product Demo - TWMS",
            "provider": "google_meet",
            "meeting_type": "scheduled",
            "lead_id": lead_id,
            "scheduled_start": start_time,
            "scheduled_end": end_time,
            "participant_emails": ["lead@beta.com"],
        }
        res = client.post("/meetings", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["provider"] == "google_meet"
        assert data["meeting_type"] == "scheduled"
        assert data["join_url"] == "https://meet.google.com/abc-defg-hij"


def test_meeting_detail_and_action_items(workspace):
    client, factory, _ = workspace

    with factory() as session:
        m = Meeting(
            title="Discovery Call",
            provider="teams",
            meeting_type="scheduled",
            status="completed",
            join_url="https://teams.microsoft.com/call",
            scheduled_start=now(),
            scheduled_end=now() + timedelta(minutes=30),
        )
        session.add(m)
        session.commit()
        meeting_id = m.id

    # Get detail
    res = client.get(f"/meetings/{meeting_id}")
    assert res.status_code == 200
    assert res.json()["title"] == "Discovery Call"

    # Add Action Item
    ai_payload = {
        "title": "Send custom quote for 25 trucks",
        "owner": "Sales Rep",
        "priority": "high",
    }
    ai_res = client.post(f"/meetings/{meeting_id}/action-items", json=ai_payload)
    assert ai_res.status_code == 201
    item = ai_res.json()
    assert item["title"] == "Send custom quote for 25 trucks"
    assert item["status"] == "open"
    item_id = item["id"]

    # Toggle Action Item status
    patch_res = client.patch(f"/meetings/action-items/{item_id}", json={"status": "completed"})
    assert patch_res.status_code == 200
    assert patch_res.json()["status"] == "completed"


def test_meeting_analysis_and_followup_dispatch(workspace):
    client, factory, _ = workspace

    with factory() as session:
        lead = Lead(company_name="Gamma Transport", company_key="gamma", domain="gamma.com")
        session.add(lead)
        session.flush()
        contact = Contact(lead_id=lead.id, name="Carlos Ray", email="carlos@gamma.com")
        session.add(contact)
        session.flush()
        m = Meeting(
            title="Strategic Review",
            provider="google_meet",
            meeting_type="scheduled",
            status="completed",
            lead_id=lead.id,
            join_url="https://meet.google.com/xyz",
            scheduled_start=now(),
            scheduled_end=now() + timedelta(minutes=45),
        )
        session.add(m)
        session.flush()
        # Add transcript
        tr = MeetingTranscript(meeting_id=m.id, external_transcript_id="tr-1", language="en")
        session.add(tr)
        session.flush()
        e1 = MeetingTranscriptEntry(
            transcript_id=tr.id,
            speaker_name="Carlos Ray",
            start_timestamp="00:00:01",
            end_timestamp="00:00:05",
            text="We need to automate dispatch and reduce deadhead miles.",
        )
        session.add(e1)
        session.commit()
        meeting_id = m.id
        lead_id = lead.id

    # Run analysis (will run Bedrock or fallback)
    an_res = client.post(f"/meetings/{meeting_id}/analyze")
    assert an_res.status_code == 200
    meeting_data = an_res.json()
    assert meeting_data["analysis"] is not None
    assert meeting_data["analysis"]["executive_summary"]
    assert len(meeting_data["action_items"]) >= 1
    assert meeting_data["analysis"]["followup_draft_body"] is not None

    # Test send follow-up draft endpoint
    send_payload = {
        "recipient": "carlos@gamma.com",
        "subject": "Follow-up: DENSO TWMS discussion",
        "body": "<p>Hi Carlos, thank you for sharing your dispatch automation goals...</p>",
    }
    send_res = client.post(f"/meetings/{meeting_id}/send-followup", json=send_payload)
    assert send_res.status_code == 200
    assert send_res.json()["status"] == "sent"
    assert send_res.json()["message_id"] is not None


def test_lead_360_profile_includes_meetings(workspace):
    client, factory, _ = workspace

    with factory() as session:
        lead = Lead(company_name="Delta Fleet", company_key="delta", domain="delta.com")
        session.add(lead)
        session.commit()
        lead_id = lead.id
        m = Meeting(
            title="Delta Intro Call",
            provider="teams",
            meeting_type="instant",
            status="completed",
            lead_id=lead.id,
            join_url="https://teams.microsoft.com/meet/delta",
            scheduled_start=now(),
        )
        session.add(m)
        session.commit()

    res = client.get(f"/leads/{lead_id}/profile")
    assert res.status_code == 200
    data = res.json()
    assert "meetings" in data
    assert data["meetings"]["implemented"] is True
    assert len(data["meetings"]["items"]) == 1
    assert data["meetings"]["items"][0]["title"] == "Delta Intro Call"
    assert data["overview"]["meeting_count"] == 1


def test_schedule_google_meeting_includes_send_updates_all(workspace, monkeypatch):
    client, factory, _ = workspace
    captured_urls = []

    import httpx
    orig_post = httpx.Client.post

    def fake_post(self, url, *args, **kwargs):
        if "calendar/v3" in str(url):
            captured_urls.append(str(url))
            class DummyResp:
                status_code = 200
                def json(self):
                    return {
                        "id": "gcal-12345",
                        "hangoutLink": "https://meet.google.com/xyz-abcd-efg",
                        "attendees": [{"email": "guest1@gmail.com"}, {"email": "guest2@gmail.com"}],
                    }
            return DummyResp()
        return orig_post(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    with factory() as session:
        cred = GoogleOAuthCredential(
            id="organizer",
            organizer_email="organizer@gmail.com",
            refresh_token_encrypted=b"dummy",
            scopes=["https://www.googleapis.com/auth/calendar.events"],
        )
        session.merge(cred)
        session.commit()

    monkeypatch.setattr("app.google_workspace.google_access_token", lambda *a, **kw: "mock-google-token")

    res = client.post(
        "/meetings",
        json={
            "provider": "google_meet",
            "title": "Discovery Demo",
            "meeting_type": "scheduled",
            "scheduled_start": "2026-11-20T10:00:00Z",
            "scheduled_end": "2026-11-20T10:30:00Z",
            "participant_emails": ["guest1@gmail.com", "guest2@gmail.com"],
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["join_url"] == "https://meet.google.com/xyz-abcd-efg"
    # Ensure sendUpdates=all was appended to Google Calendar event creation URL
    assert any("sendUpdates=all" in u for u in captured_urls)


def test_resend_meeting_invites_endpoint(workspace, monkeypatch):
    client, factory, _ = workspace
    captured_patch_urls = []

    import httpx
    orig_patch = httpx.Client.patch

    def fake_patch(self, url, *args, **kwargs):
        if "calendar/v3" in str(url):
            captured_patch_urls.append(str(url))
            class DummyResp:
                status_code = 200
                def json(self):
                    return {
                        "id": "gcal-12345",
                        "attendees": [{"email": "guest1@gmail.com"}],
                    }
            return DummyResp()
        return orig_patch(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "patch", fake_patch)
    monkeypatch.setattr("app.google_workspace.google_access_token", lambda *a, **kw: "mock-google-token")

    with factory() as session:
        m = Meeting(
            title="Invite Test",
            provider="google_meet",
            external_meeting_id="gcal-12345",
            meeting_type="scheduled",
            join_url="https://meet.google.com/xyz-abcd-efg",
        )
        session.add(m)
        session.commit()
        meeting_id = m.id

    res = client.post(f"/meetings/{meeting_id}/send-invites")
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["success"] is True
    assert "sendUpdates=all" in captured_patch_urls[0]


def test_reschedule_meeting_endpoint(workspace, monkeypatch):
    client, factory, _ = workspace
    captured_patch = []

    import httpx
    orig_patch = httpx.Client.patch

    def fake_patch(self, url, *args, **kwargs):
        if "calendar/v3" in str(url):
            captured_patch.append((str(url), kwargs.get("json")))
            class DummyResp:
                status_code = 200
                def json(self):
                    return {"id": "gcal-12345", "status": "confirmed"}
            return DummyResp()
        return orig_patch(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "patch", fake_patch)
    monkeypatch.setattr("app.google_workspace.google_access_token", lambda *a, **kw: "mock-google-token")

    with factory() as session:
        m = Meeting(
            title="Pre-Reschedule",
            provider="google_meet",
            external_meeting_id="gcal-resched-123",
            meeting_type="scheduled",
            join_url="https://meet.google.com/xyz-abcd-efg",
        )
        session.add(m)
        session.commit()
        meeting_id = m.id

    res = client.post(
        f"/meetings/{meeting_id}/reschedule",
        json={
            "new_start": "2026-11-25T14:00:00Z",
            "new_end": "2026-11-25T14:45:00Z",
            "timezone": "UTC",
            "note": "Prospect requested delay",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "scheduled"
    assert "2026-11-25" in data["scheduled_start"]
    assert any("sendUpdates=all" in item[0] for item in captured_patch)


def test_cancel_meeting_endpoint(workspace, monkeypatch):
    client, factory, _ = workspace
    captured_delete = []

    import httpx
    orig_delete = httpx.Client.delete

    def fake_delete(self, url, *args, **kwargs):
        if "calendar/v3" in str(url):
            captured_delete.append(str(url))
            class DummyResp:
                status_code = 204
            return DummyResp()
        return orig_delete(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "delete", fake_delete)
    monkeypatch.setattr("app.google_workspace.google_access_token", lambda *a, **kw: "mock-google-token")

    with factory() as session:
        m = Meeting(
            title="To Cancel",
            provider="google_meet",
            external_meeting_id="gcal-cancel-123",
            meeting_type="scheduled",
            join_url="https://meet.google.com/xyz-abcd-efg",
        )
        session.add(m)
        session.commit()
        meeting_id = m.id

    res = client.post(f"/meetings/{meeting_id}/cancel", json={"reason": "Customer no longer interested"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "cancelled"
    assert any("sendUpdates=all" in u for u in captured_delete)


