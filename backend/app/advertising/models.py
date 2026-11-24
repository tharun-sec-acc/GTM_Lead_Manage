"""Advertising connectors, campaign reporting and website lead capture.

Every row is owned by exactly one organization. Provider credentials are stored
encrypted (Fernet) and are never serialized back to a client.
"""

from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    false,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

VALID_PROVIDERS = ("meta", "google")
VALID_FORM_PROVIDERS = ("website", "meta", "google")
VALID_CONNECTION_STATUS = {"connected", "pending_credentials", "disconnected", "error"}
VALID_SUBMISSION_STATUS = {"received", "accepted", "duplicate", "rejected", "error"}


def new_id() -> str:
    return str(uuid4())


def now() -> datetime:
    return datetime.now(timezone.utc)


class AdConnection(Base):
    """One connected advertising account (Meta ad account or Google Ads customer)."""

    __tablename__ = "ads_connections"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "provider",
            "external_account_id",
            name="uq_ads_connection_account",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    external_account_id: Mapped[str] = mapped_column(String(120), nullable=False)
    account_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # connected | pending_credentials | disconnected | error
    status: Mapped[str] = mapped_column(
        String(30), default="pending_credentials", server_default="pending_credentials", nullable=False
    )
    scopes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    access_token_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    refresh_token_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class AdCampaign(Base):
    """A provider campaign mirrored into the tenant workspace (read-only mirror)."""

    __tablename__ = "ads_campaigns"
    __table_args__ = (
        UniqueConstraint("connection_id", "external_id", name="uq_ads_campaign_external"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("ads_connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    objective: Mapped[str | None] = mapped_column(String(120), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="INR", server_default="INR", nullable=False)
    daily_budget_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Totals are recomputed from ads_metrics rows; provider payloads are never invented.
    spend_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    impressions: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    clicks: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    provider_leads: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    conversions: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class AdMetric(Base):
    """Daily provider-reported metrics for one campaign (idempotent per day)."""

    __tablename__ = "ads_metrics"
    __table_args__ = (
        UniqueConstraint("campaign_id", "metric_date", name="uq_ads_metric_campaign_day"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("ads_campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric_date: Mapped[date] = mapped_column(Date, nullable=False)
    spend_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    impressions: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    clicks: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    leads: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    conversions: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class LeadCaptureForm(Base):
    """A hosted/embeddable capture form, or the mirror of a provider lead form."""

    __tablename__ = "lead_capture_forms"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_capture_form_slug"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # website | meta | google
    provider: Mapped[str] = mapped_column(String(20), default="website", server_default="website", nullable=False)
    provider_form_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    fields: Mapped[list] = mapped_column(JSON, default=list)
    consent_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    requires_consent: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )
    success_message: Mapped[str | None] = mapped_column(String(300), nullable=True)
    redirect_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )
    submission_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class CapturedSubmission(Base):
    """One inbound submission (website form, Meta lead ad, Google lead form)."""

    __tablename__ = "lead_capture_submissions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "provider",
            "provider_submission_id",
            name="uq_capture_submission_provider_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    form_id: Mapped[str | None] = mapped_column(
        ForeignKey("lead_capture_forms.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_submission_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    provider_form_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lead_id: Mapped[str | None] = mapped_column(
        ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # received | accepted | duplicate | rejected | error
    status: Mapped[str] = mapped_column(String(20), default="received", server_default="received", nullable=False)
    source: Mapped[str | None] = mapped_column(String(60), nullable=True)
    campaign: Mapped[str | None] = mapped_column(String(200), nullable=True)
    utm: Mapped[dict] = mapped_column(JSON, default=dict)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AttributionTouchpoint(Base):
    """A capture event tying a lead to its source, campaign and UTM parameters."""

    __tablename__ = "attribution_touchpoints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lead_id: Mapped[str] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    submission_id: Mapped[str | None] = mapped_column(
        ForeignKey("lead_capture_submissions.id", ondelete="SET NULL"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    campaign_external_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    medium: Mapped[str | None] = mapped_column(String(120), nullable=True)
    campaign: Mapped[str | None] = mapped_column(String(200), nullable=True)
    term: Mapped[str | None] = mapped_column(String(200), nullable=True)
    content: Mapped[str | None] = mapped_column(String(200), nullable=True)
    landing_page: Mapped[str | None] = mapped_column(Text, nullable=True)
    referrer: Mapped[str | None] = mapped_column(Text, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WebhookReceipt(Base):
    """Idempotency ledger for provider webhook deliveries."""

    __tablename__ = "webhook_receipts"
    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="uq_webhook_receipt_event"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    event_id: Mapped[str] = mapped_column(String(200), nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, default=True, server_default=false(), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
