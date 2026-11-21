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
from app.company_intelligence.analysis import (
    detect_research_changes,
    evaluate_product_opportunities,
    generate_one_page_summary,
    generate_strategic_analysis,
)
from app.company_intelligence.discovery.engine import run_discovery
from app.company_intelligence.sources.website import Page, SourceError, gather_official_pages

logger = logging.getLogger(__name__)

RESEARCH_CATEGORIES = (
    "company",
    "leadership",
    "corporate_relationships",
    "financial",
    "funding",
    "financial_risk",
    "business_operations",
    "fleet_transportation",
    "manufacturing_infrastructure",
    "technology_digital",
    "news",
    "competitors",
    "industry_market",
    "hiring_expansion",
    "signals",
)
AGENTS = (*RESEARCH_CATEGORIES, "verification", "synthesis")

TITLES = {
    "company": "Company Profile & Identity",
    "company_identity": "Company Profile & Identity",
    "leadership": "Leadership & Governance",
    "leadership_intelligence": "Leadership & Governance",
    "corporate_relationships": "Corporate Relationships & Subsidiaries",
    "financial": "Financial Performance & Scope",
    "financial_research": "Financial Performance & Scope",
    "funding": "Investments & Capital Allocation",
    "investment_funding": "Investments & Capital Allocation",
    "financial_risk": "Financial & Operational Risks",
    "business_operations": "Facilities & Operational Footprint",
    "fleet_transportation": "Fleet, Logistics & Transportation",
    "manufacturing_infrastructure": "Manufacturing & Plant Infrastructure",
    "technology_digital": "Technology, IT & Digital Maturity",
    "news": "News & Corporate Developments",
    "news_developments": "News & Corporate Developments",
    "competitors": "Competitors & Market Share",
    "competitor_intelligence": "Competitors & Market Share",
    "industry_market": "Industry Trends & Regulations",
    "hiring_expansion": "Hiring & Expansion Signals",
    "signals": "Operational Pain Points & GTM Fit",
    "pain_points_opportunities": "Operational Pain Points & GTM Fit",
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
        is_document=getattr(page, "is_document", False),
        mime_type=getattr(page, "mime_type", "text/html"),
        total_pages=getattr(page, "total_pages", None),
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
    if not source or not quote:
        return False
    norm_quote = re.sub(r"\s+", " ", quote).strip()
    norm_source = re.sub(r"\s+", " ", source.content_text or "").strip()
    if norm_quote not in norm_source:
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


def _format_executive_brief(company_name: str, grouped: dict[str, list[ResearchFact]]) -> str:
    name = company_name or "The company"
    paragraphs = []

    # 1. Company identity and business
    company_facts = [f for f in (grouped.get("company", []) + grouped.get("company_identity", [])) if f.verification_status == "reported"]
    if company_facts:
        lines = [f"{f.field_name}: {f.value}" for f in company_facts[:6]]
        paragraphs.append(f"**Company Profile & Operations:** {name} is evidenced across public sources with the following core operations:\n" + "\n".join(f"• {line}" for line in lines))

    # 2. Financial & Leadership
    fin_facts = [f for f in (grouped.get("financial", []) + grouped.get("financial_research", [])) if f.verification_status == "reported"]
    lead_facts = [f for f in (grouped.get("leadership", []) + grouped.get("leadership_intelligence", [])) if f.verification_status == "reported"]
    fin_lead_lines = []
    if lead_facts:
        fin_lead_lines.append(f"Key Leadership: {', '.join(f'{f.field_name} ({f.value})' for f in lead_facts[:4])}")
    if fin_facts:
        fin_lead_lines.append(f"Financial Metrics: {', '.join(f'{f.field_name} {f.value}' for f in fin_facts[:4])}")
    if fin_lead_lines:
        paragraphs.append(f"**Leadership & Financial Overview:**\n" + "\n".join(f"• {line}" for line in fin_lead_lines))

    # 3. Market, Signals & News
    signals = [f for f in (grouped.get("signals", []) + grouped.get("pain_points_opportunities", [])) if f.verification_status == "reported"]
    news = [f for f in (grouped.get("news", []) + grouped.get("news_developments", [])) if f.verification_status == "reported"]
    sig_lines = []
    if news:
        sig_lines.append(f"Recent Announcements: {', '.join(f'{f.field_name} ({f.value})' for f in news[:3])}")
    if signals:
        sig_lines.append(f"Operational & Technology Signals: {', '.join(f'{f.field_name}: {f.value}' for f in signals[:4])}")
    if sig_lines:
        paragraphs.append(f"**Strategic & Operational Signals:**\n" + "\n".join(f"• {line}" for line in sig_lines))

    if not paragraphs:
        all_reported = [f for cat in grouped.values() for f in cat if f.verification_status == "reported"][:8]
        if all_reported:
            return f"**Intelligence Summary for {name}:**\n" + "\n".join(f"• {f.field_name}: {f.value}" for f in all_reported)
        return "No supported company facts were available from the retrieved sources."
    return "\n\n".join(paragraphs)


def _generate_report_narratives(company_name: str, profile_arn: str | None,
                                facts_by_category: dict[str, list[dict]]) -> tuple[str, dict[str, str]]:
    """Synthesize executive overview and section narratives using Bedrock if profile provided."""
    if not profile_arn or not facts_by_category:
        return "", {}
    instruction = (
        "You are an executive research synthesis analyst for Solwer enterprise sales and GTM intelligence. "
        "Based ONLY on the provided verified company facts, generate an executive company brief. "
        "Return JSON with: "
        "- 'summary': A comprehensive 2-3 paragraph executive summary of the company, covering what they do, their industry presence, operational scale/infrastructure/fleet, key leadership, and strategic direction. "
        "- 'section_narratives': An object mapping category keys to a well-written 1-2 paragraph narrative briefing for that category explaining the facts in professional prose. "
        "Only state facts directly evidenced in the provided data. Do not fabricate or extrapolate unsupported claims. "
        "If a category has no facts, its narrative should be 'Not available from the retrieved public sources.'"
    )
    payload = {
        "company_name": company_name,
        "facts_by_category": facts_by_category,
    }
    try:
        from app import bedrock
        parsed = bedrock.converse_json(instruction, payload, model_id=profile_arn or None, max_tokens=4000)
        summary = parsed.get("summary") or ""
        narratives = parsed.get("section_narratives") or {}
        if isinstance(summary, str) and summary.strip() and isinstance(narratives, dict):
            return summary.strip(), {k: str(v) for k, v in narratives.items()}
    except Exception as exc:
        logger.warning("Bedrock executive synthesis failed (%s); using deterministic fact summary.", exc)
    return "", {}


def _synthesize_report(job_id: str, company_id: str, limitations: list[str],
                       company_name: str = "", profile_arn: str | None = None) -> ResearchReport:
    with SessionLocal.begin() as session:
        job = session.get(ResearchJob, job_id)
        domain = ""
        comp = session.get(CompanyResearchProfile, company_id)
        if comp:
            if not company_name:
                company_name = comp.company_name
            domain = comp.domain
        facts = session.scalars(select(ResearchFact).where(
            ResearchFact.job_id == job_id
        ).order_by(ResearchFact.category, ResearchFact.field_name)).all()
        grouped: dict[str, list[ResearchFact]] = {category: [] for category in RESEARCH_CATEGORIES}
        for fact in facts:
            grouped.setdefault(fact.category, []).append(fact)

        facts_dict = {}
        for category, items in grouped.items():
            valid_items = [f for f in items if f.verification_status in {"reported", "conflicting"}]
            if valid_items:
                facts_dict[category] = [{"field_name": f.field_name, "value": f.value} for f in valid_items]

        # 1. Strategic Research Analysis Engine
        strategic_analysis = generate_strategic_analysis(
            company_name=company_name,
            domain=domain,
            facts=facts,
            profile_arn=profile_arn,
        )

        # 2. Solwer Product Opportunity Engine (TWMS, LOSS_TRACKER_IM, VDI, FLEET_MGMT, MCE, CARBON_MGMT)
        product_opportunities = evaluate_product_opportunities(
            company_name=company_name,
            domain=domain,
            facts=facts,
            profile_arn=profile_arn,
        )

        # 3. 1-Page Executive Summary
        one_page_summary = generate_one_page_summary(
            company_name=company_name,
            domain=domain,
            facts=facts,
            analysis=strategic_analysis,
            product_opportunities=product_opportunities,
        )

        # 4. What Changed Since Last Research Run
        previous_job = session.scalar(select(ResearchJob).where(
            ResearchJob.company_id == company_id,
            ResearchJob.id != job_id,
            ResearchJob.status.in_(("completed", "partial")),
        ).order_by(ResearchJob.created_at.desc()))
        previous_facts = []
        if previous_job:
            previous_facts = session.scalars(select(ResearchFact).where(
                ResearchFact.job_id == previous_job.id
            )).all()
        what_changed = detect_research_changes(
            current_facts=facts,
            previous_facts=previous_facts,
            company_name=company_name,
        )

        executive_summary, narratives = _generate_report_narratives(company_name, profile_arn, facts_dict)

        sections = []
        for category in RESEARCH_CATEGORIES:
            items = [item for item in grouped.get(category, [])
                     if item.verification_status in {"reported", "conflicting"}]
            fact_ids = [item.id for item in items]
            run = session.scalar(select(ResearchAgentRun).where(
                ResearchAgentRun.job_id == job_id, ResearchAgentRun.agent == category
            ))

            narrative = narratives.get(category, "").strip()
            key_points = "\n".join(f"• {item.field_name}: {item.value}"
                                   + (" [conflicting; do not use for outreach]" if item.verification_status == "conflicting" else "")
                                   for item in items)
            if narrative and key_points:
                text = f"{narrative}\n\nKey Evidenced Points:\n{key_points}"
            elif key_points:
                text = key_points
            elif narrative:
                text = narrative
            else:
                text = ("Research not completed: " + run.error if run and run.status == "failed"
                        else "Not available from the retrieved public sources.")
            if run and run.status == "failed" and items:
                text += "\nResearch incomplete: " + run.error
            elif any(item.verification_status == "conflicting" for item in items):
                text += "\nConflicting claims are retained for review."

            sections.append({
                "category": category,
                "title": TITLES.get(category, category.replace("_", " ").title()),
                "status": "available" if items else "not_available",
                "fact_ids": fact_ids,
                "text": text,
            })

        if executive_summary:
            summary = executive_summary
        else:
            summary = _format_executive_brief(company_name, grouped)
        if not limitations:
            limitations.append(
                "Research used bounded discovery across the official site, sitemaps, feeds, "
                "outbound references, statutory filings, documents and public indexes; coverage is not comprehensive."
            )
        limitations.append(
            "Discovered URLs are leads; only retrieved page and document content supports reported facts."
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
            one_page_summary=one_page_summary,
            analysis_data=strategic_analysis,
            product_opportunities=product_opportunities,
            what_changed=what_changed,
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
            pages = []
            try:
                pages, crawl_notes, _total_bytes = gather_official_pages(
                    domain, max_pages, max_depth, max_bytes, cancelled=lambda: _job_cancelled(job_id)
                )
                limitations.extend(crawl_notes)
            except SourceError as exc:
                limitations.append(f"Official website crawl not completed: {_error_text(str(exc))}")
                _total_bytes = 0

            with SessionLocal.begin() as session:
                for page in pages:
                    source = _source_from_page(session, company_id, domain, page)
                    if source and session.get(ResearchJobSource, (job_id, source.id)) is None:
                        session.add(ResearchJobSource(job_id=job_id, source_id=source.id))
                        session.flush()
            pages_count = len(pages)
            if settings.research_discovery_enabled and not _job_cancelled(job_id):
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
        job.documents_analyzed = sum(1 for s in sources if getattr(s, "is_document", False))
        if errors or limitations:
            job.error = "; ".join(errors + limitations[:4])[:1000]

    selected_categories = set(RESEARCH_CATEGORIES) if depth == "comprehensive" else {
        "company", "news", "leadership", "signals", "financial",
    }
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
            report = _synthesize_report(job_id, company_id, limitations + errors,
                                        company_name=company_name, profile_arn=profile_arn)
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

        # Phase 8: Sync AI Research & Findings to Zoho CRM Note & Account
        try:
            from app.zoho.service import ZohoService
            ZohoService(session).sync_research_to_zoho(job.id)
        except Exception as ze:
            logger.warning("Zoho CRM research note sync deferred or skipped: %s", ze)

        return {"status": job.status, "report_id": report_id}
