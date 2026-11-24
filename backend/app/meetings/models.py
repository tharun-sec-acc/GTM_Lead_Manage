from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)  # "teams" | "google_meet"
    external_meeting_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    organizer_email: Mapped[str | None] = mapped_column(String(320), nullable=True)

    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True)
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    meeting_type: Mapped[str] = mapped_column(String(32), default="scheduled")  # "instant" | "scheduled"
    join_url: Mapped[str] = mapped_column(Text, nullable=False)

    scheduled_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")

    status: Mapped[str] = mapped_column(String(32), default="scheduled", index=True)  # "scheduled" | "completed" | "cancelled" | "in_progress"
    provider_metadata: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    # Relationships
    participants: Mapped[list["MeetingParticipant"]] = relationship(
        "MeetingParticipant", back_populates="meeting", cascade="all, delete-orphan", order_by="MeetingParticipant.created_at"
    )
    recordings: Mapped[list["MeetingRecording"]] = relationship(
        "MeetingRecording", back_populates="meeting", cascade="all, delete-orphan", order_by="MeetingRecording.created_at"
    )
    transcripts: Mapped[list["MeetingTranscript"]] = relationship(
        "MeetingTranscript", back_populates="meeting", cascade="all, delete-orphan", order_by="MeetingTranscript.created_at"
    )
    analysis: Mapped["MeetingAnalysis | None"] = relationship(
        "MeetingAnalysis", back_populates="meeting", uselist=False, cascade="all, delete-orphan"
    )
    action_items: Mapped[list["MeetingActionItem"]] = relationship(
        "MeetingActionItem", back_populates="meeting", cascade="all, delete-orphan", order_by="MeetingActionItem.created_at"
    )


class MeetingParticipant(Base):
    __tablename__ = "meeting_participants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True)
    external_participant_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    participant_role: Mapped[str] = mapped_column(String(64), default="attendee")  # "organizer" | "attendee" | "presenter"
    join_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    leave_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="participants")


class MeetingRecording(Base):
    __tablename__ = "meeting_recordings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True)
    external_recording_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), default="video/mp4")
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    s3_bucket: Mapped[str | None] = mapped_column(String(255), nullable=True)
    s3_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    processing_status: Mapped[str] = mapped_column(String(32), default="discovered")  # "discovered" | "downloading" | "archived" | "failed" | "unavailable"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="recordings")


class MeetingTranscript(Base):
    __tablename__ = "meeting_transcripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True)
    external_transcript_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language: Mapped[str] = mapped_column(String(16), default="en")
    source: Mapped[str] = mapped_column(String(64), default="provider")
    s3_bucket: Mapped[str | None] = mapped_column(String(255), nullable=True)
    s3_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_status: Mapped[str] = mapped_column(String(32), default="discovered")  # "discovered" | "downloaded" | "normalized" | "analyzed" | "failed" | "unavailable"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="transcripts")
    entries: Mapped[list["MeetingTranscriptEntry"]] = relationship(
        "MeetingTranscriptEntry", back_populates="transcript", cascade="all, delete-orphan", order_by="MeetingTranscriptEntry.created_at"
    )


class MeetingTranscriptEntry(Base):
    __tablename__ = "meeting_transcript_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    transcript_id: Mapped[str] = mapped_column(ForeignKey("meeting_transcripts.id", ondelete="CASCADE"), nullable=False, index=True)
    speaker_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    speaker_name: Mapped[str] = mapped_column(String(255), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_timestamp: Mapped[str | None] = mapped_column(String(64), nullable=True)
    end_timestamp: Mapped[str | None] = mapped_column(String(64), nullable=True)
    original_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    transcript: Mapped["MeetingTranscript"] = relationship("MeetingTranscript", back_populates="entries")


class MeetingAnalysis(Base):
    __tablename__ = "meeting_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    analysis_version: Mapped[str] = mapped_column(String(32), default="v1")
    executive_summary: Mapped[str] = mapped_column(Text, nullable=False)
    customer_requirements: Mapped[list] = mapped_column(JSON, default=list)
    customer_pain_points: Mapped[list] = mapped_column(JSON, default=list)
    technical_requirements: Mapped[list] = mapped_column(JSON, default=list)
    objections: Mapped[list] = mapped_column(JSON, default=list)
    buying_signals: Mapped[list] = mapped_column(JSON, default=list)
    decisions: Mapped[list] = mapped_column(JSON, default=list)
    next_steps: Mapped[list] = mapped_column(JSON, default=list)
    meeting_minutes: Mapped[str] = mapped_column(Text, nullable=False)
    followup_draft_subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    followup_draft_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_sales_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recommended_next_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_analysis: Mapped[dict] = mapped_column(JSON, default=dict)
    analysis_status: Mapped[str] = mapped_column(String(32), default="completed")  # "pending" | "completed" | "failed"
    confidence: Mapped[float] = mapped_column(Float, default=0.85)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="analysis")


class MeetingActionItem(Base):
    __tablename__ = "meeting_action_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True)
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    due_date: Mapped[str | None] = mapped_column(String(64), nullable=True)
    priority: Mapped[str] = mapped_column(String(16), default="medium")  # "low" | "medium" | "high"
    status: Mapped[str] = mapped_column(String(32), default="open")  # "open" | "in_progress" | "completed" | "cancelled"
    source_timestamp: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="action_items")
