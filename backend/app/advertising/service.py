"""Advertising sync, attribution and lead-capture services.

Design rules enforced here:

* every query is scoped by ``organization_id``;
* provider credentials are encrypted at rest and never serialized;
* submissions are idempotent per provider receipt id;
* CRM leads are created through the shared ``Lead`` model, so advertising,
  website forms and the CRM all read the same customer record;
* reported numbers come from provider payloads or explicit operator input,
  never from generated placeholders.
"""

import hashlib
import hmac
import logging
import re
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.advertising.models import (
    VALID_PROVIDERS,
    AdCampaign,
    AdConnection,
    AdMetric,
    AttributionTouchpoint,
    CapturedSubmission,
    LeadCaptureForm,
    WebhookReceipt,
    now,
)
from app.advertising.providers import (
    GoogleAdsClient,
    MetaAdsClient,
    ProviderError,
    ProviderNotConfigured,
)
from app.auth.models import Organization
from app.auth.security import decrypt_token, encrypt_token
from app.crm.models import Opportunity
from app.models import Lead

logger = logging.getLogger(__name__)

ATTRIBUTION_MODEL = "last-touch lead source"
ATTRIBUTION_CAVEAT = (
    "Campaign attribution links each captured lead to the campaign that produced it. "
    "It shows correlation between spend and revenue, not proof that the campaign caused the sale."
)


def company_key(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "Unknown").casefold()).strip()


def _email_domain(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    domain = email.rsplit("@", 1)[1].strip().lower()
    return domain or None


# ------------------------------- serializers ------------------------------


def serialize_connection(connection: AdConnection) -> dict:
    """Connection payload. Tokens never leave the server."""
    return {
        "id": connection.id,
        "provider": connection.provider,
        "external_account_id": connection.external_account_id,
        "account_name": connection.account_name,
        "status": connection.status,
        "has_credentials": bool(connection.access_token_encrypted),
        "scopes": connection.scopes,
        "token_expires_at": connection.token_expires_at,
        "last_synced_at": connection.last_synced_at,
        "last_error": connection.last_error,
        "metadata": connection.metadata_json or {},
        "created_at": connection.created_at,
        "updated_at": connection.updated_at,
    }


def serialize_campaign(campaign: AdCampaign) -> dict:
    return {
        "id": campaign.id,
        "provider": campaign.provider,
        "external_id": campaign.external_id,
        "name": campaign.name,
        "status": campaign.status,
        "objective": campaign.objective,
        "currency": campaign.currency,
        "daily_budget_cents": campaign.daily_budget_cents,
        "spend_cents": campaign.spend_cents,
        "impressions": campaign.impressions,
        "clicks": campaign.clicks,
        "provider_leads": campaign.provider_leads,
        "conversions": campaign.conversions,
        "started_at": campaign.started_at,
        "last_synced_at": campaign.last_synced_at,
    }


def serialize_form(form: LeadCaptureForm) -> dict:
    return {
        "id": form.id,
        "name": form.name,
        "slug": form.slug,
        "description": form.description,
        "provider": form.provider,
        "provider_form_id": form.provider_form_id,
        "fields": form.fields or [],
        "consent_text": form.consent_text,
        "requires_consent": form.requires_consent,
        "success_message": form.success_message,
        "redirect_url": form.redirect_url,
        "is_active": form.is_active,
        "submission_count": form.submission_count,
        "created_at": form.created_at,
    }


def serialize_submission(submission: CapturedSubmission) -> dict:
    return {
        "id": submission.id,
        "form_id": submission.form_id,
        "provider": submission.provider,
        "provider_submission_id": submission.provider_submission_id,
        "provider_form_id": submission.provider_form_id,
        "lead_id": submission.lead_id,
        "status": submission.status,
        "source": submission.source,
        "campaign": submission.campaign,
        "utm": submission.utm or {},
        "payload": submission.payload or {},
        "error": submission.error,
        "created_at": submission.created_at,
    }


# ------------------------------- connections ------------------------------


def list_connections(session: Session, organization: Organization) -> list[AdConnection]:
    return list(
        session.scalars(
            select(AdConnection)
            .where(AdConnection.organization_id == organization.id)
            .order_by(AdConnection.provider, AdConnection.account_name)
        ).all()
    )


def require_connection(
    session: Session, organization: Organization, connection_id: str
) -> AdConnection:
    connection = session.get(AdConnection, connection_id)
    if not connection or connection.organization_id != organization.id:
        raise LookupError("Advertising account not found.")
    return connection


def create_connection(
    session: Session,
    organization: Organization,
    *,
    provider: str,
    external_account_id: str,
    account_name: str | None = None,
    access_token: str | None = None,
    refresh_token: str | None = None,
    token_expires_at: datetime | None = None,
    scopes: str | None = None,
    metadata: dict | None = None,
) -> AdConnection:
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"Unknown advertising provider '{provider}'.")

    connection = session.scalar(
        select(AdConnection).where(
            AdConnection.organization_id == organization.id,
            AdConnection.provider == provider,
            AdConnection.external_account_id == external_account_id,
        )
    )
    if connection is None:
        connection = AdConnection(
            organization_id=organization.id,
            provider=provider,
            external_account_id=external_account_id,
        )
        session.add(connection)

    connection.account_name = account_name or connection.account_name
    connection.scopes = scopes or connection.scopes
    connection.token_expires_at = token_expires_at or connection.token_expires_at
    if access_token:
        connection.access_token_encrypted = encrypt_token(access_token)
    if refresh_token:
        connection.refresh_token_encrypted = encrypt_token(refresh_token)
    if metadata:
        connection.metadata_json = {**(connection.metadata_json or {}), **metadata}
    connection.status = "connected" if connection.access_token_encrypted else "pending_credentials"
    connection.last_error = None
    session.commit()
    session.refresh(connection)
    return connection


def disconnect_connection(session: Session, connection: AdConnection) -> AdConnection:
    """Drop stored credentials locally.

    Provider-side revocation needs the provider's revoke endpoint, which is
    documented as a follow-up in ``docs/advertising-and-lead-capture.md``; the
    stored token is destroyed here regardless.
    """
    connection.access_token_encrypted = None
    connection.refresh_token_encrypted = None
    connection.status = "disconnected"
    connection.last_error = None
    session.commit()
    session.refresh(connection)
    return connection


def connection_token(connection: AdConnection) -> str | None:
    if not connection.access_token_encrypted:
        return None
    return decrypt_token(connection.access_token_encrypted)


def _mark_sync_failure(session: Session, connection: AdConnection, message: str) -> None:
    connection.status = "error"
    connection.last_error = message[:1000]
    session.commit()


# --------------------------------- sync ----------------------------------


def upsert_campaigns(
    session: Session,
    organization: Organization,
    connection: AdConnection,
    rows: list[dict],
) -> dict:
    """Insert or update provider campaigns, keyed by provider campaign id."""
    created = 0
    updated = 0
    for row in rows:
        external_id = str(row.get("external_id") or "").strip()
        if not external_id:
            continue
        campaign = session.scalar(
            select(AdCampaign).where(
                AdCampaign.connection_id == connection.id,
                AdCampaign.external_id == external_id,
            )
        )
        if campaign is None:
            campaign = AdCampaign(
                organization_id=organization.id,
                connection_id=connection.id,
                provider=connection.provider,
                external_id=external_id,
                name=row.get("name") or external_id,
            )
            session.add(campaign)
            created += 1
        else:
            updated += 1

        if row.get("name"):
            campaign.name = str(row["name"])[:300]
        if row.get("status"):
            campaign.status = str(row["status"])[:40]
        if row.get("objective"):
            campaign.objective = str(row["objective"])[:120]
        if row.get("currency"):
            campaign.currency = str(row["currency"])[:3]
        if row.get("daily_budget_cents") is not None:
            campaign.daily_budget_cents = int(row["daily_budget_cents"])
        if row.get("started_at"):
            campaign.started_at = row["started_at"]
        if row.get("raw"):
            campaign.raw = row["raw"]
        campaign.last_synced_at = now()

    connection.last_synced_at = now()
    connection.status = "connected"
    connection.last_error = None
    session.commit()
    return {"created": created, "updated": updated}


def record_daily_metrics(
    session: Session,
    organization: Organization,
    campaign: AdCampaign,
    rows: list[dict],
) -> int:
    """Upsert daily metrics for a campaign and recompute its totals."""
    recorded = 0
    seen_dates: set[date] = set()
    # Sessions run with autoflush disabled, so track this payload's rows locally
    # instead of relying on a follow-up SELECT to see the pending insert.
    pending: dict[date, AdMetric] = {}
    for row in rows:
        raw_date = row.get("metric_date") or row.get("date")
        if isinstance(raw_date, datetime):
            metric_date = raw_date.date()
        elif isinstance(raw_date, date):
            metric_date = raw_date
        elif raw_date:
            try:
                metric_date = date.fromisoformat(str(raw_date)[:10])
            except ValueError:
                continue
        else:
            continue

        metric = pending.get(metric_date)
        if metric is None:
            metric = session.scalar(
                select(AdMetric).where(
                    AdMetric.campaign_id == campaign.id,
                    AdMetric.metric_date == metric_date,
                )
            )
        if metric is None:
            metric = AdMetric(
                organization_id=organization.id,
                campaign_id=campaign.id,
                metric_date=metric_date,
            )
            session.add(metric)
        pending[metric_date] = metric
        metric.spend_cents = int(row.get("spend_cents") or 0)
        metric.impressions = int(row.get("impressions") or 0)
        metric.clicks = int(row.get("clicks") or 0)
        metric.leads = int(row.get("leads") or 0)
        metric.conversions = int(row.get("conversions") or 0)
        if metric_date not in seen_dates:
            seen_dates.add(metric_date)
            recorded += 1

    session.flush()
    totals = session.execute(
        select(
            func.coalesce(func.sum(AdMetric.spend_cents), 0),
            func.coalesce(func.sum(AdMetric.impressions), 0),
            func.coalesce(func.sum(AdMetric.clicks), 0),
            func.coalesce(func.sum(AdMetric.leads), 0),
            func.coalesce(func.sum(AdMetric.conversions), 0),
        ).where(AdMetric.campaign_id == campaign.id)
    ).one()
    campaign.spend_cents = int(totals[0])
    campaign.impressions = int(totals[1])
    campaign.clicks = int(totals[2])
    campaign.provider_leads = int(totals[3])
    campaign.conversions = int(totals[4])
    campaign.last_synced_at = now()
    session.commit()
    return recorded


def sync_connection(
    session: Session, organization: Organization, connection: AdConnection
) -> dict:
    """Pull read-only campaign data from the provider.

    Raises :class:`ProviderNotConfigured` when credentials or provider approval
    are missing, so callers can report the external requirement instead of
    showing placeholder numbers.
    """
    token = connection_token(connection)
    if not token:
        raise ProviderNotConfigured(
            f"{connection.provider.title()} account '{connection.external_account_id}' has no stored token. "
            "Connect it with a provider-approved token first."
        )

    try:
        if connection.provider == "meta":
            client = MetaAdsClient(token)
            campaigns = client.fetch_campaigns(connection.external_account_id)
            stats = upsert_campaigns(session, organization, connection, campaigns)
            since = date.today() - timedelta(days=29)
            insights = client.fetch_daily_insights(connection.external_account_id, since, date.today())
            by_campaign: dict[str, list[dict]] = {}
            for row in insights:
                by_campaign.setdefault(str(row.get("campaign_external_id")), []).append(row)
            metrics = 0
            for external_id, rows in by_campaign.items():
                campaign = session.scalar(
                    select(AdCampaign).where(
                        AdCampaign.connection_id == connection.id,
                        AdCampaign.external_id == external_id,
                    )
                )
                if campaign:
                    metrics += record_daily_metrics(session, organization, campaign, rows)
            return {**stats, "metrics": metrics}
        else:
            client = GoogleAdsClient(token, login_customer_id=(connection.metadata_json or {}).get("login_customer_id"))
            campaigns = client.fetch_campaigns(connection.external_account_id)
            stats = upsert_campaigns(session, organization, connection, campaigns)
            metrics = 0
            for row in campaigns:
                metrics_rows = row.get("metrics")
                if not metrics_rows:
                    continue
                campaign = session.scalar(
                    select(AdCampaign).where(
                        AdCampaign.connection_id == connection.id,
                        AdCampaign.external_id == row["external_id"],
                    )
                )
                if campaign:
                    snapshot = dict(metrics_rows)
                    snapshot["metric_date"] = date.today()
                    metrics += record_daily_metrics(session, organization, campaign, [snapshot])
            return {**stats, "metrics": metrics}
    except ProviderError as exc:
        _mark_sync_failure(session, connection, str(exc))
        raise


# ------------------------------ lead capture -----------------------------


def meta_lead_fields(lead_data: dict) -> dict:
    collected: dict[str, str] = {}
    for item in lead_data.get("field_data") or []:
        name = str(item.get("name") or "").lower()
        values = item.get("values") or []
        if name and values:
            collected[name] = str(values[0])
    name = (
        collected.get("full_name")
        or " ".join(part for part in (collected.get("first_name"), collected.get("last_name")) if part)
        or None
    )
    return {
        "name": name,
        "email": collected.get("email"),
        "phone": collected.get("phone_number") or collected.get("phone"),
        "company": collected.get("company_name") or collected.get("company"),
        "title": collected.get("job_title"),
        "message": collected.get("custom_question_1") or collected.get("message"),
    }


def google_lead_fields(columns: list[dict]) -> dict:
    collected: dict[str, str] = {}
    for column in columns or []:
        key = str(column.get("column_id") or "").upper()
        value = column.get("string_value")
        if key and value:
            collected[key] = str(value)
    name = collected.get("FULL_NAME") or " ".join(
        part for part in (collected.get("FIRST_NAME"), collected.get("LAST_NAME")) if part
    )
    return {
        "name": name or None,
        "email": collected.get("EMAIL"),
        "phone": collected.get("PHONE_NUMBER"),
        "company": collected.get("COMPANY_NAME"),
        "title": collected.get("JOB_TITLE"),
        "message": collected.get("MESSAGE") or collected.get("CUSTOM_QUESTION"),
    }


def _find_existing_lead(
    session: Session, organization: Organization, email: str | None, phone: str | None
) -> Lead | None:
    if email:
        lead = session.scalar(
            select(Lead).where(
                Lead.organization_id == organization.id,
                Lead.email == email,
                Lead.merged_into_id.is_(None),
            )
        )
        if lead:
            return lead
    if phone:
        return session.scalar(
            select(Lead).where(
                Lead.organization_id == organization.id,
                Lead.phone == phone,
                Lead.merged_into_id.is_(None),
            )
        )
    return None


def ingest_lead(
    session: Session,
    organization: Organization,
    *,
    provider: str,
    fields: dict,
    form: LeadCaptureForm | None = None,
    submission_id: str | None = None,
    campaign_external_id: str | None = None,
    campaign_name: str | None = None,
    utm: dict | None = None,
    landing_page: str | None = None,
    referrer: str | None = None,
    source: str | None = None,
) -> tuple[Lead, bool]:
    """Create (or extend) a tenant lead and record its attribution touchpoint."""
    email = (fields.get("email") or "").strip().lower() or None
    phone = (fields.get("phone") or "").strip() or None
    if not email and not phone:
        raise ValueError("A captured lead needs an email address or a phone number.")

    person = (fields.get("name") or "").strip() or None
    company = (fields.get("company") or "").strip() or person or _email_domain(email) or "Unknown"
    form_name = form.name if form else None
    source_label = source or (form.provider if form else provider)

    lead = _find_existing_lead(session, organization, email, phone)
    created = False
    if lead is None:
        lead = Lead(
            organization_id=organization.id,
            company_name=company[:500],
            company_key=company_key(company)[:500],
            domain=_email_domain(email),
            email=email,
            phone=phone,
            designation=(fields.get("title") or None),
            remarks=(fields.get("message") or None),
            lifecycle_stage="lead",
            source=source_label[:60],
            source_detail=(campaign_name or form_name or None),
            custom_fields={
                "ad_provider": provider,
                "ad_campaign_external_id": campaign_external_id,
                "captured_by": "advertising",
            },
        )
        session.add(lead)
        session.flush()
        created = True
    else:
        if email and not lead.email:
            lead.email = email
        if phone and not lead.phone:
            lead.phone = phone
        if person and not lead.designation:
            lead.designation = person
        if not lead.source:
            lead.source = source_label[:60]
        if campaign_name and not lead.source_detail:
            lead.source_detail = campaign_name
        if lead.lifecycle_stage in (None, ""):
            lead.lifecycle_stage = "lead"

    utm = utm or {}
    session.add(
        AttributionTouchpoint(
            organization_id=organization.id,
            lead_id=lead.id,
            submission_id=submission_id,
            channel=provider,
            campaign_external_id=campaign_external_id,
            source=(utm.get("utm_source") or source_label)[:120] if (utm.get("utm_source") or source_label) else None,
            medium=(utm.get("utm_medium") or None),
            campaign=(utm.get("utm_campaign") or campaign_name or None),
            term=(utm.get("utm_term") or None),
            content=(utm.get("utm_content") or None),
            landing_page=landing_page,
            referrer=referrer,
        )
    )
    return lead, created


def record_submission(
    session: Session,
    organization: Organization,
    *,
    provider: str,
    fields: dict,
    form: LeadCaptureForm | None = None,
    provider_submission_id: str | None = None,
    provider_form_id: str | None = None,
    campaign_external_id: str | None = None,
    campaign_name: str | None = None,
    utm: dict | None = None,
    landing_page: str | None = None,
    referrer: str | None = None,
    source: str | None = None,
    payload: dict | None = None,
) -> CapturedSubmission:
    """Store one submission exactly once (idempotent per provider receipt id).

    A ``received`` row means the provider delivered the event but its field data
    could not be fetched yet; processing that row later reuses it instead of
    creating a second record.
    """
    existing = None
    if provider_submission_id:
        existing = session.scalar(
            select(CapturedSubmission).where(
                CapturedSubmission.organization_id == organization.id,
                CapturedSubmission.provider == provider,
                CapturedSubmission.provider_submission_id == provider_submission_id,
            )
        )
        if existing and existing.status != "received":
            return existing

    submission = existing or CapturedSubmission(
        organization_id=organization.id,
        provider=provider,
        provider_submission_id=provider_submission_id,
    )
    submission.form_id = form.id if form else submission.form_id
    submission.provider_form_id = (
        provider_form_id or (form.provider_form_id if form else None) or submission.provider_form_id
    )
    submission.campaign = campaign_name or submission.campaign
    submission.utm = utm or submission.utm or {}
    submission.payload = payload or fields or submission.payload
    submission.status = "received"
    submission.error = None
    session.add(submission)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        return session.scalar(
            select(CapturedSubmission).where(
                CapturedSubmission.organization_id == organization.id,
                CapturedSubmission.provider == provider,
                CapturedSubmission.provider_submission_id == provider_submission_id,
            )
        )

    try:
        lead, created = ingest_lead(
            session,
            organization,
            provider=provider,
            fields=fields,
            form=form,
            submission_id=submission.id,
            campaign_external_id=campaign_external_id,
            campaign_name=campaign_name,
            utm=utm,
            landing_page=landing_page,
            referrer=referrer,
            source=source,
        )
        submission.lead_id = lead.id
        submission.status = "accepted"
        if form is not None and created:
            form.submission_count = (form.submission_count or 0) + 1
    except ValueError as exc:
        submission.status = "rejected"
        submission.error = str(exc)

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(
            select(CapturedSubmission).where(
                CapturedSubmission.organization_id == organization.id,
                CapturedSubmission.provider == provider,
                CapturedSubmission.provider_submission_id == provider_submission_id,
            )
        )
        if existing:
            return existing
        raise
    session.refresh(submission)
    return submission


def store_received_submission(
    session: Session,
    organization: Organization,
    *,
    provider: str,
    provider_submission_id: str,
    provider_form_id: str | None = None,
    payload: dict | None = None,
    error: str | None = None,
) -> CapturedSubmission:
    """Persist a provider delivery we cannot process yet (missing credentials)."""
    submission = session.scalar(
        select(CapturedSubmission).where(
            CapturedSubmission.organization_id == organization.id,
            CapturedSubmission.provider == provider,
            CapturedSubmission.provider_submission_id == provider_submission_id,
        )
    )
    if submission is None:
        submission = CapturedSubmission(
            organization_id=organization.id,
            provider=provider,
            provider_submission_id=provider_submission_id,
            provider_form_id=provider_form_id,
            status="received",
            payload=payload or {},
        )
        session.add(submission)
    submission.error = (error or "")[:1000] or submission.error
    session.commit()
    session.refresh(submission)
    return submission


def process_meta_leadgen(
    session: Session,
    organization: Organization,
    connection: AdConnection | None,
    leadgen_id: str,
    *,
    form: LeadCaptureForm | None = None,
) -> CapturedSubmission:
    """Fetch a Meta lead's field data and store it once."""
    if connection is None:
        raise ProviderNotConfigured(
            "No Meta ad account is connected for this organization, so the lead cannot be fetched."
        )
    client = MetaAdsClient(connection_token(connection))
    data = client.fetch_lead(leadgen_id)
    fields = meta_lead_fields(data)
    return record_submission(
        session,
        organization,
        provider="meta",
        fields=fields,
        form=form,
        provider_submission_id=leadgen_id,
        provider_form_id=str(data.get("form_id") or "") or None,
        campaign_external_id=str(data.get("campaign_id") or "") or None,
        source="meta_lead_ads",
        payload=data,
    )


# ------------------------------- reporting --------------------------------


def _funnel_for_campaign(session: Session, organization: Organization, campaign: AdCampaign) -> dict:
    lead_ids = list(
        session.scalars(
            select(AttributionTouchpoint.lead_id)
            .where(
                AttributionTouchpoint.organization_id == organization.id,
                AttributionTouchpoint.campaign_external_id == campaign.external_id,
            )
            .distinct()
        ).all()
    )
    qualified = 0
    opportunities = 0
    won_count = 0
    won_value_cents = 0
    if lead_ids:
        qualified = int(
            session.scalar(
                select(func.count(Lead.id)).where(
                    Lead.id.in_(lead_ids), Lead.qualification_status == "qualified"
                )
            )
            or 0
        )
        rows = session.scalars(
            select(Opportunity).where(
                Opportunity.organization_id == organization.id,
                Opportunity.lead_id.in_(lead_ids),
            )
        ).all()
        opportunities = len(rows)
        for opportunity in rows:
            if opportunity.status == "won":
                won_count += 1
                won_value_cents += int(opportunity.amount_cents or 0)
    return {
        "crm_leads": len(lead_ids),
        "qualified_leads": qualified,
        "opportunities": opportunities,
        "won_deals": won_count,
        "won_value_cents": won_value_cents,
    }


def campaign_report(session: Session, organization: Organization) -> dict:
    """Spend, provider leads and CRM outcomes per campaign, with attribution caveat."""
    campaigns = list(
        session.scalars(
            select(AdCampaign)
            .where(AdCampaign.organization_id == organization.id)
            .order_by(AdCampaign.spend_cents.desc(), AdCampaign.name)
        ).all()
    )
    rows = []
    for campaign in campaigns:
        funnel = _funnel_for_campaign(session, organization, campaign)
        spend = int(campaign.spend_cents or 0)
        provider_leads = int(campaign.provider_leads or 0)
        rows.append(
            {
                **serialize_campaign(campaign),
                **funnel,
                "cost_per_lead_cents": (spend // provider_leads) if provider_leads else None,
                "cost_per_qualified_lead_cents": (
                    spend // funnel["qualified_leads"] if funnel["qualified_leads"] else None
                ),
                "roas": round(funnel["won_value_cents"] / spend, 2) if spend else None,
            }
        )

    totals = {
        "spend_cents": sum(row["spend_cents"] for row in rows),
        "provider_leads": sum(row["provider_leads"] for row in rows),
        "crm_leads": sum(row["crm_leads"] for row in rows),
        "qualified_leads": sum(row["qualified_leads"] for row in rows),
        "opportunities": sum(row["opportunities"] for row in rows),
        "won_deals": sum(row["won_deals"] for row in rows),
        "won_value_cents": sum(row["won_value_cents"] for row in rows),
    }
    totals["cost_per_lead_cents"] = (
        totals["spend_cents"] // totals["provider_leads"] if totals["provider_leads"] else None
    )
    totals["cost_per_qualified_lead_cents"] = (
        totals["spend_cents"] // totals["qualified_leads"] if totals["qualified_leads"] else None
    )
    return {
        "campaigns": rows,
        "totals": totals,
        "attribution_model": ATTRIBUTION_MODEL,
        "caveat": ATTRIBUTION_CAVEAT,
    }


def channel_summary(session: Session, organization: Organization) -> dict:
    """Lead volume by capture channel, so unattributed channels stay visible."""
    rows = session.execute(
        select(AttributionTouchpoint.channel, func.count(AttributionTouchpoint.id))
        .where(AttributionTouchpoint.organization_id == organization.id)
        .group_by(AttributionTouchpoint.channel)
    ).all()
    return {channel: int(count) for channel, count in rows}


def submission_summary(session: Session, organization: Organization) -> dict:
    rows = session.execute(
        select(CapturedSubmission.status, func.count(CapturedSubmission.id))
        .where(CapturedSubmission.organization_id == organization.id)
        .group_by(CapturedSubmission.status)
    ).all()
    return {status: int(count) for status, count in rows}


# ------------------------------- webhooks ---------------------------------


def verify_meta_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """Verify Meta's ``X-Hub-Signature-256`` using the configured app secret."""
    secret = settings_secret("meta_app_secret")
    if not secret or not signature_header:
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.strip())


def verify_meta_verify_token(token: str | None) -> bool:
    expected = settings_secret("meta_webhook_verify_token")
    return bool(expected and token and hmac.compare_digest(expected, token))


def verify_google_key(key: str | None) -> bool:
    expected = settings_secret("google_lead_form_key")
    return bool(expected and key and hmac.compare_digest(expected, key))


def settings_secret(name: str) -> str:
    from app.config import settings

    return str(getattr(settings, name, "") or "")


def record_webhook_receipt(
    session: Session, *, provider: str, event_id: str, organization_id: str | None
) -> bool:
    """Return True the first time an event id is seen, False for repeats."""
    exists = session.scalar(
        select(WebhookReceipt).where(
            WebhookReceipt.provider == provider,
            WebhookReceipt.event_id == event_id,
        )
    )
    if exists:
        return False
    session.add(
        WebhookReceipt(provider=provider, event_id=event_id, organization_id=organization_id)
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return False
    return True
