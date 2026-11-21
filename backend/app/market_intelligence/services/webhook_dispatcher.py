import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.market_intelligence.models import (
    MarketAlert,
    MarketCompany,
    MarketEvent,
    MarketWebhookSubscription,
    OpportunitySignal,
    now,
)

logger = logging.getLogger(__name__)


class WebhookDispatcherService:
    """Dispatches real-time opportunity and market alert payloads to external subscribers."""

    def dispatch_alert(
        self,
        session: Session,
        alert: MarketAlert,
        opp: Optional[OpportunitySignal] = None,
        company: Optional[MarketCompany] = None,
        event: Optional[MarketEvent] = None,
    ) -> list[dict[str, Any]]:
        subscriptions = session.scalars(
            select(MarketWebhookSubscription).where(MarketWebhookSubscription.is_active == True)
        ).all()

        if not subscriptions:
            logger.info("No active webhook subscriptions configured; skipping external dispatch.")
            return []

        # Resolve relationships if omitted
        if not opp and alert.opportunity_id:
            opp = session.get(OpportunitySignal, alert.opportunity_id)
        if opp and not company:
            company = opp.company
        if opp and not event:
            event = opp.event

        product_code = getattr(getattr(opp, "product", None), "code", None)
        product_name = getattr(getattr(opp, "product", None), "name", None)

        payload: dict[str, Any] = {
            "event_type": alert.alert_type,
            "text": f"🚨 [{alert.priority.upper()}] {alert.headline}\n{alert.summary}",
            "alert": {
                "id": alert.id,
                "headline": alert.headline,
                "summary": alert.summary,
                "priority": alert.priority,
                "created_at": alert.created_at.isoformat() if alert.created_at else now().isoformat(),
            },
            "opportunity": {
                "id": opp.id,
                "product_code": product_code,
                "product_name": product_name,
                "market_signal_score": opp.market_signal_score,
                "sales_readiness_score": opp.sales_readiness_score,
                "priority_level": opp.priority_level,
                "suggested_next_action": opp.suggested_next_action,
                "suggested_buyer_roles": opp.suggested_buyer_roles or [],
            }
            if opp
            else None,
            "company": {
                "id": company.id,
                "company_name": company.company_name,
                "domain": company.domain,
                "is_new": company.is_new,
                "industry": company.industry,
                "gtm_lead_id": company.gtm_lead_id,
            }
            if company
            else None,
            "source_event": {
                "id": event.id,
                "category": event.event_category,
                "title": event.event_title,
                "description": event.description,
                "location": event.location,
            }
            if event
            else None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        json_bytes = json.dumps(payload, default=str).encode("utf-8")
        results = []

        for sub in subscriptions:
            # Check event filter
            sub_events = sub.events or []
            if sub_events and "all" not in sub_events and alert.alert_type not in sub_events:
                continue

            headers = {
                "Content-Type": "application/json",
                "User-Agent": "GTMProspecting-MarketIntelligence/1.0",
            }
            if sub.secret_token:
                headers["X-Webhook-Secret"] = sub.secret_token
                signature = hmac.new(sub.secret_token.encode("utf-8"), json_bytes, hashlib.sha256).hexdigest()
                headers["X-GTM-Signature"] = signature

            try:
                with httpx.Client(timeout=6.0) as client:
                    resp = client.post(sub.target_url, content=json_bytes, headers=headers)
                    sub.last_dispatched_at = now()
                    sub.last_status_code = resp.status_code
                    sub.last_error = None if resp.is_success else f"HTTP {resp.status_code}: {resp.text[:300]}"
                    results.append(
                        {
                            "subscription_id": sub.id,
                            "target_url": sub.target_url,
                            "status_code": resp.status_code,
                            "success": resp.is_success,
                        }
                    )
            except Exception as exc:
                logger.warning("Failed dispatching webhook to %s: %s", sub.target_url, exc)
                sub.last_dispatched_at = now()
                sub.last_status_code = 0
                sub.last_error = str(exc)[:500]
                results.append(
                    {
                        "subscription_id": sub.id,
                        "target_url": sub.target_url,
                        "status_code": 0,
                        "success": False,
                        "error": str(exc),
                    }
                )

        session.commit()
        return results

    def test_target(self, target_url: str, secret_token: Optional[str] = None) -> dict[str, Any]:
        """Pings a destination URL with a test payload to verify connectivity."""
        test_payload = {
            "event_type": "test_ping",
            "text": "⚡ GTMProspecting Automotive Market Intelligence: Test webhook connection successful!",
            "message": "Automotive Market Intelligence Webhook test dispatch.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        json_bytes = json.dumps(test_payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "GTMProspecting-MarketIntelligence/1.0",
        }
        if secret_token:
            headers["X-Webhook-Secret"] = secret_token
            headers["X-GTM-Signature"] = hmac.new(
                secret_token.encode("utf-8"), json_bytes, hashlib.sha256
            ).hexdigest()

        start = time.perf_counter()
        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.post(target_url, content=json_bytes, headers=headers)
                elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
                return {
                    "success": resp.is_success,
                    "status_code": resp.status_code,
                    "duration_ms": elapsed_ms,
                    "response_preview": resp.text[:300],
                }
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            return {
                "success": False,
                "status_code": 0,
                "duration_ms": elapsed_ms,
                "error": str(exc),
            }
