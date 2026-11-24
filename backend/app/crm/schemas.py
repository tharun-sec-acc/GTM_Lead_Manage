from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class PipelineCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class PipelineUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    is_archived: bool | None = None


class StageCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    position: int = Field(default=0, ge=0, le=10000)
    probability: int = Field(default=0, ge=0, le=100)
    is_won: bool = False
    is_lost: bool = False


class StageUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    position: int | None = Field(default=None, ge=0, le=10000)
    probability: int | None = Field(default=None, ge=0, le=100)
    is_won: bool | None = None
    is_lost: bool | None = None


class OpportunityCreate(BaseModel):
    lead_id: str = Field(min_length=1, max_length=36)
    name: str = Field(min_length=1, max_length=300)
    pipeline_id: str | None = None
    stage_id: str | None = None
    contact_id: str | None = None
    amount_cents: int = Field(default=0, ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    expected_close_date: date | None = None
    owner_id: str | None = None
    source: str | None = Field(default=None, max_length=60)
    source_detail: str | None = Field(default=None, max_length=300)
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class OpportunityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    contact_id: str | None = None
    amount_cents: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    expected_close_date: date | None = None
    owner_id: str | None = None
    source: str | None = Field(default=None, max_length=60)
    source_detail: str | None = Field(default=None, max_length=300)
    custom_fields: dict[str, Any] | None = None


class StageChangeRequest(BaseModel):
    stage_id: str = Field(min_length=1, max_length=36)
    note: str | None = Field(default=None, max_length=2000)


class CloseRequest(BaseModel):
    status: Literal["won", "lost"]
    lost_reason: str | None = Field(default=None, max_length=2000)


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    priority: Literal["high", "medium", "low"] = "medium"
    due_at: datetime | None = None
    lead_id: str | None = None
    opportunity_id: str | None = None
    owner_id: str | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    status: Literal["open", "done", "cancelled"] | None = None
    priority: Literal["high", "medium", "low"] | None = None
    due_at: datetime | None = None
    owner_id: str | None = None


class ActivityCreate(BaseModel):
    activity_type: Literal["note", "call", "email", "meeting", "task"] = "note"
    subject: str = Field(default="", max_length=300)
    body: str | None = Field(default=None, max_length=10000)
    lead_id: str | None = None
    contact_id: str | None = None
    opportunity_id: str | None = None
    occurred_at: datetime | None = None


class LeadCrmUpdate(BaseModel):
    owner_id: str | None = None
    lifecycle_stage: Literal["lead", "qualified", "opportunity", "customer"] | None = None
    qualification_status: Literal["unqualified", "qualified", "disqualified"] | None = None
    source: str | None = Field(default=None, max_length=60)
    custom_fields: dict[str, Any] | None = None


class MergeRequest(BaseModel):
    source_lead_ids: list[str] = Field(min_length=1, max_length=20)


class CustomFieldCreate(BaseModel):
    entity: Literal["lead", "opportunity"] = "lead"
    key: str = Field(min_length=1, max_length=60, pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1, max_length=120)
    field_type: Literal["text", "number", "date", "boolean", "select"] = "text"
    options: list[str] = Field(default_factory=list)
    is_required: bool = False
    position: int = 0


class CustomFieldUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=120)
    field_type: Literal["text", "number", "date", "boolean", "select"] | None = None
    options: list[str] | None = None
    is_required: bool | None = None
    position: int | None = None


class SavedViewCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    entity: Literal["lead", "opportunity", "task"] = "opportunity"
    filters: dict[str, Any] = Field(default_factory=dict)
    is_shared: bool = False
