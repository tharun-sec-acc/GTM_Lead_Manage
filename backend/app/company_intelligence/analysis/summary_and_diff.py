"""One-Page Executive Summary Generator and 'What Changed?' Diff Engine.

Provides concise executive briefings for sales reps and tracks changes between research runs.
"""

from __future__ import annotations

import logging
from typing import Any

from app.company_intelligence.models import ResearchFact

logger = logging.getLogger(__name__)


def generate_one_page_summary(
    company_name: str,
    domain: str,
    facts: list[ResearchFact],
    analysis: dict[str, Any],
    product_opportunities: list[dict[str, Any]],
) -> dict[str, Any]:
    """Generate a high-density, 1-page executive summary for sales representatives and executives."""
    facts_by_cat: dict[str, list[ResearchFact]] = {}
    for f in facts:
        facts_by_cat.setdefault(f.category, []).append(f)

    # 1. Company Overview
    overview_text = analysis.get("business_model", {}).get("what_it_sells", f"{company_name} corporate operations.")
    industry = analysis.get("business_model", {}).get("industries_served", "Commercial & Industrial")
    hq = "India"
    for f in facts_by_cat.get("company_identity", facts_by_cat.get("company", [])):
        if "headquarter" in f.field_name.lower() or "location" in f.field_name.lower():
            hq = f.value
            break

    # 2. Business Scale
    revenue = "Not disclosed in public official pages"
    for f in facts_by_cat.get("financial_research", facts_by_cat.get("financial", [])):
        if any(term in f.field_name.lower() for term in ("revenue", "turnover", "sales")):
            revenue = f.value
            if f.unit:
                revenue += f" {f.unit}"
            if f.reporting_period:
                revenue += f" ({f.reporting_period})"
            break

    fleet_scale = "Disclosed in logistics/transport operations"
    for f in facts_by_cat.get("fleet_transportation", []):
        if any(term in f.field_name.lower() for term in ("fleet", "truck", "vehicle")):
            fleet_scale = f"{f.field_name}: {f.value}"
            break

    facilities = "Multiple operational hubs and regional branches"
    for f in facts_by_cat.get("manufacturing_infrastructure", []):
        if any(term in f.field_name.lower() for term in ("plant", "factory", "warehouse", "depot")):
            facilities = f"{f.field_name}: {f.value}"
            break

    # 3. Recent Developments
    recent_developments = []
    for sig in analysis.get("business_development_signals", [])[:4]:
        recent_developments.append(sig.get("signal") if isinstance(sig, dict) else str(sig))
    if not recent_developments:
        for f in facts_by_cat.get("news_developments", facts_by_cat.get("news", []))[:3]:
            recent_developments.append(f"{f.field_name}: {f.value}")

    # 4. Operational Insights
    ops_insights = [
        f"Operational Footprint: {analysis.get('operational_analysis', {}).get('manufacturing_footprint', 'Active multi-site operations.')}",
        f"Logistics & Network: {analysis.get('operational_analysis', {}).get('fleet_and_logistics_scale', 'Fleet and warehouse distribution.')}",
        f"Technology Adoption: {analysis.get('technology_maturity', {}).get('erp_systems_identified', 'Enterprise ERP and tracking tools.')}",
    ]

    # 5. Top DENSO Product Opportunities
    top_opportunities = []
    for opp in product_opportunities:
        top_opportunities.append({
            "product_code": opp.get("product_code"),
            "product_name": opp.get("product_name"),
            "relevance_level": opp.get("relevance_level"),
            "summary": opp.get("opportunity_summary"),
            "target_stakeholder": opp.get("recommended_stakeholder"),
            "talk_track": opp.get("sales_talk_track"),
        })

    # 6. Recommended Sales Strategy
    strongest = next(
        (o for o in product_opportunities if o.get("relevance_level") == "strong_evidence_backed"),
        product_opportunities[0] if product_opportunities else None,
    )
    sales_strategy = {
        "primary_product": strongest.get("product_name") if strongest else "DENSO Enterprise Solutions",
        "primary_contact_role": strongest.get("recommended_stakeholder") if strongest else "Head of Operations",
        "recommended_first_touch": strongest.get("sales_talk_track") if strongest else "Introduce DENSO operational optimization capabilities.",
        "key_discovery_question": strongest.get("discovery_questions", ["What are your primary initiatives to reduce operational losses?"])[0] if strongest else "",
        "suggested_next_action": strongest.get("next_recommended_action") if strongest else "Reach out with tailored solution brief.",
    }

    # 7. Research Confidence & Provenance
    verified_count = sum(1 for f in facts if getattr(f, "verification_status", "reported") == "verified")
    confidence_data = {
        "total_facts_extracted": len(facts),
        "verified_facts_count": verified_count,
        "evidence_grounding_score": round((verified_count / max(1, len(facts))) * 100, 1),
        "research_date": facts[0].created_at.strftime("%d %b %Y") if facts and hasattr(facts[0], "created_at") else "Current",
    }

    return {
        "company_name": company_name,
        "domain": domain,
        "overview": {
            "summary": overview_text,
            "industry": industry,
            "headquarters": hq,
        },
        "business_scale": {
            "revenue": revenue,
            "fleet_scale": fleet_scale,
            "facilities": facilities,
        },
        "recent_developments": recent_developments,
        "operational_insights": ops_insights,
        "denso_product_opportunities": top_opportunities,
        "sales_strategy": sales_strategy,
        "confidence": confidence_data,
    }


def detect_research_changes(
    current_facts: list[ResearchFact],
    previous_facts: list[ResearchFact],
    company_name: str,
) -> list[dict[str, Any]]:
    """Compare facts between successive research runs to identify what changed."""
    if not previous_facts:
        return []

    prev_by_field: dict[str, str] = {
        f.field_name.strip().lower(): f.value.strip() for f in previous_facts
    }

    changes: list[dict[str, Any]] = []

    for curr in current_facts:
        field_key = curr.field_name.strip().lower()
        curr_val = curr.value.strip()
        prev_val = prev_by_field.get(field_key)

        if prev_val is None:
            # Newly discovered fact
            is_high_impact = any(k in field_key for k in (
                "revenue", "profit", "ebitda", "director", "ceo", "cfo", "acquisition",
                "contract", "plant", "facility", "fleet", "warehouse"
            ))
            if is_high_impact:
                changes.append({
                    "category": curr.category,
                    "field_name": curr.field_name,
                    "change_type": "new_information",
                    "previous_value": "Not captured in previous research",
                    "new_value": curr_val,
                    "significance": f"Newly disclosed corporate development for {company_name}.",
                })
        elif curr_val.lower() != prev_val.lower():
            # Updated fact value
            changes.append({
                "category": curr.category,
                "field_name": curr.field_name,
                "change_type": "value_updated",
                "previous_value": prev_val,
                "new_value": curr_val,
                "significance": f"Updated figure/status from recent reports.",
            })

    return changes[:15]
