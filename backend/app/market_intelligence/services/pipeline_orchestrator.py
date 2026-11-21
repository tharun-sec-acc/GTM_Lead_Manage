import logging
from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.market_intelligence.models import (
    MarketArticle,
    MarketEvent,
    MarketCompany,
    OpportunitySignal,
    MarketAlert,
    CompanyWatchlist,
    now,
)
from app.market_intelligence.ai.event_classifier import EventClassifierService
from app.market_intelligence.services.company_resolution import CompanyResolutionService
from app.market_intelligence.services.product_matching import ProductMatchingService

logger = logging.getLogger(__name__)


class MarketIntelligenceOrchestrator:
    def __init__(
        self,
        classifier: EventClassifierService | None = None,
        company_resolver: CompanyResolutionService | None = None,
        product_matcher: ProductMatchingService | None = None,
    ):
        self.classifier = classifier or EventClassifierService()
        self.company_resolver = company_resolver or CompanyResolutionService()
        self.product_matcher = product_matcher or ProductMatchingService()

    def process_article(self, session: Session, article_id: str) -> dict[str, Any]:
        """Processes a single extracted article through event classification, company resolution, and product matching."""
        article = session.get(MarketArticle, article_id)
        if not article:
            raise ValueError(f"MarketArticle {article_id} not found")

        logger.info("Processing article intelligence for: %s", article.headline)

        # 1. Classify event with Bedrock / heuristic engine
        extracted = self.classifier.classify_article(
            headline=article.headline,
            body_text=article.body_text or article.summary or "",
            publisher=article.publisher,
        )

        if not extracted.is_relevant:
            article.ai_processed = True
            session.commit()
            return {"article_id": article_id, "is_relevant": False}

        # 2. Resolve company
        company = self.company_resolver.resolve_or_create_company(
            session=session,
            company_name=extracted.company_name,
            domain=extracted.company_domain,
            industry="Automotive",
            business_segment=extracted.business_segment,
            location=extracted.location,
            parent_company=extracted.parent_company,
        )

        # 3. Store MarketEvent
        event = MarketEvent(
            article_id=article.id,
            company_id=company.id,
            event_category=extracted.event_category,
            event_title=extracted.event_title,
            description=extracted.event_description,
            business_implication=extracted.business_implication,
            operational_problem=extracted.operational_problem,
            location=extracted.location,
            country=extracted.country,
            event_date=article.published_at or now(),
            supporting_evidence=extracted.supporting_evidence,
            confidence_score=extracted.confidence,
            raw_ai_payload=extracted.model_dump(),
        )
        session.add(event)
        session.flush()

        # 4. Match against Solwer Products and calculate explainable scores
        opportunities = self.product_matcher.evaluate_event_for_opportunities(
            session=session,
            event=event,
            company=company,
        )

        # 5. Check Watchlists
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
                    headline=f"Watchlist Alert: {company.company_name}",
                    summary=f"Monitored company {company.company_name} published news: {event.event_title}",
                    priority="high",
                    target_user_id=w.user_id,
                )
                session.add(w_alert)

        article.ai_processed = True
        session.commit()

        return {
            "article_id": article_id,
            "is_relevant": True,
            "company_name": company.company_name,
            "is_new_company": company.is_new,
            "event_category": event.event_category,
            "opportunities_generated": len(opportunities),
        }

    def process_all_pending_articles(self, session: Session, limit: int = 50) -> dict[str, int]:
        """Processes all unprocessed articles in the queue."""
        pending_articles = session.scalars(
            select(MarketArticle).where(MarketArticle.ai_processed == False).order_by(MarketArticle.created_at.desc()).limit(limit)
        ).all()

        processed_count = 0
        opportunities_count = 0

        for a in pending_articles:
            try:
                res = self.process_article(session, a.id)
                processed_count += 1
                opportunities_count += res.get("opportunities_generated", 0)
            except Exception as e:
                logger.error("Failed to process article %s: %s", a.id, e)
                continue

        return {"articles_processed": processed_count, "opportunities_generated": opportunities_count}
