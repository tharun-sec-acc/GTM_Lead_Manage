"""Shared conversation model for the omnichannel inbox (Release 4).

One conversation belongs to one organization and, where possible, to one CRM
lead. Messages are channel-agnostic: email, WhatsApp Business, SMS and website
chat all land in the same thread so the customer timeline stays complete.
"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

VALID_CHANNELS = ("email", "whatsapp", "sms", "web_chat")
SENDING_CHANNELS = ("email", "whatsapp", "sms")
VALID_STATUS = {"open", "pending", "resolved", "snoozed"}
VALID_PRIORITY = {"low", "normal", "high", "urgent"}
VALID_DIRECTIONS = {"inbound", "outbound", "note"}
VALID_MESSAGE_STATUS = {"received", "queued", "sent", "delivered", "read", "failed", "note"}
VALID_CONSENT = {"opted_in", "opted_out"}


def new_id() -> str:
    return str(uuid4())


def now() -> datetime:
    return datetime.now(timezone.utc)


class ConversationAccount(Base):
    """A WhatsApp/WABA or SMS sending identity owned by one organization."""

    __tablename__ = "conversation_accounts"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "channel", "sender_id", name="uq_conversation_account_sender"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # WhatsApp phone-number id, or the SMS sender id.
    sender_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), default="connected", server_default="connected", nullable=False
    )
    credentials_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "channel", "external_thread_id", name="uq_conversation_thread"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(300), nullable=True)
    lead_id: Mapped[str | None] = mapped_column(
        ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True
    )
    contact_id: Mapped[str | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assignee_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    team: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open", server_default="open", nullable=False)
    priority: Mapped[str] = mapped_column(
        String(20), default="normal", server_default="normal", nullable=False
    )
    tags: Mapped[list] = mapped_column(JSON, default=list)
    unread_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    external_thread_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    channel_account_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversation_accounts.id", ondelete="SET NULL"), nullable=True
    )
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "external_id", name="uq_conversation_external_message"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    direction: Mapped[str] = mapped_column(String(12), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    author_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(300), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="received", server_default="received", nullable=False
    )
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ChannelConsent(Base):
    """Opt-in/opt-out per channel and address (email or phone)."""

    __tablename__ = "channel_consent"
    __table_args__ = (
        UniqueConstraint("organization_id", "channel", "address", name="uq_channel_consent"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    address: Mapped[str] = mapped_column(String(320), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str | None] = mapped_column(String(60), nullable=True)
    lead_id: Mapped[str | None] = mapped_column(
        ForeignKey("leads.id", ondelete="SET NULL"), nullable=True
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
