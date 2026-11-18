from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class MeetingParticipantSchema(BaseModel):
    id: str
    email: str
    display_name: str | None = None
    participant_role: str = "attendee"
    join_time: datetime | None = None
    leave_time: datetime | None = None
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(from_attributes=True)


class MeetingRecordingSchema(BaseModel):
    id: str
    filename: str
    mime_type: str = "video/mp4"
    duration_seconds: int | None = None
    s3_key: str | None = None
    source_location: str | None = None
    download_url: str | None = None
    processing_status: str = "discovered"
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class MeetingTranscriptEntrySchema(BaseModel):
    id: str
    speaker_name: str
    text: str
    start_timestamp: str | None = None
    end_timestamp: str | None = None
    model_config = ConfigDict(from_attributes=True)


class MeetingTranscriptSchema(BaseModel):
    id: str
    language: str = "en"
    source: str = "provider"
    processing_status: str = "discovered"
    entries: list[MeetingTranscriptEntrySchema] = Field(default_factory=list)
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class MeetingActionItemSchema(BaseModel):
    id: str
    meeting_id: str
    lead_id: str | None = None
    title: str
    description: str | None = None
    owner: str | None = None
    due_date: str | None = None
    priority: str = "medium"
    status: str = "open"
    source_timestamp: str | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class MeetingAnalysisSchema(BaseModel):
    id: str
    analysis_version: str = "v1"
    executive_summary: str
    customer_requirements: list[str] = Field(default_factory=list)
    customer_pain_points: list[str] = Field(default_factory=list)
    technical_requirements: list[str] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    buying_signals: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    meeting_minutes: str
    followup_draft_subject: str | None = None
    followup_draft_body: str | None = None
    recommended_sales_stage: str | None = None
    recommended_next_action: str | None = None
    analysis_status: str = "completed"
    confidence: float = 0.85
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class MeetingSummarySchema(BaseModel):
    id: str
    provider: Literal["teams", "google_meet"]
    external_meeting_id: str | None = None
    organizer_email: str | None = None
    lead_id: str | None = None
    company_name: str | None = None
    contact_id: str | None = None
    contact_name: str | None = None
    product_id: str | None = None
    product_name: str | None = None
    title: str
    description: str | None = None
    meeting_type: Literal["instant", "scheduled"] = "scheduled"
    join_url: str
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    timezone: str = "UTC"
    status: str = "scheduled"
    has_recording: bool = False
    has_transcript: bool = False
    has_analysis: bool = False
    action_items_count: int = 0
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class MeetingDetailSchema(BaseModel):
    id: str
    provider: Literal["teams", "google_meet"]
    external_meeting_id: str | None = None
    organizer_email: str | None = None
    lead_id: str | None = None
    company_name: str | None = None
    contact_id: str | None = None
    contact_name: str | None = None
    product_id: str | None = None
    product_name: str | None = None
    title: str
    description: str | None = None
    meeting_type: Literal["instant", "scheduled"] = "scheduled"
    join_url: str
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    actual_start: datetime | None = None
    actual_end: datetime | None = None
    timezone: str = "UTC"
    status: str = "scheduled"
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    participants: list[MeetingParticipantSchema] = Field(default_factory=list)
    recordings: list[MeetingRecordingSchema] = Field(default_factory=list)
    transcripts: list[MeetingTranscriptSchema] = Field(default_factory=list)
    analysis: MeetingAnalysisSchema | None = None
    action_items: list[MeetingActionItemSchema] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class MeetingCreateRequest(BaseModel):
    provider: Literal["teams", "google_meet"] = "teams"
    meeting_type: Literal["instant", "scheduled"] = "scheduled"
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    lead_id: str | None = None
    contact_id: str | None = None
    product_id: str | None = None
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    timezone: str = "UTC"
    participant_emails: list[str] = Field(default_factory=list)


class MeetingActionItemCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    owner: str | None = None
    due_date: str | None = None
    priority: Literal["low", "medium", "high"] = "medium"


class MeetingActionItemUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    owner: str | None = None
    due_date: str | None = None
    priority: Literal["low", "medium", "high"] | None = None
    status: Literal["open", "in_progress", "completed", "cancelled"] | None = None


class SendFollowupDraftRequest(BaseModel):
    recipient: str
    subject: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)


class ManualTranscriptInput(BaseModel):
    raw_text: str = Field(..., min_length=5, description="Pasted meeting dialog, call recording transcript, or sales notes")


class MeetingRescheduleRequest(BaseModel):
    new_start: datetime = Field(..., description="New scheduled start datetime")
    new_end: datetime = Field(..., description="New scheduled end datetime")
    timezone: str = "UTC"
    note: str | None = None


class MeetingCancelRequest(BaseModel):
    reason: str | None = Field(default=None, description="Optional cancellation reason")


class ProviderStatusSchema(BaseModel):
    provider: Literal["teams", "google_meet"]
    connected: bool
    organizer_email: str | None = None
    scopes: list[str] = Field(default_factory=list)
    capabilities: dict[str, bool] = Field(default_factory=dict)
