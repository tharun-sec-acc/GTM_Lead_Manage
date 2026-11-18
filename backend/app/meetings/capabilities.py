from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ProviderCapabilities:
    instant_meeting: bool
    scheduled_meeting: bool
    calendar_invitations: bool
    recording_retrieval: bool
    transcript_retrieval: bool
    availability_lookup: bool

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)


TEAMS_CAPABILITIES = ProviderCapabilities(
    instant_meeting=True,
    scheduled_meeting=True,
    calendar_invitations=True,
    recording_retrieval=True,
    transcript_retrieval=True,
    availability_lookup=True,
)

GOOGLE_MEET_CAPABILITIES = ProviderCapabilities(
    instant_meeting=True,
    scheduled_meeting=True,
    calendar_invitations=True,
    recording_retrieval=True,
    transcript_retrieval=True,
    availability_lookup=True,
)
