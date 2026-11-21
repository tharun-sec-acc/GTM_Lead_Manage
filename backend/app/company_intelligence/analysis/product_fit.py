"""Solwer Product Opportunity Intelligence Engine.

Evaluates company research evidence against 6 official Solwer products:
- TWMS: Transport & Warehouse Management System
- LOSS_TRACKER_IM: Loss Tracker / IM (Integrated Manufacturing)
- VDI: Vehicle Digital Inspection
- FLEET_MGMT: Fleet Management
- MCE: Mobility Aftermarket SuperApp
- CARBON_MGMT: Carbon Footprint Management
"""

from __future__ import annotations

import logging
from typing import Any

from app import bedrock
from app.config import settings
from app.company_intelligence.models import ResearchFact

logger = logging.getLogger(__name__)

APPROVED_SOLWER_PRODUCTS: dict[str, dict[str, Any]] = {
    "TWMS": {
        "full_name": "TWMS (Transport & Warehouse Management System)",
        "official_url": "https://solwerindia.com/products/transport-warehouse-management/",
        "business_area": "Logistics & Supply Chain",
        "description": (
            "Solwer TWMS unifies and digitizes end-to-end inbound and outbound supply chain operations, "
            "raw material movements, multi-depot warehouse management, dock scheduling, vehicle selection, "
            "load optimization, and route planning, delivering 20–30% in transport and logistics cost savings."
        ),
        "target_departments": [
            "Logistics & Supply Chain",
            "Warehouse Operations",
            "Distribution & Fulfillment",
            "Freight & Procurement",
        ],
        "target_stakeholders": [
            "Chief Logistics Officer",
            "VP / Director of Supply Chain",
            "Head of Warehousing",
            "Freight & Distribution Head",
        ],
        "signals_looked_for": [
            "warehouse", "warehouses", "depot", "depots", "distribution center", "distribution centers",
            "freight", "logistics", "supply chain", "inbound", "outbound", "cross-docking", "cargo",
            "3pl", "4pl", "multimodal", "dock door", "shipping", "transport", "ftl", "ltl", "dispatch",
        ],
    },
    "LOSS_TRACKER_IM": {
        "full_name": "Loss Tracker / IM (Integrated Manufacturing)",
        "official_url": "https://solwerindia.com/products/loss-tracker/",
        "business_area": "Manufacturing & Plant Operations",
        "description": (
            "Solwer Loss Tracker / IM digitizes factory shop-floor operations, captures real-time machine uptime "
            "and downtime root causes, tracks micro-stoppages, calculates line-level OEE, reduces scrap rates, "
            "and drives continuous KAIZEN improvements across manufacturing lines."
        ),
        "target_departments": [
            "Manufacturing & Plant Operations",
            "Industrial Engineering",
            "Quality Assurance & Kaizen",
            "Operations Excellence",
        ],
        "target_stakeholders": [
            "Plant Head / Factory Director",
            "VP / Director of Manufacturing",
            "Head of Operations Excellence",
            "Continuous Improvement / Kaizen Lead",
        ],
        "signals_looked_for": [
            "manufacturing", "factory", "factories", "plant", "plants", "production facility", "assembly line",
            "machinery", "shop-floor", "oee", "kaizen", "scrap", "downtime", "bottleneck", "micro-stoppages",
            "lean manufacturing", "fabrication", "industrial equipment",
        ],
    },
    "VDI": {
        "full_name": "Vehicle Digital Inspection (VDI)",
        "official_url": "https://solwerindia.com/products/vehicle-digital-inspection/",
        "business_area": "Automotive Inspection & Quality Assurance",
        "description": (
            "Solwer Vehicle Digital Inspection (VDI) provides AI-powered mobile inspections, standardized digital checklists, "
            "automated scratch/dent detection, tamper-proof photo audit trails, and transparent vehicle condition grading "
            "to eliminate turnaround delays and damage dispute claims."
        ),
        "target_departments": [
            "Vehicle Quality & Inspection",
            "Used Car / Pre-Owned Operations",
            "Fleet Maintenance",
            "Yard Operations & Intake",
        ],
        "target_stakeholders": [
            "VP Pre-Owned / Used Car Business",
            "Head of Quality & Inspection",
            "Fleet Maintenance Director",
            "Workshop & Yard General Manager",
        ],
        "signals_looked_for": [
            "vehicle inspection", "inspection", "used car", "pre-owned", "condition checklist", "damage detection",
            "scratch", "dent", "yard management", "dealership", "vehicle intake", "refurbishment", "grading report",
            "pre-trip", "post-trip", "vehicle turnaround",
        ],
    },
    "FLEET_MGMT": {
        "full_name": "Fleet Management",
        "official_url": "https://solwerindia.com/products/fleet-management/",
        "business_area": "Fleet & Mobility",
        "description": (
            "Solwer Fleet Management provides a comprehensive fleet digitalization platform managing driver pre/post-trip readiness, "
            "preventative vehicle maintenance schedules, driver accountability scorecards, telematics integration, "
            "and commercial asset uptime monitoring."
        ),
        "target_departments": [
            "Fleet Operations & Maintenance",
            "Transport Logistics",
            "Driver Operations & Safety",
        ],
        "target_stakeholders": [
            "Head of Fleet Operations",
            "Director of Fleet Maintenance",
            "VP Transportation",
            "Chief Operating Officer",
        ],
        "signals_looked_for": [
            "fleet", "trucks", "trailers", "commercial vehicles", "drivers", "telematics", "gps",
            "vehicle maintenance", "road transport", "safety checklist", "vehicle downtime", "breakdowns",
            "fuel management", "asset tracking", "tankers", "haulage",
        ],
    },
    "MCE": {
        "full_name": "Mobility Aftermarket SuperApp (MCE)",
        "official_url": "https://solwerindia.com/products/mobility-aftermarket-superapp/",
        "business_area": "Automotive Aftermarket & Service Networks",
        "description": (
            "Solwer Mobility Aftermarket SuperApp (MCE) creates a unified digital ecosystem connecting workshops, spare parts distributors, "
            "and vehicle owners for transparent maintenance workflows, rapid parts ordering, job card digitization, "
            "and customer service updates."
        ),
        "target_departments": [
            "Aftermarket & Service Networks",
            "Spare Parts Distribution",
            "Workshop Operations & Dealer Service",
        ],
        "target_stakeholders": [
            "VP Aftermarket & Customer Service",
            "Head of Service Network",
            "Spare Parts Business Head",
            "Workshop Operations Director",
        ],
        "signals_looked_for": [
            "workshop", "workshops", "service center", "service network", "spare parts", "aftermarket",
            "garages", "mechanics", "job card", "repair", "vehicle servicing", "dealership service", "spare parts distributor",
        ],
    },
    "CARBON_MGMT": {
        "full_name": "Carbon Footprint Management",
        "official_url": "https://solwerindia.com/products/carbon-footprint-management/",
        "business_area": "ESG & Sustainable Mobility",
        "description": (
            "Solwer Carbon Footprint Management automates Scope 1, 2, and 3 emissions accounting across freight routes, "
            "factories, and multi-depot supply chains, enabling green carrier allocation, fleet decarbonization pathways, "
            "and regulatory compliance for SEBI BRSR and global ESG disclosures."
        ),
        "target_departments": [
            "Sustainability & ESG",
            "EHS (Environmental Health & Safety)",
            "Green Supply Chain",
            "Corporate Compliance",
        ],
        "target_stakeholders": [
            "Chief Sustainability Officer (CSO)",
            "Head of ESG & Compliance",
            "VP Logistics & Green Supply Chain",
            "Director of Regulatory Affairs",
        ],
        "signals_looked_for": [
            "carbon", "esg", "scope 1", "scope 2", "scope 3", "emission", "emissions", "sustainability",
            "green logistics", "decarbonization", "net zero", "brsr", "environmental", "fuel efficiency", "ev fleet", "green energy",
        ],
    },
}

# Alias for backwards compatibility
APPROVED_DENSO_PRODUCTS = APPROVED_SOLWER_PRODUCTS


def _normalize_opportunity(opp: dict[str, Any], default_info: dict[str, Any], code: str, company_name: str) -> dict[str, Any]:
    """Ensure an opportunity dict contains all required UI and analysis fields."""
    prod_code = opp.get("product_code") or opp.get("product") or code
    prod_name = opp.get("product_name") or opp.get("full_name") or default_info["full_name"]
    relevance = opp.get("relevance_level") or opp.get("classification") or "potential_opportunity"
    
    # Calculate numeric fit score (0-100)
    raw_score = opp.get("fit_score")
    if raw_score is None:
        confidence = float(opp.get("confidence") or 0.65)
        fit_score = int(confidence * 100) if confidence <= 1.0 else int(confidence)
    else:
        fit_score = int(raw_score)

    summary = (
        opp.get("opportunity_summary")
        or opp.get("rationale")
        or opp.get("summary")
        or f"Opportunities for {company_name} to leverage Solwer {prod_name}."
    )
    dept = (
        opp.get("recommended_department")
        or opp.get("target_department")
        or default_info["target_departments"][0]
    )
    stakeholder = (
        opp.get("recommended_stakeholder")
        or opp.get("target_stakeholder")
        or default_info["target_stakeholders"][0]
    )
    talk_track = (
        opp.get("sales_talk_track")
        or opp.get("talk_track")
        or f"Solwer {prod_name} enables enterprises to digitize operations and achieve significant cost and efficiency gains."
    )
    questions = opp.get("discovery_questions") or [
        f"How does {company_name} currently manage operational workflows in {dept}?",
        "What are your primary initiatives to reduce operational turnaround times and operating costs?",
        "Are you actively evaluating digital solutions to integrate with your enterprise backbone?",
    ]
    action = (
        opp.get("next_recommended_action")
        or opp.get("action")
        or f"Engage {stakeholder} with a tailored {prod_name} briefing."
    )
    fact_ids = opp.get("supporting_fact_ids") or []

    return {
        "product_code": prod_code,
        "product_name": prod_name,
        "relevance_level": relevance,
        "confidence": round(fit_score / 100.0, 2),
        "fit_score": fit_score,
        "opportunity_summary": summary,
        "identified_pain_point": opp.get("identified_pain_point") or f"Scale and complexity in {dept}.",
        "supporting_fact_ids": fact_ids[:10],
        "target_department": dept,
        "recommended_department": dept,
        "recommended_stakeholder": stakeholder,
        "discovery_questions": questions,
        "sales_talk_track": talk_track,
        "next_recommended_action": action,
    }


def evaluate_product_opportunities(
    company_name: str,
    domain: str,
    facts: list[ResearchFact],
    profile_arn: str | None = None,
) -> list[dict[str, Any]]:
    """Evaluate research facts against the 6 approved Solwer products using Amazon Bedrock or heuristic fallback."""
    facts_summary = []
    for f in facts[:100]:
        val = f.value
        if f.unit:
            val += f" {f.unit}"
        if f.reporting_period:
            val += f" ({f.reporting_period})"
        facts_summary.append({
            "fact_id": f.id,
            "category": f.category,
            "field": f.field_name,
            "value": val,
        })

    prompt_instruction = (
        "You are an expert Solwer Enterprise Sales Strategy Consultant. "
        "Analyze the target company's verified research facts and map them against all 6 official Solwer solutions:\n"
        "1. TWMS: Transport & Warehouse Management System (inbound/outbound logistics, freight cost reduction, multi-depot WMS)\n"
        "2. LOSS_TRACKER_IM: Loss Tracker / IM (smart factory shop-floor optimization, OEE, downtime/scrap reduction, Kaizen)\n"
        "3. VDI: Vehicle Digital Inspection (commercial vehicle condition checklists, AI scratch/damage detection, yard intake audits)\n"
        "4. FLEET_MGMT: Fleet Management (driver pre/post-trip checks, fleet maintenance scheduling, telematics, asset uptime)\n"
        "5. MCE: Mobility Aftermarket SuperApp (workshop digitization, spare parts ordering, job cards, service network)\n"
        "6. CARBON_MGMT: Carbon Footprint Management (Scope 1/2/3 logistics emissions, green routing, SEBI BRSR ESG compliance)\n\n"
        "Rules:\n"
        "- Return JSON object with key `opportunities`: an array of exactly 6 objects (one for each product: TWMS, LOSS_TRACKER_IM, VDI, FLEET_MGMT, MCE, CARBON_MGMT).\n"
        "- Each object must have: `product_code`, `product_name`, `relevance_level`, `fit_score` (0-100), `opportunity_summary`, "
        "`recommended_department`, `recommended_stakeholder`, `sales_talk_track` (2-3 sentences), `discovery_questions` (list of 3), `next_recommended_action`, and `supporting_fact_ids`.\n"
        "- `relevance_level` must be strictly one of: 'strong_evidence_backed', 'moderate_evidence', 'potential_opportunity', 'insufficient_evidence'.\n"
        "- Base all assessments strictly on the provided facts. Never fabricate unsupported customer problems."
    )

    payload = {
        "company_name": company_name,
        "domain": domain,
        "approved_products": APPROVED_SOLWER_PRODUCTS,
        "facts": facts_summary,
    }

    bedrock_results_by_code: dict[str, dict[str, Any]] = {}
    try:
        parsed = bedrock.converse_json(
            prompt_instruction,
            payload,
            model_id=profile_arn or None,
            max_tokens=5000,
        )
        if isinstance(parsed, dict) and isinstance(parsed.get("opportunities"), list):
            for opp in parsed["opportunities"]:
                if isinstance(opp, dict):
                    c = str(opp.get("product_code") or opp.get("product") or "").strip()
                    if c:
                        bedrock_results_by_code[c] = opp
    except Exception as exc:
        logger.warning("Product opportunity evaluation LLM call failed: %s; falling back to deterministic heuristic.", exc)

    # Deterministic fallback & completion for any missing products
    final_results = []
    facts_text = " ".join([f"{f.field_name} {f.value}" for f in facts]).lower()

    for code, info in APPROVED_SOLWER_PRODUCTS.items():
        if code in bedrock_results_by_code:
            final_results.append(_normalize_opportunity(bedrock_results_by_code[code], info, code, company_name))
            continue

        matched_facts = []
        for f in facts:
            f_str = f"{f.field_name} {f.value}".lower()
            if any(signal in f_str for signal in info["signals_looked_for"]):
                matched_facts.append(f.id)

        match_count = len(matched_facts)
        if match_count >= 3:
            classification = "strong_evidence_backed"
            confidence = 0.88
            fit_score = 88
        elif match_count >= 1:
            classification = "moderate_evidence"
            confidence = 0.70
            fit_score = 70
        else:
            classification = "potential_opportunity"
            confidence = 0.45
            fit_score = 45

        fallback_opp = {
            "product_code": code,
            "product_name": info["full_name"],
            "relevance_level": classification,
            "confidence": confidence,
            "fit_score": fit_score,
            "opportunity_summary": f"Opportunities for {company_name} to leverage Solwer {info['full_name']} based on {match_count} identified operating signals.",
            "identified_pain_point": f"Operating scale in {info['target_departments'][0]} requiring enhanced digital efficiency.",
            "supporting_fact_ids": matched_facts[:6],
            "target_department": info["target_departments"][0],
            "recommended_department": info["target_departments"][0],
            "recommended_stakeholder": info["target_stakeholders"][0],
            "discovery_questions": [
                f"How does {company_name} currently track and optimize operational efficiency in your {info['target_departments'][0].lower()}?",
                f"What are your key metrics around reducing turnaround time and operational costs?",
                f"Are you exploring digital initiatives to integrate with your enterprise systems?"
            ],
            "sales_talk_track": f"Solwer {info['full_name']} has enabled leading enterprises to digitize operations and reduce costs. We would welcome a 15-minute discussion to share how we can support {company_name}.",
            "next_recommended_action": f"Reach out to {info['target_stakeholders'][0]} with relevant {code} case study.",
        }
        final_results.append(_normalize_opportunity(fallback_opp, info, code, company_name))

    return final_results
