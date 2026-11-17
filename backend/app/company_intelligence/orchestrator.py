import hashlib
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update

from app.config import settings
from app.database import SessionLocal
from app.models import Lead, now
from app.company_intelligence.agents.runner import extract_category_facts, quote_supports_fact
from app.company_intelligence.models import (CompanyResearchProfile, ResearchAgentRun,
                                             ResearchCitation, ResearchFact, ResearchJob,
                                             ResearchJobSource,
                                             ResearchReport, ResearchSource)
from app.company_intelligence.services.budget import (
    BudgetExceeded, release_source_bytes, reserve_source_bytes,
)
from app.company_intelligence.discovery.engine import run_discovery
from app.company_intelligence.sources.website import Page, SourceError, gather_official_pages

logger = logging.getLogger(__name__)

RESEARCH_CATEGORIES = ("company", "news", "financial", "funding", "leadership", "competitors", "signals")
AGENTS = (*RESEARCH_CATEGORIES, "verification", "synthesis")
TITLES = {
    "company": "Company overview",
    "news": "News and announcements",
    "financial": "Financial information",
    "funding": "Funding and investment",
    "leadership": "Leadership and management",
    "competitors": "Competitors and market",
    "signals": "Business signals",
}


def _error_text(message: str) -> str:
    return re.sub(r"\s+", " ", message).strip()[:1000]


def _add_agent_runs(session, job_id: str) -> None:
    for agent in AGENTS:
        if not session.scalar(select(ResearchAgentRun.id).where(
            ResearchAgentRun.job_id == job_id, ResearchAgentRun.agent == agent
        )):
            session.add(ResearchAgentRun(job_id=job_id, agent=agent, status="pending", progress=0))
    session.flush()


def _source_from_page(session, company_id: str, domain: str, page: Page) -> ResearchSource | None:
    existing = session.scalar(select(ResearchSource).where(
        ResearchSource.company_id == company_id,
        ResearchSource.url == page.url,
        ResearchSource.content_hash == page.content_hash,
    ))
    if existing:
        return existing
    duplicate = session.scalar(select(ResearchSource).where(
        ResearchSource.company_id == company_id,
        ResearchSource.content_hash == page.content_hash,
    ))
    if duplicate:
        return duplicate
    source = ResearchSource(
        company_id=company_id, url=page.url, canonical_url=page.url,
        domain=domain, title=page.title or page.url, publisher=domain,
        published_at=page.published_at, retrieved_at=now(),
        content_hash=page.content_hash or hashlib.sha256(page.text.encode("utf-8")).hexdigest(),
        category=page.category, reliability="official", retrieval_method=page.retrieval_method,
        excerpt=page.text[:2000], content_text=page.text,
    )
    session.add(source)
    session.flush()
    return source


def _sources_for_company(session, company_id: str) -> list[ResearchSource]:
    return session.scalars(select(ResearchSource).where(
        ResearchSource.company_id == company_id
    ).order_by(ResearchSource.retrieved_at.desc())).all()


def _job_cancelled(job_id: str) -> bool:
    with SessionLocal() as session:
        job = session.get(ResearchJob, job_id)
        return job is None or job.status == "cancelled"


def _agent_start(job_id: str, agent: str) -> bool:
    with SessionLocal.begin() as session:
        job = session.get(ResearchJob, job_id)
        if not job or job.status == "cancelled":
            return False
        run = session.scalar(select(ResearchAgentRun).where(
            ResearchAgentRun.job_id == job_id, ResearchAgentRun.agent == agent
        ))
        if not run or run.status in {"completed", "not_available"}:
            return False
        run.status, run.progress, run.error = "running", 5, None
        run.started_at, run.finished_at = now(), None
        job.stage = agent
        job.updated_at = now()
        return True


def _agent_finish(job_id: str, agent: str, status: str, output: dict | None = None,
                  error: str | None = None, progress: int = 100,
                  token_usage: dict | None = None) -> None:
    with SessionLocal.begin() as session:
        run = session.scalar(select(ResearchAgentRun).where(
            ResearchAgentRun.job_id == job_id, ResearchAgentRun.agent == agent
        ))
        if run:
            run.status, run.progress, run.error = status, progress, _error_text(error) if error else None
            run.output = output
            run.token_usage = token_usage
            run.finished_at = now()
        job = session.get(ResearchJob, job_id)
        if job:
            completed = session.scalar(select(func.count(ResearchAgentRun.id)).where(
                ResearchAgentRun.job_id == job_id,
                ResearchAgentRun.status.in_(("completed", "not_available", "failed")),
            )) or 0
            job.progress = min(95, int(completed * 100 / len(AGENTS)))
            job.updated_at = now()


def _verified_quote(source: ResearchSource | None, quote: str, fact: ResearchFact) -> bool:
    if not source or not quote or quote not in (source.content_text or ""):
        return False
    return quote_supports_fact(fact, quote, fact.category)


def _verify_facts(job_id: str) -> dict:
    with SessionLocal.begin() as session:
        facts = session.scalars(select(ResearchFact).where(ResearchFact.job_id == job_id)).all()
        grouped: dict[tuple, list[ResearchFact]] = {}
        accepted = 0
        for fact in facts:
            citations = session.scalars(select(ResearchCitation).where(
                ResearchCitation.fact_id == fact.id
            )).all()
            supported = any(
                _verified_quote(session.get(ResearchSource, citation.source_id),
                                citation.excerpt, fact)
                for citation in citations
            )
            fact.verification_status = "reported" if supported else "unverified"
            if supported:
                accepted += 1
                if fact.category in {"company", "financial", "leadership"}:
                    grouped.setdefault((fact.category, fact.field_name.casefold(),
                                        fact.reporting_period, fact.entity_scope, fact.currency, fact.unit), []).append(fact)
        conflicting = 0
        for claims in grouped.values():
            if len({claim.value.casefold().strip() for claim in claims}) > 1:
                conflicting += len(claims)
                for claim in claims:
                    claim.verification_status = "conflicting"
        return {"checked": len(facts), "reported": accepted - conflicting, "conflicting": conflicting}


def _synthesize_report(job_id: str, company_id: str, limitations: list[str]) -> ResearchReport:
    with SessionLocal.begin() as session:
        job = session.get(ResearchJob, job_id)
        facts = session.scalars(select(ResearchFact).where(
            ResearchFact.job_id == job_id
        ).order_by(ResearchFact.category, ResearchFact.field_name)).all()
        grouped: dict[str, list[ResearchFact]] = {category: [] for category in RESEARCH_CATEGORIES}
        for fact in facts:
            grouped.setdefault(fact.category, []).append(fact)
        sections = []
        for category in RESEARCH_CATEGORIES:
            items = [item for item in grouped.get(category, [])
                     if item.verification_status in {"reported", "conflicting"}]
            fact_ids = [item.id for item in items]
            text = "\n".join(f"{item.field_name}: {item.value}"
                             + (" [conflicting; do not use for outreach]" if item.verification_status == "conflicting" else "")
                             for item in items)
            run = session.scalar(select(ResearchAgentRun).where(
                ResearchAgentRun.job_id == job_id, ResearchAgentRun.agent == category
            ))
            if not text:
                text = ("Research not completed: " + run.error if run and run.status == "failed"
                        else "Not available from the retrieved public sources.")
            elif run and run.status == "failed":
                text += "\nResearch incomplete: " + run.error
            elif any(item.verification_status == "conflicting" for item in items):
                text += "\nConflicting claims are retained for review."
            sections.append({
                "category": category,
                "title": TITLES[category],
                "status": "available" if items else "not_available",
                "fact_ids": fact_ids,
                "text": text,
            })
        summary_facts = [item for item in facts if item.verification_status == "reported"][:5]
        summary = ("\n".join(f"{item.field_name}: {item.value}" for item in summary_facts)
                   if summary_facts else "No supported company facts were available from the retrieved sources.")
        if not limitations:
            limitations.append(
                "Research used bounded discovery across the official site, sitemaps, feeds, "
                "outbound references and public indexes; coverage is not comprehensive."
            )
        limitations.append(
            "No external search API provider is used. Discovered URLs are leads; only retrieved "
            "page content supports reported facts."
        )
        limitations.extend([
            ("Text-only browser fallback omits styles and allows only public same-site GET resources; external "
             "CDNs/APIs, images, media, WebSockets and service workers are blocked, so some content may be unavailable."
             if settings.research_browser_enabled
             else "Browser rendering is disabled; JavaScript-only pages were not accessed."),
            "Authenticated, paywalled, CAPTCHA-protected and access-controlled pages are not fetched.",
            "Numerical financial claims are excluded unless the source supports legal entity, currency, unit, period and scope.",
        ])
        version = (session.scalar(select(func.max(ResearchReport.version)).where(
            ResearchReport.company_id == company_id
        )) or 0) + 1
        report = ResearchReport(
            company_id=company_id, job_id=job_id, version=version,
            summary=summary, sections=sections, limitations=list(dict.fromkeys(limitations)),
        )
        session.add(report)
        session.flush()
        return report


def _role_response(job_id: str, company_id: str, agent: str,
                   profile_arn: str | None) -> tuple[str, dict, dict]:
    payload, usage = extract_category_facts(job_id, company_id, agent, profile_arn)
    return agent, payload, usage


def run_research_job(job_id: str) -> dict:
    errors: list[str] = []
    limitations: list[str] = []
    with SessionLocal.begin() as session:
        job = session.get(ResearchJob, job_id)
        if not job:
            return {"status": "not_found"}
        if job.status == "cancelled":
            return {"status": "cancelled"}
        claimed = session.execute(update(ResearchJob).where(
            ResearchJob.id == job_id, ResearchJob.status == "queued"
        ).values(status="running"))
        if claimed.rowcount != 1:
            return {"status": job.status}
        company = session.get(CompanyResearchProfile, job.company_id)
        if not company:
            job.status, job.error, job.finished_at = "failed", "Company research profile is unavailable.", now()
            return {"status": "failed"}
        _add_agent_runs(session, job_id)
        job.status, job.stage, job.error, job.updated_at = "running", "source_gathering", None, now()
        job.error = None
        company_id, domain, company_name = company.id, company.domain, company.company_name
        force_refresh, profile_arn, depth = job.force_refresh, job.inference_profile_id, job.depth

    with SessionLocal() as session:
        previous = session.scalar(select(ResearchJob).where(
            ResearchJob.company_id == company_id, ResearchJob.id != job_id,
            ResearchJob.status.in_(("completed", "partial"))
        ).order_by(ResearchJob.created_at.desc()))
        snapshot_job = previous.id if previous else job_id
        old_sources = session.scalars(select(ResearchSource).join(ResearchJobSource).where(
            ResearchJobSource.job_id == snapshot_job
        )).all()
    fresh_cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, settings.research_cache_ttl_hours))
    use_cache = bool(old_sources) and not force_refresh and all(
        (source.retrieved_at.replace(tzinfo=timezone.utc) if source.retrieved_at.tzinfo is None
         else source.retrieved_at) >= fresh_cutoff for source in old_sources
    )
    if use_cache:
        pages_count = len(old_sources)
        with SessionLocal.begin() as session:
            for source in old_sources:
                if session.get(ResearchJobSource, (job_id, source.id)) is None:
                    session.add(ResearchJobSource(job_id=job_id, source_id=source.id))
    else:
        max_pages = max(1, min(50, settings.research_max_pages_per_company))
        max_depth = max(0, min(5, settings.research_max_crawl_depth))
        if depth == "quick":
            max_pages, max_depth = min(max_pages, 5), min(max_depth, 1)
        max_bytes = max(65536, min(100_000_000, settings.research_max_total_content_size))
        reserved = False
        try:
            with SessionLocal.begin() as session:
                reserve_source_bytes(session, max_bytes)
            reserved = True
            pages, crawl_notes, _total_bytes = gather_official_pages(
                domain, max_pages, max_depth, max_bytes, cancelled=lambda: _job_cancelled(job_id)
            )
            limitations.extend(crawl_notes)
            with SessionLocal.begin() as session:
                for page in pages:
                    source = _source_from_page(session, company_id, domain, page)
                    if source and session.get(ResearchJobSource, (job_id, source.id)) is None:
                        session.add(ResearchJobSource(job_id=job_id, source_id=source.id))
                        session.flush()
            pages_count = len(pages)
            if settings.research_discovery_enabled and pages and not _job_cancelled(job_id):
                try:
                    discovery = run_discovery(
                        job_id, company_id, company_name, domain,
                        seed_texts=[page.text for page in pages][:10],
                        seed_links=[link for page in pages for link in page.external_links][:500],
                        cancelled=lambda: _job_cancelled(job_id),
                    )
                    if discovery.get("status") == "failed":
                        limitations.append(
                            "Cross-domain discovery did not complete: "
                            + str(discovery.get("error") or "unknown error")[:200]
                        )
                except Exception as exc:
                    limitations.append(f"Cross-domain discovery failed: {_error_text(str(exc))}")
            if reserved:
                with SessionLocal.begin() as session:
                    release_source_bytes(session, max_bytes - min(max_bytes, _total_bytes))
        except SourceError as exc:
            errors.append(_error_text(str(exc)))
            pages_count = 0
        except BudgetExceeded as exc:
            errors.append(_error_text(str(exc)))
            pages_count = 0
    with SessionLocal.begin() as session:
        sources = session.scalars(select(ResearchSource).join(ResearchJobSource).where(
            ResearchJobSource.job_id == job_id
        )).all()
        job = session.get(ResearchJob, job_id)
        if not job or job.status == "cancelled":
            return {"status": "cancelled"}
        job.pages_processed = pages_count
        job.sources_count = len(sources)
        if errors or limitations:
            job.error = "; ".join(errors + limitations[:4])[:1000]

    selected_categories = RESEARCH_CATEGORIES if depth == "comprehensive" else (
        "company", "news", "leadership", "signals"
    )
    work = []
    for agent in RESEARCH_CATEGORIES:
        with SessionLocal() as session:
            run = session.scalar(select(ResearchAgentRun).where(
                ResearchAgentRun.job_id == job_id, ResearchAgentRun.agent == agent
            ))
            if run and run.status == "completed":
                continue
        if _job_cancelled(job_id):
            break
        if agent not in selected_categories:
            _agent_finish(job_id, agent, "not_available", {
                "facts": [], "not_available": "This category is not included in quick research depth."
            })
            continue
        if not sources:
            if errors or limitations:
                error = "; ".join(errors + limitations[:2]) or "No accessible official-site sources."
                _agent_finish(job_id, agent, "failed", error=error, progress=0)
            else:
                _agent_finish(job_id, agent, "not_available",
                              {"facts": [], "not_available": "No accessible official-site sources."})
            continue
        if not _agent_start(job_id, agent):
            continue
        work.append(agent)

    max_workers = max(1, min(5, settings.research_max_concurrent_agents))
    if work:
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="company-research") as pool:
            futures = {pool.submit(_role_response, job_id, company_id, agent, profile_arn): agent for agent in work}
            for future in as_completed(futures):
                agent = futures[future]
                if _job_cancelled(job_id):
                    _agent_finish(job_id, agent, "cancelled", error="Research was cancelled.")
                    continue
                try:
                    _name, output, usage = future.result()
                    _agent_finish(job_id, agent, "completed", output, token_usage=usage)
                except Exception as exc:
                    error = _error_text(str(exc) or "The research agent failed.")
                    errors.append(f"{agent}: {error}")
                    logger.warning("Company research agent %s failed for job %s: %s", agent, job_id, error)
                    _agent_finish(job_id, agent, "failed", error=error, progress=0)

    if _job_cancelled(job_id):
        with SessionLocal.begin() as session:
            job = session.get(ResearchJob, job_id)
            if job:
                job.status, job.stage, job.finished_at = "cancelled", "cancelled", now()
        return {"status": "cancelled"}

    verification_ready = _agent_start(job_id, "verification")
    if verification_ready:
        try:
            output = _verify_facts(job_id)
            _agent_finish(job_id, "verification", "completed", output)
        except Exception as exc:
            errors.append(f"verification: {_error_text(str(exc))}")
            _agent_finish(job_id, "verification", "failed", error=str(exc), progress=0)
    synthesis_ready = _agent_start(job_id, "synthesis")
    report_id = None
    if synthesis_ready:
        try:
            report = _synthesize_report(job_id, company_id, limitations + errors)
            report_id = report.id
            _agent_finish(job_id, "synthesis", "completed", {"report_id": report.id})
        except Exception as exc:
            errors.append(f"synthesis: {_error_text(str(exc))}")
            _agent_finish(job_id, "synthesis", "failed", error=str(exc), progress=0)

    with SessionLocal.begin() as session:
        job = session.get(ResearchJob, job_id)
        company = session.get(CompanyResearchProfile, company_id)
        if not job or job.status == "cancelled":
            return {"status": "cancelled"}
        runs = session.scalars(select(ResearchAgentRun).where(
            ResearchAgentRun.job_id == job_id
        )).all()
        failed = [run.agent for run in runs if run.status == "failed"]
        report = session.scalar(select(ResearchReport).where(
            ResearchReport.job_id == job_id
        ).order_by(ResearchReport.version.desc()))
        if report:
            report_id = report.id
        job.facts_count = session.scalar(select(func.count(ResearchFact.id)).where(
            ResearchFact.job_id == job_id
        )) or 0
        job.sources_count = session.scalar(select(func.count(ResearchSource.id)).where(
            ResearchSource.id.in_(select(ResearchJobSource.source_id).where(ResearchJobSource.job_id == job_id))
        )) or 0
        job.status = ("failed" if not report else
                      "partial" if failed or job.error or errors or limitations else "completed")
        job.stage, job.progress, job.finished_at, job.updated_at = (
            "completed" if job.status == "completed" else "partial",
            100, now(), now()
        )
        if errors and not job.error:
            job.error = "; ".join(errors)[:1000]
        if company:
            company.latest_job_id, company.last_researched_at = job.id, now()
        return {"status": job.status, "report_id": report_id}
