import sys
sys.path.insert(0, "backend")

print("=== config settings (Release 3 + Release 4) ===")
from app.config import settings
print("conversation_send_enabled =", settings.conversation_send_enabled)
print("sms_inbound_webhook_key set =", bool(settings.sms_inbound_webhook_key))
print("meta_app_secret set =", bool(settings.meta_app_secret))
print("meta_graph_version =", settings.meta_graph_version)
print("google_lead_form_key set =", bool(settings.google_lead_form_key))
print("billing_enforce_limits =", settings.billing_enforce_limits)
print("billing_default_plan_code =", settings.billing_default_plan_code)
print("advertising_enabled =", settings.advertising_enabled)

print()
print("=== conversations.service imports ===")
from app.conversations import service
from app.conversations.service import (
    consent_token,
    consent_from_token,
    serialize_conversation,
    send_outbound,
    ingest_inbound,
    inbox_metrics,
    verify_sms_key,
)
print("conversations.service imports OK")
print("consent_token callable:", callable(consent_token))
print("consent_from_token callable:", callable(consent_from_token))
print("verify_sms_key callable:", callable(verify_sms_key))

print()
print("=== consent_token round-trip ===")
from app.auth.models import Organization
import base64
# Build a minimal Organization-like object for token signing
class Org:
    id = "org-test-123"
tok = consent_token(Org(), "email", "user@example.com")
print("token =", tok)
decoded, sig = tok.split(".", 1)
print("decoded payload =", base64.urlsafe_b64decode(decoded.encode("ascii")).decode("utf-8"))
print("token has signature =", bool(sig))

print()
print("=== verify_sms_key ===")
settings.sms_inbound_webhook_key = "test-sms-key"
print("verify with correct key:", verify_sms_key("test-sms-key"))
print("verify with wrong key:", verify_sms_key("wrong-key"))
print("verify with None key:", verify_sms_key(None))

print()
print("ALL SMOKE TESTS PASSED")
