"""Request models for the omnichannel inbox."""

from typing import Any, Literal

from pydantic import BaseModel, Field

Channel = Literal["email", "whatsapp", "sms", "web_chat"]


class AccountCreate(BaseModel):
    channel: Literal["whatsapp", "sms"]
    provider: str = Field(min_length=1, max_length=40)
    sender_id: str | None = Field(default=None, max_length=120)
    display_name: str | None = Field(default=None, max_length=200)
    credentials: dict[str, str] | None = None
    config: dict[str, Any] | None = None


class ConversationCreate(BaseModel):
    channel: Channel
    lead_id: str | None = None
    subject: str | None = Field(default=None, max_length=300)
    assignee_id: str | None = None
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    tags: list[str] = Field(default_factory=list)
    team: str | None = Field(default=None, max_length=120)


class ReplyRequest(BaseModel):
    body: str = Field(min_length=1, max_length=8000)
    subject: str | None = Field(default=None, max_length=300)
    template_name: str | None = Field(default=None, max_length=120)


class NoteRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class ConversationUpdate(BaseModel):
    assignee_id: str | None = None
    status: Literal["open", "pending", "resolved", "snoozed"] | None = None
    priority: Literal["low", "normal", "high", "urgent"] | None = None
    team: str | None = Field(default=None, max_length=120)
    tags: list[str] | None = None


class ConsentRequest(BaseModel):
    channel: Channel
    address: str = Field(min_length=3, max_length=320)
    status: Literal["opted_in", "opted_out"]
    source: str | None = Field(default=None, max_length=60)
    lead_id: str | None = None


class SmsInboundWebhook(BaseModel):
    """Inbound SMS from a configured provider's webhook."""

    from_number: str = Field(min_length=3, max_length=60)
    to_number: str | None = Field(default=None, max_length=60)
    body: str = Field(min_length=1, max_length=4000)
    provider_message_id: str | None = Field(default=None, max_length=200)
    key: str | None = Field(default=None, max_length=200)
