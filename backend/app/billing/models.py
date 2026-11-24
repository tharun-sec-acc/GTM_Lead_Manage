from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
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


class Plan(Base):
    """A configurable subscription plan.

    Pricing and entitlements live in the database, never in application logic.
    ``limits`` maps a metered metric name to an integer allowance; an explicit
    ``None`` means unlimited for that metric.
    """

    __tablename__ = "billing_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # None means "contact sales" / custom pricing.
    price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR", nullable=False)
    # month, year, custom
    billing_interval: Mapped[str] = mapped_column(
        String(20), default="month", server_default="month", nullable=False
    )
    trial_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    limits: Mapped[dict] = mapped_column(JSON, default=dict)
    features: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    subscriptions: Mapped[list["Subscription"]] = relationship("Subscription", back_populates="plan")


class Subscription(Base):
    """One subscription per organization, provider-agnostic by design.

    Payment-provider identifiers are optional columns so a PSP integration can be
    attached later without reshaping the entitlement model.
    """

    __tablename__ = "billing_subscriptions"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_subscription_org"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[str] = mapped_column(ForeignKey("billing_plans.id"), nullable=False, index=True)
    # trialing, active, past_due, canceled
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active", nullable=False)
    seats: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Payment-provider linkage (unused until a provider is configured).
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    plan: Mapped["Plan"] = relationship("Plan", back_populates="subscriptions")


class UsageRecord(Base):
    """Metered consumption for one organization, metric and billing period."""

    __tablename__ = "billing_usage_records"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "metric", "period_start", name="uq_usage_org_metric_period"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
