"""Product opportunity analysis, research fact diff, and manual override APIs."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import bedrock
from app.database import get_db
from app.models import (
    Lead, Product, ProductLead, ProductOpportunity, ResearchFactOverride, now,
)
from app.company_intelligence.models import (
    CompanyResearchProfile, ResearchFact, ResearchJob,
)

router = APIRouter(tags=["product-research"])

OPPORTUNITY_STATUSES = {"draft", "reviewed", "approved"}


# ---- Schemas ----

class OpportunityStatusUpdate(BaseModel):
    status: str


class OverrideCreate(BaseModel):
    override_value: str = Field(min_length=1, max_length=50000)
    reason: str | None = Field(default=None, max_length=2000)
    created_by_note: str | None = Field(default=None, max_length=500)


# ---- Helpers ----

def _opp_response(opp: ProductOpportunity) -> dict:
    return {
        "id": opp.id, "product_lead_id": opp.product_lead_id,
        "research_job_id": opp.research_job_id,
        "opportunity_summary": opp.opportunity_summary,
        "pain_points": opp.pain_points, "use_cases": opp.use_cases,
        "relevance_score": opp.relevance_score, "confidence": opp.confidence,
        "evidence_fact_ids": opp.evidence_fact_ids,
        "status": opp.status, "manual_override": opp.manual_override,
        "created_at": opp.created_at, "updated_at": opp.updated_at,
    }


def _require_product_lead(session: Session, product_id: str, lead_id: str) -> ProductLead:
    pl = session.scalar(select(ProductLead).where(
        ProductLead.product_id == product_id, ProductLead.lead_id == lead_id
    ))
    if not pl:
        raise HTTPException(404, "Product-lead association not found.")
    return pl


# ---- Opportunity analysis ----

@router.post("/products/{product_id}/leads/{lead_id}/opportunity", status_code=201)
def create_opportunity(
    product_id: str, lead_id: str,
    inference_profile_id: str | None = Query(default=None),
    session: Session = Depends(get_db),
):
    product = session.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found.")
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found.")
    pl = _require_product_lead(session, product_id, lead_id)

    # Require completed research job for this company
    profile = session.scalar(
        select(CompanyResearchProfile).where(CompanyResearchProfile.lead_id == lead_id)
    )
    if not profile:
        raise HTTPException(422, "No research profile found for this company. Run company research first.")
    latest_job = session.scalar(
        select(ResearchJob).where(
            ResearchJob.company_id == profile.id,
            ResearchJob.status == "completed",
        ).order_by(ResearchJob.created_at.desc())
    )
    if not latest_job:
        raise HTTPException(422, "No completed research job found. Run and complete company research first.")

    # Collect reviewed facts
    facts = session.scalars(
        select(ResearchFact).where(
            ResearchFact.company_id == profile.id,
            ResearchFact.verification_status.in_(["reported", "verified", "partially_verified"]),
        ).limit(50)
    ).all()
    fact_summaries = [f"{f.field_name}: {f.value}" for f in facts]
    fact_ids = [f.id for f in facts]

    # Call Bedrock for opportunity analysis
    system_prompt = (
        "Return only a JSON object with these fields: "
        "opportunity_summary (string), pain_points (array of strings), "
        "use_cases (array of strings), relevance_score (float 0-1), confidence (float 0-1). "
        "Analyze the product fit for this company using only the supplied evidence. "
        "Do not invent facts. Mark hypotheses explicitly. "
        "Distinguish source-supported facts from inferences."
    )
    payload = {
        "product_name": product.name,
        "product_value_proposition": product.value_proposition or "",
        "product_context": product.product_context or "",
        "target_industries": product.target_industries or [],
        "company_name": lead.company_name,
        "company_domain": lead.domain or "",
        "company_industry": lead.industry or "",
        "research_facts": fact_summaries,
    }
    try:
        result = bedrock.converse_json(system_prompt, payload, model_id=inference_profile_id)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc

    if not isinstance(result, dict):
        raise HTTPException(502, "Bedrock returned an unexpected response for opportunity analysis.")

    opp = ProductOpportunity(
        product_lead_id=pl.id,
        research_job_id=latest_job.id,
        opportunity_summary=result.get("opportunity_summary") or "",
        pain_points=result.get("pain_points") or [],
        use_cases=result.get("use_cases") or [],
        relevance_score=result.get("relevance_score"),
        confidence=result.get("confidence"),
        evidence_fact_ids=fact_ids,
        status="draft",  # Always draft — never auto-approved
        manual_override=False,
        created_at=now(), updated_at=now(),
    )
    session.add(opp)
    session.commit()
    return _opp_response(opp)


@router.get("/products/{product_id}/leads/{lead_id}/opportunity")
def get_latest_opportunity(product_id: str, lead_id: str, session: Session = Depends(get_db)):
    pl = _require_product_lead(session, product_id, lead_id)
    opp = session.scalar(
        select(ProductOpportunity).where(ProductOpportunity.product_lead_id == pl.id)
        .order_by(ProductOpportunity.created_at.desc())
    )
    if not opp:
        raise HTTPException(404, "No opportunity analysis found.")
    return _opp_response(opp)


@router.patch("/products/{product_id}/leads/{lead_id}/opportunity/{opp_id}/status")
def update_opportunity_status(
    product_id: str, lead_id: str, opp_id: str,
    data: OpportunityStatusUpdate,
    session: Session = Depends(get_db),
):
    if data.status not in OPPORTUNITY_STATUSES:
        raise HTTPException(422, f"status must be one of: {sorted(OPPORTUNITY_STATUSES)}")
    pl = _require_product_lead(session, product_id, lead_id)
    opp = session.scalar(
        select(ProductOpportunity).where(
            ProductOpportunity.id == opp_id,
            ProductOpportunity.product_lead_id == pl.id,
        )
    )
    if not opp:
        raise HTTPException(404, "Opportunity not found.")
    opp.status = data.status
    opp.updated_at = now()
    session.commit()
    return _opp_response(opp)


# ---- Research fact diff ----

@router.get("/research/jobs/{job_id}/diff")
def research_fact_diff(job_id: str, session: Session = Depends(get_db)):
    """Compare facts from job_id against the previous completed job for the same company."""
    new_job = session.get(ResearchJob, job_id)
    if not new_job:
        raise HTTPException(404, "Research job not found.")

    prev_job = session.scalar(
        select(ResearchJob).where(
            ResearchJob.company_id == new_job.company_id,
            ResearchJob.id != new_job.id,
            ResearchJob.status == "completed",
        ).order_by(ResearchJob.created_at.desc())
    )

    new_facts = session.scalars(
        select(ResearchFact).where(ResearchFact.job_id == new_job.id)
    ).all()
    prev_facts = session.scalars(
        select(ResearchFact).where(ResearchFact.job_id == prev_job.id)
    ).all() if prev_job else []

    # Build lookup by (category, field_name)
    prev_map = {(f.category, f.field_name): f for f in prev_facts}
    new_map = {(f.category, f.field_name): f for f in new_facts}

    added, changed, unchanged, conflicting = [], [], [], []

    for key, new_f in new_map.items():
        if key not in prev_map:
            added.append({"fact_id": new_f.id, "category": new_f.category,
                          "field": new_f.field_name, "new_value": new_f.value, "old_value": None})
        else:
            old_f = prev_map[key]
            if new_f.value == old_f.value:
                unchanged.append({"fact_id": new_f.id, "category": new_f.category,
                                   "field": new_f.field_name, "value": new_f.value})
            else:
                # Simple heuristic: if both numeric, flag as conflicting; otherwise changed
                entry = {"fact_id": new_f.id, "old_fact_id": old_f.id,
                         "category": new_f.category, "field": new_f.field_name,
                         "old_value": old_f.value, "new_value": new_f.value}
                if any(c.isdigit() for c in old_f.value) and any(c.isdigit() for c in new_f.value):
                    conflicting.append(entry)
                else:
                    changed.append(entry)

    for key, old_f in prev_map.items():
        if key not in new_map:
            pass  # removed facts not surfaced (source may have been unavailable)

    return {
        "job_id": job_id,
        "prev_job_id": prev_job.id if prev_job else None,
        "added": added, "changed": changed,
        "unchanged_count": len(unchanged),
        "conflicting": conflicting,
    }


# ---- Research fact overrides ----

@router.post("/research/facts/{fact_id}/override", status_code=201)
def create_fact_override(fact_id: str, data: OverrideCreate, session: Session = Depends(get_db)):
    fact = session.get(ResearchFact, fact_id)
    if not fact:
        raise HTTPException(404, "Research fact not found.")
    override = ResearchFactOverride(
        fact_id=fact_id,
        override_value=data.override_value,
        reason=data.reason,
        created_by_note=data.created_by_note,
        created_at=now(),
    )
    session.add(override)
    session.commit()
    # Original fact unchanged
    return {
        "id": override.id, "fact_id": fact_id,
        "override_value": override.override_value,
        "reason": override.reason,
        "created_by_note": override.created_by_note,
        "created_at": override.created_at,
    }


@router.get("/research/facts/{fact_id}/overrides")
def list_fact_overrides(fact_id: str, session: Session = Depends(get_db)):
    fact = session.get(ResearchFact, fact_id)
    if not fact:
        raise HTTPException(404, "Research fact not found.")
    overrides = session.scalars(
        select(ResearchFactOverride).where(ResearchFactOverride.fact_id == fact_id)
        .order_by(ResearchFactOverride.created_at.desc())
    ).all()
    return [{"id": o.id, "fact_id": fact_id, "override_value": o.override_value,
             "reason": o.reason, "created_at": o.created_at} for o in overrides]


# Block mutating override records
@router.put("/research/fact-overrides/{override_id}", status_code=405)
def override_put_not_allowed(override_id: str):
    raise HTTPException(405, "Research fact overrides are append-only.")


@router.patch("/research/fact-overrides/{override_id}", status_code=405)
def override_patch_not_allowed(override_id: str):
    raise HTTPException(405, "Research fact overrides are append-only.")


@router.delete("/research/fact-overrides/{override_id}", status_code=405)
def override_delete_not_allowed(override_id: str):
    raise HTTPException(405, "Research fact overrides are append-only.")