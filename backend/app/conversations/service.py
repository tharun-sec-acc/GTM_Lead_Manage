"""Conversation threading, consent, outbound sending and inbox metrics.

Rules enforced here:

* every query is scoped by ``organization_id``;
* inbound messages are always stored, outbound messages require consent and an
  explicit deployment kill switch;
* email reuses the existing OAuth mailbox sender instead of a second mail path;
* WhatsApp/SMS credentials stay encrypted and never reach a response;
* messages are idempotent per provider message id.
"""

import hmac
import json
import logging

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.advertising.service import verify_meta_signature, verify_meta_verify_token
from app.auth.models import OAuthConnection, Organization
from app.auth.security import decrypt_token, encrypt_token
from app.config import settings
from app.conversations.models import (
    VALID_CHANNELS,
    ChannelConsent,
    Conversation,
    ConversationAccount,
    ConversationMessage,
    now,
)
from app.conversations.providers import (
    ChannelNotConfigured,
    ProviderError,
    SendingDisabled,
    SmsClient,
    WhatsAppClient,
)
from app.email_sender import EmailSendError, send_email_via_account
from app.models import Lead

logger = logging.getLogger(__name__)


class ConsentBlocked(RuntimeError):
    """The contact opted out of this channel."""


def verify_sms_key(key: str | None) -> bool:
    """Shared-secret check for the inbound SMS webhook."""
    expected = settings.sms_inbound_webhook_key
    return bool(expected and key and hmac.compare_digest(expected, key))


def normalize_address(channel: str, value: str | None) -> str:
    if not value:
        return ""
    cleaned = value.strip()
    if channel == "email":
        return cleaned.lower()
    return "".join(ch for ch in cleaned if ch.isdigit() or ch == "+")


# ------------------------------- serializers ------------------------------


def serialize_account(account: ConversationAccount) -> dict:
    return {
        "id": account.id,
        "channel": account.channel,
        "provider": account.provider,
        "display_name": account.display_name,
        "sender_id": account.sender_id,
        "status": account.status,
        "has_credentials": bool(account.credentials_encrypted),
        "config": {
            key: value
            for key, value in (account.config or {}).items()
            if key in {"endpoint", "sender_id", "auth_header", "extra"}
        },
        "last_error": account.last_error,
        "last_used_at": account.last_used_at,
        "created_at": account.created_at,
    }


def serialize_message(message: ConversationMessage) -> dict:
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "direction": message.direction,
        "channel": message.channel,
        "author_user_id": message.author_user_id,
        "subject": message.subject,
        "body": message.body,
        "status": message.status,
        "external_id": message.external_id,
        "error": message.error,
        "sent_at": message.sent_at,
        "created_at": message.created_at,
    }


def serialize_conversation(
    conversation: Conversation, lead: Lead | None = None, last_message: ConversationMessage | None = None
) -> dict:
    return {
        "id": conversation.id,
        "channel": conversation.channel,
        "subject": conversation.subject,
        "lead_id": conversation.lead_id,
        "lead_name": (lead.company_name if lead else None),
        "lead_email": (lead.email if lead else None),
        "lead_phone": (lead.phone if lead else None),
        "contact_id": conversation.contact_id,
        "assignee_id": conversation.assignee_id,
        "team": conversation.team,
        "status": conversation.status,
        "priority": conversation.priority,
        "tags": conversation.tags or [],
        "unread_count": conversation.unread_count,
        "first_response_at": conversation.first_response_at,
        "last_message_at": conversation.last_message_at,
        "resolved_at": conversation.resolved_at,
        "preview": (last_message.body[:180] if last_message else None),
        "preview_direction": (last_message.direction if last_message else None),
    }


# -------------------------------- accounts --------------------------------


def list_accounts(session: Session, organization: Organization) -> list[ConversationAccount]:
    return list(
        session.scalars(
            select(ConversationAccount)
            .where(ConversationAccount.organization_id == organization.id)
            .order_by(ConversationAccount.created_at.desc())
        ).all()
    )


def upsert_account(
    session: Session,
    organization: Organization,
    *,
    channel: str,
    provider: str,
    sender_id: str | None,
    display_name: str | None = None,
    credentials: dict | None = None,
    config: dict | None = None,
) -> ConversationAccount:
    if channel not in ("whatsapp", "sms"):
        raise ValueError("Messaging accounts exist for WhatsApp and SMS only.")
    account = session.scalar(
        select(ConversationAccount).where(
            ConversationAccount.organization_id == organization.id,
            ConversationAccount.channel == channel,
            ConversationAccount.sender_id == sender_id,
        )
    )
    if account is None:
        account = ConversationAccount(
            organization_id=organization.id,
            channel=channel,
            provider=provider,
            sender_id=sender_id,
        )
        session.add(account)
    account.provider = provider
    account.display_name = display_name or account.display_name
    if credentials is not None:
        account.credentials_encrypted = encrypt_token(json.dumps(credentials)) if credentials else None
    if config is not None:
        account.config = {**(account.config or {}), **config}
    account.status = "connected" if account.credentials_encrypted else "pending_credentials"
    account.last_error = None
    session.commit()
    session.refresh(account)
    return account


def account_credentials(account: ConversationAccount) -> dict:
    if not account.credentials_encrypted:
        return {}
    try:
        return json.loads(decrypt_token(account.credentials_encrypted))
    except (ValueError, TypeError):  # pragma: no cover - corrupt ciphertext
        logger.warning("Could not decrypt conversation account %s credentials", account.id)
        return {}


def delete_account(session: Session, account: ConversationAccount) -> None:
    session.delete(account)
    session.commit()


# --------------------------------- consent --------------------------------


def get_consent(session: Session, organization: Organization, channel: str, address: str) -> str | None:
    record = session.scalar(
        select(ChannelConsent).where(
            ChannelConsent.organization_id == organization.id,
            ChannelConsent.channel == channel,
            ChannelConsent.address == address,
        )
    )
    return record.status if record else None


def set_consent(
    session: Session,
    organization: Organization,
    *,
    channel: str,
    address: str,
    status: str,
    source: str | None = None,
    lead_id: str | None = None,
) -> ChannelConsent:
    if channel not in VALID_CHANNELS:
        raise ValueError(f"Unknown channel '{channel}'.")
    if status not in ("opted_in", "opted_out"):
        raise ValueError("Consent status must be opted_in or opted_out.")
    normalised = normalize_address(channel, address)
    if not normalised:
        raise ValueError("A consent record needs an address.")

    record = session.scalar(
        select(ChannelConsent).where(
            ChannelConsent.organization_id == organization.id,
            ChannelConsent.channel == channel,
            ChannelConsent.address == normalised,
        )
    )
    if record is None:
        record = ChannelConsent(
            organization_id=organization.id,
            channel=channel,
            address=normalised,
            status=status,
        )
        session.add(record)
    record.status = status
    record.source = source or record.source
    record.lead_id = lead_id or record.lead_id
    record.updated_at = now()
    session.commit()
    session.refresh(record)
    return record


def list_consent(session: Session, organization: Organization, channel: str | None = None) -> list[dict]:
    statement = select(ChannelConsent).where(ChannelConsent.organization_id == organization.id)
    if channel:
        statement = statement.where(ChannelConsent.channel == channel)
    rows = session.scalars(statement.order_by(ChannelConsent.updated_at.desc()).limit(500)).all()
    return [
        {
            "id": row.id,
            "channel": row.channel,
            "address": row.address,
            "status": row.status,
            "source": row.source,
            "lead_id": row.lead_id,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]


# ------------------------------- threading --------------------------------


def find_lead(session: Session, organization: Organization, channel: str, address: str) -> Lead | None:
    normalised = normalize_address(channel, address)
    if not normalised:
        return None
    column = Lead.email if channel == "email" else Lead.phone
    value = normalised if channel == "email" else address.strip()
    return session.scalar(
        select(Lead).where(
            Lead.organization_id == organization.id,
            column == value,
            Lead.merged_into_id.is_(None),
        )
    )


def _conversation_by_thread(
    session: Session, organization: Organization, channel: str, external_thread_id: str | None
) -> Conversation | None:
    if not external_thread_id:
        return None
    return session.scalar(
        select(Conversation).where(
            Conversation.organization_id == organization.id,
            Conversation.channel == channel,
            Conversation.external_thread_id == external_thread_id,
        )
    )


def open_conversation_for_lead(
    session: Session, organization: Organization, channel: str, lead_id: str | None
) -> Conversation | None:
    if not lead_id:
        return None
    return session.scalar(
        select(Conversation)
        .where(
            Conversation.organization_id == organization.id,
            Conversation.channel == channel,
            Conversation.lead_id == lead_id,
            Conversation.status != "resolved",
        )
        .order_by(Conversation.last_message_at.desc())
    )


def create_conversation(
    session: Session,
    organization: Organization,
    *,
    channel: str,
    lead_id: str | None = None,
    subject: str | None = None,
    external_thread_id: str | None = None,
    assignee_id: str | None = None,
    priority: str = "normal",
    tags: list | None = None,
    channel_account_id: str | None = None,
) -> Conversation:
    if channel not in VALID_CHANNELS:
        raise ValueError(f"Unknown channel '{channel}'.")
    conversation = Conversation(
        organization_id=organization.id,
        channel=channel,
        lead_id=lead_id,
        subject=subject,
        external_thread_id=external_thread_id,
        assignee_id=assignee_id,
        priority=priority,
        tags=tags or [],
        channel_account_id=channel_account_id,
    )
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return conversation


def ingest_inbound(
    session: Session,
    organization: Organization,
    *,
    channel: str,
    sender_address: str,
    body: str,
    subject: str | None = None,
    external_id: str | None = None,
    external_thread_id: str | None = None,
    provider_payload: dict | None = None,
) -> tuple[Conversation, ConversationMessage, bool]:
    """Store one inbound message. Returns (conversation, message, created)."""
    if channel not in VALID_CHANNELS:
        raise ValueError(f"Unknown channel '{channel}'.")

    conversation = _conversation_by_thread(session, organization, channel, external_thread_id)
    lead = find_lead(session, organization, channel, sender_address)
    if conversation is None:
        conversation = open_conversation_for_lead(
            session, organization, channel, lead.id if lead else None
        )
    if conversation is None:
        conversation = Conversation(
            organization_id=organization.id,
            channel=channel,
            lead_id=lead.id if lead else None,
            subject=subject,
            external_thread_id=external_thread_id,
            status="open",
        )
        session.add(conversation)
        session.flush()

    if external_id:
        existing = session.scalar(
            select(ConversationMessage).where(
                ConversationMessage.conversation_id == conversation.id,
                ConversationMessage.external_id == external_id,
            )
        )
        if existing:
            return conversation, existing, False

    message = ConversationMessage(
        organization_id=organization.id,
        conversation_id=conversation.id,
        direction="inbound",
        channel=channel,
        body=body,
        subject=subject,
        status="received",
        external_id=external_id,
        provider_payload=provider_payload or {},
    )
    session.add(message)
    conversation.last_message_at = now()
    conversation.unread_count = (conversation.unread_count or 0) + 1
    if conversation.status == "resolved":
        conversation.status = "open"
        conversation.resolved_at = None
    session.commit()
    session.refresh(conversation)
    session.refresh(message)

    consent = get_consent(session, organization, channel, normalize_address(channel, sender_address))
    if consent is None:
        set_consent(
            session,
            organization,
            channel=channel,
            address=sender_address,
            status="opted_in",
            source="inbound_message",
            lead_id=conversation.lead_id,
        )
    return conversation, message, True


def record_note(
    session: Session, conversation: Conversation, *, body: str, user_id: str | None
) -> ConversationMessage:
    message = ConversationMessage(
        organization_id=conversation.organization_id,
        conversation_id=conversation.id,
        direction="note",
        channel=conversation.channel,
        author_user_id=user_id,
        body=body,
        status="note",
    )
    session.add(message)
    session.commit()
    session.refresh(message)
    return message


def _recipient(conversation: Conversation, lead: Lead | None) -> str:
    if lead is None:
        raise ValueError("This conversation is not linked to a lead with a reachable address.")
    if conversation.channel == "email":
        if not lead.email:
            raise ValueError("The linked lead has no email address.")
        return lead.email
    if not lead.phone:
        raise ValueError("The linked lead has no phone number.")
    return lead.phone


def _email_connection(session: Session, organization: Organization) -> OAuthConnection:
    connection = session.scalar(
        select(OAuthConnection)
        .where(
            OAuthConnection.organization_id == organization.id,
            OAuthConnection.provider.in_(["google", "microsoft"]),
            OAuthConnection.status != "disconnected",
        )
        .order_by(OAuthConnection.created_at.desc())
    )
    if connection is None:
        raise ChannelNotConfigured(
            "No Gmail or Microsoft mailbox is connected for this organization."
        )
    return connection


def _messaging_account(
    session: Session, organization: Organization, channel: str, account_id: str | None = None
) -> ConversationAccount:
    statement = select(ConversationAccount).where(
        ConversationAccount.organization_id == organization.id,
        ConversationAccount.channel == channel,
    )
    if account_id:
        statement = statement.where(ConversationAccount.id == account_id)
    account = session.scalar(statement.order_by(ConversationAccount.created_at.desc()))
    if account is None:
        raise ChannelNotConfigured(
            f"No {channel} sending account is connected for this organization."
        )
    return account


def send_outbound(
    session: Session,
    organization: Organization,
    conversation: Conversation,
    *,
    body: str,
    user_id: str | None,
    subject: str | None = None,
    template_name: str | None = None,
) -> ConversationMessage:
    """Send (or record, for web chat) an outbound reply."""
    if not settings.conversation_send_enabled:
        raise SendingDisabled(
            "Outbound messaging is disabled by configuration (CONVERSATION_SEND_ENABLED=false)."
        )

    lead = session.get(Lead, conversation.lead_id) if conversation.lead_id else None
    recipient = None
    if conversation.channel != "web_chat":
        recipient = _recipient(conversation, lead)
        consent = get_consent(
            session, organization, conversation.channel, normalize_address(conversation.channel, recipient)
        )
        if consent == "opted_out":
            raise ConsentBlocked(
                f"{recipient} has opted out of {conversation.channel} messages."
            )

    message = ConversationMessage(
        organization_id=organization.id,
        conversation_id=conversation.id,
        direction="outbound",
        channel=conversation.channel,
        author_user_id=user_id,
        subject=subject or conversation.subject,
        body=body,
        status="queued",
    )
    session.add(message)
    session.flush()

    try:
        if conversation.channel == "email":
            connection = _email_connection(session, organization)
            result = send_email_via_account(
                session,
                connection,
                recipient=recipient or "",
                subject=(subject or conversation.subject or "Re: your enquiry")[:500],
                body_html=body.replace("\n", "<br />"),
                body_text=body,
                lead_id=conversation.lead_id,
                user_id=user_id,
                org_id=organization.id,
            )
            message.external_id = str(result.get("message_id"))[:200]
            message.status = "sent"
            message.sent_at = now()
        elif conversation.channel == "whatsapp":
            account = _messaging_account(
                session, organization, "whatsapp", conversation.channel_account_id
            )
            credentials = account_credentials(account)
            client = WhatsAppClient(account.sender_id, credentials.get("access_token"))
            if template_name:
                result = client.send_template(
                    recipient or "",
                    template_name,
                    language=(account.config or {}).get("template_language", "en"),
                )
            else:
                result = client.send_text(recipient or "", body)
            message.external_id = result.get("message_id")
            message.status = "sent"
            message.sent_at = now()
            account.last_used_at = now()
        elif conversation.channel == "sms":
            account = _messaging_account(session, organization, "sms", conversation.channel_account_id)
            credentials = account_credentials(account)
            client = SmsClient(account.config, credentials.get("api_key"))
            result = client.send(recipient or "", body)
            message.external_id = result.get("message_id")
            message.status = "sent"
            message.sent_at = now()
            account.last_used_at = now()
        else:
            # Website chat: delivered by our own widget, no external transport.
            message.status = "sent"
            message.sent_at = now()
        message.provider_payload = {"channel": conversation.channel}
    except (ChannelNotConfigured, SendingDisabled, ConsentBlocked) as exc:
        session.rollback()
        raise
    except (ProviderError, EmailSendError) as exc:
        message.status = "failed"
        message.error = str(exc)[:1000]
        session.commit()
        raise ProviderError(str(exc)) from exc

    conversation.last_message_at = now()
    if conversation.first_response_at is None:
        conversation.first_response_at = now()
    if conversation.status == "open":
        conversation.status = "pending"
    session.commit()
    session.refresh(message)
    return message


# -------------------------------- queries ---------------------------------


def list_conversations(
    session: Session,
    organization: Organization,
    *,
    channel: str | None = None,
    status_filter: str | None = None,
    assignee_id: str | None = None,
    unassigned: bool = False,
    query: str | None = None,
    limit: int = 100,
) -> list[dict]:
    statement = select(Conversation).where(Conversation.organization_id == organization.id)
    if channel:
        statement = statement.where(Conversation.channel == channel)
    if status_filter:
        statement = statement.where(Conversation.status == status_filter)
    if assignee_id:
        statement = statement.where(Conversation.assignee_id == assignee_id)
    if unassigned:
        statement = statement.where(Conversation.assignee_id.is_(None))
    if query and query.strip():
        like = f"%{query.strip()}%"
        statement = statement.where(
            or_(Conversation.subject.ilike(like), Conversation.team.ilike(like))
        )
    rows = session.scalars(
        statement.order_by(Conversation.last_message_at.desc()).limit(limit)
    ).all()

    payload = []
    for conversation in rows:
        lead = session.get(Lead, conversation.lead_id) if conversation.lead_id else None
        last_message = session.scalar(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation.id)
            .order_by(ConversationMessage.created_at.desc())
            .limit(1)
        )
        payload.append(serialize_conversation(conversation, lead, last_message))
    return payload


def get_conversation(session: Session, organization: Organization, conversation_id: str) -> Conversation:
    conversation = session.get(Conversation, conversation_id)
    if not conversation or conversation.organization_id != organization.id:
        raise LookupError("Conversation not found.")
    return conversation


def conversation_detail(session: Session, conversation: Conversation, limit: int = 200) -> dict:
    lead = session.get(Lead, conversation.lead_id) if conversation.lead_id else None
    messages = session.scalars(
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation.id)
        .order_by(ConversationMessage.created_at.asc())
        .limit(limit)
    ).all()
    consent = None
    if lead:
        address = lead.email if conversation.channel == "email" else lead.phone
        if address:
            record = session.scalar(
                select(ChannelConsent).where(
                    ChannelConsent.organization_id == conversation.organization_id,
                    ChannelConsent.channel == conversation.channel,
                    ChannelConsent.address == normalize_address(conversation.channel, address),
                )
            )
            consent = record.status if record else None
    return {
        **serialize_conversation(conversation, lead),
        "messages": [serialize_message(message) for message in messages],
        "consent": consent,
    }


def consent_token(organization: Organization, channel: str, address: str) -> str:
    """Signed token for a public unsubscribe link (opt-out, no login required)."""
    import base64
    import hashlib

    payload = f"{organization.id}:{channel}:{address}"
    signature = hmac.new(
        settings.jwt_secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    encoded = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")
    return f"{encoded}.{signature}"


def consent_from_token(session: Session, token: str) -> ChannelConsent:
    """Verify and apply an opt-out token. Raises ValueError on tampering."""
    import base64
    import hashlib

    try:
        encoded, signature = token.split(".", 1)
        payload = base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid opt-out token.") from exc

    expected = hmac.new(
        settings.jwt_secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise ValueError("Invalid opt-out token.")

    organization_id, channel, address = payload.split(":", 2)
    organization = session.get(Organization, organization_id)
    if organization is None:
        raise ValueError("Invalid opt-out token.")
    return set_consent(
        session,
        organization,
        channel=channel,
        address=address,
        status="opted_out",
        source="public_opt_out_link",
    )


def inbox_metrics(session: Session, organization: Organization) -> dict:
    base = select(func.count(Conversation.id)).where(
        Conversation.organization_id == organization.id
    )
    open_count = session.scalar(base.where(Conversation.status == "open")) or 0
    pending_count = session.scalar(base.where(Conversation.status == "pending")) or 0
    resolved_count = session.scalar(base.where(Conversation.status == "resolved")) or 0
    unassigned = session.scalar(base.where(Conversation.assignee_id.is_(None))) or 0

    awaiting = session.scalar(
        base.where(Conversation.first_response_at.is_(None), Conversation.status != "resolved")
    ) or 0

    responded = session.scalars(
        select(Conversation).where(
            Conversation.organization_id == organization.id,
            Conversation.first_response_at.is_not(None),
        )
    ).all()
    durations = []
    for conversation in responded:
        created = conversation.created_at
        first = conversation.first_response_at
        if created and first and first >= created:
            durations.append((first - created).total_seconds() / 60)
    average = round(sum(durations) / len(durations), 1) if durations else None

    return {
        "open": int(open_count),
        "pending": int(pending_count),
        "resolved": int(resolved_count),
        "unassigned": int(unassigned),
        "awaiting_first_response": int(awaiting),
        "average_first_response_minutes": average,
    }
