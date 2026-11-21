import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, select

from app.database import get_db
from app.models import Lead, new_id, now
from app.market_intelligence.models import (
    MarketSource,
    MarketSourceRun,
    MarketArticle,
    MarketEvent,
    MarketCompany,
    ProductCatalog,
    ProductMatchRule,
    OpportunitySignal,
    MarketAlert,
    CompanyWatchlist,
    MarketWebhookSubscription,
)
from app.market_intelligence.schemas import (
    MarketSourceResponse,
    MarketSourceUpdate,
    MarketArticleItem,
    MarketEventItem,
    ProductCatalogItem,
    OpportunitySignalItem,
    DiscoveredCompanyItem,
    MarketAlertItem,
    MarketIntelligenceOverview,
    WatchlistCreate,
    WatchlistItem,
    MarketWebhookInboundPayload,
    MarketWebhookSubscriptionCreate,
    MarketWebhookSubscriptionItem,
    MarketWebhookTestPayload,
)
from app.market_intelligence.services.source_discovery import SourceDiscoveryService
from app.market_intelligence.services.crawl_service import CrawlService
from app.market_intelligence.services.pipeline_orchestrator import MarketIntelligenceOrchestrator
from app.market_intelligence.services.webhook_dispatcher import WebhookDispatcherService
from app.market_intelligence.providers.playwright_provider import normalize_url

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/market-intelligence", tags=["Market Intelligence"])


@router.get("/overview", response_model=MarketIntelligenceOverview)
def get_market_intelligence_overview(session: Session = Depends(get_db)):
    """Executive summary metrics across automotive market signals, opportunities, and sources."""
    utcnow = datetime.now(timezone.utc)
    today_start = utcnow.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = utcnow - timedelta(days=7)

    signals_today = session.scalar(
        select(func.count(OpportunitySignal.id)).where(OpportunitySignal.created_at >= today_start)
    ) or 0

    signals_this_week = session.scalar(
        select(func.count(OpportunitySignal.id)).where(OpportunitySignal.created_at >= week_start)
    ) or 0

    total_articles = session.scalar(select(func.count(MarketArticle.id))) or 0

    high_priority_opps = session.scalar(
        select(func.count(OpportunitySignal.id)).where(OpportunitySignal.priority_level == "high")
    ) or 0

    existing_companies = session.scalar(
        select(func.count(MarketCompany.id)).where(MarketCompany.is_new == False)
    ) or 0

    new_companies = session.scalar(
        select(func.count(MarketCompany.id)).where(MarketCompany.is_new == True)
    ) or 0

    pending_approvals = session.scalar(
        select(func.count(MarketCompany.id)).where(MarketCompany.approval_status == "pending_review")
    ) or 0

    # Opportunities by product
    product_counts_raw = session.execute(
        select(ProductCatalog.code, func.count(OpportunitySignal.id))
        .join(OpportunitySignal, OpportunitySignal.product_id == ProductCatalog.id, isouter=True)
        .group_by(ProductCatalog.code)
    ).all()
    opps_by_product = {code: count for code, count in product_counts_raw}

    # Opportunities by event category
    cat_counts_raw = session.execute(
        select(MarketEvent.event_category, func.count(OpportunitySignal.id))
        .join(OpportunitySignal, OpportunitySignal.event_id == MarketEvent.id, isouter=True)
        .group_by(MarketEvent.event_category)
    ).all()
    opps_by_cat = {cat: count for cat, count in cat_counts_raw}

    # Source health
    sources_total = session.scalar(select(func.count(MarketSource.id))) or 0
    sources_active = session.scalar(select(func.count(MarketSource.id)).where(MarketSource.enabled == True)) or 0
    sources_validated = session.scalar(
        select(func.count(MarketSource.id)).where(MarketSource.validation_status == "validated")
    ) or 0
    sources_failed = session.scalar(
        select(func.count(MarketSource.id)).where(MarketSource.validation_status == "failed")
    ) or 0

    last_crawl = session.scalar(
        select(func.max(MarketSource.last_crawl_at))
    )

    return MarketIntelligenceOverview(
        signals_today=signals_today,
        signals_this_week=signals_this_week,
        total_articles=total_articles,
        high_priority_opportunities=high_priority_opps,
        existing_companies_with_news=existing_companies,
        new_companies_discovered=new_companies,
        pending_approvals=pending_approvals,
        opportunities_by_product=opps_by_product,
        opportunities_by_category=opps_by_cat,
        sources_total=sources_total,
        sources_active=sources_active,
        sources_validated=sources_validated,
        sources_failed=sources_failed,
        last_crawl_time=last_crawl,
    )


@router.get("/feed", response_model=list[MarketArticleItem])
def get_market_feed(
    source_category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=500),
    session: Session = Depends(get_db),
):
    """Returns the continuous stream of discovered and processed automotive articles."""
    query = select(MarketArticle).join(MarketSource, MarketArticle.source_id == MarketSource.id)

    if source_category:
        query = query.where(MarketSource.source_category == source_category)

    if search:
        search_term = f"%{search.strip().lower()}%"
        query = query.where(func.lower(MarketArticle.headline).like(search_term))

    articles = session.scalars(query.order_by(desc(MarketArticle.published_at)).limit(limit)).all()

    return [
        MarketArticleItem(
            id=a.id,
            headline=a.headline,
            original_url=a.original_url,
            canonical_url=a.canonical_url,
            publisher=a.publisher,
            author=a.author,
            published_at=a.published_at,
            summary=a.summary,
            body_preview=(a.body_text or "")[:280] if a.body_text else None,
            content_hash=a.content_hash,
            version_count=a.version_count,
            source_id=a.source_id,
            source_name=a.source.name if a.source else None,
            ai_processed=a.ai_processed,
            created_at=a.created_at,
        )
        for a in articles
    ]


@router.get("/opportunities", response_model=list[OpportunitySignalItem])
def get_opportunity_signals(
    product: Optional[str] = Query(None, description="Filter by Solwer product code e.g. TWMS"),
    priority: Optional[str] = Query(None, description="high, medium, low"),
    company_status: Optional[str] = Query(None, description="existing or new"),
    review_status: Optional[str] = Query(None, description="new, reviewed, approved, dismissed"),
    company_name: Optional[str] = Query(None, description="Filter by company name"),
    lead_id: Optional[str] = Query(None, description="Filter by GTM lead ID"),
    limit: int = Query(200, ge=1, le=500),
    session: Session = Depends(get_db),
):
    """Retrieves qualified Solwer product opportunities with explainable dual scores."""
    query = (
        select(OpportunitySignal)
        .join(ProductCatalog, OpportunitySignal.product_id == ProductCatalog.id)
        .join(MarketCompany, OpportunitySignal.company_id == MarketCompany.id)
        .join(MarketEvent, OpportunitySignal.event_id == MarketEvent.id)
    )

    if product:
        query = query.where(ProductCatalog.code == product.upper())
    if priority:
        query = query.where(OpportunitySignal.priority_level == priority.lower())
    if company_status == "existing":
        query = query.where(MarketCompany.is_new == False)
    elif company_status == "new":
        query = query.where(MarketCompany.is_new == True)
    if review_status:
        query = query.where(OpportunitySignal.review_status == review_status.lower())
    if lead_id:
        query = query.where(MarketCompany.gtm_lead_id == lead_id)
    if company_name:
        query = query.where(MarketCompany.company_name.ilike(f"%{company_name}%"))

    opps = session.scalars(query.order_by(desc(OpportunitySignal.market_signal_score)).limit(limit)).all()

    return [
        OpportunitySignalItem(
            id=o.id,
            event_id=o.event_id,
            event_title=o.event.event_title,
            event_category=o.event.event_category,
            event_description=o.event.description if o.event else None,
            operational_problem=o.event.operational_problem if o.event else None,
            business_implication=o.event.business_implication if o.event else None,
            location=o.event.location if o.event else None,
            article_headline=o.event.article.headline if (o.event and o.event.article) else None,
            article_publisher=o.event.article.publisher if (o.event and o.event.article) else None,
            article_url=o.event.article.original_url if (o.event and o.event.article) else None,
            company_id=o.company_id,
            company_name=o.company.company_name,
            company_domain=o.company.domain,
            is_new_company=o.company.is_new,
            gtm_lead_id=o.company.gtm_lead_id,
            product_id=o.product_id,
            product_code=o.product.code,
            product_name=o.product.name,
            market_signal_score=o.market_signal_score,
            sales_readiness_score=o.sales_readiness_score,
            score_breakdown=o.score_breakdown or {},
            score_explanation=o.score_explanation,
            suggested_buyer_roles=o.suggested_buyer_roles or [],
            suggested_next_action=o.suggested_next_action,
            priority_level=o.priority_level,
            review_status=o.review_status,
            created_at=o.created_at,
        )
        for o in opps
    ]


@router.post("/opportunities/{opp_id}/approve")
def approve_opportunity(opp_id: str, session: Session = Depends(get_db)):
    """Approves an opportunity signal for sales outreach."""
    opp = session.get(OpportunitySignal, opp_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity signal not found")
    opp.review_status = "approved"
    opp.updated_at = now()
    session.commit()
    return {"message": "Opportunity approved successfully.", "id": opp.id}


@router.post("/opportunities/{opp_id}/dismiss")
def dismiss_opportunity(opp_id: str, session: Session = Depends(get_db)):
    """Dismisses an opportunity signal."""
    opp = session.get(OpportunitySignal, opp_id)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity signal not found")
    opp.review_status = "dismissed"
    opp.updated_at = now()
    session.commit()
    return {"message": "Opportunity dismissed.", "id": opp.id}


@router.get("/companies", response_model=list[DiscoveredCompanyItem])
def get_discovered_companies(
    status_filter: Optional[str] = Query(None, description="pending_review, matched_existing, approved, dismissed"),
    is_new: Optional[bool] = Query(None),
    limit: int = Query(200, ge=1, le=500),
    session: Session = Depends(get_db),
):
    """Retrieves discovered companies and their CRM match status."""
    query = select(MarketCompany)

    if status_filter:
        query = query.where(MarketCompany.approval_status == status_filter)
    if is_new is not None:
        query = query.where(MarketCompany.is_new == is_new)

    companies = session.scalars(query.order_by(desc(MarketCompany.created_at)).limit(limit)).all()

    return [
        DiscoveredCompanyItem(
            id=c.id,
            company_name=c.company_name,
            normalized_name=c.normalized_name,
            domain=c.domain,
            industry=c.industry,
            business_segment=c.business_segment,
            country=c.country,
            location=c.location,
            is_new=c.is_new,
            gtm_lead_id=c.gtm_lead_id,
            match_confidence=c.match_confidence,
            approval_status=c.approval_status,
            events_count=len(c.events),
            opportunities_count=len(c.opportunities),
            created_at=c.created_at,
        )
        for c in companies
    ]


@router.post("/companies/{company_id}/approve")
def approve_discovered_company(company_id: str, session: Session = Depends(get_db)):
    """Approves a newly discovered company and promotes it into a verified CRM Lead."""
    company = session.get(MarketCompany, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="MarketCompany not found")

    if not company.gtm_lead_id:
        # Create corresponding GTM Lead
        lead = Lead(
            id=new_id(),
            company_name=company.company_name,
            domain=company.domain,
            industry=company.industry,
            location=company.location,
            remarks=f"Discovered via Market Intelligence from automotive news monitoring.",
        )
        session.add(lead)
        session.flush()
        company.gtm_lead_id = lead.id

    company.approval_status = "approved"
    company.is_new = False
    company.approved_by = "sales_user"
    company.updated_at = now()
    session.commit()

    return {"message": f"Company '{company.company_name}' approved and linked to CRM Lead.", "lead_id": company.gtm_lead_id}


@router.post("/companies/{company_id}/dismiss")
def dismiss_discovered_company(company_id: str, session: Session = Depends(get_db)):
    """Dismisses a proposed company from the discovery queue."""
    company = session.get(MarketCompany, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="MarketCompany not found")
    company.approval_status = "dismissed"
    company.updated_at = now()
    session.commit()
    return {"message": f"Company '{company.company_name}' dismissed."}


@router.get("/sources", response_model=list[MarketSourceResponse])
def get_sources(session: Session = Depends(get_db)):
    """Returns all 62 registered automotive monitoring sources and their crawl status."""
    sources = session.scalars(
        select(MarketSource).order_by(MarketSource.priority.asc(), MarketSource.name.asc())
    ).all()

    return [
        MarketSourceResponse(
            id=s.id,
            name=s.name,
            domain=s.domain,
            homepage_url=s.homepage_url,
            discovered_news_url=s.discovered_news_url,
            discovered_feed_url=s.discovered_feed_url,
            source_category=s.source_category,
            industry=s.industry,
            country=s.country,
            ingestion_method=s.ingestion_method,
            crawl_frequency_minutes=s.crawl_frequency_minutes,
            priority=s.priority,
            enabled=s.enabled,
            validation_status=s.validation_status,
            last_crawl_at=s.last_crawl_at,
            last_success_at=s.last_success_at,
            articles_discovered=s.articles_discovered,
            articles_processed=s.articles_processed,
            failed_requests=s.failed_requests,
            last_error=s.last_error,
            created_at=s.created_at,
        )
        for s in sources
    ]


@router.patch("/sources/{source_id}", response_model=MarketSourceResponse)
def update_source(source_id: str, payload: MarketSourceUpdate, session: Session = Depends(get_db)):
    """Allows administrators to toggle sources, adjust crawl frequencies, and change priorities."""
    source = session.get(MarketSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    if payload.enabled is not None:
        source.enabled = payload.enabled
    if payload.crawl_frequency_minutes is not None:
        source.crawl_frequency_minutes = payload.crawl_frequency_minutes
    if payload.priority is not None:
        source.priority = payload.priority
    if payload.source_category is not None:
        source.source_category = payload.source_category
    if payload.industry is not None:
        source.industry = payload.industry

    source.updated_at = now()
    session.commit()

    return MarketSourceResponse(
        id=source.id,
        name=source.name,
        domain=source.domain,
        homepage_url=source.homepage_url,
        discovered_news_url=source.discovered_news_url,
        discovered_feed_url=source.discovered_feed_url,
        source_category=source.source_category,
        industry=source.industry,
        country=source.country,
        ingestion_method=source.ingestion_method,
        crawl_frequency_minutes=source.crawl_frequency_minutes,
        priority=source.priority,
        enabled=source.enabled,
        validation_status=source.validation_status,
        last_crawl_at=source.last_crawl_at,
        last_success_at=source.last_success_at,
        articles_discovered=source.articles_discovered,
        articles_processed=source.articles_processed,
        failed_requests=source.failed_requests,
        last_error=source.last_error,
        created_at=source.created_at,
    )


@router.post("/sources/{source_id}/test")
def test_source_discovery(source_id: str, session: Session = Depends(get_db)):
    """Actively tests and discovers the news/media section of a source using SSRF-safe Playwright inspection."""
    discovery_svc = SourceDiscoveryService()
    try:
        res = discovery_svc.discover_source_sections(session, source_id)
        return res
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Source test failed: {e}") from e


@router.post("/sources/{source_id}/crawl")
def trigger_source_crawl(source_id: str, max_articles: int = Query(10, ge=1, le=30), session: Session = Depends(get_db)):
    """Triggers an immediate crawl of a source, discovers new articles, and runs AI intelligence pipeline."""
    crawl_svc = CrawlService()
    try:
        crawl_res = crawl_svc.crawl_source(session, source_id, max_articles=max_articles)
        # Run AI intelligence on any new articles
        orchestrator = MarketIntelligenceOrchestrator()
        ai_res = orchestrator.process_all_pending_articles(session, limit=max_articles)
        crawl_res["ai_processing"] = ai_res
        return crawl_res
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Crawl execution failed: {e}") from e


@router.get("/alerts", response_model=list[MarketAlertItem])
def get_market_alerts(
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=100),
    session: Session = Depends(get_db),
):
    """Returns high-priority notifications and alerts for sales team."""
    query = select(MarketAlert)
    if unread_only:
        query = query.where(MarketAlert.is_read == False)

    alerts = session.scalars(query.order_by(desc(MarketAlert.created_at)).limit(limit)).all()

    return [
        MarketAlertItem(
            id=a.id,
            opportunity_id=a.opportunity_id,
            alert_type=a.alert_type,
            headline=a.headline,
            summary=a.summary,
            priority=a.priority,
            is_read=a.is_read,
            is_dismissed=a.is_dismissed,
            read_at=a.read_at,
            created_at=a.created_at,
        )
        for a in alerts
    ]


@router.post("/alerts/{alert_id}/read")
def mark_alert_read(alert_id: str, session: Session = Depends(get_db)):
    """Marks a market notification as read."""
    alert = session.get(MarketAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.is_read = True
    alert.read_at = now()
    session.commit()
    return {"message": "Alert marked as read.", "id": alert.id}


@router.post("/alerts/{alert_id}/dismiss")
def dismiss_alert(alert_id: str, session: Session = Depends(get_db)):
    """Dismisses a market notification."""
    alert = session.get(MarketAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.is_dismissed = True
    session.commit()
    return {"message": "Alert dismissed.", "id": alert.id}


@router.get("/watchlists", response_model=list[WatchlistItem])
def get_watchlists(session: Session = Depends(get_db)):
    """Returns salesperson's company watchlists."""
    watchlists = session.scalars(select(CompanyWatchlist).where(CompanyWatchlist.is_active == True)).all()
    return [
        WatchlistItem(
            id=w.id,
            company_name=w.company_name,
            company_domain=w.company_domain,
            lead_id=w.lead_id,
            notify_on_events=w.notify_on_events or [],
            is_active=w.is_active,
            created_at=w.created_at,
        )
        for w in watchlists
    ]


@router.post("/watchlists", response_model=WatchlistItem)
def create_watchlist_entry(payload: WatchlistCreate, session: Session = Depends(get_db)):
    """Adds a company to the salesperson's monitoring watchlist."""
    domain = payload.company_domain.strip().lower()
    existing = session.scalar(
        select(CompanyWatchlist).where(
            CompanyWatchlist.company_domain == domain,
            CompanyWatchlist.user_id == "default_sales_user",
        )
    )
    if existing:
        existing.is_active = True
        session.commit()
        return WatchlistItem(
            id=existing.id,
            company_name=existing.company_name,
            company_domain=existing.company_domain,
            lead_id=existing.lead_id,
            notify_on_events=existing.notify_on_events or [],
            is_active=existing.is_active,
            created_at=existing.created_at,
        )

    w = CompanyWatchlist(
        user_id="default_sales_user",
        company_name=payload.company_name.strip(),
        company_domain=domain,
        lead_id=payload.lead_id,
        notify_on_events=payload.notify_on_events,
        is_active=True,
    )
    session.add(w)
    session.commit()

    return WatchlistItem(
        id=w.id,
        company_name=w.company_name,
        company_domain=w.company_domain,
        lead_id=w.lead_id,
        notify_on_events=w.notify_on_events or [],
        is_active=w.is_active,
        created_at=w.created_at,
    )


@router.delete("/watchlists/{watchlist_id}")
def delete_watchlist_entry(watchlist_id: str, session: Session = Depends(get_db)):
    """Removes a company from the watchlist."""
    w = session.get(CompanyWatchlist, watchlist_id)
    if not w:
        raise HTTPException(status_code=404, detail="Watchlist entry not found")
    session.delete(w)
    session.commit()
    return {"message": "Watchlist entry removed."}


@router.get("/products", response_model=list[ProductCatalogItem])
def get_product_catalogue(session: Session = Depends(get_db)):
    """Returns official Solwer product catalogue and capabilities."""
    products = session.scalars(
        select(ProductCatalog).where(ProductCatalog.is_active == True).order_by(ProductCatalog.priority.asc())
    ).all()

    return [
        ProductCatalogItem(
            id=p.id,
            code=p.code,
            name=p.name,
            official_url=p.official_url,
            business_area=p.business_area,
            priority=p.priority,
            is_active=p.is_active,
            description=p.description,
            features=p.features or [],
            problems_solved=p.problems_solved or [],
            target_industries=p.target_industries or [],
            potential_buyer_roles=p.potential_buyer_roles or [],
        )
        for p in products
    ]


# ---------------------------------------------------------------------------
# Inbound Webhook: Automated Signal Ingestion & Notification Trigger Engine
# ---------------------------------------------------------------------------

@router.post("/webhook")
def trigger_inbound_market_webhook(
    payload: MarketWebhookInboundPayload,
    session: Session = Depends(get_db),
):
    """
    Inbound webhook to ingest an automotive market signal, tender, or business expansion.
    Automatically executes:
    1. Article ingestion & deduplication
    2. Bedrock/heuristic event classification
    3. Company resolution & CRM lead matching
    4. Solwer product opportunity evaluation & explainable dual-scoring
    5. MarketAlert creation
    6. Outbound webhook notification dispatch to subscribed endpoints (Slack, Teams, CRMs)
    """
    logger.info("Received inbound market webhook: %s", payload.headline)

    # 1. URL and Content Hash
    raw_url = payload.url or f"http://localhost:8000/signals/webhook-{new_id()[:8]}"
    canonical_url = normalize_url(raw_url)
    content_text = f"{payload.headline}\n{payload.body_text or ''}".strip()
    content_hash = hashlib.sha256(content_text.encode("utf-8")).hexdigest()

    # 2. Ingestion Source
    source = session.scalar(select(MarketSource).where(MarketSource.domain == "webhook.internal"))
    if not source:
        source = MarketSource(
            name="Automated Inbound Webhook",
            domain="webhook.internal",
            homepage_url="http://localhost:8000/api/market-intelligence/webhook",
            source_category="webhook",
            industry="Automotive & Mobility",
            country="India",
            ingestion_method="webhook",
            validation_status="validated",
            enabled=True,
        )
        session.add(source)
        session.flush()

    # 3. Ingest or update article
    article = session.scalar(select(MarketArticle).where(MarketArticle.canonical_url == canonical_url))
    if not article:
        article = MarketArticle(
            source_id=source.id,
            headline=payload.headline.strip(),
            original_url=raw_url,
            canonical_url=canonical_url,
            publisher=payload.publisher or "Inbound Signal Webhook",
            author=payload.author or "Automated Signal Trigger",
            published_at=now(),
            summary=(payload.body_text or payload.headline)[:500],
            body_text=payload.body_text or payload.headline,
            content_hash=content_hash,
            extraction_status="extracted",
            ai_processed=False,
            metadata_json={"webhook_trigger": True, "event_category": payload.event_category},
        )
        session.add(article)
        session.flush()
    else:
        article.headline = payload.headline.strip()
        article.body_text = payload.body_text or payload.headline
        article.content_hash = content_hash
        article.ai_processed = False

    # 4. Pipeline Orchestration
    orchestrator = MarketIntelligenceOrchestrator()
    extracted = orchestrator.classifier.classify_article(
        headline=article.headline,
        body_text=article.body_text or article.summary or "",
        publisher=article.publisher,
    )

    # Determine company & category (allowing explicit payload override)
    resolved_company_name = payload.company_name.strip() if payload.company_name else extracted.company_name
    resolved_domain = payload.domain.strip().lower() if payload.domain else extracted.company_domain
    resolved_category = payload.event_category.strip() if payload.event_category else extracted.event_category

    # 5. Company Resolution
    company = orchestrator.company_resolver.resolve_or_create_company(
        session=session,
        company_name=resolved_company_name,
        domain=resolved_domain,
        industry="Automotive",
        business_segment=extracted.business_segment or "Automotive OEM / Tier 1",
        location=extracted.location or "India",
        parent_company=extracted.parent_company,
    )

    # 6. Store MarketEvent
    event = MarketEvent(
        article_id=article.id,
        company_id=company.id,
        event_category=resolved_category,
        event_title=extracted.event_title or article.headline,
        description=extracted.event_description or article.body_text or article.headline,
        business_implication=extracted.business_implication,
        operational_problem=extracted.operational_problem,
        location=extracted.location or "India",
        country=extracted.country or "India",
        event_date=now(),
        supporting_evidence=extracted.supporting_evidence or article.headline,
        confidence_score=max(extracted.confidence, 0.85),
        raw_ai_payload=extracted.model_dump(),
    )
    session.add(event)
    session.flush()

    # 7. Evaluate Solwer Products
    opportunities = orchestrator.product_matcher.evaluate_event_for_opportunities(
        session=session,
        event=event,
        company=company,
    )

    # 8. Collect alerts and ensure notification is triggered
    alerts = session.scalars(
        select(MarketAlert).where(MarketAlert.opportunity_id.in_([o.id for o in opportunities]))
    ).all() if opportunities else []

    if not alerts and opportunities:
        top_opp = opportunities[0]
        top_prod_name = getattr(top_opp.product, "name", "Solwer Solution")
        fallback_alert = MarketAlert(
            opportunity_id=top_opp.id,
            alert_type="webhook_triggered_opportunity",
            headline=f"Opportunity Alert: {top_prod_name} for {company.company_name}",
            summary=f"Inbound webhook signal: {event.event_title}. Market Signal Score: {top_opp.market_signal_score:.0f}/100.",
            priority=top_opp.priority_level or "high",
        )
        session.add(fallback_alert)
        session.flush()
        alerts = [fallback_alert]

    # 9. Check Watchlists
    if company.domain:
        watchlists = session.scalars(
            select(CompanyWatchlist).where(
                CompanyWatchlist.company_domain == company.domain,
                CompanyWatchlist.is_active == True,
            )
        ).all()
        for w in watchlists:
            w_alert = MarketAlert(
                opportunity_id=opportunities[0].id if opportunities else None,
                alert_type="watchlist_update",
                headline=f"Watchlist Notification: {company.company_name}",
                summary=f"Monitored company {company.company_name} triggered signal: {event.event_title}",
                priority="high",
                target_user_id=w.user_id,
            )
            session.add(w_alert)
            alerts.append(w_alert)

    # 10. Outbound Webhook Dispatch
    dispatcher = WebhookDispatcherService()
    dispatch_logs = []
    for alert in alerts:
        opp = next((o for o in opportunities if o.id == alert.opportunity_id), None)
        dispatches = dispatcher.dispatch_alert(session, alert=alert, opp=opp, company=company, event=event)
        dispatch_logs.extend(dispatches)

    article.ai_processed = True
    session.commit()

    return {
        "status": "success",
        "notification_triggered": True,
        "message": f"Webhook processed: Detected {len(opportunities)} opportunities and triggered {len(alerts)} alerts.",
        "article_id": article.id,
        "event_id": event.id,
        "company": {
            "id": company.id,
            "company_name": company.company_name,
            "domain": company.domain,
            "is_new": company.is_new,
            "approval_status": company.approval_status,
        },
        "opportunities_count": len(opportunities),
        "opportunities": [
            {
                "id": o.id,
                "product_code": getattr(o.product, "code", ""),
                "product_name": getattr(o.product, "name", ""),
                "market_signal_score": o.market_signal_score,
                "sales_readiness_score": o.sales_readiness_score,
                "priority_level": o.priority_level,
                "suggested_next_action": o.suggested_next_action,
            }
            for o in opportunities
        ],
        "alerts_count": len(alerts),
        "alerts": [
            {
                "id": a.id,
                "headline": a.headline,
                "summary": a.summary,
                "priority": a.priority,
            }
            for a in alerts
        ],
        "outbound_dispatches": dispatch_logs,
    }


# ---------------------------------------------------------------------------
# Outbound Webhook Subscription Management
# ---------------------------------------------------------------------------

@router.get("/webhooks", response_model=list[MarketWebhookSubscriptionItem])
def get_webhook_subscriptions(session: Session = Depends(get_db)):
    """Lists all configured outbound webhook endpoints (Slack, Teams, CRM, Zapier)."""
    subs = session.scalars(
        select(MarketWebhookSubscription).order_by(MarketWebhookSubscription.created_at.desc())
    ).all()
    return [
        MarketWebhookSubscriptionItem(
            id=s.id,
            name=s.name,
            target_url=s.target_url,
            secret_token=s.secret_token,
            events=s.events or [],
            is_active=s.is_active,
            last_dispatched_at=s.last_dispatched_at,
            last_status_code=s.last_status_code,
            last_error=s.last_error,
            created_at=s.created_at,
        )
        for s in subs
    ]


@router.post("/webhooks", response_model=MarketWebhookSubscriptionItem)
def create_webhook_subscription(
    payload: MarketWebhookSubscriptionCreate,
    session: Session = Depends(get_db),
):
    """Registers a new outbound webhook subscription to receive real-time opportunity alerts."""
    sub = MarketWebhookSubscription(
        name=payload.name.strip() or "Sales Alert Webhook",
        target_url=payload.target_url.strip(),
        secret_token=payload.secret_token.strip() if payload.secret_token else None,
        events=payload.events or ["high_priority_opportunity", "new_company_discovered", "existing_lead_update"],
        is_active=payload.is_active,
    )
    session.add(sub)
    session.commit()
    return MarketWebhookSubscriptionItem(
        id=sub.id,
        name=sub.name,
        target_url=sub.target_url,
        secret_token=sub.secret_token,
        events=sub.events or [],
        is_active=sub.is_active,
        last_dispatched_at=sub.last_dispatched_at,
        last_status_code=sub.last_status_code,
        last_error=sub.last_error,
        created_at=sub.created_at,
    )


@router.delete("/webhooks/{subscription_id}")
def delete_webhook_subscription(subscription_id: str, session: Session = Depends(get_db)):
    """Removes an outbound webhook subscription."""
    sub = session.get(MarketWebhookSubscription, subscription_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Webhook subscription not found")
    session.delete(sub)
    session.commit()
    return {"message": "Webhook subscription deleted successfully."}


@router.post("/webhooks/test")
def test_webhook_connection(payload: MarketWebhookTestPayload):
    """Pings a target webhook URL with a test notification payload to verify connectivity."""
    dispatcher = WebhookDispatcherService()
    result = dispatcher.test_target(target_url=payload.target_url, secret_token=payload.secret_token)
    return result

