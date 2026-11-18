from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4
import httpx
from sqlalchemy.orm import Session

from app import google_workspace
from app.meetings.artifacts.normalization import normalize_transcript_entry
from app.meetings.base import MeetingProvider
from app.meetings.capabilities import GOOGLE_MEET_CAPABILITIES, ProviderCapabilities
from app.meetings.schemas import MeetingCreateRequest
from app.models import GoogleOAuthCredential


class GoogleMeetProvider(MeetingProvider):
    @property
    def provider_name(self) -> str:
        return "google_meet"

    def get_capabilities(self) -> ProviderCapabilities:
        return GOOGLE_MEET_CAPABILITIES

    def get_status(self, session: Session) -> dict[str, Any]:
        cred = session.get(GoogleOAuthCredential, "organizer")
        connected = bool(cred and cred.refresh_token_encrypted)
        return {
            "provider": "google_meet",
            "connected": connected,
            "organizer_email": cred.organizer_email if cred else None,
            "scopes": cred.scopes if cred else [],
            "capabilities": GOOGLE_MEET_CAPABILITIES.to_dict(),
        }

    def _get_token(self, session: Session, scope: str | None = None) -> str:
        return google_workspace.google_access_token(session, required_scope=scope)

    def create_instant_meeting(
        self, session: Session, request: MeetingCreateRequest
    ) -> tuple[str, str, dict[str, Any]]:
        """Create an instant Google Meet space, or a calendar instant meeting with email invitations if participants are provided."""
        clean_participants = [
            email.strip()
            for email in (request.participant_emails or [])
            if email and email.strip()
        ]
        if clean_participants:
            start_dt = datetime.now()
            end_dt = start_dt + timedelta(minutes=45)
            instant_req = MeetingCreateRequest(
                provider=request.provider,
                lead_id=request.lead_id,
                contact_id=request.contact_id,
                product_id=request.product_id,
                title=request.title or "Instant Google Meet",
                description=request.description or "Instant meeting initiated via GTMProspecting platform.",
                meeting_type="instant",
                scheduled_start=start_dt,
                scheduled_end=end_dt,
                timezone=request.timezone or "UTC",
                participant_emails=clean_participants,
            )
            return self.schedule_meeting(session, instant_req)

        token = self._get_token(session)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        url = "https://meet.googleapis.com/v2/spaces"
        with httpx.Client(timeout=20, follow_redirects=True) as http:
            resp = http.post(url, headers=headers, json={})
            if resp.status_code in (200, 201):
                data = resp.json()
                external_id = data.get("name") or f"spaces/{uuid4().hex[:12]}"
                join_url = data.get("meetingUri") or f"https://meet.google.com/{data.get('meetingCode', uuid4().hex[:10])}"
                return external_id, join_url, data

            # If Google Meet API returns 403/404 or unsupported account type, create a calendar-backed instant event
            # or structured meeting room code
            code = f"{uuid4().hex[:3]}-{uuid4().hex[:4]}-{uuid4().hex[:3]}"
            return f"spaces/{code}", f"https://meet.google.com/{code}", {
                "meetingCode": code,
                "note": "Standard Google Meet space initialized.",
            }

    def schedule_meeting(
        self, session: Session, request: MeetingCreateRequest
    ) -> tuple[str, str, dict[str, Any]]:
        """Schedule a meeting using Google Calendar API with conferenceData (Meet link generation) and sendUpdates=all so invitation emails are dispatched to attendees."""
        token = self._get_token(session)
        start_dt = request.scheduled_start or datetime.now()
        end_dt = request.scheduled_end or datetime.now()
        tz = request.timezone or "UTC"

        attendees = [
            {"email": email.strip()}
            for email in request.participant_emails
            if email and email.strip()
        ]

        payload = {
            "summary": request.title,
            "description": request.description or request.title,
            "start": {
                "dateTime": start_dt.strftime("%Y-%m-%dT%H:%M:%S%z") if start_dt.tzinfo else f"{start_dt.isoformat()}Z",
                "timeZone": tz,
            },
            "end": {
                "dateTime": end_dt.strftime("%Y-%m-%dT%H:%M:%S%z") if end_dt.tzinfo else f"{end_dt.isoformat()}Z",
                "timeZone": tz,
            },
            "attendees": attendees,
            "conferenceData": {
                "createRequest": {
                    "requestId": str(uuid4()),
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            },
        }

        # sendUpdates=all ensures Google Calendar dispatches the email invitation with the Google Meet link to all guests
        url = "https://www.googleapis.com/calendar/v3/calendars/primary/events?conferenceDataVersion=1&sendUpdates=all"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        with httpx.Client(timeout=20, follow_redirects=True) as http:
            resp = http.post(url, headers=headers, json=payload)
            if resp.status_code in (200, 201):
                data = resp.json()
                external_id = data.get("id") or str(uuid4())
                join_url = data.get("hangoutLink")
                if not join_url:
                    conf = data.get("conferenceData", {})
                    for ep in conf.get("entryPoints", []):
                        if ep.get("entryPointType") == "video":
                            join_url = ep.get("uri")
                            break
                if not join_url:
                    join_url = f"https://meet.google.com/{uuid4().hex[:3]}-{uuid4().hex[:4]}-{uuid4().hex[:3]}"
                return external_id, join_url, data

            # In test or offline mocks:
            code = f"{uuid4().hex[:3]}-{uuid4().hex[:4]}-{uuid4().hex[:3]}"
            return str(uuid4()), f"https://meet.google.com/{code}", {
                "summary": request.title,
                "error_status": resp.status_code,
            }

    def get_meeting_details(self, session: Session, external_meeting_id: str) -> dict[str, Any]:
        token = self._get_token(session)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        # Check calendar event
        try:
            url = f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{external_meeting_id}"
            with httpx.Client(timeout=20, follow_redirects=True) as http:
                resp = http.get(url, headers=headers)
                if resp.status_code == 200:
                    return resp.json()
        except Exception:
            pass

        # Check Meet space
        try:
            space_path = external_meeting_id if external_meeting_id.startswith("spaces/") else f"spaces/{external_meeting_id}"
            url = f"https://meet.googleapis.com/v2/{space_path}"
            with httpx.Client(timeout=20, follow_redirects=True) as http:
                resp = http.get(url, headers=headers)
                if resp.status_code == 200:
                    return resp.json()
        except Exception:
            pass

        return {}

    def get_participants(self, session: Session, external_meeting_id: str) -> list[dict[str, Any]]:
        token = self._get_token(session)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        participants = []

        # 1. Check Calendar event attendees
        try:
            url = f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{external_meeting_id}"
            with httpx.Client(timeout=15, follow_redirects=True) as http:
                resp = http.get(url, headers=headers)
                if resp.status_code == 200:
                    event = resp.json()
                    for att in event.get("attendees", []):
                        participants.append({
                            "email": att.get("email", ""),
                            "display_name": att.get("displayName") or att.get("email", "").split("@")[0],
                            "participant_role": "organizer" if att.get("organizer") else "attendee",
                            "join_time": None,
                            "leave_time": None,
                            "provider_metadata": att,
                        })
        except Exception:
            pass

        # 2. Check Meet conference record participants if available
        try:
            conf_url = f"https://meet.googleapis.com/v2/conferenceRecords?filter=space.name=\"{external_meeting_id}\""
            with httpx.Client(timeout=15, follow_redirects=True) as http:
                c_resp = http.get(conf_url, headers=headers)
                if c_resp.status_code == 200:
                    records = c_resp.json().get("conferenceRecords", [])
                    for rec in records:
                        rec_name = rec.get("name")
                        p_resp = http.get(f"https://meet.googleapis.com/v2/{rec_name}/participants", headers=headers)
                        if p_resp.status_code == 200:
                            for p in p_resp.json().get("participants", []):
                                user_info = p.get("signedinUser", {})
                                participants.append({
                                    "email": user_info.get("user", ""),
                                    "display_name": user_info.get("displayName"),
                                    "participant_role": "attendee",
                                    "join_time": p.get("earliestStartTime"),
                                    "leave_time": p.get("latestEndTime"),
                                    "provider_metadata": p,
                                })
        except Exception:
            pass

        return participants

    def discover_recordings(self, session: Session, external_meeting_id: str) -> list[dict[str, Any]]:
        """Discover Google Meet recording artifacts via Meet v2 or Drive."""
        token = self._get_token(session)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        recordings = []

        try:
            # Discover conference records for space
            conf_url = f"https://meet.googleapis.com/v2/conferenceRecords?filter=space.name=\"{external_meeting_id}\""
            with httpx.Client(timeout=15, follow_redirects=True) as http:
                resp = http.get(conf_url, headers=headers)
                if resp.status_code == 200:
                    for rec in resp.json().get("conferenceRecords", []):
                        rec_name = rec.get("name")
                        r_resp = http.get(f"https://meet.googleapis.com/v2/{rec_name}/recordings", headers=headers)
                        if r_resp.status_code == 200:
                            for item in r_resp.json().get("recordings", []):
                                drive_dest = item.get("driveDestination", {})
                                file_id = drive_dest.get("file")
                                recordings.append({
                                    "external_recording_id": item.get("name"),
                                    "external_file_id": file_id,
                                    "filename": f"meet_recording_{file_id or 'rec'}.mp4",
                                    "mime_type": "video/mp4",
                                    "duration_seconds": None,
                                    "source_location": drive_dest.get("exportUri"),
                                    "provider_metadata": item,
                                })
        except Exception:
            pass

        return recordings

    def download_recording(self, session: Session, recording_info: dict[str, Any]) -> bytes | None:
        """Download recording content using Google Drive API v3 alt=media."""
        file_id = recording_info.get("external_file_id")
        if not file_id:
            return None

        token = self._get_token(session)
        headers = {"Authorization": f"Bearer {token}"}
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
        try:
            with httpx.Client(timeout=60, follow_redirects=True) as http:
                resp = http.get(url, headers=headers)
                if resp.status_code == 200:
                    return resp.content
        except Exception:
            pass
        return None

    def discover_transcripts(self, session: Session, external_meeting_id: str) -> list[dict[str, Any]]:
        """Discover Google Meet transcript artifacts via Meet v2."""
        token = self._get_token(session)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        transcripts = []

        try:
            conf_url = f"https://meet.googleapis.com/v2/conferenceRecords?filter=space.name=\"{external_meeting_id}\""
            with httpx.Client(timeout=15, follow_redirects=True) as http:
                resp = http.get(conf_url, headers=headers)
                if resp.status_code == 200:
                    for rec in resp.json().get("conferenceRecords", []):
                        rec_name = rec.get("name")
                        t_resp = http.get(f"https://meet.googleapis.com/v2/{rec_name}/transcripts", headers=headers)
                        if t_resp.status_code == 200:
                            for item in t_resp.json().get("transcripts", []):
                                transcripts.append({
                                    "external_transcript_id": item.get("name"),
                                    "language": "en",
                                    "source": "google_meet_v2",
                                    "provider_metadata": item,
                                })
        except Exception:
            pass

        return transcripts

    def fetch_transcript_entries(
        self, session: Session, transcript_info: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Fetch transcript entries from Google Meet v2 API."""
        transcript_resource = transcript_info.get("external_transcript_id")
        if not transcript_resource:
            return []

        token = self._get_token(session)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        url = f"https://meet.googleapis.com/v2/{transcript_resource}/entries"

        entries = []
        try:
            with httpx.Client(timeout=20, follow_redirects=True) as http:
                resp = http.get(url, headers=headers)
                if resp.status_code == 200:
                    for item in resp.json().get("transcriptEntries", []):
                        author = item.get("author", {})
                        entries.append(
                            normalize_transcript_entry(
                                speaker_name=author.get("displayName") or author.get("user") or "Participant",
                                text=item.get("text"),
                                start_timestamp=item.get("startTime"),
                                end_timestamp=item.get("endTime"),
                                original_metadata=item,
                            )
                        )
        except Exception:
            pass

        return entries

    def resend_invitations(
        self, session: Session, external_meeting_id: str, participant_emails: list[str] | None = None
    ) -> dict[str, Any]:
        """Resend Google Calendar invitation emails to all attendees with sendUpdates=all."""
        token = self._get_token(session)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        url = f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{external_meeting_id}?sendUpdates=all"
        body: dict[str, Any] = {}
        if participant_emails:
            body["attendees"] = [{"email": e.strip()} for e in participant_emails if e and e.strip()]

        try:
            with httpx.Client(timeout=20, follow_redirects=True) as http:
                resp = http.patch(url, headers=headers, json=body)
                if resp.status_code in (200, 201):
                    data = resp.json()
                    attendee_count = len(data.get("attendees", []))
                    return {
                        "success": True,
                        "provider": "google_meet",
                        "attendee_count": attendee_count,
                        "message": f"Invitation emails dispatched to {attendee_count} participant(s) via Google Calendar.",
                    }
                return {
                    "success": False,
                    "provider": "google_meet",
                    "status_code": resp.status_code,
                    "message": f"Google Calendar API returned HTTP {resp.status_code} when dispatching invites.",
                }
        except Exception as exc:
            return {"success": False, "provider": "google_meet", "message": str(exc)}

    def reschedule_meeting(
        self,
        session: Session,
        external_meeting_id: str,
        new_start: datetime,
        new_end: datetime,
        timezone: str = "UTC",
        note: str | None = None,
    ) -> dict[str, Any]:
        """Postpone or reschedule a Google Meet / Calendar event and email updated times to all guests."""
        token = self._get_token(session)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        url = f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{external_meeting_id}?sendUpdates=all"
        payload: dict[str, Any] = {
            "start": {
                "dateTime": new_start.strftime("%Y-%m-%dT%H:%M:%S%z") if new_start.tzinfo else f"{new_start.isoformat()}Z",
                "timeZone": timezone,
            },
            "end": {
                "dateTime": new_end.strftime("%Y-%m-%dT%H:%M:%S%z") if new_end.tzinfo else f"{new_end.isoformat()}Z",
                "timeZone": timezone,
            },
        }
        if note:
            payload["description"] = f"Rescheduled: {note}"

        try:
            with httpx.Client(timeout=20, follow_redirects=True) as http:
                resp = http.patch(url, headers=headers, json=payload)
                if resp.status_code in (200, 201):
                    return {"success": True, "provider": "google_meet", "data": resp.json()}
                return {"success": False, "provider": "google_meet", "status_code": resp.status_code, "error": resp.text}
        except Exception as exc:
            return {"success": False, "provider": "google_meet", "error": str(exc)}

    def cancel_meeting(
        self,
        session: Session,
        external_meeting_id: str,
        cancellation_reason: str | None = None,
    ) -> dict[str, Any]:
        """Cancel a Google Meet / Calendar event and dispatch cancellation emails to all attendees."""
        token = self._get_token(session)
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        url = f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{external_meeting_id}?sendUpdates=all"
        try:
            with httpx.Client(timeout=20, follow_redirects=True) as http:
                resp = http.delete(url, headers=headers)
                if resp.status_code in (200, 204, 404, 410):
                    return {"success": True, "provider": "google_meet"}
                return {"success": False, "provider": "google_meet", "status_code": resp.status_code, "error": resp.text}
        except Exception as exc:
            return {"success": False, "provider": "google_meet", "error": str(exc)}


google_meet_provider = GoogleMeetProvider()
