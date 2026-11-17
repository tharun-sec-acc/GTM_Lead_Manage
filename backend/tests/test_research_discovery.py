"""Autonomous discovery tests: queries, policy, engine states, budgets and API."""

import hashlib
import json
from urllib.robotparser import RobotFileParser

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import Lead, now
from app.company_intelligence import models as research_models
from app.company_intelligence.discovery import adapters, engine, policy
from app.company_intelligence.discovery.adapters import Candidate
from app.company_intelligence.discovery.queries import (
    DiscoveryQuery, expand_queries, query_terms,
)
from app.company_intelligence.models import (
    CompanyResearchProfile, ResearchCandidateSource, ResearchDiscoveryRun,
    ResearchDiscoveryTask, ResearchFact, ResearchJobSource, ResearchJob, ResearchSource,
)
from app.company_intelligence.services.budget import BudgetExceeded
from app.company_intelligence.sources.website import Page


@pytest.fixture
def db(tmp_path):
    engine_ = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine_)
    factory = sessionmaker(bind=engine_, expire_on_commit=False)

    def override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        yield client, factory
    app.dependency_overrides.clear()
    engine_.dispose()


def make_profile(factory, name="Acme Ltd", domain="acme.example", industry="Automotive"):
    with factory() as session:
        lead = Lead(company_name=name, company_key=name.lower(), domain=domain,
                    industry=industry, extra={})
        session.add(lead)
        session.flush()
        profile = CompanyResearchProfile(lead_id=lead.id, company_name=name, domain=domain,
                                         country="Japan", created_at=now())
        session.add(profile)
        session.flush()
        job = ResearchJob(company_id=profile.id, lead_id=lead.id, status="running",
                          depth="comprehensive")
        session.add(job)
        session.commit()
        return profile.id, job.id


def allow_robots(host, deadline=None):
    parser = RobotFileParser()
    parser.parse(["User-agent: *", "Allow: /"])
    return parser, [], 0


def page_for(url, text, method="http"):
    return Page(
        url=url, title=url.rsplit("/", 1)[-1] or url, text=text, links=[],
        published_at=None, category="news",
        content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        retrieval_method=method,
    )


def patch_discovery(monkeypatch, factory, pages, robots=None):
    """Wire the engine to a temp DB and synthetic retrieval."""
    monkeypatch.setattr(engine, "SessionLocal", factory)
    monkeypatch.setattr(engine, "robots_for", robots or allow_robots)

    def retrieve(url, *args, **kwargs):
        if url in pages:
            return pages[url], []
        return page_for(url, "Public directory listing with generic information. " * 20), []

    monkeypatch.setattr(engine, "fetch_public_page_adaptive", retrieve)
    monkeypatch.setattr(engine.adapters, "sitemap_candidates",
                        lambda *args, **kwargs: [
                            Candidate("https://acme.example/about", discovered_via="sitemap"),
                            Candidate("https://acme.example/news", discovered_via="sitemap"),
                        ])
    monkeypatch.setattr(engine.adapters, "feed_candidates",
                        lambda *args, **kwargs: [
                            Candidate("https://news.example.net/acme-annual-report",
                                      title="Acme annual report", discovered_via="feed"),
                        ])
    monkeypatch.setattr(engine.adapters, "reference_candidates",
                        lambda *args, **kwargs: [
                            Candidate("https://registry.example.org/acme-filing",
                                      discovered_via="document_reference"),
                            Candidate("https://news.example.net/acme-annual-report",
                                      discovered_via="document_reference"),
                        ])
    monkeypatch.setattr(engine.adapters, "link_candidates",
                        lambda *args, **kwargs: [
                            Candidate("https://www.linkedin.com/company/acme",
                                      discovered_via="outbound_link"),
                        ])
    monkeypatch.setattr(engine.adapters, "directory_candidates",
                        lambda *args, **kwargs: [
                            Candidate("https://en.wikipedia.org/wiki/Acme_Ltd",
                                      title="Acme Ltd", discovered_via="wikipedia_search"),
                        ])
    monkeypatch.setattr(engine.adapters, "sec_edgar_candidates",
                        lambda *args, **kwargs: [])


# ---- Query expansion ----


def test_query_expansion_is_deterministic_and_bounded():
    first = expand_queries("Acme Ltd", domain="acme.example",
                           subsidiaries=("Acme Japan",), industries=("Automotive",))
    second = expand_queries("Acme Ltd", domain="acme.example",
                            subsidiaries=("Acme Japan",), industries=("Automotive",))
    assert [item.text for item in first] == [item.text for item in second]
    assert len(first) <= 120
    texts = [item.text.casefold() for item in first]
    assert any("annual report" in text for text in texts)
    assert any("subsidiaries" in text for text in texts)
    assert any("automotive" in text for text in texts)
    categories = {item.category for item in first}
    assert {"company", "financial", "news", "leadership", "competitors", "signals"} <= categories
    assert len(texts) == len(set(texts))


def test_query_expansion_requires_a_name():
    assert expand_queries("   ") == []


def test_query_terms_exclude_generic_words():
    queries = [DiscoveryQuery("Acme Ltd annual report", "financial")]
    terms = query_terms(queries, "Acme Ltd")
    assert "acme" in terms
    assert "annual" not in terms and "report" not in terms


# ---- Policy ----


def test_url_normalisation_removes_tracking_and_fragments():
    url = policy.normalize_candidate_url(
        "https://News.Example.net/a/report/?utm_source=x&b=2&a=1#section")
    assert url == "https://news.example.net/a/report?a=1&b=2"


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/admin",
    "http://10.0.0.5/report",
    "http://169.254.169.254/latest/meta-data",
    "http://metadata.google.internal/computeMetadata/v1/",
    "http://localhost:8000/leads",
    "https://user:pass@example.com/file",
    "javascript:alert(1)",
])
def test_private_and_unsafe_urls_are_rejected(url):
    assert policy.normalize_candidate_url(url) is None
    assert policy.is_blocked_url(url)[0] is True


def test_social_and_binary_urls_are_blocked():
    assert policy.is_blocked_url("https://linkedin.com/company/acme")[0] is True
    assert policy.is_blocked_url("https://example.com/file.exe")[0] is True
    assert policy.is_blocked_url("https://example.com/about")[0] is False


def test_gleif_adapter_parses_public_registry_records(monkeypatch):
    payload = {"data": [{
        "id": "549300ABCDEFGHIJKL12",
        "attributes": {"entity": {
            "legalName": {"name": "Siemens AG"},
            "legalAddress": {"city": "Munich"},
        }},
    }]}
    monkeypatch.setattr(adapters, "_api_allowed", lambda url, deadline, notes: True)
    monkeypatch.setattr(adapters, "fetch_public_text",
                        lambda url, size, deadline: (json.dumps(payload), 200))
    notes: list[str] = []
    candidates = adapters.gleif_candidates("Siemens AG", None, 3, notes)
    assert candidates[0].url == (
        "https://api.gleif.org/api/v1/lei-records/549300ABCDEFGHIJKL12")
    assert candidates[0].title == "Siemens AG"
    assert candidates[0].discovered_via == "gleif_registry"
    assert notes == []


def test_registry_and_news_classification_and_scoring():
    assert policy.source_type_for("https://www.sec.gov/Archives/edgar/data/1/2.htm",
                                  "acme.example") in {"registry", "other"}
    assert policy.source_type_for("https://www.reuters.com/business/acme", "acme.example") == "news"
    assert policy.source_type_for("https://acme.example/about", "acme.example") == "official"
    registry_score, hits = policy.relevance_score(
        "https://www.sec.gov/Archives/edgar/data/acme-10k.htm", "Acme 10-K",
        {"acme"}, "registry", "acme.example")
    social_score, _ = policy.relevance_score(
        "https://linkedin.com/company/acme", "Acme", {"acme"}, "other", "acme.example")
    assert registry_score > social_score
    assert "acme" in hits


# ---- Engine ----


def test_discovery_collects_cross_domain_sources_and_metrics(db, monkeypatch):
    _, factory = db
    company_id, job_id = make_profile(factory)
    pages = {
        "https://acme.example/about": page_for(
            "https://acme.example/about", "Acme Ltd company profile and history." * 20),
        "https://acme.example/news": page_for(
            "https://acme.example/news", "Acme Ltd news." * 20),
        "https://news.example.net/acme-annual-report": page_for(
            "https://news.example.net/acme-annual-report",
            "Acme Ltd annual report revenue and financial results." * 20),
        "https://registry.example.org/acme-filing": page_for(
            "https://registry.example.org/acme-filing",
            "Acme Ltd regulatory filing registration." * 20, method="http_pdf"),
        "https://en.wikipedia.org/wiki/Acme_Ltd": page_for(
            "https://en.wikipedia.org/wiki/Acme_Ltd", "Acme Ltd is an automotive company." * 20),
    }
    patch_discovery(monkeypatch, factory, pages)

    result = engine.run_discovery(job_id, company_id, "Acme Ltd", "acme.example",
                                  seed_texts=["see https://news.example.net/acme-annual-report"],
                                  seed_links=["https://registry.example.org/acme-filing"])
    assert result["status"] == "completed"
    counters = result["counters"]
    assert counters["discovery_tasks_created"] > 0
    assert counters["candidate_urls_discovered"] >= 5
    assert counters["urls_queued"] >= 3
    assert counters["cross_domain_sources"] >= 2
    assert counters["http_retrievals"] >= 3
    assert counters["pdfs_processed"] == 1
    assert counters["evidence_bearing_sources"] >= 2
    assert counters["duplicate_sources"] >= 1  # same annual-report URL from feed and reference
    assert counters["urls_rejected"] >= 1      # social link

    with factory() as session:
        run = session.scalars(select(ResearchDiscoveryRun)).one()
        assert run.status == "completed"
        assert run.coverage["company"]["sources"] >= 1
        tasks = session.scalars(select(ResearchDiscoveryTask)).all()
        assert len(tasks) == counters["discovery_tasks_created"]
        assert all(task.status == "completed" for task in tasks)
        candidates = session.scalars(select(ResearchCandidateSource)).all()
        assert all(candidate.state in engine.STATES for candidate in candidates)
        assert {candidate.discovered_via for candidate in candidates} >= {"sitemap", "feed", "document_reference"}
        sources = session.scalars(select(ResearchSource)).all()
        assert len(sources) >= 3
        linked = session.scalars(select(ResearchJobSource)).all()
        assert len(linked) == len(sources)
        assert {source.reliability for source in sources} >= {"directory", "unclassified"}
        assert any(source.retrieval_method == "http_pdf" for source in sources)


def test_discovery_uses_only_identifier_terms_for_evidence(db, monkeypatch):
    _, factory = db
    company_id, job_id = make_profile(factory)
    pages = {
        "https://news.example.net/acme-annual-report": page_for(
            "https://news.example.net/acme-annual-report",
            "Completely unrelated market commentary. " * 40),
    }
    patch_discovery(monkeypatch, factory, pages)
    result = engine.run_discovery(job_id, company_id, "Acme Ltd", "acme.example")
    with factory() as session:
        candidate = session.scalars(select(ResearchCandidateSource).where(
            ResearchCandidateSource.normalized_url ==
            "https://news.example.net/acme-annual-report"
        )).one()
        assert candidate.state == "relevant"
    assert result["counters"]["evidence_bearing_sources"] == 0


def test_robots_disallow_marks_candidate_rejected(db, monkeypatch):
    _, factory = db
    company_id, job_id = make_profile(factory)
    pages = {
        "https://news.example.net/acme": page_for(
            "https://news.example.net/acme", "Acme Ltd annual report " * 30),
    }

    def deny(host, deadline=None):
        parser = RobotFileParser()
        parser.parse(["User-agent: *", "Disallow: /"])
        return parser, [], 0

    patch_discovery(monkeypatch, factory, pages, robots=deny)
    engine.run_discovery(job_id, company_id, "Acme Ltd", "acme.example")
    with factory() as session:
        states = {candidate.state for candidate in session.scalars(
            select(ResearchCandidateSource)).all()}
        assert states == {"rejected"}
        assert session.scalars(select(ResearchSource)).all() == []


def test_budget_exhaustion_is_recorded(db, monkeypatch):
    _, factory = db
    company_id, job_id = make_profile(factory)

    def exhausted(session, amount):
        raise BudgetExceeded("The daily company research source bytes budget is exhausted.")

    patch_discovery(monkeypatch, factory, {
        "https://news.example.net/acme": page_for("https://news.example.net/acme", "Acme"),
    })
    monkeypatch.setattr(engine, "reserve_source_bytes", exhausted)
    result = engine.run_discovery(job_id, company_id, "Acme Ltd", "acme.example")
    assert result["counters"]["budget_exhausted"] == 1
    with factory() as session:
        states = {c.state for c in session.scalars(select(ResearchCandidateSource)).all()}
        assert states == {"unavailable"}
        assert session.scalars(select(ResearchSource)).all() == []


def test_fetch_failure_is_marked_unavailable(db, monkeypatch):
    _, factory = db
    company_id, job_id = make_profile(factory)
    patch_discovery(monkeypatch, factory, {})

    def broken(url, *args, **kwargs):
        from app.company_intelligence.sources.website import SourceError
        raise SourceError("Company website returned HTTP 404.")

    monkeypatch.setattr(engine, "fetch_public_page_adaptive", broken)
    result = engine.run_discovery(job_id, company_id, "Acme Ltd", "acme.example")
    assert result["counters"]["extraction_failures"] >= 1
    with factory() as session:
        states = {c.state for c in session.scalars(select(ResearchCandidateSource)).all()}
        assert states == {"unavailable"}


def test_discovery_disabled_returns_disabled(db, monkeypatch):
    _, factory = db
    company_id, job_id = make_profile(factory)
    monkeypatch.setattr(engine.settings, "research_discovery_enabled", False)
    assert engine.run_discovery(job_id, company_id, "Acme", "acme.example")["status"] == "disabled"


# ---- API ----


def test_discovery_endpoint_reports_run_and_coverage(db, monkeypatch):
    client, factory = db
    company_id, job_id = make_profile(factory)
    pages = {
        "https://news.example.net/acme-annual-report": page_for(
            "https://news.example.net/acme-annual-report",
            "Acme Ltd annual report revenue." * 30),
    }
    patch_discovery(monkeypatch, factory, pages)
    engine.run_discovery(job_id, company_id, "Acme Ltd", "acme.example")

    response = client.get(f"/intelligence/research/{job_id}/discovery")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["queries_count"] > 0
    assert body["counters"]["urls_queued"] >= 1
    assert body["tasks"] and body["candidates"]
    assert "company" in body["coverage"]

    missing = client.get("/intelligence/research/does-not-exist/discovery")
    assert missing.status_code == 404


def test_discovery_endpoint_handles_job_without_run(db):
    client, factory = db
    _, job_id = make_profile(factory)
    body = client.get(f"/intelligence/research/{job_id}/discovery").json()
    assert body["status"] == "not_run"
    assert body["counters"] == {}
