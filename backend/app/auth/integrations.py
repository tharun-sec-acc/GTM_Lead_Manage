import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import TenantContext, get_tenant_context, require_role
from app.auth.models import OAuthConnection, now
from app.config import settings
from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integrations", tags=["Integration Lifecycle"])


@router.get("/status")
def get_integrations_status(
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Get the connection status and health of all third-party integrations
    for the current organization and user.
    """
    org_id = ctx.org_id
    user_id = ctx.user.id if ctx.user else None

    # Query OAuth connections for this org
    connections = session.scalars(
        select(OAuthConnection).where(OAuthConnection.organization_id == org_id)
    ).all()

    conn_by_provider = {c.provider: c for c in connections}

    # Google status
    google_conn = conn_by_provider.get("google")
    # Also check legacy Google credential if exists
    legacy_google_connected = False
    legacy_google_email = ""
    try:
        from app.models import GoogleOAuthCredential
        g_cred = session.scalar(select(GoogleOAuthCredential).limit(1))
        if g_cred:
            legacy_google_connected = True
            legacy_google_email = g_cred.organizer_email
    except Exception:
        pass

    google_status = {
        "provider": "google",
        "display_name": "Google Workspace (Meet, Calendar, Gmail)",
        "connected": (google_conn is not None and google_conn.status == "connected") or legacy_google_connected,
        "status": google_conn.status if google_conn else ("connected" if legacy_google_connected else "not_connected"),
        "account_email": google_conn.account_email if google_conn else legacy_google_email,
        "scopes": google_conn.scopes if google_conn else ["calendar.freebusy", "meetings.space.created"],
        "capabilities": ["Google Meet", "Google Calendar", "Gmail Sending", "Google Drive"],
        "updated_at": google_conn.updated_at if google_conn else None,
        "error_message": google_conn.error_message if google_conn else None,
        "connect_url": "/google/oauth/start",
    }

    # Microsoft status
    ms_conn = conn_by_provider.get("microsoft")
    legacy_ms_connected = False
    legacy_ms_email = ""
    try:
        from app.models import MicrosoftOAuthCredential
        m_cred = session.scalar(select(MicrosoftOAuthCredential).limit(1))
        if m_cred:
            legacy_ms_connected = True
            legacy_ms_email = m_cred.organizer_email
    except Exception:
        pass

    ms_status = {
        "provider": "microsoft",
        "display_name": "Microsoft 365 (Teams, Outlook, Calendar)",
        "connected": (ms_conn is not None and ms_conn.status == "connected") or legacy_ms_connected,
        "status": ms_conn.status if ms_conn else ("connected" if legacy_ms_connected else "not_connected"),
        "account_email": ms_conn.account_email if ms_conn else legacy_ms_email,
        "scopes": ms_conn.scopes if ms_conn else ["User.Read", "Calendars.ReadBasic", "OnlineMeetings.ReadWrite"],
        "capabilities": ["Microsoft Teams Meetings", "Outlook Calendar", "Exchange Email"],
        "updated_at": ms_conn.updated_at if ms_conn else None,
        "error_message": ms_conn.error_message if ms_conn else None,
        "connect_url": "/microsoft/oauth/start",
    }

    # Zoho status
    zoho_conn = conn_by_provider.get("zoho")
    legacy_zoho_connected = False
    legacy_zoho_email = ""
    try:
        from app.zoho.models import ZohoConnection
        z_conn = session.scalar(select(ZohoConnection).where(ZohoConnection.is_active.is_(True)).limit(1))
        if z_conn:
            legacy_zoho_connected = True
            legacy_zoho_email = z_conn.user_email or z_conn.org_name
    except Exception:
        pass

    zoho_status = {
        "provider": "zoho",
        "display_name": "Zoho CRM (v8 API)",
        "connected": (zoho_conn is not None and zoho_conn.status == "connected") or legacy_zoho_connected,
        "status": zoho_conn.status if zoho_conn else ("connected" if legacy_zoho_connected else "not_connected"),
        "account_email": zoho_conn.account_email if zoho_conn else legacy_zoho_email,
        "scopes": zoho_conn.scopes if zoho_conn else ["ZohoCRM.modules.ALL", "ZohoCRM.users.READ"],
        "capabilities": ["Bi-directional Leads Sync", "Contacts", "Deals Sync", "Conflict Resolution"],
        "updated_at": zoho_conn.updated_at if zoho_conn else None,
        "error_message": zoho_conn.error_message if zoho_conn else None,
        "connect_url": "/zoho/oauth/authorize",
    }

    # Apollo API status
    apollo_configured = bool(settings.apollo_api_key)
    apollo_status = {
        "provider": "apollo",
        "display_name": "Apollo.io Lead & Contact Intelligence",
        "connected": apollo_configured,
        "status": "connected" if apollo_configured else "not_connected",
        "account_email": "API Key Configured" if apollo_configured else "",
        "scopes": ["people.search", "people.enrich", "organizations.search"],
        "capabilities": ["B2B Contact Discovery", "Email Finding", "Company Enrichment"],
        "updated_at": None,
        "error_message": None,
        "connect_url": None,
    }

    # AWS Bedrock status
    bedrock_configured = bool(settings.bedrock_model_id and settings.aws_region)
    bedrock_status = {
        "provider": "bedrock",
        "display_name": "AWS Bedrock Generative AI & Intelligence",
        "connected": bedrock_configured,
        "status": "connected" if bedrock_configured else "not_connected",
        "account_email": f"Region: {settings.aws_region or 'none'}",
        "scopes": ["bedrock:InvokeModel"],
        "capabilities": ["Email Personalization", "Meeting Summarization", "Company Intelligence Agents"],
        "updated_at": None,
        "error_message": None,
        "connect_url": None,
    }

    return {
        "organization_id": org_id,
        "organization_name": ctx.organization.name,
        "integrations": [
            google_status,
            ms_status,
            zoho_status,
            apollo_status,
            bedrock_status,
        ],
    }


@router.post("/{provider}/disconnect")
def disconnect_integration(
    provider: str,
    ctx: TenantContext = Depends(require_role("admin")),
    session: Session = Depends(get_db),
):
    """Disconnect an external integration provider and revoke/purge tokens."""
    provider = provider.lower().strip()
    if provider not in ("google", "microsoft", "zoho"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown provider.")

    connections = session.scalars(
        select(OAuthConnection).where(
            OAuthConnection.organization_id == ctx.org_id,
            OAuthConnection.provider == provider,
        )
    ).all()

    for conn in connections:
        conn.status = "disconnected"
        conn.error_message = "Disconnected by user."
        conn.updated_at = now()

    # Also clean legacy records if any
    if provider == "google":
        try:
            from app.models import GoogleOAuthCredential
            for c in session.scalars(select(GoogleOAuthCredential)).all():
                session.delete(c)
        except Exception:
            pass
    elif provider == "microsoft":
        try:
            from app.models import MicrosoftOAuthCredential
            for c in session.scalars(select(MicrosoftOAuthCredential)).all():
                session.delete(c)
        except Exception:
            pass
    elif provider == "zoho":
        try:
            from app.zoho.models import ZohoConnection
            for z in session.scalars(select(ZohoConnection)).all():
                z.is_active = False
        except Exception:
            pass

    session.commit()
    logger.info("Provider %s disconnected for organization %s", provider, ctx.org_id)
    return {"status": "ok", "message": f"{provider.capitalize()} integration has been disconnected."}
