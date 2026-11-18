from app.meetings.base import MeetingProvider
from app.meetings.providers.google_meet_provider import google_meet_provider
from app.meetings.providers.teams_provider import teams_provider

_PROVIDERS: dict[str, MeetingProvider] = {
    "teams": teams_provider,
    "google_meet": google_meet_provider,
}


def get_meeting_provider(provider_name: str) -> MeetingProvider:
    provider = _PROVIDERS.get(provider_name.lower())
    if not provider:
        raise ValueError(f"Unsupported meeting provider: {provider_name}. Choose 'teams' or 'google_meet'.")
    return provider


__all__ = ["teams_provider", "google_meet_provider", "get_meeting_provider"]
