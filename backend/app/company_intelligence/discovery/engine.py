"""Autonomous multi-source discovery engine.

Runs after the official-site crawl. It builds deterministic discovery queries, gathers
candidate URLs from sitemaps, feeds, outbound links, references and public indexes, then
retrieves a bounded, scored set of pages from multiple domains. A candidate is only a lead:
it becomes a usable source after its content is actually retrieved and persisted.
"""

import hashlib
import logging
import re
import time
from urllib.parse import urlsplit

from sqlalchemy import func, select

from app.config import settings
from app.database import SessionLocal
from app.models import Lead, now
from app.company_intelligence.discovery import adapters, policy
from app.company_intelligence.discovery.queries import expand_queries, query_terms
from app.company_intelligence.models import (
    CompanyResearchProfile, ResearchCandidateSource, ResearchDiscoveryRun,
    ResearchDiscoveryTask, ResearchJobSource, ResearchSource,
)
from app.company_intelligence.services.budget import (
    BudgetExceeded, release_source_bytes, reserve_source_bytes,
)
from app.company_intelligence.sources.website import (
    SourceError, crawl_delay_for, fetch_public_page_adaptive, robots_for,
)

logger = logging.getLogger(__name__)

COVERAGE_CATEGORIES = ("company", "news", "financial", "funding", "leadership", "competitors", "signals")

# States a discovered source can hold. Verification applies to facts, not to URLs.
STATES = (
    "discovered", "queued", "retrieved", "extracted", "relevant",
    "evidence_bearing", "verified", "conflicting", "rejected", "unavailable",
)


def _empty_counters() -> dict:
    return {
        "discovery_tasks_created": 0,
        "candidate_urls_discovered": 0,
        "unique_domains_discovered": 0,
        "urls_rejected": 0,
        "urls_queued": 0,
        "http_retrievals": 0,
        "browser_retrievals": 0,
        "pdfs_processed": 0,
        "sources_with_content": 0,
        "evidence_bearing_sources": 0,
        "extraction_failures": 0,
        "duplicate_sources": 0,
        "budget_exhausted": 0,
        "cross_domain_sources": 0,
        "domains_fetched": 0,
    }


def _create_run(job_id: str, company_id: str) -> str:
    with SessionLocal.begin() as session:
        run = ResearchDiscoveryRun(
            job_id=job_id, company_id=company_id, status="running",
            counters=_empty_counters(), coverage={}, limitations=[], started_at=now(),
        )
        session.add(run)
        session.flush()
        return run.id


def _profile_context(company_id: str) -> dict:
    with SessionLocal() as session:
        profile = session.get(CompanyResearchProfile, company_id)
        lead = session.get(Lead, profile.lead_id) if profile and profile.lead_id else None
        return {
            "domain": profile.domain if profile else "",
            "country": profile.country if profile else None,
            "industry": lead.industry if lead else None,
            "existing_urls": set(session.scalars(select(ResearchSource.url).where(
                ResearchSource.company_id == company_id
            )).all()),
            "existing_hashes": set(session.scalars(select(ResearchSource.content_hash).where(
                ResearchSource.company_id == company_id
            )).all()),
        }


def _persist_tasks(run_id: str, queries) -> list[dict]:
    rows = []
    with SessionLocal.begin() as session:
        for query in queries:
            existing = session.scalar(select(ResearchDiscoveryTask.id).where(
                ResearchDiscoveryTask.run_id == run_id,
                ResearchDiscoveryTask.query == query.text,
                ResearchDiscoveryTask.category == query.category,
            ))
            if existing:
                continue
            session.add(ResearchDiscoveryTask(
                run_id=run_id, query=query.text, category=query.category,
                source_type="query", status="pending", candidates_found=0,
            ))
            rows.append({"id": None, "query": query.text, "category": query.category})
        session.flush()
        stored = session.scalars(select(ResearchDiscoveryTask).where(
            ResearchDiscoveryTask.run_id == run_id
        )).all()
        return [{"id": item.id, "query": item.query, "category": item.category} for item in stored]


def _discover(domain: str, company_name: str, seed_texts: list[str], seed_links: list[str],
              deadline: float, limitations: list[str], queries=None) -> list[adapters.Candidate]:
    limit = max(10, min(500, settings.research_discovery_max_candidates * 12))
    raw: list[adapters.Candidate] = []

    def attempt(label: str, function) -> None:
        try:
            raw.extend(function())
        except Exception as exc:  # adapters must never abort research
            logger.warning("Discovery adapter %s failed: %s", label, exc)
            limitations.append(f"{label} discovery failed: {str(exc)[:200]}")

    attempt("Sitemap", lambda: adapters.sitemap_candidates(domain, deadline, limit, limitations))
    attempt("Feed", lambda: adapters.feed_candidates(domain, deadline, limit, limitations))
    attempt("Reference", lambda: adapters.reference_candidates(seed_texts, domain, limit))
    attempt("Outbound link", lambda: adapters.link_candidates(seed_links, domain, limit))
    if settings.research_discovery_wikipedia_enabled:
        attempt("Wikipedia/Wikidata", lambda: adapters.directory_candidates(
            company_name, deadline, 6, limitations))
    attempt("News RSS", lambda: adapters.news_rss_candidates(
        company_name, [q.text for q in queries] if queries else None, deadline, 10, limitations))
    if settings.research_discovery_sec_enabled:
        attempt("SEC EDGAR", lambda: adapters.sec_edgar_candidates(
            company_name, deadline, 5, limitations))
    if settings.research_discovery_gleif_enabled:
        attempt("GLEIF registry", lambda: adapters.gleif_candidates(
            company_name, deadline, 3, limitations))
    attempt("Search accelerator", lambda: adapters.search_accelerator_candidates(
        company_name, [q.text for q in queries] if queries else None, deadline, 6, limitations))
    return raw


def _select_candidates(raw: list[adapters.Candidate], context: dict, terms: set[str],
                       counters: dict) -> list[dict]:
    official = context["domain"]
    existing_urls = context["existing_urls"]
    max_candidates = max(1, settings.research_discovery_max_candidates)
    max_domains = max(1, settings.research_discovery_max_domains)
    per_domain_cap = max(1, settings.research_discovery_max_candidates_per_domain)
    minimum = settings.research_discovery_min_score

    normalised: dict[str, dict] = {}
    domains_seen: set[str] = set()
    for candidate in raw:
        url = policy.normalize_candidate_url(candidate.url)
        if not url:
            counters["urls_rejected"] += 1
            continue
        if url in existing_urls:
            counters["duplicate_sources"] += 1
            continue
        blocked, reason = policy.is_blocked_url(url)
        if blocked:
            counters["urls_rejected"] += 1
            continue
        domains_seen.add((urlsplit(url).hostname or "").lower())
        if url in normalised:
            counters["duplicate_sources"] += 1
            continue
        source_type = policy.source_type_for(url, official)
        category = policy.research_category_for(source_type, url)
        score, matched = policy.relevance_score(
            url, candidate.title, terms, source_type, official)
        normalised[url] = {
            "url": url,
            "normalized_url": url,
            "domain": (urlsplit(url).hostname or "").lower(),
            "title": (candidate.title or "")[:1000],
            "source_type": source_type,
            "source_category": category,
            "discovered_via": candidate.discovered_via or "unknown",
            "score": score,
            "matched_terms": matched,
            "published_at": candidate.published_at,
            "snippet": (candidate.snippet or "")[:1000],
        }
    counters["unique_domains_discovered"] = len(domains_seen)

    eligible = [item for item in normalised.values() if item["score"] >= minimum]
    counters["urls_rejected"] += len(normalised) - len(eligible)
    eligible.sort(key=lambda item: (-item["score"], item["url"]))

    selected: list[dict] = []
    domain_counts: dict[str, int] = {}
    for item in eligible:
        if len(selected) >= max_candidates:
            break
        domain = item["domain"]
        if domain not in domain_counts and len(domain_counts) >= max_domains:
            counters["urls_rejected"] += 1
            continue
        if domain_counts.get(domain, 0) >= per_domain_cap:
            counters["urls_rejected"] += 1
            continue
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        selected.append(item)
    counters["urls_queued"] = len(selected)
    return selected


def _persist_candidates(run_id: str, company_id: str, selected: list[dict]) -> list[dict]:
    rows = []
    with SessionLocal.begin() as session:
        for item in selected:
            existing = session.scalar(select(ResearchCandidateSource).where(
                ResearchCandidateSource.run_id == run_id,
                ResearchCandidateSource.normalized_url == item["normalized_url"],
            ))
            if existing:
                continue
            row = ResearchCandidateSource(
                run_id=run_id, company_id=company_id, url=item["url"],
                normalized_url=item["normalized_url"], domain=item["domain"],
                title=item["title"], source_category=item["source_category"],
                discovered_via=item["discovered_via"], state="queued",
                score=item["score"], matched_terms=item["matched_terms"],
                published_at=item["published_at"],
            )
            session.add(row)
            session.flush()
            rows.append({"id": row.id, **item})
    return rows


def _persist_source(session, company_id: str, page, category: str,
                    source_type: str) -> ResearchSource:
    content_hash = page.content_hash or hashlib.sha256(page.text.encode("utf-8")).hexdigest()
    source = session.scalar(select(ResearchSource).where(
        ResearchSource.company_id == company_id,
        ResearchSource.content_hash == content_hash,
    ))
    if source:
        return source
    host = (urlsplit(page.url).hostname or "").lower()
    source = ResearchSource(
        company_id=company_id, url=page.url, canonical_url=page.url, domain=host,
        title=(page.title or page.url)[:1000], publisher=host,
        published_at=page.published_at, retrieved_at=now(), content_hash=content_hash,
        category=category, reliability=policy.reliability_for(source_type),
        retrieval_method=page.retrieval_method, excerpt=page.text[:2000],
        content_text=page.text,
    )
    session.add(source)
    session.flush()
    return source


def _state_for_page(page, terms: set[str]) -> tuple[str, str]:
    lowered = page.text.casefold()
    hits = [term for term in terms if term in lowered]
    if len(page.text) >= 400 and hits:
        return "evidence_bearing", f"matched terms: {', '.join(sorted(hits)[:6])}"
    if len(page.text) >= 200:
        return "relevant", "retrieved but no identifier term matched the page text"
    return "extracted", "very little usable text was extracted"


def _fetch_selected(rows: list[dict], company_id: str, job_id: str, terms: set[str],
                    deadline: float, counters: dict, limitations: list[str],
                    cancelled) -> None:
    if not rows:
        return
    budget = max(65536, min(settings.research_discovery_max_bytes,
                            settings.research_max_total_content_size))
    reserved = True
    try:
        with SessionLocal.begin() as session:
            reserve_source_bytes(session, budget)
    except BudgetExceeded as exc:
        reserved = False
        counters["budget_exhausted"] += 1
        limitations.append(str(exc))
        with SessionLocal.begin() as session:
            for row in rows:
                candidate = session.get(ResearchCandidateSource, row["id"])
                if candidate:
                    candidate.state = "unavailable"
                    candidate.relevance_note = "Daily source-byte budget exhausted before retrieval."
        return
    remaining = budget
    fetched_domains: set[str] = set()
    try:
        for row in rows:
            if cancelled and cancelled():
                limitations.append("Discovery stopped because the research job was cancelled.")
                break
            if time.monotonic() >= deadline:
                limitations.append("Discovery job deadline reached before every candidate was retrieved.")
                break
            host = row["domain"]
            robots, robot_notes, consumed = robots_for(host, deadline)
            limitations.extend(robot_notes[:2])
            remaining -= consumed
            if not robots.can_fetch("GTMProspectingResearch", row["normalized_url"]):
                _update_candidate(row["id"], state="rejected",
                                  note="robots policy disallows this URL")
                counters["urls_rejected"] += 1
                continue
            delay = crawl_delay_for(robots)
            if delay:
                time.sleep(min(delay, max(0.0, min(1.0, deadline - time.monotonic()))))
            per_page = max(65536, min(settings.research_max_content_size, remaining))
            try:
                page, notes = fetch_public_page_adaptive(
                    row["normalized_url"], per_page, deadline,
                    can_fetch=lambda target: robots.can_fetch("GTMProspectingResearch", target),
                    cancelled=cancelled,
                )
            except SourceError as exc:
                counters["extraction_failures"] += 1
                _update_candidate(row["id"], state="unavailable", note=str(exc)[:500])
                limitations.append(f"{row['normalized_url']}: {str(exc)[:200]}")
                remaining -= min(per_page, 16384)
                continue
            limitations.extend(notes[:2])
            remaining -= min(len(page.text.encode("utf-8")), per_page)
            fetched_domains.add(host)
            if page.retrieval_method == "playwright":
                counters["browser_retrievals"] += 1
            elif page.retrieval_method == "http_pdf":
                counters["pdfs_processed"] += 1
                counters["http_retrievals"] += 1
            else:
                counters["http_retrievals"] += 1
            counters["sources_with_content"] += 1
            state, note = _state_for_page(page, terms)
            if state == "evidence_bearing":
                counters["evidence_bearing_sources"] += 1
            with SessionLocal.begin() as session:
                source = _persist_source(session, company_id, page,
                                         row["source_category"], row["source_type"])
                if session.get(ResearchJobSource, (job_id, source.id)) is None:
                    session.add(ResearchJobSource(job_id=job_id, source_id=source.id))
                candidate = session.get(ResearchCandidateSource, row["id"])
                if candidate:
                    candidate.state = state
                    candidate.title = (page.title or candidate.title)[:1000]
                    candidate.http_status = 200
                    candidate.retrieval_method = page.retrieval_method
                    candidate.content_hash = page.content_hash
                    candidate.source_id = source.id
                    candidate.relevance_note = note[:500]
                    candidate.published_at = page.published_at or candidate.published_at
            # retrieval -> extracted -> relevance states were traversed above
    finally:
        if reserved and remaining > 0:
            try:
                with SessionLocal.begin() as session:
                    release_source_bytes(session, remaining)
            except Exception:  # releasing is best-effort
                logger.warning("Could not release unused discovery byte budget", exc_info=True)


def _update_candidate(candidate_id: str, state: str, note: str | None = None) -> None:
    with SessionLocal.begin() as session:
        candidate = session.get(ResearchCandidateSource, candidate_id)
        if candidate:
            candidate.state = state
            candidate.relevance_note = (note or "")[:500]


def _coverage(run_id: str) -> dict:
    with SessionLocal() as session:
        rows = session.execute(
            select(ResearchCandidateSource.source_category, ResearchCandidateSource.state,
                   func.count(ResearchCandidateSource.id))
            .where(ResearchCandidateSource.run_id == run_id)
            .group_by(ResearchCandidateSource.source_category, ResearchCandidateSource.state)
        ).all()
    coverage = {category: {"sources": 0, "evidence_bearing": 0, "relevant": 0}
                for category in COVERAGE_CATEGORIES}
    for category, state, count in rows:
        bucket = coverage.setdefault(category or "company",
                                     {"sources": 0, "evidence_bearing": 0, "relevant": 0})
        if state in {"retrieved", "extracted", "relevant", "evidence_bearing", "verified"}:
            bucket["sources"] += count
        if state == "evidence_bearing":
            bucket["evidence_bearing"] += count
        if state == "relevant":
            bucket["relevant"] += count
    covered = sum(1 for bucket in coverage.values() if bucket["evidence_bearing"] > 0)
    coverage["covered_categories"] = covered
    coverage["total_categories"] = len(COVERAGE_CATEGORIES)
    return coverage


def _update_tasks(run_id: str, selected: list[dict], counters: dict) -> None:
    with SessionLocal.begin() as session:
        tasks = session.scalars(select(ResearchDiscoveryTask).where(
            ResearchDiscoveryTask.run_id == run_id
        )).all()
        for task in tasks:
            terms = set(re.findall(r"[a-z0-9]{3,}", task.query.casefold()))
            task.candidates_found = sum(
                1 for item in selected
                if set(item["matched_terms"]) & terms
                or any(term in item["url"].casefold() for term in terms)
            )
            task.status = "completed"
        counters["discovery_tasks_created"] = len(tasks)


def run_discovery(job_id: str, company_id: str, company_name: str, domain: str, *,
                  seed_texts: list[str] | None = None,
                  seed_links: list[str] | None = None,
                  cancelled=None) -> dict:
    """Discover and retrieve cross-domain sources for one research job."""
    if not settings.research_discovery_enabled:
        return {"status": "disabled"}
    started = time.monotonic()
    deadline = started + max(10, settings.research_discovery_deadline_seconds)
    counters = _empty_counters()
    limitations: list[str] = []
    run_id = _create_run(job_id, company_id)
    try:
        context = _profile_context(company_id)
        queries = expand_queries(
            company_name, domain=domain,
            industries=(context["industry"],) if context["industry"] else (),
            countries=(context["country"],) if context["country"] else (),
        )
        tasks = _persist_tasks(run_id, queries)
        counters["discovery_tasks_created"] = len(queries)
        terms = query_terms(queries, company_name)
        raw = _discover(domain, company_name, seed_texts or [], seed_links or [],
                        deadline, limitations, queries=queries)
        counters["candidate_urls_discovered"] = len(raw)
        selected = _select_candidates(raw, context, terms, counters)
        rows = _persist_candidates(run_id, company_id, selected)
        _fetch_selected(rows, company_id, job_id, terms, deadline, counters,
                        limitations, cancelled)
        base = domain.lower().removeprefix("www.")
        counters["cross_domain_sources"] = sum(
            1 for row in rows
            if row["domain"] != base and not row["domain"].endswith(f".{base}")
        )
        counters["domains_fetched"] = len({row["domain"] for row in rows})
        _update_tasks(run_id, selected, counters)
        coverage = _coverage(run_id)
        unique_limitations = list(dict.fromkeys(item for item in limitations if item))[:20]
        with SessionLocal.begin() as session:
            run = session.get(ResearchDiscoveryRun, run_id)
            if run:
                run.status = "completed"
                run.counters = counters
                run.coverage = coverage
                run.limitations = unique_limitations
                run.queries_count = counters["discovery_tasks_created"]
                run.finished_at = now()
        return {
            "status": "completed", "run_id": run_id, "counters": counters,
            "coverage": coverage, "limitations": unique_limitations,
        }
    except Exception as exc:  # never fail the research job because discovery failed
        logger.exception("Research discovery failed for job %s", job_id)
        with SessionLocal.begin() as session:
            run = session.get(ResearchDiscoveryRun, run_id)
            if run:
                run.status = "failed"
                run.error = str(exc)[:1000]
                run.counters = counters
                run.limitations = list(dict.fromkeys(limitations))[:20]
                run.finished_at = now()
        return {"status": "failed", "run_id": run_id, "error": str(exc)[:500],
                "counters": counters}
