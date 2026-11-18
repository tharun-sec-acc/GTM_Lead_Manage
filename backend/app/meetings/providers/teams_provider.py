from datetime import datetime
from typing import Any
from sqlalchemy.orm import Session

from app import microsoft_graph
from app.meetings.artifacts.normalization import normalize_transcript_entry, parse_vtt_content
from app.meetings.base import MeetingProvider
from app.meetings.capabilities import TEAMS_CAPABILITIES, ProviderCapabilities
from app.meetings.schemas import MeetingCreateRequest
from app.models import MicrosoftOAuthCredential


class TeamsMeetingProvider(MeetingProvider):
    @property
    def provider_name(self) -> str:
        return "teams"

    def get_capabilities(self) -> ProviderCapabilities:
        return TEAMS_CAPABILITIES

    def get_status(self, session: Session) -> dict[str, Any]:
        cred = session.get(MicrosoftOAuthCredential, "organizer")
        connected = bool(cred and cred.token_cache_encrypted)
        return {
            "provider": "teams",
            "connected": connected,
            "organizer_email": cred.organizer_email if cred else None,
            "scopes": cred.scopes if cred else [],
            "capabilities": TEAMS_CAPABILITIES.to_dict(),
        }

    def _get_token(self, session: Session) -> str:
        return microsoft_graph.access_token(session)

    def create_instant_meeting(
        self, session: Session, request: MeetingCreateRequest
    ) -> tuple[str, str, dict[str, Any]]:
        """Create an instant Teams online meeting via Graph /me/onlineMeetings."""
        token = self._get_token(session)
        payload = {
            "subject": request.title,
        }
        res = microsoft_graph.graph_request(token, "POST", "/me/onlineMeetings", payload=payload)
        external_id = res.get("id") or ""
        join_url = res.get("joinWebUrl") or res.get("joinUrl") or ""
        return external_id, join_url, res

    def schedule_meeting(
        self, session: Session, request: MeetingCreateRequest
    ) -> tuple[str, str, dict[str, Any]]:
        """Schedule a Teams meeting with Outlook Calendar event via Graph /me/events."""
        token = self._get_token(session)
        start_dt = request.scheduled_start or datetime.now()
        end_dt = request.scheduled_end or datetime.now()
        tz = request.timezone or "UTC"

        attendees = [
            {"emailAddress": {"address": email.strip()}, "type": "required"}
            for email in request.participant_emails
            if email and email.strip()
        ]

        payload = {
            "subject": request.title,
            "body": {
                "contentType": "HTML",
                "content": f"<p>{request.description or request.title}</p>",
            },
            "start": {
                "dateTime": start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                "timeZone": tz,
            },
            "end": {
                "dateTime": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                "timeZone": tz,
            },
            "attendees": attendees,
            "isOnlineMeeting": True,
            "onlineMeetingProvider": "teamsForBusiness",
        }

        res = microsoft_graph.graph_request(
            token,
            "POST",
            "/me/events",
            payload=payload,
            headers={"Prefer": f'outlook.timezone="{tz}"'},
        )

        external_id = res.get("id") or ""
        online_meeting = res.get("onlineMeeting") or {}
        join_url = online_meeting.get("joinUrl") or res.get("webLink") or ""

        # If onlineMeeting was created, store joinUrl and details
        return external_id, join_url, res

    def get_meeting_details(self, session: Session, external_meeting_id: str) -> dict[str, Any]:
        token = self._get_token(session)
        try:
            # Try /me/events first
            return microsoft_graph.graph_request(token, "GET", f"/me/events/{external_meeting_id}")
        except Exception:
            # Fall back to /me/onlineMeetings
            return microsoft_graph.graph_request(token, "GET", f"/me/onlineMeetings/{external_meeting_id}")

    def get_participants(self, session: Session, external_meeting_id: str) -> list[dict[str, Any]]:
        """Extract participants from Outlook calendar event or attendance reports."""
        token = self._get_token(session)
        participants = []
        try:
            event = microsoft_graph.graph_request(token, "GET", f"/me/events/{external_meeting_id}")
            for att in event.get("attendees", []):
                email_obj = att.get("emailAddress", {})
                participants.append({
                    "email": email_obj.get("address", ""),
                    "display_name": email_obj.get("name"),
                    "participant_role": att.get("type", "attendee"),
                    "join_time": None,
                    "leave_time": None,
                    "provider_metadata": att,
                })
        except Exception:
            pass
        return participants

    def discover_recordings(self, session: Session, external_meeting_id: str) -> list[dict[str, Any]]:
        """Discover recording artifacts from /me/onlineMeetings/{id}/recordings."""
        token = self._get_token(session)
        recordings = []
        try:
            res = microsoft_graph.graph_request(
                token, "GET", f"/me/onlineMeetings/{external_meeting_id}/recordings"
            )
            items = res.get("value", []) if isinstance(res, dict) else []
            for item in items:
                recordings.append({
                    "external_recording_id": item.get("id"),
                    "external_file_id": item.get("contentDownloadUrl"),
                    "filename": f"teams_recording_{item.get('id', 'item')}.mp4",
                    "mime_type": "video/mp4",
                    "duration_seconds": None,
                    "source_location": item.get("contentDownloadUrl"),
                    "provider_metadata": item,
                })
        except Exception:
            # Not available or permission denied (policy-dependent)
            pass
        return recordings

    def download_recording(self, session: Session, recording_info: dict[str, Any]) -> bytes | None:
        """Download recording content from Microsoft Graph download URL."""
        token = self._get_token(session)
        download_url = recording_info.get("source_location")
        if not download_url:
            return None
        import httpx
        try:
            headers = {"Authorization": f"Bearer {token}"}
            with httpx.Client(timeout=60, follow_redirects=True) as http:
                resp = http.get(download_url, headers=headers)
                if resp.status_code == 200:
                    return resp.content
        except Exception:
            pass
        return None

    def discover_transcripts(self, session: Session, external_meeting_id: str) -> list[dict[str, Any]]:
        """Discover transcript artifacts from /me/onlineMeetings/{id}/transcripts."""
        token = self._get_token(session)
        transcripts = []
        try:
            res = microsoft_graph.graph_request(
                token, "GET", f"/me/onlineMeetings/{external_meeting_id}/transcripts"
            )
            items = res.get("value", []) if isinstance(res, dict) else []
            for item in items:
                transcripts.append({
                    "external_transcript_id": item.get("id"),
                    "language": item.get("meetingOrganizerLanguage", "en"),
                    "source": "teams_graph",
                    "provider_metadata": item,
                })
        except Exception:
            pass
        return transcripts

    def fetch_transcript_entries(
        self, session: Session, transcript_info: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Fetch transcript content and parse WebVTT format into standardized entries."""
        token = self._get_token(session)
        meeting_id = transcript_info.get("external_meeting_id")
        transcript_id = transcript_info.get("external_transcript_id")
        if not meeting_id or not transcript_id:
            return []

        try:
            # Fetch VTT formatted content
            import httpx
            url = f"{microsoft_graph.settings.microsoft_graph_base_url.rstrip('/')}/me/onlineMeetings/{meeting_id}/transcripts/{transcript_id}/content?$format=text/vtt"
            headers = {"Authorization": f"Bearer {token}", "Accept": "text/vtt"}
            with httpx.Client(timeout=30, follow_redirects=True) as http:
                resp = http.get(url, headers=headers)
                if resp.status_code == 200:
                    return parse_vtt_content(resp.text)
        except Exception:
            pass
        return []

    def resend_invitations(
        self, session: Session, external_meeting_id: str, participant_emails: list[str] | None = None
    ) -> dict[str, Any]:
        """Resend Teams calendar invitation emails to all attendees via Microsoft Graph."""
        token = self._get_token(session)
        payload: dict[str, Any] = {}
        if participant_emails:
            payload["attendees"] = [
                {"emailAddress": {"address": e.strip()}, "type": "required"}
                for e in participant_emails
                if e and e.strip()
            ]
        try:
            res = microsoft_graph.graph_request(
                token,
                "PATCH",
                f"/me/events/{external_meeting_id}",
                payload=payload or {"body": {"contentType": "HTML", "content": "<p>Meeting details updated.</p>"}},
            )
            return {
                "success": True,
                "provider": "teams",
                "message": "Teams meeting invitation notifications dispatched via Outlook Calendar.",
                "details": res,
            }
        except Exception as exc:
            return {"success": False, "provider": "teams", "message": str(exc)}

    def reschedule_meeting(
        self,
        session: Session,
        external_meeting_id: str,
        new_start: Any,
        new_end: Any,
        timezone: str = "UTC",
        note: str | None = None,
    ) -> dict[str, Any]:
        """Reschedule Teams meeting via Outlook Calendar /me/events/{id}."""
        token = self._get_token(session)
        payload: dict[str, Any] = {
            "start": {
                "dateTime": new_start.strftime("%Y-%m-%dT%H:%M:%S") if hasattr(new_start, "strftime") else str(new_start),
                "timeZone": timezone,
            },
            "end": {
                "dateTime": new_end.strftime("%Y-%m-%dT%H:%M:%S") if hasattr(new_end, "strftime") else str(new_end),
                "timeZone": timezone,
            },
        }
        try:
            res = microsoft_graph.graph_request(
                token,
                "PATCH",
                f"/me/events/{external_meeting_id}",
                payload=payload,
            )
            return {"success": True, "provider": "teams", "data": res}
        except Exception as exc:
            return {"success": False, "provider": "teams", "error": str(exc)}

    def cancel_meeting(
        self,
        session: Session,
        external_meeting_id: str,
        cancellation_reason: str | None = None,
    ) -> dict[str, Any]:
        """Cancel Teams meeting via Graph API and notify attendees."""
        token = self._get_token(session)
        try:
            res = microsoft_graph.graph_request(
                token,
                "POST",
                f"/me/events/{external_meeting_id}/cancel",
                payload={"comment": cancellation_reason or "Meeting cancelled by organizer."},
            )
            return {"success": True, "provider": "teams", "data": res}
        except Exception:
            try:
                microsoft_graph.graph_request(token, "DELETE", f"/me/events/{external_meeting_id}")
                return {"success": True, "provider": "teams"}
            except Exception as exc:
                return {"success": False, "provider": "teams", "error": str(exc)}


teams_provider = TeamsMeetingProvider()
