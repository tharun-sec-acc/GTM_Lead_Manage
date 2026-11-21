import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, and_

from app.database import SessionLocal
from app.market_intelligence.models import MarketSource
from app.market_intelligence.services.source_discovery import SourceDiscoveryService
from app.market_intelligence.services.crawl_service import CrawlService
from app.market_intelligence.services.pipeline_orchestrator import MarketIntelligenceOrchestrator

logger = logging.getLogger(__name__)


def crawl_due_market_sources(max_sources: int = 5):
    """
    Periodic task executed by Celery Beat to crawl due sources
    based on priority and configured crawl_frequency_minutes.
    """
    logger.info("Starting periodic market intelligence source crawl check")
    utcnow = datetime.now(timezone.utc)

    with SessionLocal() as session:
        # Find enabled sources that are due for crawl
        sources = session.scalars(
            select(MarketSource)
            .where(MarketSource.enabled == True)
            .order_by(MarketSource.priority.asc(), MarketSource.last_crawl_at.asc().nullsfirst())
        ).all()

        due_sources = []
        for s in sources:
            if s.last_crawl_at is None:
                due_sources.append(s)
            else:
                elapsed = (utcnow - s.last_crawl_at).total_seconds() / 60.0
                if elapsed >= s.crawl_frequency_minutes:
                    due_sources.append(s)

            if len(due_sources) >= max_sources:
                break

        logger.info("Found %d due sources to crawl", len(due_sources))
        crawl_svc = CrawlService()
        orchestrator = MarketIntelligenceOrchestrator()

        for s in due_sources:
            try:
                # If discovered_news_url is missing, run discovery first
                if not s.discovered_news_url:
                    SourceDiscoveryService().discover_source_sections(session, s.id)

                crawl_res = crawl_svc.crawl_source(session, s.id, max_articles=8)
                logger.info("Crawl result for %s: %s", s.name, crawl_res)
            except Exception as e:
                logger.error("Error crawling source %s: %s", s.name, e)
                continue

        # Process all newly extracted articles through AI intelligence
        try:
            ai_res = orchestrator.process_all_pending_articles(session, limit=20)
            logger.info("AI intelligence processing result: %s", ai_res)
        except Exception as e:
            logger.error("Error running AI intelligence processing: %s", e)
