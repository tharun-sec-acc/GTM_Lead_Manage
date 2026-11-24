"""WhatsApp Business Cloud API and configurable SMS transports.

Sending is only reachable through the conversation service, which enforces
consent, the master kill switch and per-channel configuration. Nothing here
uses unofficial WhatsApp Web automation.
"""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

META_DEFAULT_VERSION = "v21.0"


class ChannelNotConfigured(RuntimeError):
    """The channel has no connected sending identity."""


class SendingDisabled(RuntimeError):
    """The deployment disabled outbound messaging."""


class ProviderError(RuntimeError):
    """The provider rejected the message or could not be reached."""


def whatsapp_app_configured() -> bool:
    return bool(settings.meta_app_id and settings.meta_app_secret)


class WhatsAppClient:
    """Meta WhatsApp Business Cloud API sender."""

    def __init__(self, phone_number_id: str | None, access_token: str | None, *, version: str | None = None):
        self.phone_number_id = phone_number_id or ""
        self.access_token = access_token or ""
        self.version = version or settings.meta_graph_version or META_DEFAULT_VERSION

    @property
    def configured(self) -> bool:
        return bool(self.phone_number_id and self.access_token)

    def send_text(self, to: str, body: str, *, preview_url: bool = False) -> dict:
        if not self.configured:
            raise ChannelNotConfigured(
                "WhatsApp needs a phone-number id and a Cloud API access token for this organization."
            )
        url = f"https://graph.facebook.com/{self.version}/{self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": preview_url, "body": body},
        }
        return self._post(url, payload)

    def send_template(self, to: str, template_name: str, language: str = "en", components: list | None = None) -> dict:
        if not self.configured:
            raise ChannelNotConfigured(
                "WhatsApp needs a phone-number id and a Cloud API access token for this organization."
            )
        url = f"https://graph.facebook.com/{self.version}/{self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
                "components": components or [],
            },
        }
        return self._post(url, payload)

    def _post(self, url: str, payload: dict) -> dict:
        try:
            response = httpx.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=20.0,
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"WhatsApp request failed: {exc}") from exc
        if response.status_code >= 400:
            try:
                detail = response.json().get("error", {}).get("message")
            except ValueError:
                detail = response.text[:300]
            raise ProviderError(f"WhatsApp API error {response.status_code}: {detail}")
        data = response.json()
        messages = data.get("messages") or []
        return {
            "provider": "whatsapp",
            "message_id": str(messages[0].get("id")) if messages else None,
            "raw": data,
        }


class SmsClient:
    """Provider-agnostic SMS sender driven by per-account JSON configuration.

    ``config`` holds ``endpoint``, ``sender_id``, ``auth_header`` and, optionally,
    ``payload_template`` keys. Providers that need a bespoke shape are handled by
    registering a different adapter rather than hardcoding vendor logic here.
    """

    def __init__(self, config: dict | None, api_key: str | None):
        self.config = config or {}
        self.api_key = api_key or ""

    @property
    def configured(self) -> bool:
        return bool(self.config.get("endpoint") and self.api_key and self.config.get("sender_id"))

    def send(self, to: str, body: str) -> dict:
        if not self.configured:
            raise ChannelNotConfigured(
                "SMS needs an endpoint, a sender id and an API key for this organization."
            )
        endpoint = self.config["endpoint"]
        headers = {"Content-Type": "application/json"}
        header_name = self.config.get("auth_header") or "Authorization"
        headers[header_name] = (
            self.api_key if header_name.lower() != "authorization" else f"Bearer {self.api_key}"
        )
        payload = {
            "to": to,
            "sender": self.config["sender_id"],
            "message": body,
        }
        if isinstance(self.config.get("extra"), dict):
            payload.update(self.config["extra"])
        try:
            response = httpx.post(endpoint, headers=headers, json=payload, timeout=20.0)
        except httpx.HTTPError as exc:
            raise ProviderError(f"SMS request failed: {exc}") from exc
        if response.status_code >= 400:
            raise ProviderError(f"SMS provider error {response.status_code}: {response.text[:300]}")
        try:
            data = response.json()
        except ValueError:
            data = {}
        return {
            "provider": "sms",
            "message_id": str(data.get("id") or data.get("message_id") or "") or None,
            "raw": data,
        }
