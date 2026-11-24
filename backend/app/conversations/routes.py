"""Omnichannel inbox API: conversations, replies, consent and webhooks.

Reads need tenant context, writes need ``rep``, and channel accounts / consent
administration need ``manager``.
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import TenantContext, get_tenant_context, require_role
from app.auth.models import AuditLog, Organization, OrganizationMember
from app.config import settings
from app.conversations import service
from app.conversations.models import Conversation, ConversationAccount, ConversationMessage
from app.conversations.providers import (
    ChannelNotConfigured,
    ProviderError,
    SendingDisabled,
)
from app.conversations.schemas import (
    AccountCreate,
    ConsentRequest,
    ConversationCreate,
    ConversationUpdate,
    NoteRequest,
    ReplyRequest,
    SmsInboundWebhook,
)
from app.conversations.service import (
    ConversationAccount,
    consent_token,
    consent_from_token,
)
from app.conversations.service import ConsentBlocked
from app.database import get_db
from app.models import Lead

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["Omnichannel Inbox"])
webhook_router = APIRouter(prefix="/public/webhooks", tags=["Inbox Webhooks"])
public_router = APIRouter(prefix="/public/conversations", tags=["Inbox Public"])


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


def _conversation_or_404(session: Session, ctx: TenantContext, conversation_id: str) -> Conversation:
    try:
        return service.get_conversation(session, ctx.organization, conversation_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


def _validate_assignee(session: Session, ctx: TenantContext, assignee_id: str | None) -> None:
    if not assignee_id:
        return
    member = session.scalar(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == ctx.org_id,
            OrganizationMember.user_id == assignee_id,
            OrganizationMember.status == "active",
        )
    )
    if member is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Assignee is not an active member of this organization."
        )


# -------------------------------- metrics ---------------------------------


@router.get("/metrics")
def inbox_metrics(
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    return service.inbox_metrics(session, ctx.organization)


# ------------------------------ conversations -----------------------------


@router.get("")
def list_conversations(
    channel: str | None = None,
    conversation_status: str | None = Query(default=None, alias="status"),
    assignee_id: str | None = None,
    unassigned: bool = False,
    query: str | None = None,
    limit: int = Query(default=100, ge=1, le=300),
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    return service.list_conversations(
        session,
        ctx.organization,
        channel=channel,
        status_filter=conversation_status,
        assignee_id=assignee_id,
        unassigned=unassigned,
        query=query,
        limit=limit,
    )


@router.post("", status_code=201)
def create_conversation(
    data: ConversationCreate,
    request: Request,
    ctx: TenantContext = Depends(require_role("rep")),
    session: Session = Depends(get_db),
):
    lead = None
    if data.lead_id:
        lead = session.get(Lead, data.lead_id)
        if not lead or lead.organization_id != ctx.org_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found.")
    _validate_assignee(session, ctx, data.assignee_id)
    conversation = service.create_conversation(
        session,
        ctx.organization,
        channel=data.channel,
        lead_id=data.lead_id,
        subject=data.subject,
        assignee_id=data.assignee_id or (ctx.user.id if ctx.user else None),
        priority=data.priority,
        tags=data.tags,
        team=data.team,
    )
    _audit(
        session, ctx, request, "conversation_created", "conversation", conversation.id,
        {"channel": conversation.channel},
    )
    session.commit()
    return service.conversation_detail(session, conversation)


@router.get("/{conversation_id}")
def get_conversation(
    conversation_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    conversation = _conversation_or_404(session, ctx, conversation_id)
    return service.conversation_detail(session, conversation)


@router.patch("/{conversation_id}")
def update_conversation(
    conversation_id: str,
    data: ConversationUpdate,
    ctx: TenantContext = Depends(require_role("rep")),
    session: Session = Depends(get_db),
):
    conversation = _conversation_or_404(session, ctx, conversation_id)
    values = data.model_dump(exclude_unset=True)
    if "assignee_id" in values:
        _validate_assignee(session, ctx, values["assignee_id"])
        conversation.assignee_id = values["assignee_id"]
    if values.get("status"):
        conversation.status = values["status"]
        if values["status"] == "resolved":
            from app.auth.models import now

            conversation.resolved_at = now()
        else:
            conversation.resolved_at = None
    if values.get("priority"):
        conversation.priority = values["priority"]
    if "team" in values:
        conversation.team = values["team"]
    if values.get("tags") is not None:
        conversation.tags = values["tags"]
    session.commit()
    return service.conversation_detail(session, conversation)


@router.post("/{conversation_id}/read")
def mark_read(
    conversation_id: str,
    ctx: TenantContext = Depends(require_role("rep")),
    session: Session = Depends(get_db),
):
    conversation = _conversation_or_404(session, ctx, conversation_id)
    conversation.unread_count = 0
    session.commit()
    return {"id": conversation.id, "unread_count": 0}


@router.post("/{conversation_id}/messages", status_code=201)
def reply(
    conversation_id: str,
    data: ReplyRequest,
    request: Request,
    ctx: TenantContext = Depends(require_role("rep")),
    session: Session = Depends(get_db),
):
    conversation = _conversation_or_404(session, ctx, conversation_id)
    try:
        message = service.send_outbound(
            session,
            ctx.organization,
            conversation,
            body=data.body,
            user_id=ctx.user.id if ctx.user else None,
            subject=data.subject,
            template_name=data.template_name,
        )
    except SendingDisabled as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ChannelNotConfigured as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ConsentBlocked as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    _audit(
        session, ctx, request, "conversation_message_sent", "conversation", conversation.id,
        {"channel": conversation.channel, "message_id": message.id},
    )
    session.commit()
    return service.serialize_message(message)


@router.post("/{conversation_id}/notes", status_code=201)
def add_note(
    conversation_id: str,
    data: NoteRequest,
    ctx: TenantContext = Depends(require_role("rep")),
    session: Session = Depends(get_db),
):
    conversation = _conversation_or_404(session, ctx, conversation_id)
    message = service.record_note(
        session, conversation, body=data.body, user_id=ctx.user.id if ctx.user else None
    )
    return service.serialize_message(message)


# ------------------------------- accounts ---------------------------------


@router.get("/accounts/list")
def list_accounts(
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    return [service.serialize_account(item) for item in service.list_accounts(session, ctx.organization)]


@router.post("/accounts", status_code=201)
def create_account(
    data: AccountCreate,
    request: Request,
    ctx: TenantContext = Depends(require_role("manager")),
    session: Session = Depends(get_db),
):
    if not settings.conversation_send_enabled:
        # Accounts may be prepared before sending is switched on.
        logger.info("Creating messaging account while outbound messaging is disabled.")
    try:
        account = service.upsert_account(
            session,
            ctx.organization,
            channel=data.channel,
            provider=data.provider,
            sender_id=data.sender_id,
            display_name=data.display_name,
            credentials=data.credentials,
            config=data.config,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    _audit(
        session, ctx, request, "messaging_account_saved", "conversation_account", account.id,
        {"channel": account.channel, "provider": account.provider},
    )
    session.commit()
    return service.serialize_account(account)


@router.delete("/accounts/{account_id}", status_code=204)
def delete_account(
    account_id: str,
    ctx: TenantContext = Depends(require_role("manager")),
    session: Session = Depends(get_db),
):
    target = session.scalar(
        select(ConversationAccount).where(
            ConversationAccount.id == account_id,
            ConversationAccount.organization_id == ctx.org_id,
        )
    )
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Messaging account not found.")
    service.delete_account(session, target)
    return None


# -------------------------------- consent ---------------------------------


@router.get("/consent/list")
def list_consent(
    channel: str | None = None,
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    return service.list_consent(session, ctx.organization, channel)


@router.post("/consent", status_code=201)
def record_consent(
    data: ConsentRequest,
    request: Request,
    ctx: TenantContext = Depends(require_role("manager")),
    session: Session = Depends(get_db),
):
    try:
        record = service.set_consent(
            session,
            ctx.organization,
            channel=data.channel,
            address=data.address,
            status=data.status,
            source=data.source or "manual",
            lead_id=data.lead_id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    _audit(
        session, ctx, request, "consent_recorded", "channel_consent", record.id,
        {"channel": record.channel, "status": record.status},
    )
    session.commit()
    return {
        "id": record.id,
        "channel": record.channel,
        "address": record.address,
        "status": record.status,
        "source": record.source,
    }


@router.post("/{conversation_id}/opt-out-link")
def opt_out_link(
    conversation_id: str,
    ctx: TenantContext = Depends(require_role("rep")),
    session: Session = Depends(get_db),
):
    """Signed unsubscribe URL for the recipient of this conversation."""
    conversation = _conversation_or_404(session, ctx, conversation_id)
    lead = session.get(Lead, conversation.lead_id) if conversation.lead_id else None
    if lead is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Conversation has no linked lead.")
    address = lead.email if conversation.channel == "email" else lead.phone
    if not address:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "The linked lead has no address for this channel."
        )
    token = service.consent_token(ctx.organization, conversation.channel, address)
    base = (settings.public_base_url or "http://localhost:8000").rstrip("/")
    return {
        "channel": conversation.channel,
        "address": address,
        "url": f"{base}/api/public/conversations/opt-out?token={token}",
    }


@public_router.get("/opt-out")
def public_opt_out(token: str = Query(min_length=10, max_length=2000)):
    """One-click unsubscribe; no login required and no address echo beyond the channel."""
    from app.database import SessionLocal

    session = SessionLocal()
    try:
        record = service.consent_from_token(session, token)
        return {
            "status": record.status,
            "channel": record.channel,
            "message": "You will not receive further messages on this channel.",
        }
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    finally:
        session.close()


# -------------------------------- webhooks --------------------------------


@webhook_router.get("/whatsapp")
def whatsapp_verification(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    if hub_mode != "subscribe" or not service.verify_meta_verify_token(hub_verify_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Verification failed.")
    return int(hub_challenge) if hub_challenge and hub_challenge.isdigit() else hub_challenge


@webhook_router.post("/whatsapp")
async def whatsapp_webhook(request: Request, session: Session = Depends(get_db)):
    raw = await request.body()
    if not service.verify_meta_signature(raw, request.headers.get("x-hub-signature-256")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature.")
    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid JSON body.")

    stored = 0
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value") or {}
            metadata = value.get("metadata") or {}
            phone_number_id = metadata.get("phone_number_id")
            if not phone_number_id:
                continue
            account = session.scalar(
                select(ConversationAccount).where(
                    ConversationAccount.channel == "whatsapp",
                    ConversationAccount.sender_id == phone_number_id,
                )
            )
            if account is None:
                logger.warning("WhatsApp delivery for unknown phone number id %s", phone_number_id)
                continue
            organization = session.get(Organization, account.organization_id)
            if organization is None:
                continue

            for message in value.get("messages", []):
                if message.get("type") not in (None, "text"):
                    continue
                text = (message.get("text") or {}).get("body")
                if not text:
                    continue
                service.ingest_inbound(
                    session,
                    organization,
                    channel="whatsapp",
                    sender_address=str(message.get("from")),
                    body=text,
                    external_id=str(message.get("id") or "") or None,
                    external_thread_id=str(message.get("from")),
                    provider_payload=message,
                )
                stored += 1

            for delivery in value.get("statuses", []):
                external_id = delivery.get("id")
                if not external_id:
                    continue
                record = session.scalar(
                    select(ConversationMessage).where(
                        ConversationMessage.organization_id == organization.id,
                        ConversationMessage.external_id == str(external_id),
                    )
                )
                if record:
                    record.status = str(delivery.get("status") or record.status)[:20]
                    session.commit()
    return {"status": "ok", "stored": stored}


@webhook_router.post("/sms")
def sms_webhook(data: SmsInboundWebhook, session: Session = Depends(get_db)):
    if not service.verify_sms_key(data.key):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid SMS webhook key.")

    account = session.scalar(
        select(ConversationAccount).where(
            ConversationAccount.channel == "sms",
            ConversationAccount.sender_id == (data.to_number or ""),
        )
    )
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No SMS account matches this number.")
    organization = session.get(Organization, account.organization_id)
    if organization is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found.")

    conversation, message, created = service.ingest_inbound(
        session,
        organization,
        channel="sms",
        sender_address=data.from_number,
        body=data.body,
        external_id=data.provider_message_id,
        external_thread_id=data.from_number,
        provider_payload=data.model_dump(),
    )
    return {"status": "created" if created else "duplicate", "conversation_id": conversation.id}
