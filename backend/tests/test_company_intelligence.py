import hashlib
import io
from datetime import timedelta
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app import bedrock
from app.company_intelligence import api, orchestrator
from app.company_intelligence.agents import runner
from app.company_intelligence.models import (CompanyResearchProfile, ResearchAgentRun, ResearchCitation,
                                             ResearchFact, ResearchJob, ResearchJobSource, ResearchReport,
                                             ResearchSource)
from app.company_intelligence.sources import website
from app.company_intelligence.sources.browser import BrowserRenderer
from app.database import Base, get_db
from app.main import app
from app.models import Lead, now

TEXT = ("Synthetic Company manufactures test components. Synthetic Company standalone revenue was "
        "INR 100 million in FY2026. Synthetic Company announced a new factory.")


@pytest.fixture
def research(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'research.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    for module in (orchestrator, runner):
        monkeypatch.setattr(module, "SessionLocal", factory)
    for key, value in {
        "company_intelligence_enabled": True, "aws_region": "us-east-1", "bedrock_model_id": "test-model",
        "research_max_concurrent_agents": 1, "research_daily_budget": 100,
        "research_daily_bedrock_calls": 500, "research_daily_source_bytes": 100_000_000,
        "research_max_total_content_size": 100_000, "research_search_provider": "",
        "research_browser_enabled": False, "research_discovery_enabled": False,
    }.items():
        monkeypatch.setattr(api.settings, key, value)
    queued = []
    monkeypatch.setattr(api.run_company_research, "delay", lambda job_id: queued.append(job_id))
    monkeypatch.setattr(orchestrator, "gather_official_pages", lambda *args, **kwargs: ([
        website.Page("https://example.com/", "Synthetic Company", TEXT, [], now(), "company",
                     hashlib.sha256(TEXT.encode()).hexdigest())
    ], [], len(TEXT)))
    calls = []

    def converse(instruction, data, **kwargs):
        calls.append((instruction, data, kwargs))
        if "sources" in data and data["sources"]:
            source_id = data["sources"][0]["source_id"]
            fact = {"field_name": "business", "value": "Synthetic Company manufactures test components.",
                    "source_id": source_id, "quote": TEXT}
            return {"facts": [fact], "not_available": None}, {"input_tokens": 25, "output_tokens": 10}
        return {}, {"input_tokens": 25, "output_tokens": 10}

    monkeypatch.setattr(bedrock, "converse_json", converse)
    with factory.begin() as session:
        lead = Lead(company_name="Synthetic Company", company_key="synthetic", domain="example.com", extra={})
        session.add(lead)
        session.flush()
        lead_id = lead.id
    with TestClient(app) as client:
        yield client, factory, lead_id, queued, calls
    app.dependency_overrides.clear()
    engine.dispose()


def submit(client, lead_id=None, **kwargs):
    return client.post("/intelligence/research", json={
        "company_name": "Synthetic Company", "website": "example.com", "lead_id": lead_id, **kwargs,
    })


def test_submission_reuse_disabled_and_domain_mismatch(research, monkeypatch):
    client, factory, lead_id, queued, _ = research
    monkeypatch.setattr(api.settings, "company_intelligence_enabled", False)
    assert client.get("/intelligence/status").json()["enabled"] is False
    assert submit(client, lead_id).status_code == 503
    monkeypatch.setattr(api.settings, "company_intelligence_enabled", True)
    assert submit(client, lead_id, website="another.example").status_code == 409
    first = submit(client, lead_id)
    assert first.status_code == 202
    assert submit(client, lead_id).json() == {**first.json(), "reused": True}
    assert submit(client, lead_id, depth="comprehensive").status_code == 409
    assert len(queued) == 1
    with factory() as session:
        assert session.scalar(select(func.count(CompanyResearchProfile.id))) == 1
        assert session.scalar(select(func.count(ResearchAgentRun.id))) == 17


def test_complete_lifecycle_report_snapshots_and_duplicate_worker(research):
    client, factory, lead_id, _, calls = research
    created = submit(client, lead_id, depth="comprehensive").json()
    result = orchestrator.run_research_job(created["job_id"])
    assert result["status"] == "completed"
    extraction_calls = [c for c in calls if "sources" in c[1]]
    assert len(extraction_calls) == 15
    assert orchestrator.run_research_job(created["job_id"])["status"] == "completed"
    extraction_calls = [c for c in calls if "sources" in c[1]]
    assert len(extraction_calls) == 15
    detail = client.get(f"/intelligence/research/{created['job_id']}").json()
    assert detail["progress"] == 100 and detail["facts_count"] == 15
    report = client.get(f"/intelligence/reports/{detail['report_id']}").json()
    assert report["version"] == 1 and len(report["sections"]) == 15
    assert "manufactures test components" in report["summary"]
    assert all(fact["verification_status"] == "reported" for fact in client.get(
        f"/intelligence/companies/{created['company_id']}/facts").json()["items"])
    assert submit(client, lead_id, depth="comprehensive").json()["reused"] is True
    second = submit(client, lead_id, depth="comprehensive", force_refresh=True).json()
    assert second["job_id"] != created["job_id"]
    assert client.get(f"/intelligence/companies/{created['company_id']}/facts").json()["total"] == 0
    assert client.get(f"/intelligence/companies/{created['company_id']}/facts",
                      params={"job_id": created["job_id"]}).json()["total"] == 15
    orchestrator.run_research_job(second["job_id"])
    assert client.get(f"/intelligence/companies/{created['company_id']}/sources",
                      params={"job_id": created["job_id"]}).json()["total"] == 1
    with factory() as session:
        assert session.scalar(select(func.count(ResearchReport.id))) == 2
        assert session.scalar(select(func.count(ResearchSource.id))) == 1


def test_retry_preserves_successful_agents_and_versions_report(research, monkeypatch):
    client, factory, lead_id, _, _ = research
    original = runner.extract_category_facts

    def one_failure(job_id, company_id, agent, profile):
        if agent == "news":
            raise RuntimeError("Synthetic provider failure")
        return original(job_id, company_id, agent, profile)

    monkeypatch.setattr(orchestrator, "extract_category_facts", one_failure)
    created = submit(client, lead_id).json()
    assert orchestrator.run_research_job(created["job_id"])["status"] == "partial"
    with factory() as session:
        old_ids = set(session.scalars(select(ResearchFact.id)).all())
    assert client.post(f"/intelligence/research/{created['job_id']}/retry").status_code == 200
    monkeypatch.setattr(orchestrator, "extract_category_facts", original)
    assert orchestrator.run_research_job(created["job_id"])["status"] == "completed"
    with factory() as session:
        assert old_ids.issubset(set(session.scalars(select(ResearchFact.id)).all()))
        assert session.scalar(select(func.count(ResearchReport.id))) == 2
    assert client.post(f"/intelligence/research/{created['job_id']}/retry").status_code == 409


def test_cancel_before_execution_and_wrong_job_association(research):
    client, _, lead_id, _, calls = research
    created = submit(client, lead_id).json()
    assert client.post(f"/intelligence/research/{created['job_id']}/cancel").json()["status"] == "cancelled"
    assert orchestrator.run_research_job(created["job_id"])["status"] == "cancelled"
    assert not calls
    other = submit(client, website="other.example").json()
    for kind in ("facts", "sources"):
        assert client.get(f"/intelligence/companies/{other['company_id']}/{kind}",
                          params={"job_id": created["job_id"]}).status_code == 404


def test_fabricated_quotes_and_values_are_excluded(research, monkeypatch):
    client, _, lead_id, _, _ = research

    def invalid(instruction, data, **kwargs):
        return {"facts": [
            {"field_name": "fabricated", "value": "Synthetic Company manufactures missiles.",
             "source_id": data["sources"][0]["source_id"], "quote": TEXT},
            {"field_name": "unknown_source", "value": TEXT, "source_id": "not-a-source", "quote": TEXT},
            {"field_name": "fake_quote", "value": "Fake manufacturing", "source_id": data["sources"][0]["source_id"],
             "quote": "Fake manufacturing appears nowhere."},
        ]}, {}

    monkeypatch.setattr(bedrock, "converse_json", invalid)
    created = submit(client, lead_id).json()
    orchestrator.run_research_job(created["job_id"])
    assert client.get(f"/intelligence/companies/{created['company_id']}/facts").json()["total"] == 0


@pytest.mark.parametrize("changes,accepted", [
    ({}, True), ({"currency": "USD"}, False), ({"unit": "billion"}, False),
    ({"entity_scope": "Different Company consolidated"}, False), ({"reporting_period": "FY2025"}, False),
    ({"entity_scope": None}, False), ({"value": "200"}, False),
])
def test_financial_qualifiers_are_supported_not_inferred(changes, accepted):
    values = {"value": "100", "currency": "INR", "unit": "million", "reporting_period": "FY2026",
              "entity_scope": "Synthetic Company standalone"}
    values.update(changes)
    assert runner.quote_supports_fact(SimpleNamespace(**values), TEXT, "financial") is accepted


@pytest.mark.parametrize("url", [
    "http://localhost", "http://127.0.0.1", "http://169.254.169.254/", "ftp://example.com",
    "https://user:password@example.com", "https://example.com:1234", "https://example.com:bad",
    "https://[::1]/", "https://example..com/",
])
def test_unsafe_website_inputs_are_rejected(url):
    with pytest.raises(website.SourceError):
        website.normalize_domain(url)


def test_mixed_dns_is_rejected(monkeypatch):
    monkeypatch.setattr(website.socket, "getaddrinfo", lambda *args, **kwargs: [
        (2, 1, 6, "", ("93.184.216.34", 443)), (2, 1, 6, "", ("127.0.0.1", 443)),
    ])
    with pytest.raises(website.SourceError, match="mixed"):
        website._validated_ips("example.com", 443)


def test_socket_is_pinned_and_redirect_is_rechecked(monkeypatch):
    targets = []

    class Socket:
        def sendall(self, value):
            assert b"Host: example.com" in value

        def makefile(self, *args):
            return io.BytesIO(b"HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1/\r\nContent-Length: 0\r\n\r\n")

        def close(self):
            pass

    monkeypatch.setattr(website, "_validated_ips", lambda *args: ["93.184.216.34"])
    monkeypatch.setattr(website.socket, "create_connection", lambda target, **kwargs: targets.append(target) or Socket())
    with pytest.raises(website.SourceError, match="confirmed company"):
        website._pinned_request("http://example.com/", "example.com", 100)
    assert targets == [("93.184.216.34", 80)]


def test_robots_404_and_failed_page_request_budget(monkeypatch):
    requests = []
    monkeypatch.setattr(website.settings, "research_max_content_size", 1000)

    def response(url, *args, **kwargs):
        requests.append(url)
        if url.endswith("/robots.txt"):
            return website._Response(url, 404, {}, b"User-agent: *\nDisallow: /")
        if url.endswith("/"):
            body = ('<html><title>Synthetic</title><p>Components</p>' +
                    "".join(f'<a href="/page-{number}">Page</a>' for number in range(100)) + "</html>").encode()
            return website._Response(url, 200, {"content-type": "text/html"}, body)
        raise website.SourceError("Synthetic unavailable page")

    monkeypatch.setattr(website, "_pinned_request", response)
    pages, notes, _ = website.gather_official_pages("example.com", 2, 2, 100000)
    assert len(pages) == 1
    assert len(requests) <= 5
    assert any("request-count" in note for note in notes)


def test_failed_downloads_consume_cumulative_byte_budget(monkeypatch):
    requests = []

    def response(url, domain, max_bytes, **kwargs):
        requests.append((url, max_bytes))
        if url.endswith("/robots.txt"):
            return website._Response(url, 404, {}, b"")
        raise website.SourceError("Oversized response")

    monkeypatch.setattr(website, "_pinned_request", response)
    pages, _, consumed = website.gather_official_pages("example.com", 12, 2, 1000)
    assert not pages and consumed == 1000 and len(requests) == 2


def test_javascript_shell_uses_opt_in_rendering_and_crawls_rendered_links(monkeypatch):
    monkeypatch.setattr(website.settings, "research_browser_enabled", True)

    def response(url, *args, **kwargs):
        body = (b"" if url.endswith("/robots.txt") else
                b'<title>Example</title><script src="/app.js"></script><div id="root"></div>')
        return website._Response(url, 404 if url.endswith("/robots.txt") else 200,
                                 {"content-type": "text/html"}, body)

    rendered = []

    def render(self, response, remaining):
        rendered.append(response.url)
        assert remaining > 0
        self.consumed = 50
        return website._Response(response.url, 200, {"content-type": "text/html"},
                                 (f'<p>{"Public company products and services. " * 10}</p>'
                                  '<a href="/about">About</a>').encode())

    monkeypatch.setattr(website, "_pinned_request", response)
    monkeypatch.setattr(BrowserRenderer, "render", render)
    pages, _, consumed = website.gather_official_pages("example.com", 2, 1, 100000)
    assert rendered == ["https://example.com/", "https://example.com/about"]
    assert len(pages) == 2 and all(page.retrieval_method == "playwright" for page in pages)
    assert consumed >= 100


@pytest.mark.parametrize("url,method,kind,robots_allowed", [
    ("http://169.254.169.254/latest/meta-data/", "GET", "fetch", True),
    ("https://external.example/app.js", "GET", "script", True),
    ("https://example.com/submit", "POST", "fetch", True),
    ("https://example.com/movie", "GET", "media", True),
    ("https://example.com/private", "GET", "fetch", False),
])
def test_browser_blocks_unsafe_external_mutating_and_disallowed_requests(url, method, kind, robots_allowed):
    renderer = BrowserRenderer("example.com", float("inf"), lambda _: robots_allowed, 0, None)
    assert not renderer._allowed(SimpleNamespace(url=url, method=method, resource_type=kind))


def test_browser_broker_reserves_failed_download_bytes_and_stops_at_budget(monkeypatch):
    from app.company_intelligence.sources import browser

    renderer = BrowserRenderer("example.com", float("inf"), lambda _: True, 0, None)
    renderer.remaining = 100
    aborted = []
    route = SimpleNamespace(abort=lambda: aborted.append(True))
    request = SimpleNamespace(url="https://example.com/app.js", method="GET", resource_type="script",
                              is_navigation_request=lambda: False)

    def fail(*args, **kwargs):
        raise website.SourceError("Oversized script")

    monkeypatch.setattr(browser, "_pinned_request", fail)
    initial = website._Response("https://example.com/", 200, {}, b"")
    renderer._route(route, request, initial)
    renderer._route(route, request, initial)
    assert renderer.consumed == 100 and renderer.remaining == 0
    assert renderer.requests == 1 and len(aborted) == 2
    assert any("budget" in note for note in renderer.notes)


def test_text_only_browser_resolves_styles_without_fetching_visual_dependencies():
    renderer = BrowserRenderer("example.com", float("inf"), lambda _: True, 0, None)
    responses = []
    route = SimpleNamespace(fulfill=lambda **kwargs: responses.append(kwargs))
    request = SimpleNamespace(url="https://example.com/app.css", method="GET", resource_type="stylesheet")
    renderer._route(route, request, website._Response("https://example.com/", 200, {}, b""))
    assert responses[0]["content_type"] == "text/css"
    assert renderer.requests == 0 and renderer.consumed == 0


def test_daily_budget_and_queue_failure_are_explicit(research, monkeypatch):
    client, _, lead_id, _, _ = research
    monkeypatch.setattr(api.settings, "research_daily_budget", 1)
    created = submit(client, lead_id).json()
    client.post(f"/intelligence/research/{created['job_id']}/cancel")
    assert submit(client, lead_id).status_code == 429


def test_additive_migration_preserves_existing_leads(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setattr(api.settings, "database_url", database_url)
    import os
    config = Config("backend/alembic.ini" if os.path.exists("backend/alembic.ini") else "alembic.ini")
    if not os.path.exists(config.get_main_option("script_location")):
        config.set_main_option("script_location", "backend/migrations")
    command.upgrade(config, "0009_microsoft_oauth")
    engine = create_engine(database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    import uuid
    from datetime import datetime, timezone
    from sqlalchemy import text
    lead_id = str(uuid.uuid4())
    with factory.begin() as session:
        session.execute(
            text(
                "INSERT INTO leads (id, company_name, company_key, extra, created_at) "
                "VALUES (:id, :company_name, :company_key, :extra, :created_at)"
            ),
            {
                "id": lead_id,
                "company_name": "Preserved",
                "company_key": "preserved",
                "extra": "{}",
                "created_at": datetime.now(timezone.utc),
            },
        )
    command.upgrade(config, "head")
    command.check(config)
    with factory() as session:
        assert session.get(Lead, lead_id).company_name == "Preserved"
        assert session.scalar(select(func.count(ResearchJob.id))) == 0
    engine.dispose()


def test_selected_facts_only_for_correct_lead_and_never_approve(research, monkeypatch):
    client, factory, lead_id, _, _ = research
    created = submit(client, lead_id).json()
    orchestrator.run_research_job(created["job_id"])
    fact = client.get(f"/intelligence/companies/{created['company_id']}/facts").json()["items"][0]
    campaign_id = client.post("/campaigns", json={"name": "Synthetic", "mode": "manual", "delays": []}).json()["id"]
    enrollment = client.post(f"/campaigns/{campaign_id}/enrollments",
                             json={"lead_id": lead_id, "recipient": "alex@example.com"}).json()["id"]
    contexts = []

    def generate(company, context, steps, **kwargs):
        contexts.append(context)
        return [{"subject": "Synthetic introduction", "body": "Reviewed draft."} for _ in range(steps)]

    monkeypatch.setattr(bedrock, "generate_sequence", generate)
    result = client.post(f"/enrollments/{enrollment}/generate", json={"context": "Approved offering", "research_fact_ids": [fact["id"]]})
    assert result.status_code == 200
    assert result.json()[0]["status"] == "draft"
    assert "https://example.com/" in contexts[0]
    with factory.begin() as session:
        item = session.get(ResearchFact, fact["id"])
        item.verification_status = "conflicting"
    assert client.post(f"/enrollments/{enrollment}/generate",
                       json={"context": "Approved offering", "research_fact_ids": [fact["id"]]}).status_code == 400
    with factory.begin() as session:
        item = session.get(ResearchFact, fact["id"])
        item.verification_status = "reported"
        company = session.get(CompanyResearchProfile, item.company_id)
        company.lead_id = None
    assert client.post(f"/enrollments/{enrollment}/generate",
                       json={"context": "Approved offering", "research_fact_ids": [fact["id"]]}).status_code == 400
    assert len(contexts) == 1
