"""DENSO Product Opportunity Intelligence Engine.

Evaluates company research evidence against approved DENSO products:
- IM: Integrated Manufacturing
- MCE: Mobility Commute Equipment
- VDI: Vehicle Digital Inspection
- TWMS: Transport Warehouse Management System
"""

from __future__ import annotations

import logging
from typing import Any

from app import bedrock
from app.config import settings
from app.company_intelligence.models import ResearchFact

logger = logging.getLogger(__name__)

APPROVED_DENSO_PRODUCTS = {
    "IM": {
        "full_name": "Integrated Manufacturing",
        "description": (
            "DENSO's Integrated Manufacturing (IM) solution digitizes factory shop-floor operations, "
            "optimizes production line efficiency, provides real-time loss tracking, industrial IoT telemetry, "
            "and enhances overall equipment effectiveness (OEE) with 75+ years of DENSO manufacturing excellence."
        ),
        "target_departments": ["Manufacturing & Plant Operations", "Industrial Engineering", "Quality Assurance", "Operations Excellence"],
        "target_stakeholders": ["Plant Head / Factory Manager", "VP / Director of Manufacturing", "Head of Operations", "Chief Technology Officer / Smart Factory Lead"],
        "signals_looked_for": [
            "manufacturing plants", "factories", "production facilities", "assembly lines",
            "capacity expansion", "shop-floor automation", "defect reduction", "downtime", "OEE",
            "lean manufacturing", "tier-1 manufacturing", "machinery"
        ],
    },
    "MCE": {
        "full_name": "Mobility Commute Equipment",
        "description": (
            "DENSO's Mobility Commute Equipment (MCE) provides digital hardware and software systems for "
            "corporate employee transportation, corporate commute route optimization, passenger safety monitoring, "
            "fleet transit equipment, and driver telemetry."
        ),
        "target_departments": ["Corporate Mobility & Commute", "Administration & Facilities", "Employee Transit", "Human Resources Operations"],
        "target_stakeholders": ["Head of Corporate Mobility", "VP Facilities & Administration", "Transport Operations Manager", "Director of Employee Services"],
        "signals_looked_for": [
            "employee commute", "workforce transit", "corporate buses", "shuttle operations",
            "shift transport", "passenger transport", "employee safety", "commute logistics"
        ],
    },
    "VDI": {
        "full_name": "Vehicle Digital Inspection",
        "description": (
            "DENSO's Vehicle Digital Inspection (VDI) digitizes pre-trip and post-trip commercial vehicle "
            "inspections, automated damage detection, tyre and component wear audits, driver checklists, "
            "and preventative maintenance scheduling to eliminate roadside breakdowns and audit failures."
        ),
        "target_departments": ["Fleet Maintenance", "Logistics Operations", "Vehicle Safety & Compliance", "Transportation"],
        "target_stakeholders": ["Fleet Director / Head of Fleet", "VP Logistics / Transport", "Fleet Maintenance Manager", "Safety & Compliance Officer"],
        "signals_looked_for": [
            "commercial vehicle fleet", "trucks", "trailers", "vehicles", "fleet maintenance",
            "inspections", "breakdowns", "driver checklists", "vehicle turnaround", "yard management",
            "fleet expansion", "road transport"
        ],
    },
    "TWMS": {
        "full_name": "Transport Warehouse Management System",
        "description": (
            "DENSO's Solwer TWMS (Transport & Warehouse Management System) unifies and digitizes end-to-end "
            "inbound and outbound supply chain operations, raw material movements, multi-depot warehouse management, "
            "dock scheduling, route optimization, and cross-docking, delivering 20–30% in freight cost savings."
        ),
        "target_departments": ["Supply Chain Management", "Logistics & Distribution", "Warehouse Operations", "Procurement & Freight"],
        "target_stakeholders": ["Chief Logistics Officer", "VP / Director of Supply Chain", "Head of Warehousing", "Freight & Distribution Head"],
        "signals_looked_for": [
            "warehouses", "depots", "distribution centers", "freight costs", "logistics network",
            "cross-docking", "supply chain digitization", "inbound logistics", "outbound distribution",
            "3PL", "4PL", "fleet operations", "dispatch tracking"
        ],
    },
}


def evaluate_product_opportunities(
    company_name: str,
    domain: str,
    facts: list[ResearchFact],
    profile_arn: str | None = None,
) -> list[dict[str, Any]]:
    """Evaluate research facts against the 4 approved DENSO products using Amazon Bedrock."""
    facts_summary = []
    for f in facts[:80]:
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
        "You are an expert DENSO Enterprise Sales Strategy Consultant. "
        "Analyze the target company's verified research facts and map them against the 4 approved DENSO solutions:\n"
        "1. IM: Integrated Manufacturing (factory shop-floor optimization, OEE, loss tracking)\n"
        "2. MCE: Mobility Commute Equipment (employee commute transport, corporate mobility transit)\n"
        "3. VDI: Vehicle Digital Inspection (commercial vehicle digital inspection checklists, damage/maintenance audits)\n"
        "4. TWMS: Transport Warehouse Management System (Solwer TWMS, inbound/outbound logistics, freight savings, warehouse management)\n\n"
        "Rules:\n"
        "- Return JSON object with key `opportunities`: an array of 4 objects (one for each product: IM, MCE, VDI, TWMS).\n"
        "- Classification must be strictly one of: 'strong_evidence_backed', 'potential_opportunity', 'opportunity_requiring_validation', 'insufficient_evidence'.\n"
        "- Never represent an inferred business challenge as a confirmed customer problem.\n"
        "- Include `supporting_fact_ids` linking to provided facts.\n"
        "- Provide 3 practical `discovery_questions` and a concise `sales_talk_track` (2-3 sentences) grounded in DENSO value.\n"
        "- Provide `confidence` (float 0.0 to 1.0) and `next_recommended_action`."
    )

    payload = {
        "company_name": company_name,
        "domain": domain,
        "approved_products": APPROVED_DENSO_PRODUCTS,
        "facts": facts_summary,
    }

    try:
        parsed = bedrock.converse_json(
            prompt_instruction,
            payload,
            model_id=profile_arn or None,
            max_tokens=4000,
        )
        if isinstance(parsed, dict) and isinstance(parsed.get("opportunities"), list):
            return parsed["opportunities"]
    except Exception as exc:
        logger.warning("Product opportunity evaluation LLM call failed: %s; falling back to deterministic heuristic.", exc)

    # Deterministic fallback heuristic grounded in facts
    results = []
    facts_text = " ".join([f"{f.field_name} {f.value}" for f in facts]).lower()

    for code, info in APPROVED_DENSO_PRODUCTS.items():
        matched_facts = []
        for f in facts:
            f_str = f"{f.field_name} {f.value}".lower()
            if any(signal in f_str for signal in info["signals_looked_for"]):
                matched_facts.append(f.id)

        match_count = len(matched_facts)
        if match_count >= 3:
            classification = "strong_evidence_backed"
            confidence = 0.85
        elif match_count >= 1:
            classification = "potential_opportunity"
            confidence = 0.65
        else:
            classification = "insufficient_evidence"
            confidence = 0.30

        results.append({
            "product_code": code,
            "product_name": info["full_name"],
            "relevance_level": classification,
            "confidence": confidence,
            "opportunity_summary": f"Opportunities for {company_name} to leverage DENSO {info['full_name']} based on {match_count} identified operating signals.",
            "identified_pain_point": f"Operating scale in {info['target_departments'][0]} requiring enhanced digital efficiency.",
            "supporting_fact_ids": matched_facts[:6],
            "target_department": info["target_departments"][0],
            "recommended_stakeholder": info["target_stakeholders"][0],
            "discovery_questions": [
                f"How does {company_name} currently track and optimize operational efficiency in your {info['target_departments'][0].lower()}?",
                f"What are your key metrics around reducing turnaround time and operational losses?",
                f"Are you exploring digital initiatives to integrate with your enterprise systems?"
            ],
            "sales_talk_track": f"DENSO {info['full_name']} has enabled leading enterprises to digitize operations and reduce costs with automotive-grade precision. We would welcome a 15-minute discussion to share how we can support {company_name}.",
            "next_recommended_action": f"Reach out to {info['target_stakeholders'][0]} with relevant {code} case study.",
        })

    return results
