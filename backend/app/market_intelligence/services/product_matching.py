import logging
from datetime import datetime, timezone
from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.market_intelligence.models import (
    MarketEvent,
    MarketCompany,
    ProductCatalog,
    ProductMatchRule,
    OpportunitySignal,
    MarketAlert,
    now,
)

logger = logging.getLogger(__name__)


class ProductMatchingService:
    def evaluate_event_for_opportunities(
        self,
        session: Session,
        event: MarketEvent,
        company: MarketCompany,
    ) -> list[OpportunitySignal]:
        """
        Evaluates a market event against all active Solwer products and their configurable rules,
        calculating dual explainable scores (Market Signal Score & Sales Readiness Score).
        """
        active_products = session.scalars(
            select(ProductCatalog).where(ProductCatalog.is_active == True).order_by(ProductCatalog.priority.asc())
        ).all()

        signals: list[OpportunitySignal] = []

        for product in active_products:
            score_data = self._calculate_scores(product, event, company)
            if not score_data.get("is_qualified"):
                continue

            market_score = score_data["market_signal_score"]
            readiness_score = score_data["sales_readiness_score"]

            # Only generate signal if market relevance >= 50 points
            if market_score >= 50.0:
                priority = "high" if (market_score >= 80 or readiness_score >= 80) else ("medium" if market_score >= 65 else "low")

                suggested_roles = product.potential_buyer_roles or [
                    "Head of Operations",
                    "VP Technology",
                    "General Manager",
                ]

                # Compose action recommendation
                if product.code == "TWMS":
                    next_action = f"Reach out to {company.company_name} Logistics leadership with Solwer TWMS multi-depot and dispatch optimization overview."
                elif product.code == "LOSS_TRACKER_IM":
                    next_action = f"Engage {company.company_name} Plant/Manufacturing Head proposing Loss Tracker & OEE KAIZEN demonstration."
                elif product.code == "VDI":
                    next_action = f"Demonstrate Solwer Vehicle Digital Inspection AI checklist and damage scanning to {company.company_name} inspection lead."
                elif product.code == "FLEET_MGMT":
                    next_action = f"Present Solwer Fleet Management driver pre-trip checklists and vehicle readiness portal to {company.company_name} fleet director."
                elif product.code == "MCE":
                    next_action = f"Propose Mobility Aftermarket SuperApp workshop management and spare parts catalogue integration."
                elif product.code == "CARBON_MGMT":
                    next_action = f"Offer Scope 1, 2, and 3 logistics emissions baseline calculation and BRSR reporting deck."
                else:
                    next_action = f"Coordinate introductory discovery call regarding Solwer {product.name}."

                opp = OpportunitySignal(
                    event_id=event.id,
                    company_id=company.id,
                    product_id=product.id,
                    market_signal_score=market_score,
                    sales_readiness_score=readiness_score,
                    score_breakdown=score_data["breakdown"],
                    score_explanation=score_data["explanation"],
                    suggested_buyer_roles=suggested_roles,
                    suggested_next_action=next_action,
                    priority_level=priority,
                    review_status="new",
                )
                session.add(opp)
                session.flush()
                signals.append(opp)

                # Generate alert for high priority opportunities
                if priority == "high":
                    alert_headline = f"High-Priority Opportunity: {product.name} for {company.company_name}"
                    alert_summary = (
                        f"Detected {event.event_category.replace('_', ' ').title()} at {company.company_name}. "
                        f"Market Signal Score: {market_score:.0f}/100. "
                        f"Operational problem: {event.operational_problem or 'Expansion requiring modern tooling'}."
                    )
                    alert = MarketAlert(
                        opportunity_id=opp.id,
                        alert_type="high_priority_opportunity" if company.is_new else "existing_lead_update",
                        headline=alert_headline,
                        summary=alert_summary,
                        priority="high",
                    )
                    session.add(alert)

        session.commit()
        logger.info("Generated %d opportunity signals for event '%s'", len(signals), event.event_title)
        return signals

    def _calculate_scores(
        self,
        product: ProductCatalog,
        event: MarketEvent,
        company: MarketCompany,
    ) -> dict[str, Any]:
        """Calculates explainable Market Signal and Sales Readiness scores with strict qualification."""
        combined_text = f"{event.event_title}\n{event.description or ''}\n{event.business_implication or ''}".lower()

        # 1. Product Relevance (up to 30 pts)
        relevance_score = 0.0
        matched_rules = []
        is_relevant = False

        # Category alignment
        cat_direct = bool(product.relevant_business_events and event.event_category in product.relevant_business_events)
        if cat_direct:
            relevance_score += 10.0
            is_relevant = True

        for rule in product.rules:
            if not rule.is_active:
                continue
            cat_match = bool(rule.event_categories and event.event_category in rule.event_categories)
            kw_match = any(kw.lower() in combined_text for kw in (rule.positive_keywords or []))
            neg_match = any(nkw.lower() in combined_text for nkw in (rule.negative_keywords or []))

            if neg_match:
                continue

            if kw_match and cat_match:
                relevance_score += 16.0 * rule.weight
                matched_rules.append(rule.rule_name)
                is_relevant = True
            elif kw_match:
                relevance_score += 12.0 * rule.weight
                matched_rules.append(rule.rule_name)
                is_relevant = True
            elif cat_match:
                relevance_score += 6.0 * rule.weight
                matched_rules.append(f"{rule.rule_name} (Category)")
                is_relevant = True

        relevance_score = min(30.0, relevance_score)

        # If zero rules matched and no direct category match, this event is NOT relevant to this product
        if not is_relevant or relevance_score < 6.0:
            return {
                "is_qualified": False,
                "market_signal_score": 0.0,
                "sales_readiness_score": 0.0,
                "breakdown": {
                    "product_relevance": 0.0,
                    "event_strength": 0.0,
                    "icp_fit": 0.0,
                    "recency": 0.0,
                    "relationship": 0.0,
                },
                "explanation": f"No trigger keywords or relevant event categories matched for Solwer {product.name}.",
            }

        # 2. Event Strength (up to 25 pts)
        event_strength = 12.0
        if any(w in combined_text for w in ["crore", "million", "billion", "investment", "plant", "hub", "acres", "contract"]):
            event_strength += 13.0
        event_strength = min(25.0, event_strength)

        # 3. ICP Fit (up to 20 pts)
        icp_score = 5.0
        if company.business_segment in (product.target_company_segments or []):
            icp_score += 15.0
        icp_score = min(20.0, icp_score)

        # 4. Recency (up to 15 pts)
        recency_score = 15.0  # newly extracted

        # 5. Existing Relationship (up to 10 pts)
        relationship_score = 10.0 if not company.is_new else 5.0

        total_market_signal = min(100.0, relevance_score + event_strength + icp_score + recency_score + relationship_score)

        # Sales Readiness Score
        readiness_score = 0.0
        if company.domain:
            readiness_score += 30.0
        if event.operational_problem:
            readiness_score += 30.0
        if event.supporting_evidence:
            readiness_score += 25.0
        if not company.is_new:
            readiness_score += 15.0
        else:
            readiness_score += 10.0
        total_readiness = min(100.0, readiness_score)

        explanation = (
            f"Evaluated Solwer {product.name} against event '{event.event_category}'. "
            f"Product relevance scored {relevance_score:.0f}/30 pts based on matched operational rules ({', '.join(matched_rules) or 'Direct category match'}). "
            f"Event strength scored {event_strength:.0f}/25 pts. "
            f"ICP fit scored {icp_score:.0f}/20 pts for segment '{company.business_segment or 'Automotive'}'. "
            f"Sales readiness scored {total_readiness:.0f}/100 with verified company and actionable operational gap."
        )

        return {
            "is_qualified": True,
            "market_signal_score": round(total_market_signal, 1),
            "sales_readiness_score": round(total_readiness, 1),
            "breakdown": {
                "product_relevance": round(relevance_score, 1),
                "event_strength": round(event_strength, 1),
                "icp_fit": round(icp_score, 1),
                "recency": round(recency_score, 1),
                "relationship": round(relationship_score, 1),
            },
            "explanation": explanation,
        }
