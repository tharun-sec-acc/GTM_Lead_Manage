from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PlanResponse(BaseModel):
    id: str
    code: str
    name: str
    description: str | None = None
    price_cents: int | None = None
    currency: str
    billing_interval: str
    trial_days: int
    limits: dict[str, Any] = {}
    features: list[str] = []


class SubscriptionDetail(BaseModel):
    id: str
    status: str
    plan_code: str
    plan_name: str
    seats: int | None = None
    trial_ends_at: datetime | None = None
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool
    canceled_at: datetime | None = None
    provider: str | None = None
    price_cents: int | None = None
    currency: str
    billing_interval: str


class SubscriptionStateResponse(BaseModel):
    subscription: SubscriptionDetail
    plan: PlanResponse
    features: list[str] = []
    limits: dict[str, Any] = {}
    usage: dict[str, int] = {}
    remaining: dict[str, Any] = {}
    active: bool


class PlanChangeRequest(BaseModel):
    plan_code: str = Field(min_length=1, max_length=50)


class UsageResponse(BaseModel):
    plan_code: str
    limits: dict[str, Any] = {}
    usage: dict[str, int] = {}
    remaining: dict[str, Any] = {}
