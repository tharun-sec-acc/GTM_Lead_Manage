import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.company_intelligence.models import (CompanyResearchProfile, ResearchAgentRun,
                                             ResearchCandidateSource, ResearchCitation,
                                             ResearchDiscoveryRun, ResearchDiscoveryTask,
                                             ResearchFact, ResearchJob,
                                             ResearchJobSource,
                                             ResearchReport, ResearchSource)
from app.company_intelligence.services.budget import BudgetExceeded, reserve_daily_job
from app.company_intelligence.sources.website import SourceError, normalize_domain
from app.database import get_db
from app.models import Lead, now
from app.tasks import run_company_research

router = APIRouter(prefix="/intelligence", tags=["company intelligence"])
_CATEGORIES = {"company", "news", "financial", "funding", "leadership", "competitors", "signals"}
_CATEGORY_ALIASES = {"overview": "company", "financials": "financial"}


class ResearchRequest(BaseModel):
    company_name: str = Field(min_length=1, max_length=500)
    website: str = Field(min_length=1, max_length=2048)
    lead_id: str | None = None
    country: str | None = Field(default=None, max_length=100)
    registration_id: str | None = Field(default=None, max_length=200)
    depth: str = "quick"
    inference_profile_id: str | None = Field(default=None, min_length=1, max_length=2048)
    force_refresh: bool = False

    @field_validator("depth")
    @classmethod
    def validate_depth(cls, value: str) -> str:
        if value not in {"quick", "comprehensive"}:
            raise ValueError("depth must be quick or comprehensive")
        return value

    @field_validator("inference_profile_id")
    @classmethod
    def validate_profile(cls, value: str | None) -> str | None:
        if value and not re.fullmatch(
            r"arn:aws:bedrock:[a-z0-9-]+:(?:\d{12})?:(?:application-)?inference-profile/[A-Za-z0-9._:/-]+",
            value,
        ):
            raise ValueError("Select an explicit Bedrock inference-profile ARN.")
        return value


def _json_time(value: datetime | None):
    return value.isoformat() if value else None


def _status_payload():
    provider = settings.research_search_provider.strip()
    search_configured = False
    search_name = provider or "none"
    if provider:
        search_name = f"unsupported:{provider}"
    model_configured = bool(settings.aws_region.strip() and settings.bedrock_model_id.strip())
    notes = []
    if not settings.company_intelligence_enabled:
        notes.append("Company Intelligence is disabled by configuration.")
    if not search_configured:
        notes.append("No external search API is configured; autonomous discovery uses sitemaps, feeds, outbound references and public indexes without a key.")
    if not settings.research_discovery_enabled:
        notes.append("Autonomous cross-domain discovery is disabled; only the confirmed official website is collected.")
    if not model_configured:
        notes.append("Bedrock is not configured; source collection can run, but structured extraction will be unavailable.")
    return {
        "enabled": settings.company_intelligence_enabled,
        "search_provider": search_name,
        "search_configured": search_configured,
        "model_configured": model_configured,
        "note": " ".join(notes) or "Public official-site research is available.",
    }


@router.get("/status")
def intelligence_status():
    return _status_payload()


def _require_enabled():
    if not settings.company_intelligence_enabled:
        raise HTTPException(503, "Company Intelligence is disabled by configuration.")


def _profile(session: Session, profile_id: str) -> CompanyResearchProfile:
    profile = session.get(CompanyResearchProfile, profile_id)
    if not profile:
        raise HTTPException(404, "Company intelligence profile not found.")
    return profile


def _job(session: Session, job_id: str) -> ResearchJob:
    job = session.get(ResearchJob, job_id)
    if not job:
        raise HTTPException(404, "Research job not found.")
    return job


def _report_for_job(session: Session, job_id: str) -> ResearchReport | None:
    return session.scalar(select(ResearchReport).where(
        ResearchReport.job_id == job_id
    ).order_by(ResearchReport.version.desc()))


def _summary(session: Session, job: ResearchJob):
    company = session.get(CompanyResearchProfile, job.company_id)
    report = _report_for_job(session, job.id)
    return {
        "id": job.id,
        "company_id": job.company_id,
        "company_name": company.company_name if company else "",
        "domain": company.domain if company else "",
        "lead_id": job.lead_id,
        "status": job.status,
        "progress": job.progress,
        "created_at": _json_time(job.created_at),
        "updated_at": _json_time(job.updated_at),
        "report_id": report.id if report else None,
    }


def _detail(session: Session, job: ResearchJob):
    summary = _summary(session, job)
    runs = session.scalars(select(ResearchAgentRun).where(
        ResearchAgentRun.job_id == job.id
    ).order_by(ResearchAgentRun.agent)).all()
    summary.update({
        "stage": job.stage,
        "error": job.error,
        "sources_count": job.sources_count,
        "pages_processed": job.pages_processed,
        "facts_count": job.facts_count,
        "agents": [{
            "id": run.id,
            "agent": run.agent,
            "status": run.status,
            "progress": run.progress,
            "error": run.error,
            "retry_count": run.retry_count,
            "started_at": _json_time(run.started_at),
            "finished_at": _json_time(run.finished_at),
        } for run in runs],
    })
    return summary


def _lead_domain(lead: Lead) -> str | None:
    if not lead.domain:
        return None
    try:
        return normalize_domain(lead.domain)
    except SourceError:
        return None


@router.post("/research", status_code=status.HTTP_202_ACCEPTED)
def create_research(data: ResearchRequest, session: Session = Depends(get_db)):
    _require_enabled()
    name = data.company_name.strip()
    if not name:
        raise HTTPException(422, "Company name is required.")
    try:
        domain = normalize_domain(data.website)
    except SourceError as exc:
        raise HTTPException(422, str(exc)) from exc
    lead = session.get(Lead, data.lead_id) if data.lead_id else None
    if data.lead_id and not lead:
        raise HTTPException(404, "Lead not found.")
    if lead and _lead_domain(lead) and _lead_domain(lead) != domain:
        raise HTTPException(409, "The website domain does not match the selected lead's confirmed company domain.")
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:domain))"), {"domain": domain})
    if lead:
        name = lead.company_name
    company = session.scalar(select(CompanyResearchProfile).where(
        CompanyResearchProfile.domain == domain
    ))
    if company and lead and company.lead_id and company.lead_id != lead.id:
        raise HTTPException(409, "This company profile is already linked to another lead.")
    if company is None:
        company = session.scalar(select(CompanyResearchProfile).where(
            CompanyResearchProfile.lead_id == data.lead_id
        )) if data.lead_id else None
    if company and company.domain != domain:
        raise HTTPException(409, "The selected lead already has a company profile with a different domain.")
    if company is None:
        company = CompanyResearchProfile(
            company_name=name, domain=domain, lead_id=lead.id if lead else None,
            country=data.country, registration_id=data.registration_id,
        )
        session.add(company)
        session.flush()
    else:
        if company.lead_id is None and lead:
            company.lead_id = lead.id
        company.company_name = name
        company.country = data.country or company.country
        company.registration_id = data.registration_id or company.registration_id

    active = session.scalar(select(ResearchJob).where(
        ResearchJob.company_id == company.id,
        ResearchJob.status.in_(("queued", "running")),
    ).order_by(ResearchJob.created_at.desc()))
    if active:
        if active.depth != data.depth or active.inference_profile_id != data.inference_profile_id:
            raise HTTPException(409, "Research is already active with different depth or model settings. Wait or cancel it first.")
        if lead and active.lead_id is None:
            active.lead_id = lead.id
        session.commit()
        return {"job_id": active.id, "company_id": company.id, "reused": True}
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, settings.research_cache_ttl_hours))
    recent = session.scalar(select(ResearchJob).where(
        ResearchJob.company_id == company.id,
        ResearchJob.status.in_(("completed", "partial")),
        ResearchJob.depth == data.depth,
        ResearchJob.inference_profile_id == data.inference_profile_id,
        ResearchJob.created_at >= cutoff,
    ).order_by(ResearchJob.created_at.desc()))
    if recent and not data.force_refresh:
        if lead and recent.lead_id is None:
            recent.lead_id = lead.id
        session.commit()
        return {"job_id": recent.id, "company_id": company.id, "reused": True}
    try:
        reserve_daily_job(session)
    except BudgetExceeded as exc:
        session.rollback()
        raise HTTPException(429, str(exc)) from exc
    job = ResearchJob(
        company_id=company.id, lead_id=lead.id if lead else None,
        depth=data.depth, force_refresh=data.force_refresh,
        inference_profile_id=data.inference_profile_id,
        status="queued", stage="queued", progress=0,
    )
    session.add(job)
    session.flush()
    company.latest_job_id = job.id
    from app.company_intelligence.orchestrator import _add_agent_runs
    _add_agent_runs(session, job.id)
    session.commit()
    try:
        run_company_research.delay(job.id)
    except Exception as exc:
        job.status, job.stage, job.error, job.finished_at = (
            "failed", "queue_error", "Research queue is unavailable; try again later.", now()
        )
        session.commit()
        raise HTTPException(503, job.error) from exc
    return {"job_id": job.id, "company_id": company.id, "reused": False}


@router.get("/research")
def list_research(lead_id: str | None = None, limit: int = Query(20, ge=1, le=100),
                  offset: int = Query(0, ge=0), session: Session = Depends(get_db)):
    query = select(ResearchJob)
    count_query = select(func.count(ResearchJob.id))
    if lead_id:
        query = query.where(ResearchJob.lead_id == lead_id)
        count_query = count_query.where(ResearchJob.lead_id == lead_id)
    total = session.scalar(count_query) or 0
    jobs = session.scalars(query.order_by(ResearchJob.created_at.desc()).limit(limit).offset(offset)).all()
    return {"items": [_summary(session, job) for job in jobs], "total": total}


@router.get("/research/{job_id}")
def get_research(job_id: str, session: Session = Depends(get_db)):
    return _detail(session, _job(session, job_id))


@router.get("/research/{job_id}/progress")
def get_research_progress(job_id: str, session: Session = Depends(get_db)):
    return _detail(session, _job(session, job_id))


@router.get("/research/{job_id}/discovery")
def research_discovery(job_id: str, limit: int = Query(200, ge=1, le=500),
                       session: Session = Depends(get_db)):
    job = _job(session, job_id)
    run = session.scalar(select(ResearchDiscoveryRun).where(
        ResearchDiscoveryRun.job_id == job.id
    ).order_by(ResearchDiscoveryRun.started_at.desc()))
    if not run:
        return {"job_id": job.id, "status": "not_run", "queries_count": 0,
                "counters": {}, "coverage": {}, "limitations": [],
                "tasks": [], "candidates": []}
    tasks = session.scalars(select(ResearchDiscoveryTask).where(
        ResearchDiscoveryTask.run_id == run.id
    ).order_by(ResearchDiscoveryTask.category, ResearchDiscoveryTask.query)).all()
    candidates = session.scalars(select(ResearchCandidateSource).where(
        ResearchCandidateSource.run_id == run.id
    ).order_by(ResearchCandidateSource.score.desc()).limit(limit)).all()
    return {
        "job_id": job.id, "run_id": run.id, "status": run.status,
        "queries_count": run.queries_count, "counters": run.counters or {},
        "coverage": run.coverage or {}, "limitations": run.limitations or [],
        "error": run.error, "started_at": _json_time(run.started_at),
        "finished_at": _json_time(run.finished_at),
        "tasks": [{"id": task.id, "query": task.query, "category": task.category,
                    "status": task.status, "candidates_found": task.candidates_found}
                   for task in tasks],
        "candidates": [{"id": candidate.id, "url": candidate.url,
                         "domain": candidate.domain, "title": candidate.title,
                         "source_category": candidate.source_category,
                         "discovered_via": candidate.discovered_via,
                         "state": candidate.state, "score": candidate.score,
                         "matched_terms": candidate.matched_terms,
                         "relevance_note": candidate.relevance_note,
                         "retrieval_method": candidate.retrieval_method,
                         "source_id": candidate.source_id,
                         "published_at": _json_time(candidate.published_at)}
                        for candidate in candidates],
    }


@router.post("/research/{job_id}/retry")
def retry_research(job_id: str, session: Session = Depends(get_db)):
    _require_enabled()
    job = _job(session, job_id)
    if job.status in {"queued", "running"}:
        raise HTTPException(409, "Research is already active.")
    failed = session.scalars(select(ResearchAgentRun).where(
        ResearchAgentRun.job_id == job.id, ResearchAgentRun.status == "failed"
    )).all()
    retryable = [run for run in failed if run.retry_count < max(1, settings.research_max_retries)]
    if not retryable and job.status == "failed":
        retryable = session.scalars(select(ResearchAgentRun).where(
            ResearchAgentRun.job_id == job.id, ResearchAgentRun.status == "pending"
        )).all()
    if not retryable:
        raise HTTPException(409, "No failed agent is eligible for retry.")
    for run in retryable:
        run.status, run.progress, run.error, run.finished_at = "pending", 0, None, None
        run.retry_count += 1
    for name in ("verification", "synthesis"):
        run = session.scalar(select(ResearchAgentRun).where(
            ResearchAgentRun.job_id == job.id, ResearchAgentRun.agent == name
        ))
        if run and run.status == "completed":
            run.status, run.progress, run.finished_at = "pending", 0, None
    job.status, job.stage, job.error, job.finished_at = "queued", "queued", None, None
    session.commit()
    try:
        run_company_research.delay(job.id)
    except Exception as exc:
        job.status, job.stage, job.error = "failed", "queue_error", "Research queue is unavailable; try again later."
        session.commit()
        raise HTTPException(503, job.error) from exc
    return _detail(session, job)


@router.post("/research/{job_id}/cancel")
def cancel_research(job_id: str, session: Session = Depends(get_db)):
    job = _job(session, job_id)
    if job.status in {"queued", "running"}:
        job.status, job.stage, job.error, job.finished_at = "cancelled", "cancelled", None, now()
        for run in session.scalars(select(ResearchAgentRun).where(
            ResearchAgentRun.job_id == job.id, ResearchAgentRun.status.in_(("pending", "running"))
        )):
            run.status, run.error, run.finished_at = "cancelled", "Research was cancelled.", now()
        session.commit()
    return _detail(session, job)


@router.get("/companies/{company_id}")
def company_detail(company_id: str, session: Session = Depends(get_db)):
    company = _profile(session, company_id)
    latest = session.get(ResearchJob, company.latest_job_id) if company.latest_job_id else None
    report = _report_for_job(session, latest.id) if latest else None
    return {
        "id": company.id, "company_name": company.company_name, "domain": company.domain,
        "lead_id": company.lead_id, "latest_job_id": company.latest_job_id,
        "last_researched_at": _json_time(company.last_researched_at),
        "report_id": report.id if report else None,
        "limitations": report.limitations if report else [],
    }


def _fact_item(session: Session, fact: ResearchFact):
    citations = session.scalars(select(ResearchCitation).where(
        ResearchCitation.fact_id == fact.id
    )).all()
    evidence = []
    for citation in citations:
        source = session.get(ResearchSource, citation.source_id)
        if not source:
            continue
        evidence.append({
            "source_id": source.id, "url": source.url, "title": source.title,
            "excerpt": citation.excerpt, "page_number": citation.page_number,
            "retrieved_at": _json_time(source.retrieved_at),
            "published_at": _json_time(source.published_at),
            "reliability": source.reliability,
        })
    return {
        "id": fact.id, "category": fact.category, "field_name": fact.field_name,
        "value": fact.value, "unit": fact.unit, "currency": fact.currency,
        "reporting_period": fact.reporting_period, "entity_scope": fact.entity_scope,
        "verification_status": fact.verification_status, "confidence": fact.confidence,
        "hypothesis": fact.hypothesis, "citations": evidence,
    }


@router.get("/companies/{company_id}/facts")
def company_facts(company_id: str, category: str | None = None, limit: int = Query(100, ge=1, le=500),
                  offset: int = Query(0, ge=0), session: Session = Depends(get_db), job_id: str | None = None):
    profile = _profile(session, company_id)
    selected_job = _company_job(session, profile, job_id)
    if category:
        category = _CATEGORY_ALIASES.get(category, category)
        if category not in _CATEGORIES:
            raise HTTPException(422, "Unknown research category.")
    query = select(ResearchFact).where(ResearchFact.company_id == company_id)
    count_query = select(func.count(ResearchFact.id)).where(ResearchFact.company_id == company_id)
    query = query.where(ResearchFact.job_id == selected_job)
    count_query = count_query.where(ResearchFact.job_id == selected_job)
    if category:
        query, count_query = query.where(ResearchFact.category == category), count_query.where(
            ResearchFact.category == category
        )
    total = session.scalar(count_query) or 0
    facts = session.scalars(query.order_by(ResearchFact.created_at.desc()).limit(limit).offset(offset)).all()
    return {"items": [_fact_item(session, fact) for fact in facts], "total": total}


@router.get("/companies/{company_id}/sources")
def company_sources(company_id: str, limit: int = Query(100, ge=1, le=500),
                    offset: int = Query(0, ge=0), session: Session = Depends(get_db), job_id: str | None = None):
    profile = _profile(session, company_id)
    selected_job = _company_job(session, profile, job_id)
    source_ids = select(ResearchJobSource.source_id).where(ResearchJobSource.job_id == selected_job)
    conditions = (ResearchSource.company_id == company_id, ResearchSource.id.in_(source_ids))
    total = session.scalar(select(func.count(ResearchSource.id)).where(*conditions)) or 0
    sources = session.scalars(select(ResearchSource).where(*conditions)
                              .order_by(ResearchSource.retrieved_at.desc()).limit(limit).offset(offset)).all()
    return {"items": [{
        "id": source.id, "url": source.url, "title": source.title, "domain": source.domain,
        "publisher": source.publisher, "published_at": _json_time(source.published_at),
        "retrieved_at": _json_time(source.retrieved_at), "content_hash": source.content_hash,
        "category": source.category, "reliability": source.reliability,
        "retrieval_method": source.retrieval_method, "excerpt": source.excerpt,
    } for source in sources], "total": total}


def _company_job(session: Session, company: CompanyResearchProfile, job_id: str | None) -> str | None:
    if job_id:
        job = _job(session, job_id)
        if job.company_id != company.id:
            raise HTTPException(404, "Research job does not belong to this company.")
        return job.id
    return company.latest_job_id


def _category_facts(company_id: str, category: str, limit: int, offset: int, session: Session):
    return company_facts(company_id, category, limit, offset, session)


@router.get("/companies/{company_id}/overview")
def company_overview(company_id: str, limit: int = Query(100, ge=1, le=500),
                     offset: int = Query(0, ge=0), session: Session = Depends(get_db)):
    return _category_facts(company_id, "company", limit, offset, session)


@router.get("/companies/{company_id}/financials")
def company_financials(company_id: str, limit: int = Query(100, ge=1, le=500),
                       offset: int = Query(0, ge=0), session: Session = Depends(get_db)):
    return _category_facts(company_id, "financial", limit, offset, session)


@router.get("/companies/{company_id}/news")
def company_news(company_id: str, limit: int = Query(100, ge=1, le=500),
                 offset: int = Query(0, ge=0), session: Session = Depends(get_db)):
    return _category_facts(company_id, "news", limit, offset, session)


@router.get("/companies/{company_id}/funding")
def company_funding(company_id: str, limit: int = Query(100, ge=1, le=500),
                    offset: int = Query(0, ge=0), session: Session = Depends(get_db)):
    return _category_facts(company_id, "funding", limit, offset, session)


@router.get("/companies/{company_id}/leadership")
def company_leadership(company_id: str, limit: int = Query(100, ge=1, le=500),
                       offset: int = Query(0, ge=0), session: Session = Depends(get_db)):
    return _category_facts(company_id, "leadership", limit, offset, session)


@router.get("/companies/{company_id}/competitors")
def company_competitors(company_id: str, limit: int = Query(100, ge=1, le=500),
                        offset: int = Query(0, ge=0), session: Session = Depends(get_db)):
    return _category_facts(company_id, "competitors", limit, offset, session)


@router.get("/companies/{company_id}/signals")
def company_signals(company_id: str, limit: int = Query(100, ge=1, le=500),
                    offset: int = Query(0, ge=0), session: Session = Depends(get_db)):
    return _category_facts(company_id, "signals", limit, offset, session)


@router.get("/reports/{report_id}")
def get_report(report_id: str, session: Session = Depends(get_db)):
    report = session.get(ResearchReport, report_id)
    if not report:
        raise HTTPException(404, "Research report not found.")
    return {
        "id": report.id, "company_id": report.company_id, "job_id": report.job_id,
        "version": report.version, "created_at": _json_time(report.created_at),
        "summary": report.summary, "sections": report.sections,
        "limitations": report.limitations,
    }
