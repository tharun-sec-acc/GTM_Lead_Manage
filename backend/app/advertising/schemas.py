"""Request/response models for the advertising and lead-capture module."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

ProviderName = Literal["meta", "google"]
FormProvider = Literal["website", "meta", "google"]


class ConnectionCreate(BaseModel):
    provider: ProviderName
    external_account_id: str = Field(min_length=1, max_length=120)
    account_name: str | None = Field(default=None, max_length=200)
    # Provider-approved tokens only. They are encrypted at rest and never returned.
    access_token: str | None = Field(default=None, max_length=8000)
    refresh_token: str | None = Field(default=None, max_length=8000)
    token_expires_at: datetime | None = None
    scopes: str | None = Field(default=None, max_length=500)
    login_customer_id: str | None = Field(default=None, max_length=120)

    @field_validator("external_account_id")
    @classmethod
    def _strip(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("external_account_id cannot be blank.")
        return cleaned


class FormCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=2, max_length=120, pattern=r"^[a-z0-9][a-z0-9-]*$")
    description: str | None = Field(default=None, max_length=2000)
    provider: FormProvider = "website"
    provider_form_id: str | None = Field(default=None, max_length=120)
    fields: list[str] = Field(default_factory=lambda: ["name", "email", "company", "phone", "message"])
    consent_text: str | None = Field(default=None, max_length=1000)
    requires_consent: bool = True
    success_message: str | None = Field(default=None, max_length=300)
    redirect_url: str | None = Field(default=None, max_length=500)
    is_active: bool = True


class FormUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    provider_form_id: str | None = Field(default=None, max_length=120)
    fields: list[str] | None = None
    consent_text: str | None = Field(default=None, max_length=1000)
    requires_consent: bool | None = None
    success_message: str | None = Field(default=None, max_length=300)
    redirect_url: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class UTM(BaseModel):
    utm_source: str | None = Field(default=None, max_length=200)
    utm_medium: str | None = Field(default=None, max_length=200)
    utm_campaign: str | None = Field(default=None, max_length=200)
    utm_term: str | None = Field(default=None, max_length=200)
    utm_content: str | None = Field(default=None, max_length=200)


class WebsiteSubmission(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=60)
    company: str | None = Field(default=None, max_length=300)
    message: str | None = Field(default=None, max_length=4000)
    consent: bool = False
    # Off-screen field: filled means a bot. The submission is quietly dropped.
    honeypot: str | None = Field(default=None, max_length=200)
    utm: UTM = Field(default_factory=UTM)
    campaign_id: str | None = Field(default=None, max_length=120)
    landing_page: str | None = Field(default=None, max_length=2000)
    referrer: str | None = Field(default=None, max_length=2000)


class MetricRow(BaseModel):
    metric_date: date
    spend_cents: int = Field(default=0, ge=0)
    impressions: int = Field(default=0, ge=0)
    clicks: int = Field(default=0, ge=0)
    leads: int = Field(default=0, ge=0)
    conversions: int = Field(default=0, ge=0)


class MetricSyncRequest(BaseModel):
    """Daily provider figures recorded through the provisioning API.

    Used by the scheduled sync job and by operators importing historical,
    provider-exported numbers. It never invents data: every value is supplied
    by the provider export.
    """

    rows: list[MetricRow] = Field(min_length=1, max_length=400)
    source: str = Field(default="provider_api", max_length=60)


class CampaignPayload(BaseModel):
    external_id: str = Field(min_length=1, max_length=120)
    name: str | None = Field(default=None, max_length=300)
    status: str | None = Field(default=None, max_length=40)
    objective: str | None = Field(default=None, max_length=120)
    currency: str | None = Field(default=None, max_length=3)
    daily_budget_cents: int | None = Field(default=None, ge=0)
    started_at: datetime | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class CampaignUpsertRequest(BaseModel):
    campaigns: list[CampaignPayload] = Field(min_length=1, max_length=500)


class GoogleLeadWebhook(BaseModel):
    lead_id: str = Field(min_length=1, max_length=200)
    form_id: str | None = Field(default=None, max_length=120)
    campaign_id: str | None = Field(default=None, max_length=120)
    google_key: str | None = Field(default=None, max_length=200)
    user_column_data: list[dict[str, Any]] = Field(default_factory=list)
    api_version: str | None = None
