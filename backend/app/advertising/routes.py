"""Advertising connectors, campaign reporting, forms and lead-capture webhooks.

Permissions follow the CRM module: reads need tenant context, writes need
``rep``, and anything that changes org-level configuration (connections, forms,
provider sync) needs ``manager``.
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.advertising import providers, service
from app.advertising.models import (
    AdCampaign,
    AdConnection,
    CapturedSubmission,
    LeadCaptureForm,
)
from app.advertising.providers import ProviderError, ProviderNotConfigured
from app.advertising.schemas import (
    CampaignUpsertRequest,
    ConnectionCreate,
    FormCreate,
    FormUpdate,
    GoogleLeadWebhook,
    MetricSyncRequest,
    WebsiteSubmission,
)
from app.auth.dependencies import TenantContext, get_tenant_context, require_role
from app.auth.models import AuditLog, Organization
from app.config import settings
from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/advertising", tags=["Advertising & Lead Capture"])
public_router = APIRouter(prefix="/public", tags=["Advertising Public"])
webhook_router = APIRouter(prefix="/public/webhooks", tags=["Advertising Webhooks"])


def _audit(
    session: Session,
    ctx: TenantContext,
    request: Request,
    action: str,
    resource_type: str,
    resource_id: str,
    details: dict | None = None,
) -> None:
    session.add(
        AuditLog(
            organization_id=ctx.org_id,
            user_id=ctx.user.id if ctx.user else None,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            ip_address=request.client.host if request.client else None,
        )
    )


def _require_campaign(session: Session, ctx: TenantContext, campaign_id: str) -> AdCampaign:
    campaign = session.get(AdCampaign, campaign_id)
    if not campaign or campaign.organization_id != ctx.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaign not found.")
    return campaign


def _require_form(session: Session, ctx: TenantContext, form_id: str) -> LeadCaptureForm:
    form = session.get(LeadCaptureForm, form_id)
    if not form or form.organization_id != ctx.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Form not found.")
    return form


# ------------------------------- providers --------------------------------


@router.get("/providers")
def list_providers(ctx: TenantContext = Depends(get_tenant_context)):
    """Capability catalogue. Secrets are never included."""
    return [
        {
            "provider": "meta",
            "name": "Meta Ads (Facebook & Instagram)",
            "app_configured": providers.meta_app_configured(),
            "capabilities": ["campaign_reporting", "lead_ads", "daily_insights"],
            "writes_supported": False,
            "requires": [
                "A Meta app with Marketing API access",
                "A system-user or user access token with ads_read + leads_retrieval",
                "Webhook subscription for leadgen with a verify token and app secret",
            ],
        },
        {
            "provider": "google",
            "name": "Google Ads",
            "app_configured": providers.google_app_configured(),
            "capabilities": ["campaign_reporting", "lead_form_submissions"],
            "writes_supported": False,
            "requires": [
                "Google Ads developer token with API access level approved",
                "OAuth client for offline access",
                "A lead form extension asset configured in Google Ads",
            ],
        },
    ]


# ------------------------------ connections -------------------------------


@router.get("/connections")
def list_connections(
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    return [
        service.serialize_connection(item)
        for item in service.list_connections(session, ctx.organization)
    ]


@router.post("/connections", status_code=201)
def create_connection(
    data: ConnectionCreate,
    request: Request,
    ctx: TenantContext = Depends(require_role("manager")),
    session: Session = Depends(get_db),
):
    if not settings.advertising_enabled:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Advertising connectors are disabled by configuration.",
        )
    metadata = {}
    if data.login_customer_id:
        metadata["login_customer_id"] = data.login_customer_id
    try:
        connection = service.create_connection(
            session,
            ctx.organization,
            provider=data.provider,
            external_account_id=data.external_account_id,
            account_name=data.account_name,
            access_token=data.access_token,
            refresh_token=data.refresh_token,
            token_expires_at=data.token_expires_at,
            scopes=data.scopes,
            metadata=metadata,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    _audit(
        session,
        ctx,
        request,
        "advertising_connection_saved",
        "ad_connection",
        connection.id,
        {"provider": connection.provider, "account": connection.external_account_id},
    )
    session.commit()
    return service.serialize_connection(connection)


@router.post("/connections/{connection_id}/sync")
def sync_connection(
    connection_id: str,
    request: Request,
    ctx: TenantContext = Depends(require_role("manager")),
    session: Session = Depends(get_db),
):
    """Pull read-only campaign and insight data from the provider."""
    try:
        connection = service.require_connection(session, ctx.organization, connection_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    if not settings.advertising_sync_enabled:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Provider synchronisation is disabled by configuration.",
        )
    try:
        result = service.sync_connection(session, ctx.organization, connection)
    except ProviderNotConfigured as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    _audit(
        session,
        ctx,
        request,
        "advertising_connection_synced",
        "ad_connection",
        connection.id,
        {"provider": connection.provider, **result},
    )
    session.commit()
    return {"connection": service.serialize_connection(connection), **result}


@router.delete("/connections/{connection_id}")
def disconnect_connection(
    connection_id: str,
    request: Request,
    ctx: TenantContext = Depends(require_role("manager")),
    session: Session = Depends(get_db),
):
    try:
        connection = service.require_connection(session, ctx.organization, connection_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    connection = service.disconnect_connection(session, connection)
    _audit(
        session,
        ctx,
        request,
        "advertising_connection_disconnected",
        "ad_connection",
        connection.id,
        {"provider": connection.provider},
    )
    session.commit()
    return service.serialize_connection(connection)


# -------------------------------- campaigns -------------------------------


@router.post("/connections/{connection_id}/campaigns")
def upsert_campaigns(
    connection_id: str,
    data: CampaignUpsertRequest,
    request: Request,
    ctx: TenantContext = Depends(require_role("manager")),
    session: Session = Depends(get_db),
):
    """Record campaign rows already retrieved from the provider.

    Used by the scheduled sync job and by operators importing a provider
    export. Rows describe provider state; nothing is generated here.
    """
    try:
        connection = service.require_connection(session, ctx.organization, connection_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    result = service.upsert_campaigns(
        session,
        ctx.organization,
        connection,
        [row.model_dump() for row in data.campaigns],
    )
    _audit(
        session,
        ctx,
        request,
        "advertising_campaigns_recorded",
        "ad_connection",
        connection.id,
        result,
    )
    session.commit()
    return result


@router.get("/campaigns")
def list_campaigns(
    provider: str | None = None,
    campaign_status: str | None = Query(default=None, alias="status"),
    query: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    statement = select(AdCampaign).where(AdCampaign.organization_id == ctx.org_id)
    if provider:
        statement = statement.where(AdCampaign.provider == provider)
    if campaign_status:
        statement = statement.where(AdCampaign.status == campaign_status)
    if query and query.strip():
        like = f"%{query.strip()}%"
        statement = statement.where(
            or_(AdCampaign.name.ilike(like), AdCampaign.external_id.ilike(like))
        )
    rows = session.scalars(
        statement.order_by(AdCampaign.spend_cents.desc(), AdCampaign.name).limit(limit)
    ).all()
    return [service.serialize_campaign(campaign) for campaign in rows]


@router.get("/campaigns/{campaign_id}")
def get_campaign(
    campaign_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    campaign = _require_campaign(session, ctx, campaign_id)
    return {
        **service.serialize_campaign(campaign),
        "cpl_cents": (
            campaign.spend_cents // campaign.provider_leads if campaign.provider_leads else None
        ),
    }


@router.post("/campaigns/{campaign_id}/metrics")
def record_metrics(
    campaign_id: str,
    data: MetricSyncRequest,
    ctx: TenantContext = Depends(require_role("manager")),
    session: Session = Depends(get_db),
):
    """Upsert daily metrics supplied by a provider export or the sync job."""
    campaign = _require_campaign(session, ctx, campaign_id)
    recorded = service.record_daily_metrics(
        session, ctx.organization, campaign, [row.model_dump() for row in data.rows]
    )
    return {"campaign": service.serialize_campaign(campaign), "recorded": recorded}


# --------------------------------- reports --------------------------------


@router.get("/reports/campaigns")
def campaign_report(
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    return service.campaign_report(session, ctx.organization)


@router.get("/reports/summary")
def report_summary(
    days: int = Query(default=30, ge=1, le=365),
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    report = service.campaign_report(session, ctx.organization)
    return {
        "window_days": days,
        "totals": report["totals"],
        "channels": service.channel_summary(session, ctx.organization),
        "submissions": service.submission_summary(session, ctx.organization),
        "attribution_model": report["attribution_model"],
        "caveat": report["caveat"],
    }


# ---------------------------------- forms ---------------------------------


@router.get("/forms")
def list_forms(
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    rows = session.scalars(
        select(LeadCaptureForm)
        .where(LeadCaptureForm.organization_id == ctx.org_id)
        .order_by(LeadCaptureForm.created_at.desc())
    ).all()
    return [service.serialize_form(form) for form in rows]


@router.post("/forms", status_code=201)
def create_form(
    data: FormCreate,
    request: Request,
    ctx: TenantContext = Depends(require_role("manager")),
    session: Session = Depends(get_db),
):
    clash = session.scalar(
        select(LeadCaptureForm).where(
            LeadCaptureForm.organization_id == ctx.org_id,
            LeadCaptureForm.slug == data.slug,
        )
    )
    if clash:
        raise HTTPException(status.HTTP_409_CONFLICT, "This form slug is already in use.")

    form = LeadCaptureForm(organization_id=ctx.org_id, **data.model_dump())
    session.add(form)
    session.commit()
    session.refresh(form)
    _audit(session, ctx, request, "capture_form_created", "capture_form", form.id, {"slug": form.slug})
    session.commit()
    return service.serialize_form(form)


@router.patch("/forms/{form_id}")
def update_form(
    form_id: str,
    data: FormUpdate,
    ctx: TenantContext = Depends(require_role("manager")),
    session: Session = Depends(get_db),
):
    form = _require_form(session, ctx, form_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        if value is None and key in {"name", "fields", "requires_consent", "is_active"}:
            continue
        setattr(form, key, value)
    session.commit()
    return service.serialize_form(form)


@router.delete("/forms/{form_id}", status_code=204)
def delete_form(
    form_id: str,
    ctx: TenantContext = Depends(require_role("manager")),
    session: Session = Depends(get_db),
):
    form = _require_form(session, ctx, form_id)
    session.delete(form)
    session.commit()
    return None


@router.get("/forms/{form_id}/embed")
def form_embed(
    form_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    """Ready-to-paste snippet for an existing website."""
    form = _require_form(session, ctx, form_id)
    base = (settings.public_base_url or "http://localhost:8000").rstrip("/")
    endpoint = f"{base}/api/public/forms/{form.slug}/submit"
    snippet = (
        f'<form id="gtm-{form.slug}" data-endpoint="{endpoint}">'
        '<input name="name" placeholder="Name" required />'
        '<input name="email" type="email" placeholder="Work email" required />'
        '<input name="company" placeholder="Company" />'
        '<input name="phone" placeholder="Phone" />'
        '<textarea name="message" placeholder="How can we help?"></textarea>'
        '<input name="gtm_hp" tabindex="-1" autocomplete="off" aria-hidden="true" '
        'style="position:absolute;left:-9999px" />'
        f'<label><input type="checkbox" name="consent" required /> '
        f'{(form.consent_text or "I agree to be contacted about this enquiry.")}</label>'
        '<button type="submit">Send</button></form>'
        "<script>(function(){var f=document.getElementById('gtm-" + form.slug + "');"
        "if(!f)return;f.addEventListener('submit',function(e){e.preventDefault();"
        "var d=new FormData(f);var u=new URLSearchParams(location.search);"
        "var body={name:d.get('name'),email:d.get('email'),company:d.get('company'),"
        "phone:d.get('phone'),message:d.get('message'),consent:!!d.get('consent'),"
        "honeypot:d.get('gtm_hp')||null,campaign_id:u.get('utm_campaign'),"
        "landing_page:location.href,referrer:document.referrer,"
        "utm:{utm_source:u.get('utm_source'),utm_medium:u.get('utm_medium'),"
        "utm_campaign:u.get('utm_campaign'),utm_term:u.get('utm_term'),"
        "utm_content:u.get('utm_content')}};"
        "fetch(f.dataset.endpoint,{method:'POST',headers:{'Content-Type':'application/json'},"
        "body:JSON.stringify(body)}).then(function(){f.reset();"
        "f.innerHTML='<p>Thanks — we will be in touch.</p>';});});})();</script>"
    )
    return {"slug": form.slug, "endpoint": endpoint, "snippet": snippet}


@router.get("/forms/{form_id}/submissions")
def form_submissions(
    form_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    form = _require_form(session, ctx, form_id)
    rows = session.scalars(
        select(CapturedSubmission)
        .where(
            CapturedSubmission.organization_id == ctx.org_id,
            CapturedSubmission.form_id == form.id,
        )
        .order_by(CapturedSubmission.created_at.desc())
        .limit(limit)
    ).all()
    return [service.serialize_submission(row) for row in rows]


@router.get("/submissions")
def list_submissions(
    submission_status: str | None = Query(default=None, alias="status"),
    provider: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    statement = select(CapturedSubmission).where(
        CapturedSubmission.organization_id == ctx.org_id
    )
    if submission_status:
        statement = statement.where(CapturedSubmission.status == submission_status)
    if provider:
        statement = statement.where(CapturedSubmission.provider == provider)
    rows = session.scalars(
        statement.order_by(CapturedSubmission.created_at.desc()).limit(limit)
    ).all()
    return [service.serialize_submission(row) for row in rows]


@router.post("/submissions/{submission_id}/process")
def process_submission(
    submission_id: str,
    request: Request,
    ctx: TenantContext = Depends(require_role("manager")),
    session: Session = Depends(get_db),
):
    """Retry a Meta submission that arrived before credentials were connected."""
    submission = session.get(CapturedSubmission, submission_id)
    if not submission or submission.organization_id != ctx.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found.")
    if submission.provider != "meta" or not submission.provider_submission_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Only Meta lead submissions with a provider id can be processed.",
        )
    connection = session.scalar(
        select(AdConnection)
        .where(
            AdConnection.organization_id == ctx.org_id,
            AdConnection.provider == "meta",
        )
        .order_by(AdConnection.created_at)
    )
    try:
        processed = service.process_meta_leadgen(
            session, ctx.organization, connection, submission.provider_submission_id
        )
    except ProviderNotConfigured as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    _audit(
        session,
        ctx,
        request,
        "advertising_submission_processed",
        "lead_submission",
        processed.id,
        {"provider": "meta", "status": processed.status},
    )
    session.commit()
    return service.serialize_submission(processed)


# ------------------------------ public form -------------------------------


def _form_by_slug(session: Session, slug: str) -> LeadCaptureForm | None:
    return session.scalar(
        select(LeadCaptureForm).where(
            LeadCaptureForm.slug == slug, LeadCaptureForm.is_active.is_(True)
        )
    )


@public_router.post("/forms/{slug}/submit", status_code=201)
def submit_website_form(
    slug: str,
    data: WebsiteSubmission,
    session: Session = Depends(get_db),
):
    """Public lead capture for an existing website (no tenant session needed)."""
    form = _form_by_slug(session, slug)
    if form is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Form not found.")
    if not settings.advertising_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Lead capture is disabled.")

    # Honeypot: accept silently so bots get no feedback, store nothing.
    if (data.honeypot or "").strip():
        return {"status": "accepted", "message": "Thanks."}

    if form.requires_consent and not data.consent:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Consent is required before we can contact you.",
        )
    if not (data.email or data.phone):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Please provide an email address or a phone number.",
        )

    organization = session.get(Organization, form.organization_id)
    if organization is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Form not found.")

    utm = data.utm.model_dump(exclude_none=True)
    submission = service.record_submission(
        session,
        organization,
        provider="website",
        fields={
            "name": data.name,
            "email": data.email,
            "phone": data.phone,
            "company": data.company,
            "message": data.message,
        },
        form=form,
        campaign_external_id=data.campaign_id,
        campaign_name=utm.get("utm_campaign"),
        utm=utm,
        landing_page=data.landing_page,
        referrer=data.referrer,
        source="website_form",
        payload=data.model_dump(),
    )
    return {
        "status": submission.status,
        "message": form.success_message or "Thanks — we will be in touch.",
        "redirect_url": form.redirect_url,
    }


# -------------------------------- webhooks --------------------------------


@webhook_router.get("/meta")
def meta_webhook_verification(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    if hub_mode != "subscribe" or not service.verify_meta_verify_token(hub_verify_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Verification failed.")
    return int(hub_challenge) if hub_challenge and hub_challenge.isdigit() else hub_challenge


@webhook_router.post("/meta")
async def meta_webhook(request: Request, session: Session = Depends(get_db)):
    """Meta Lead Ads delivery. Requires a valid X-Hub-Signature-256."""
    raw = await request.body()
    if not service.verify_meta_signature(raw, request.headers.get("x-hub-signature-256")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature.")

    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid JSON body.")

    accepted = 0
    pending = 0
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value") or {}
            leadgen_id = value.get("leadgen_id")
            form_id = value.get("form_id")
            if not leadgen_id:
                continue
            event_id = str(leadgen_id)
            form = session.scalar(
                select(LeadCaptureForm).where(
                    LeadCaptureForm.provider == "meta",
                    LeadCaptureForm.provider_form_id == form_id,
                )
            )
            organization = session.get(Organization, form.organization_id) if form else None
            if organization is None:
                logger.warning("Meta lead %s has no matching organization form.", leadgen_id)
                continue
            if not service.record_webhook_receipt(
                session, provider="meta", event_id=event_id, organization_id=organization.id
            ):
                continue
            connection = session.scalar(
                select(AdConnection)
                .where(
                    AdConnection.organization_id == organization.id,
                    AdConnection.provider == "meta",
                )
                .order_by(AdConnection.created_at)
            )
            try:
                service.process_meta_leadgen(
                    session, organization, connection, event_id, form=form
                )
                accepted += 1
            except (ProviderNotConfigured, ProviderError) as exc:
                # Keep the delivery so an operator can process it once credentials exist.
                service.store_received_submission(
                    session,
                    organization,
                    provider="meta",
                    provider_submission_id=event_id,
                    provider_form_id=form_id,
                    payload=value,
                    error=str(exc),
                )
                pending += 1

    return {"status": "ok", "accepted": accepted, "pending": pending}


@webhook_router.post("/google")
def google_lead_webhook(data: GoogleLeadWebhook, session: Session = Depends(get_db)):
    """Google Ads lead-form delivery, authenticated with the shared form key."""
    if not service.verify_google_key(data.google_key):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid lead form key.")

    form = None
    if data.form_id:
        form = session.scalar(
            select(LeadCaptureForm).where(
                LeadCaptureForm.provider == "google",
                LeadCaptureForm.provider_form_id == data.form_id,
            )
        )
    if form is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No Google lead form is registered for this form id.",
        )
    organization = session.get(Organization, form.organization_id)
    if organization is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found.")
    if not service.record_webhook_receipt(
        session, provider="google", event_id=data.lead_id, organization_id=organization.id
    ):
        return {"status": "duplicate"}

    submission = service.record_submission(
        session,
        organization,
        provider="google",
        fields=service.google_lead_fields(data.user_column_data),
        form=form,
        provider_submission_id=data.lead_id,
        provider_form_id=data.form_id,
        campaign_external_id=data.campaign_id,
        source="google_lead_form",
        payload=data.model_dump(),
    )
    return {"status": submission.status, "lead_id": submission.lead_id}
