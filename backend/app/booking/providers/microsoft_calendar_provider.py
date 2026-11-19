import logging
from datetime import datetime
from sqlalchemy.orm import Session

from app import microsoft_graph
from app.models import MicrosoftOAuthCredential

logger = logging.getLogger(__name__)


class MicrosoftCalendarProvider:
    @staticmethod
    def is_connected(session: Session) -> bool:
        cred = session.get(MicrosoftOAuthCredential, "organizer")
        return bool(cred and cred.token_cache_encrypted)

    @staticmethod
    def get_busy_intervals(
        session: Session, start: datetime, end: datetime
    ) -> list[tuple[datetime, datetime]]:
        """Fetch busy intervals from Microsoft Graph getSchedule in UTC."""
        if not MicrosoftCalendarProvider.is_connected(session):
            raise RuntimeError("Microsoft Outlook organizer account is not connected.")
        return microsoft_graph.busy_intervals(session, start, end)
