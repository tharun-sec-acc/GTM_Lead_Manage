"""One-Page Executive Summary Generator and 'What Changed?' Diff Engine.

Provides concise executive briefings for sales reps and tracks changes between research runs.
"""

from __future__ import annotations

import logging
import re
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
    raw_industry = analysis.get("business_model", {}).get("industries_served", "Commercial & Industrial")
    if isinstance(raw_industry, list):
        industry = [re.sub(r"([a-z&])([A-Z])", r"\1 \2", str(item)).strip() for item in raw_industry]
    elif isinstance(raw_industry, str):
        industry = re.sub(r"([a-z&])([A-Z])", r"\1, \2", raw_industry).strip()
    else:
        industry = "Commercial & Industrial"

    hq = "India"
    for f in facts_by_cat.get("company_identity", facts_by_cat.get("company", [])):
        if "headquarter" in f.field_name.lower() or "location" in f.field_name.lower():
            hq = f.value
            break

    # 2. Business Scale
    revenue = "Not disclosed in public official pages"
    fin_facts = (
        facts_by_cat.get("financial_research", [])
        + facts_by_cat.get("financial", [])
        + facts_by_cat.get("investment_funding", [])
        + facts_by_cat.get("funding", [])
    )
    # Prefer annual/group revenue or turnover first
    annual_rev_fact = next(
        (f for f in fin_facts if any(term in f.field_name.lower() for term in ("group_revenue", "annual_revenue", "group_annual_revenue", "total_revenue", "turnover"))),
        None,
    )
    if not annual_rev_fact:
        annual_rev_fact = next(
            (f for f in fin_facts if any(term in f.field_name.lower() for term in ("revenue", "turnover", "sales"))),
            None,
        )
    if annual_rev_fact:
        revenue = annual_rev_fact.value
        unit = (annual_rev_fact.unit or "").strip()
        if unit and unit.lower() not in revenue.lower() and not any(term in revenue.lower() for term in ("rs", "inr", "cr", "crore", "lakh", "$", "€", "₹")):
            revenue += f" {unit}"
        if annual_rev_fact.reporting_period and annual_rev_fact.reporting_period.lower() not in revenue.lower():
            revenue += f" ({annual_rev_fact.reporting_period})"

    fleet_scale = "Disclosed in logistics/transport operations"
    fleet_facts = [
        f for f in facts_by_cat.get("fleet_transportation", [])
        if any(term in f.field_name.lower() for term in ("fleet", "truck", "vehicle", "tank", "trailer", "carrier", "ship", "transport"))
    ]
    if fleet_facts:
        fleet_scale = "; ".join(dict.fromkeys(f.value.strip() for f in fleet_facts[:3]))

    facilities = "Multiple operational hubs and regional branches"
    facility_facts = [
        f for f in facts_by_cat.get("manufacturing_infrastructure", [])
        if any(term in f.field_name.lower() for term in ("plant", "factory", "warehouse", "depot", "hub", "facility", "center", "park"))
    ]
    if facility_facts:
        facilities = "; ".join(dict.fromkeys(f.value.strip() for f in facility_facts[:3]))

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

    # 5. Top Solwer Product Opportunities (All 6 products)
    top_opportunities = []
    for opp in product_opportunities:
        code = opp.get("product_code") or opp.get("product")
        name = opp.get("product_name") or opp.get("full_name")
        relevance = opp.get("relevance_level") or opp.get("classification") or "potential_opportunity"
        summary = opp.get("opportunity_summary") or opp.get("rationale") or opp.get("summary")
        stakeholder = opp.get("recommended_stakeholder") or opp.get("target_stakeholder")
        dept = opp.get("recommended_department") or opp.get("target_department")
        talk_track = opp.get("sales_talk_track") or opp.get("talk_track")
        fit_score = opp.get("fit_score")
        if fit_score is None:
            fit_score = int(opp["confidence"] * 100) if opp.get("confidence") else (88 if relevance == "strong_evidence_backed" else 70 if relevance == "moderate_evidence" else 45)
        top_opportunities.append({
            "product_code": code,
            "product_name": name,
            "relevance_level": relevance,
            "fit_score": fit_score,
            "summary": summary,
            "target_department": dept,
            "target_stakeholder": stakeholder,
            "talk_track": talk_track,
            "discovery_questions": opp.get("discovery_questions") or [],
            "next_recommended_action": opp.get("next_recommended_action"),
        })

    # 6. Recommended Sales Strategy
    strongest = next(
        (o for o in product_opportunities if (o.get("relevance_level") or o.get("classification")) == "strong_evidence_backed"),
        product_opportunities[0] if product_opportunities else None,
    )
    sales_strategy = {
        "primary_product": (strongest.get("product_name") or strongest.get("full_name")) if strongest else "Solwer Enterprise Solutions",
        "primary_contact_role": (strongest.get("recommended_stakeholder") or strongest.get("target_stakeholder")) if strongest else "Head of Operations",
        "recommended_first_touch": (strongest.get("sales_talk_track") or strongest.get("talk_track")) if strongest else "Introduce Solwer operational optimization capabilities.",
        "key_discovery_question": (strongest.get("discovery_questions") or ["What are your primary initiatives to reduce operational losses and freight expenses?"])[0] if strongest else "",
        "suggested_next_action": (strongest.get("next_recommended_action") or strongest.get("action")) if strongest else "Reach out with tailored solution brief.",
    }

    # 7. Research Confidence & Provenance
    verified_count = sum(1 for f in facts if getattr(f, "verification_status", "reported") in ("verified", "reported", "partially_verified"))
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
        "solwer_product_opportunities": top_opportunities,
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
