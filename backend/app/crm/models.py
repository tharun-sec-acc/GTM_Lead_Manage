from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def new_id() -> str:
    return str(uuid4())


def now() -> datetime:
    return datetime.now(timezone.utc)


class Pipeline(Base):
    """A sales pipeline owned by one organization."""

    __tablename__ = "crm_pipelines"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_pipeline_org_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    stages: Mapped[list["PipelineStage"]] = relationship(
        "PipelineStage",
        back_populates="pipeline",
        cascade="all, delete-orphan",
        order_by="PipelineStage.position",
    )


class PipelineStage(Base):
    """A configurable stage in a pipeline.

    ``is_won`` and ``is_lost`` mark terminal stages; ``probability`` drives the
    weighted forecast for open opportunities.
    """

    __tablename__ = "crm_pipeline_stages"
    __table_args__ = (
        UniqueConstraint("pipeline_id", "name", name="uq_stage_pipeline_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    pipeline_id: Mapped[str] = mapped_column(
        ForeignKey("crm_pipelines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    probability: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    is_won: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    is_lost: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    pipeline: Mapped["Pipeline"] = relationship("Pipeline", back_populates="stages")


class Opportunity(Base):
    """A revenue opportunity for a lead, always inside the owning organization."""

    __tablename__ = "crm_opportunities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pipeline_id: Mapped[str] = mapped_column(ForeignKey("crm_pipelines.id"), nullable=False, index=True)
    stage_id: Mapped[str] = mapped_column(ForeignKey("crm_pipeline_stages.id"), nullable=False, index=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR", nullable=False)
    expected_close_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # open, won, lost
    status: Mapped[str] = mapped_column(String(20), default="open", server_default="open", nullable=False)
    won_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lost_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lost_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    source: Mapped[str | None] = mapped_column(String(60), nullable=True)
    source_detail: Mapped[str | None] = mapped_column(String(300), nullable=True)
    custom_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class OpportunityStageEvent(Base):
    """Immutable stage history for an opportunity."""

    __tablename__ = "crm_opportunity_stage_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("crm_opportunities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_stage_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    to_stage_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Activity(Base):
    """Shared activity timeline entry for a lead, contact or opportunity."""

    __tablename__ = "crm_activities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), nullable=True, index=True)
    contact_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    opportunity_id: Mapped[str | None] = mapped_column(
        ForeignKey("crm_opportunities.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # note, call, email, meeting, task, system
    activity_type: Mapped[str] = mapped_column(String(30), default="note", server_default="note", nullable=False)
    subject: Mapped[str] = mapped_column(String(300), default="", server_default="", nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    activity_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CrmTask(Base):
    """A sales task that is not tied to an inbound email reply."""

    __tablename__ = "crm_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # open, done, cancelled
    status: Mapped[str] = mapped_column(String(20), default="open", server_default="open", nullable=False)
    # high, medium, low
    priority: Mapped[str] = mapped_column(String(10), default="medium", server_default="medium", nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), nullable=True, index=True)
    opportunity_id: Mapped[str | None] = mapped_column(
        ForeignKey("crm_opportunities.id", ondelete="CASCADE"), nullable=True, index=True
    )
    owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    created_by_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class CustomFieldDefinition(Base):
    """Organization-defined custom field for leads or opportunities."""

    __tablename__ = "crm_custom_fields"
    __table_args__ = (
        UniqueConstraint("organization_id", "entity", "key", name="uq_custom_field_org_entity_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity: Mapped[str] = mapped_column(String(30), default="lead", server_default="lead", nullable=False)
    key: Mapped[str] = mapped_column(String(60), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    # text, number, date, boolean, select
    field_type: Mapped[str] = mapped_column(String(20), default="text", server_default="text", nullable=False)
    options: Mapped[list] = mapped_column(JSON, default=list)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SavedView(Base):
    """A stored filter for a CRM list, optionally shared with the organization."""

    __tablename__ = "crm_saved_views"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    entity: Mapped[str] = mapped_column(String(30), default="opportunity", server_default="opportunity", nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    filters: Mapped[dict] = mapped_column(JSON, default=dict)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
