import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import Lead, Product
from app.market_intelligence.models import (
    MarketSource, MarketArticle, MarketCompany, MarketEvent,
    ProductCatalog, ProductMatchRule, OpportunitySignal, MarketAlert,
    CompanyWatchlist, now as mi_now,
)
from app.market_intelligence.providers.playwright_provider import (
    PlaywrightProvider, normalize_url, compute_sha256,
)
from app.market_intelligence.services.source_registry import (
    seed_product_catalog, seed_source_registry,
)
from app.market_intelligence.services.company_resolution import CompanyResolutionService
from app.market_intelligence.services.product_matching import ProductMatchingService
from app.market_intelligence.ai.event_classifier import EventClassifierService


@pytest.fixture
def workspace(tmp_path):
    db_path = tmp_path / "mi_test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    with factory() as session:
        yield session
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(workspace):
    return TestClient(app)


def test_html_parser_and_url_normalization():
    raw_html = """
    <!DOCTYPE html>
    <html>
      <head>
        <title>Tata Motors expands EV truck fleet across 15 hubs</title>
        <meta property="og:title" content="Tata Motors expands EV truck fleet across 15 hubs" />
        <meta property="og:description" content="Company invests 500 Cr into smart dispatch hubs." />
        <meta name="author" content="Rajesh Sharma" />
        <meta property="article:published_time" content="2026-11-20T08:00:00Z" />
      </head>
      <body>
        <main>
          <article>
            <p>Tata Motors has announced an expansion of its commercial electric truck fleet across major logistics corridors.</p>
            <p>The enterprise is implementing digital transport and warehouse management systems to optimize turnaround times.</p>
          </article>
        </main>
      </body>
    </html>
    """
    provider = PlaywrightProvider()
    article_data = provider.extract_article_metadata(raw_html, "https://autocarpro.in/news/tata-motors", "Autocar Professional")

    assert "Tata Motors" in article_data["headline"]
    assert "Rajesh Sharma" in article_data["author"]
    assert "fleet" in article_data["body_text"].lower() or "expansion" in article_data["body_text"].lower()

    # Test Canonical URL Normalization
    dirty_url = "https://www.autocarpro.in/news/tata-motors-fleet?utm_source=twitter&utm_medium=social#overview"
    canonical = normalize_url(dirty_url)
    assert canonical == "https://www.autocarpro.in/news/tata-motors-fleet"
    assert "utm_source" not in canonical

    # Content hashing
    h1 = compute_sha256("Title One Body text content")
    h2 = compute_sha256("Title One Body text content")
    assert h1 == h2
    assert len(h1) == 64


def _seed_all(workspace):
    seed_product_catalog(workspace)
    seed_source_registry(workspace)


def test_source_and_product_registry_seeding(workspace):
    """Verifies that official Solwer products and 62 sources seed cleanly into DB."""
    _seed_all(workspace)

    products = workspace.query(ProductCatalog).all()
    assert len(products) >= 6
    product_codes = {p.code for p in products}
    assert "TWMS" in product_codes
    assert "VDI" in product_codes
    assert "LOSS_TRACKER_IM" in product_codes
    assert "FLEET_MGMT" in product_codes
    assert "MCE" in product_codes
    assert "CARBON_MGMT" in product_codes

    rules = workspace.query(ProductMatchRule).all()
    assert len(rules) >= 6

    sources = workspace.query(MarketSource).all()
    assert len(sources) >= 60
    source_domains = {s.domain for s in sources}
    assert "autocarpro.in" in source_domains
    assert "tci.com" in source_domains or "tcil.com" in source_domains
    assert "rushlane.com" in source_domains


def test_company_resolution_existing_vs_new(workspace):
    """Verifies matching against existing CRM leads vs discovering new prospects."""
    # Seed an existing Lead with company_key
    lead = Lead(
        company_name="Delhivery Logistics Ltd",
        company_key="delhivery_logistics",
        domain="delhivery.com",
    )
    workspace.add(lead)
    workspace.commit()

    # Case 1: Match existing lead by domain
    resolver = CompanyResolutionService()
    matched_company = resolver.resolve_or_create_company(
        workspace,
        company_name="Delhivery Logistics",
        domain="delhivery.com",
    )
    assert matched_company.is_new is False
    assert matched_company.gtm_lead_id == lead.id
    assert matched_company.approval_status == "matched_existing"

    # Case 2: Completely new company discovered
    new_company = resolver.resolve_or_create_company(
        workspace,
        company_name="Rivigo Express Freight",
        domain="rivigo.com",
    )
    assert new_company.is_new is True
    assert new_company.gtm_lead_id is None
    assert new_company.approval_status == "pending_review"


def test_event_classification_heuristic(workspace):
    """Verifies event classification with heuristic fallback."""
    title = "Tata Motors invests 800 Cr in Sanand plant expansion for EV commercial vehicles"
    content = "Tata Motors has initiated major warehouse expansion and commercial vehicle deployment in Gujarat."

    classifier = EventClassifierService()
    event_data = classifier.classify_article(title, content, "https://autocarpro.in/news/123")
    assert event_data.company_name == "Tata Motors"
    assert event_data.event_category in (
        "manufacturing_expansion", "warehouse_expansion", "fleet_expansion",
        "dealership_expansion", "investment_contract", "general_automotive"
    )
    assert event_data.confidence >= 0.70


def test_explainable_opportunity_matching_and_alerts(workspace):
    """Verifies that events trigger explainable Solwer opportunities with dual scores and high-priority alerts."""
    _seed_all(workspace)

    # Create dummy source, article, company, and event
    source = workspace.query(MarketSource).first()
    article = MarketArticle(
        source_id=source.id,
        original_url="https://test.com/warehouse-tender",
        canonical_url="https://test.com/warehouse-tender",
        publisher="Logistics Daily",
        headline="VRL Logistics floats 200-depot transport warehouse management system modernization tender",
        body_text="VRL Logistics is seeking automated logistics software for warehouse dispatch, route optimization, and digital pre-trip inspection across 5,000 trucks.",
        content_hash="mockhash1234567890abcdef1234567890abcdef1234567890abcdef1234567890ab",
    )
    workspace.add(article)
    workspace.commit()

    resolver = CompanyResolutionService()
    company = resolver.resolve_or_create_company(workspace, "VRL Logistics", "vrlgroup.in")
    event = MarketEvent(
        article_id=article.id,
        company_id=company.id,
        event_category="warehouse_expansion",
        event_title="VRL Logistics tender for warehouse management",
        description="VRL Logistics tender for warehouse management and digital inspection.",
        business_implication="Modernizing depot operations and vehicle inspection turnaround.",
        confidence_score=0.92,
        country="IN",
    )
    workspace.add(event)
    workspace.commit()

    # Run opportunity matching
    engine = ProductMatchingService()
    signals = engine.evaluate_event_for_opportunities(workspace, event, company)
    assert len(signals) >= 1

    twms_signal = next((s for s in signals if "TWMS" in s.product.code), None)
    assert twms_signal is not None
    assert twms_signal.market_signal_score >= 50
    assert twms_signal.sales_readiness_score >= 40
    assert len(twms_signal.score_explanation) > 10
    assert len(twms_signal.suggested_next_action) > 10

    # High-priority alert verification
    alerts = workspace.query(MarketAlert).filter(MarketAlert.opportunity_id == twms_signal.id).all()
    if twms_signal.market_signal_score >= 80:
        assert len(alerts) >= 1
        assert "TWMS" in alerts[0].headline


def test_api_routes(client, workspace):
    """Verifies all Market Intelligence HTTP endpoints return 200 with schema compliance."""
    _seed_all(workspace)

    # 1. Overview metrics
    res = client.get("/api/market-intelligence/overview")
    assert res.status_code == 200
    data = res.json()
    assert "sources_total" in data
    assert data["sources_total"] >= 60

    # 2. Opportunities list
    res = client.get("/api/market-intelligence/opportunities")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

    # 3. Discovered companies
    res = client.get("/api/market-intelligence/companies")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

    # 4. Sources list
    res = client.get("/api/market-intelligence/sources")
    assert res.status_code == 200
    sources = res.json()
    assert len(sources) >= 60

    # 5. Products catalog
    res = client.get("/api/market-intelligence/products")
    assert res.status_code == 200
    products = res.json()
    assert len(products) >= 6


def test_webhook_inbound_trigger_and_subscriptions(client, workspace):
    """Verifies inbound webhook ingestion triggers automatic classification, opportunities, and alert generation."""
    _seed_all(workspace)

    # 1. Register an outbound webhook subscription
    sub_res = client.post(
        "/api/market-intelligence/webhooks",
        json={
            "name": "Test Sales Slack Webhook",
            "target_url": "https://httpbin.org/post",
            "secret_token": "secret123",
            "events": ["high_priority_opportunity", "webhook_triggered_opportunity"],
            "is_active": True,
        },
    )
    assert sub_res.status_code == 200
    sub_data = sub_res.json()
    assert sub_data["name"] == "Test Sales Slack Webhook"
    assert sub_data["target_url"] == "https://httpbin.org/post"
    sub_id = sub_data["id"]

    # 2. Get list of webhooks
    list_res = client.get("/api/market-intelligence/webhooks")
    assert list_res.status_code == 200
    assert any(s["id"] == sub_id for s in list_res.json())

    # 3. Trigger inbound webhook with an automotive tender signal
    webhook_payload = {
        "headline": "Tata Motors floats ₹250 crore tender for nationwide TWMS yard and warehouse management across 12 facilities",
        "body_text": "Tata Motors Commercial Vehicles division is deploying smart warehouse dispatch and yard management systems to optimize depot turnaround times and multi-plant vehicle dispatch across Pune, Jamshedpur, and Pantnagar.",
        "company_name": "Tata Motors Commercial Vehicles",
        "domain": "tatamotors.com",
        "event_category": "warehouse_expansion",
        "publisher": "AutoTech India Webhook",
    }
    inbound_res = client.post("/api/market-intelligence/webhook", json=webhook_payload)
    assert inbound_res.status_code == 200
    res_data = inbound_res.json()

    assert res_data["status"] == "success"
    assert res_data["notification_triggered"] is True
    assert res_data["company"]["company_name"] == "Tata Motors Commercial Vehicles"
    assert res_data["opportunities_count"] >= 1
    assert res_data["alerts_count"] >= 1

    # Check that TWMS opportunity was matched
    twms = next((o for o in res_data["opportunities"] if "TWMS" in o["product_code"]), None)
    assert twms is not None
    assert twms["market_signal_score"] >= 70

    # 4. Check alerts endpoint to verify triggered alert is now available
    alerts_res = client.get("/api/market-intelligence/alerts")
    assert alerts_res.status_code == 200
    alerts = alerts_res.json()
    assert any("Tata Motors" in a["headline"] for a in alerts)

    # 5. Delete webhook subscription
    del_res = client.delete(f"/api/market-intelligence/webhooks/{sub_id}")
    assert del_res.status_code == 200

