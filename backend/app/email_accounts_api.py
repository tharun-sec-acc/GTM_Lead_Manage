import hashlib
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import TenantContext, get_tenant_context, require_role
from app.auth.models import OAuthConnection, User, now
from app.auth.security import decrypt_token, encrypt_token
from app.config import settings
from app.database import get_db
from app.email_provider import EmailProviderError, get_email_provider
from app.email_sender import EmailSendError, send_email_via_account

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/email-accounts", tags=["Email Accounts & Sending"])

STATE_COOKIE = "gtm_email_oauth_state"


class DirectEmailRequest(BaseModel):
    account_id: str | None = Field(default=None, description="ID of connected OAuth email account. If omitted, uses default.")
    lead_id: str | None = Field(default=None, description="Optional associated lead ID")
    contact_id: str | None = Field(default=None, description="Optional associated contact ID")
    recipient: EmailStr = Field(description="Recipient email address")
    subject: str = Field(min_length=1, max_length=500, description="Email subject")
    body_html: str = Field(min_length=1, description="HTML formatted email body")
    body_text: str | None = Field(default=None, description="Optional plain-text fallback")
    cc: list[EmailStr] = Field(default_factory=list, description="CC recipient email addresses")
    bcc: list[EmailStr] = Field(default_factory=list, description="BCC recipient email addresses")


@router.get("")
def list_email_accounts(
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all connected email accounts available for sending in the current organization."""
    org_id = ctx.org_id
    user_id = ctx.user.id if ctx.user else None

    # Retrieve all google and microsoft connections for this org/user
    stmt = (
        select(OAuthConnection)
        .where(
            OAuthConnection.organization_id == org_id,
            OAuthConnection.provider.in_(["google", "microsoft"]),
            OAuthConnection.status != "disconnected",
        )
        .order_by(OAuthConnection.created_at.desc())
    )
    connections = session.scalars(stmt).all()

    items = []
    for c in connections:
        meta = dict(c.connection_metadata or {})
        is_default = bool(meta.get("is_default", False))
        items.append({
            "id": c.id,
            "provider": c.provider,
            "display_name": "Gmail / Google Workspace" if c.provider == "google" else "Microsoft Outlook / 365",
            "account_email": c.account_email,
            "status": c.status,
            "is_default": is_default,
            "scopes": c.scopes,
            "error_message": c.error_message,
            "last_sync_at": meta.get("last_sync_at"),
            "last_synced_count": meta.get("last_synced_count", 0),
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            "is_owner": c.user_id == user_id,
        })
    return items


@router.post("/{account_id}/default")
def set_default_email_account(
    account_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    """Mark an account as the user's default sender."""
    org_id = ctx.org_id
    user_id = ctx.user.id if ctx.user else None

    connections = session.scalars(
        select(OAuthConnection).where(
            OAuthConnection.organization_id == org_id,
            OAuthConnection.provider.in_(["google", "microsoft"]),
        )
    ).all()

    target = None
    for c in connections:
        meta = dict(c.connection_metadata or {})
        if c.id == account_id:
            target = c
            meta["is_default"] = True
        else:
            meta["is_default"] = False
        c.connection_metadata = meta

    if not target:
        raise HTTPException(status_code=404, detail="Email account not found.")

    session.commit()
    return {"message": f"{target.account_email} set as default sending account."}


@router.post("/{account_id}/disconnect")
def disconnect_email_account(
    account_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    """Disconnect and revoke an email sending account."""
    conn = session.get(OAuthConnection, account_id)
    if not conn or conn.organization_id != ctx.org_id:
        raise HTTPException(status_code=404, detail="Email account not found.")

    conn.status = "disconnected"
    conn.refresh_token_encrypted = b""
    conn.access_token_encrypted = None
    conn.error_message = "Disconnected by user."
    session.commit()
    return {"message": "Email account disconnected successfully."}


@router.post("/{account_id}/sync")
def sync_email_account_inbox(
    account_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    """
    Manually trigger synchronization of incoming messages, match customer replies,
    and suppress future sequence outreach for any lead that replied.
    """
    conn = session.get(OAuthConnection, account_id)
    if not conn or conn.organization_id != ctx.org_id:
        raise HTTPException(status_code=404, detail="Email account not found.")

    if conn.status != "connected":
        raise HTTPException(status_code=400, detail=f"Cannot sync account with status: {conn.status}")

    try:
        provider = get_email_provider(conn)
        result = provider.sync_inbox(session, max_messages=50)
        return {
            "success": True,
            "account_email": conn.account_email,
            "provider": conn.provider,
            "synced_count": result.get("synced_count", 0),
            "matched_replies": result.get("matched_replies", 0),
            "last_sync_at": conn.connection_metadata.get("last_sync_at") if conn.connection_metadata else None,
        }
    except EmailProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error synchronizing inbox for %s: %s", conn.account_email, exc)
        raise HTTPException(status_code=500, detail=f"Inbox synchronization failed: {exc}") from exc


# ---------------- Google OAuth for Gmail Sending & Reading ----------------

GMAIL_SEND_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]


@router.get("/oauth/google/start")
def start_google_email_oauth(
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    """Initiate Google OAuth specifically requesting gmail.send scope."""
    if not settings.google_client_id:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured on this server.")

    state_token = secrets.token_urlsafe(32)
    state_data = {
        "token": state_token,
        "org_id": ctx.org_id,
        "user_id": ctx.user.id if ctx.user else None,
        "provider": "google",
    }

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": "http://localhost:8000/api/email-accounts/oauth/google/callback",
        "response_type": "code",
        "scope": " ".join(GMAIL_SEND_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state_token,
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    response = RedirectResponse(auth_url, status_code=302)
    response.set_cookie(
        key=STATE_COOKIE,
        value=json.dumps(state_data),
        max_age=600,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/oauth/google/callback")
def google_email_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: Session = Depends(get_db),
):
    """Handle Google OAuth callback and save encrypted refresh token for Gmail sending."""
    frontend_redirect = "http://localhost:3000/settings/email-accounts"

    if error:
        return RedirectResponse(f"{frontend_redirect}?error={error}", status_code=302)

    cookie_val = request.cookies.get(STATE_COOKIE)
    if not cookie_val:
        return RedirectResponse(f"{frontend_redirect}?error=missing_state_cookie", status_code=302)

    try:
        state_data = json.loads(cookie_val)
    except Exception:
        return RedirectResponse(f"{frontend_redirect}?error=invalid_state_data", status_code=302)

    if state_data.get("token") != state:
        return RedirectResponse(f"{frontend_redirect}?error=state_mismatch", status_code=302)

    org_id = state_data.get("org_id")
    user_id = state_data.get("user_id")

    # Exchange code for tokens
    try:
        token_res = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": "http://localhost:8000/api/email-accounts/oauth/google/callback",
            },
            timeout=15,
        )
        token_data = token_res.json()
        if token_res.status_code != 200:
            err = token_data.get("error_description") or token_res.text
            return RedirectResponse(f"{frontend_redirect}?error={err}", status_code=302)

        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")

        # Get authenticated user's email
        userinfo_res = httpx.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        userinfo = userinfo_res.json()
        account_email = userinfo.get("email", "").lower().strip()
        if not account_email:
            return RedirectResponse(f"{frontend_redirect}?error=no_email_returned", status_code=302)

        # Check existing connection or create
        existing = session.scalar(
            select(OAuthConnection).where(
                OAuthConnection.organization_id == org_id,
                OAuthConnection.provider == "google",
                OAuthConnection.account_email == account_email,
            )
        )

        refresh_enc = encrypt_token(refresh_token) if refresh_token else (existing.refresh_token_encrypted if existing else b"")
        access_enc = encrypt_token(access_token)

        if not existing:
            conn = OAuthConnection(
                organization_id=org_id,
                user_id=user_id,
                provider="google",
                account_email=account_email,
                refresh_token_encrypted=refresh_enc,
                access_token_encrypted=access_enc,
                access_token_expires_at=now(),
                scopes=GMAIL_SEND_SCOPES,
                status="connected",
                connection_metadata={"is_default": True},
            )
            session.add(conn)
        else:
            if refresh_token:
                existing.refresh_token_encrypted = refresh_enc
            existing.access_token_encrypted = access_enc
            existing.status = "connected"
            existing.error_message = None
            existing.scopes = GMAIL_SEND_SCOPES

        session.commit()
    except Exception as exc:
        logger.exception("Failed to complete Google Email OAuth: %s", exc)
        return RedirectResponse(f"{frontend_redirect}?error=oauth_completion_failed", status_code=302)

    response = RedirectResponse(f"{frontend_redirect}?success=google_connected", status_code=302)
    response.delete_cookie(STATE_COOKIE)
    return response


# ---------------- Microsoft OAuth for Outlook Sending & Reading ----------------

MS_OUTLOOK_SCOPES = [
    "offline_access",
    "User.Read",
    "Mail.Send",
    "Mail.Read",
]


@router.get("/oauth/microsoft/start")
def start_microsoft_email_oauth(
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    """Initiate Microsoft Entra ID OAuth specifically requesting Mail.Send scope."""
    if not settings.microsoft_client_id:
        raise HTTPException(status_code=503, detail="Microsoft OAuth is not configured on this server.")

    state_token = secrets.token_urlsafe(32)
    state_data = {
        "token": state_token,
        "org_id": ctx.org_id,
        "user_id": ctx.user.id if ctx.user else None,
        "provider": "microsoft",
    }

    tenant = settings.microsoft_tenant_id or "common"
    params = {
        "client_id": settings.microsoft_client_id,
        "response_type": "code",
        "redirect_uri": "http://localhost:8000/api/email-accounts/oauth/microsoft/callback",
        "response_mode": "query",
        "scope": " ".join(MS_OUTLOOK_SCOPES),
        "state": state_token,
        "prompt": "select_account",
    }
    auth_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?{urlencode(params)}"

    response = RedirectResponse(auth_url, status_code=302)
    response.set_cookie(
        key=STATE_COOKIE,
        value=json.dumps(state_data),
        max_age=600,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/oauth/microsoft/callback")
def microsoft_email_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: Session = Depends(get_db),
):
    """Handle Microsoft OAuth callback and save encrypted refresh token for Outlook sending."""
    frontend_redirect = "http://localhost:3000/settings/email-accounts"

    if error:
        return RedirectResponse(f"{frontend_redirect}?error={error}", status_code=302)

    cookie_val = request.cookies.get(STATE_COOKIE)
    if not cookie_val:
        return RedirectResponse(f"{frontend_redirect}?error=missing_state_cookie", status_code=302)

    try:
        state_data = json.loads(cookie_val)
    except Exception:
        return RedirectResponse(f"{frontend_redirect}?error=invalid_state_data", status_code=302)

    if state_data.get("token") != state:
        return RedirectResponse(f"{frontend_redirect}?error=state_mismatch", status_code=302)

    org_id = state_data.get("org_id")
    user_id = state_data.get("user_id")

    tenant = settings.microsoft_tenant_id or "common"
    token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

    try:
        token_res = httpx.post(
            token_url,
            data={
                "client_id": settings.microsoft_client_id,
                "client_secret": settings.microsoft_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": "http://localhost:8000/api/email-accounts/oauth/microsoft/callback",
                "scope": " ".join(MS_OUTLOOK_SCOPES),
            },
            timeout=15,
        )
        token_data = token_res.json()
        if token_res.status_code != 200:
            err = token_data.get("error_description") or token_res.text
            return RedirectResponse(f"{frontend_redirect}?error={err}", status_code=302)

        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")

        # Get user profile email from Graph /me
        me_res = httpx.get(
            f"{settings.microsoft_graph_base_url.rstrip('/')}/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        me_data = me_res.json()
        account_email = (me_data.get("mail") or me_data.get("userPrincipalName", "")).lower().strip()
        if not account_email:
            return RedirectResponse(f"{frontend_redirect}?error=no_email_returned", status_code=302)

        existing = session.scalar(
            select(OAuthConnection).where(
                OAuthConnection.organization_id == org_id,
                OAuthConnection.provider == "microsoft",
                OAuthConnection.account_email == account_email,
            )
        )

        refresh_enc = encrypt_token(refresh_token) if refresh_token else (existing.refresh_token_encrypted if existing else b"")
        access_enc = encrypt_token(access_token)

        if not existing:
            conn = OAuthConnection(
                organization_id=org_id,
                user_id=user_id,
                provider="microsoft",
                account_email=account_email,
                refresh_token_encrypted=refresh_enc,
                access_token_encrypted=access_enc,
                access_token_expires_at=now(),
                scopes=MS_OUTLOOK_SCOPES,
                status="connected",
                connection_metadata={"is_default": True},
            )
            session.add(conn)
        else:
            if refresh_token:
                existing.refresh_token_encrypted = refresh_enc
            existing.access_token_encrypted = access_enc
            existing.status = "connected"
            existing.error_message = None
            existing.scopes = MS_OUTLOOK_SCOPES

        session.commit()
    except Exception as exc:
        logger.exception("Failed to complete Microsoft Email OAuth: %s", exc)
        return RedirectResponse(f"{frontend_redirect}?error=oauth_completion_failed", status_code=302)

    response = RedirectResponse(f"{frontend_redirect}?success=microsoft_connected", status_code=302)
    response.delete_cookie(STATE_COOKIE)
    return response


# ---------------- Direct Email Dispatch ----------------

@router.post("/send")
def send_direct_email(
    payload: DirectEmailRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    """
    Send an email directly to a customer or lead using the user's authorized Gmail
    or Microsoft Outlook account.
    """
    org_id = ctx.org_id
    user_id = ctx.user.id if ctx.user else None

    # Find the appropriate connection
    if payload.account_id:
        conn = session.get(OAuthConnection, payload.account_id)
        if not conn or conn.organization_id != org_id:
            raise HTTPException(status_code=404, detail="Selected email account was not found.")
    else:
        # Pick default or first active connection
        stmt = (
            select(OAuthConnection)
            .where(
                OAuthConnection.organization_id == org_id,
                OAuthConnection.provider.in_(["google", "microsoft"]),
                OAuthConnection.status == "connected",
            )
            .order_by(OAuthConnection.updated_at.desc())
        )
        connections = session.scalars(stmt).all()
        conn = next((c for c in connections if c.connection_metadata.get("is_default")), None) or (connections[0] if connections else None)

    if not conn or conn.status != "connected":
        raise HTTPException(
            status_code=400,
            detail="No connected email account available. Please connect your Gmail or Microsoft Outlook account in Settings > Email Accounts.",
        )

    try:
        result = send_email_via_account(
            session=session,
            conn=conn,
            recipient=payload.recipient,
            subject=payload.subject,
            body_html=payload.body_html,
            body_text=payload.body_text,
            cc=[str(c) for c in payload.cc] if payload.cc else None,
            bcc=[str(b) for b in payload.bcc] if payload.bcc else None,
            lead_id=payload.lead_id,
            contact_id=payload.contact_id,
            user_id=user_id,
            org_id=org_id,
        )
        return {
            "success": True,
            "provider": conn.provider,
            "sender_email": conn.account_email,
            "recipient": payload.recipient,
            "subject": payload.subject,
            "message_id": result.get("message_id"),
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }
    except EmailSendError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error sending direct email: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to send email: {exc}") from exc
