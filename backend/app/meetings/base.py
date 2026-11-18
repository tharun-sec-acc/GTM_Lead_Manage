from abc import ABC, abstractmethod
from typing import Any
from sqlalchemy.orm import Session

from app.meetings.capabilities import ProviderCapabilities
from app.meetings.schemas import MeetingCreateRequest


class MeetingProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of provider: 'teams' or 'google_meet'."""
        pass

    @abstractmethod
    def get_capabilities(self) -> ProviderCapabilities:
        """Return provider capabilities."""
        pass

    @abstractmethod
    def get_status(self, session: Session) -> dict[str, Any]:
        """Return provider connection and organizer status."""
        pass

    @abstractmethod
    def create_instant_meeting(
        self, session: Session, request: MeetingCreateRequest
    ) -> tuple[str, str, dict[str, Any]]:
        """Create an instant meeting space. Returns (external_meeting_id, join_url, provider_metadata)."""
        pass

    @abstractmethod
    def schedule_meeting(
        self, session: Session, request: MeetingCreateRequest
    ) -> tuple[str, str, dict[str, Any]]:
        """Schedule a meeting through calendar. Returns (external_meeting_id, join_url, provider_metadata)."""
        pass

    @abstractmethod
    def get_meeting_details(self, session: Session, external_meeting_id: str) -> dict[str, Any]:
        """Fetch updated meeting status and details from provider."""
        pass

    @abstractmethod
    def get_participants(self, session: Session, external_meeting_id: str) -> list[dict[str, Any]]:
        """Fetch meeting participants and attendance where available."""
        pass

    @abstractmethod
    def discover_recordings(self, session: Session, external_meeting_id: str) -> list[dict[str, Any]]:
        """Discover available recording artifacts."""
        pass

    @abstractmethod
    def download_recording(self, session: Session, recording_info: dict[str, Any]) -> bytes | None:
        """Download recording content bytes."""
        pass

    @abstractmethod
    def discover_transcripts(self, session: Session, external_meeting_id: str) -> list[dict[str, Any]]:
        """Discover available transcript artifacts."""
        pass

    @abstractmethod
    def fetch_transcript_entries(
        self, session: Session, transcript_info: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Fetch normalized entries (speaker, text, start_timestamp, end_timestamp) for a transcript."""
        pass

    def resend_invitations(
        self, session: Session, external_meeting_id: str, participant_emails: list[str] | None = None
    ) -> dict[str, Any]:
        """Resend calendar/meeting invitation emails to participants."""
        return {"success": False, "message": "Provider does not support resending invitations."}

    def reschedule_meeting(
        self,
        session: Session,
        external_meeting_id: str,
        new_start: Any,
        new_end: Any,
        timezone: str = "UTC",
        note: str | None = None,
    ) -> dict[str, Any]:
        """Reschedule/postpone meeting to a new time and email updated invites to all guests."""
        return {"success": False, "message": "Provider does not support rescheduling."}

    def cancel_meeting(
        self,
        session: Session,
        external_meeting_id: str,
        cancellation_reason: str | None = None,
    ) -> dict[str, Any]:
        """Cancel meeting and dispatch cancellation emails to all participants."""
        return {"success": False, "message": "Provider does not support cancelling meetings."}


