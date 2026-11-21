from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class MarketSource(Base):
    __tablename__ = "market_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    homepage_url: Mapped[str] = mapped_column(Text, nullable=False)
    discovered_news_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    discovered_feed_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # automotive_news, association, government, logistics_fleet, oem, supplier, dealership, global
    industry: Mapped[str] = mapped_column(String(64), default="automotive", index=True)
    country: Mapped[str] = mapped_column(String(8), default="IN", index=True)
    language: Mapped[str] = mapped_column(String(8), default="en")

    ingestion_method: Mapped[str] = mapped_column(String(32), default="PLAYWRIGHT")  # PLAYWRIGHT, HTTP, RSS
    crawl_frequency_minutes: Mapped[int] = mapped_column(Integer, default=60)
    priority: Mapped[int] = mapped_column(Integer, default=2)  # 1=Highest (15-30m), 2=Standard (60m), 3=OEM/Press (2-4h), 4=Gov/Assoc (4-6h), 5=Low/Daily

    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    validation_status: Mapped[str] = mapped_column(String(32), default="pending", index=True)  # pending, validated, failed, restricted
    robots_policy_status: Mapped[str] = mapped_column(String(32), default="unknown")  # allowed, restricted, checked

    last_crawl_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_article_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    articles_discovered: Mapped[int] = mapped_column(Integer, default=0)
    articles_processed: Mapped[int] = mapped_column(Integer, default=0)
    failed_requests: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    # Relationships
    runs: Mapped[list["MarketSourceRun"]] = relationship("MarketSourceRun", back_populates="source", cascade="all, delete-orphan", order_by="MarketSourceRun.started_at.desc()")
    articles: Mapped[list["MarketArticle"]] = relationship("MarketArticle", back_populates="source", cascade="all, delete-orphan", order_by="MarketArticle.published_at.desc()")


class MarketSourceRun(Base):
    __tablename__ = "market_source_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("market_sources.id", ondelete="CASCADE"), nullable=False, index=True)
    run_type: Mapped[str] = mapped_column(String(32), default="scheduled")  # scheduled, manual, discovery, test
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)  # running, completed, partial, failed
    articles_discovered: Mapped[int] = mapped_column(Integer, default=0)
    articles_extracted: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source: Mapped["MarketSource"] = relationship("MarketSource", back_populates="runs")


class MarketArticle(Base):
    __tablename__ = "market_articles"
    __table_args__ = (
        UniqueConstraint("canonical_url", name="uq_market_article_canonical_url"),
        Index("ix_market_articles_content_hash", "content_hash"),
        Index("ix_market_articles_published_at", "published_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("market_sources.id", ondelete="CASCADE"), nullable=False, index=True)
    headline: Mapped[str] = mapped_column(String(500), nullable=False)
    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    publisher: Mapped[str] = mapped_column(String(255), nullable=False)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    article_category: Mapped[str | None] = mapped_column(String(100), nullable=True)

    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    version_count: Mapped[int] = mapped_column(Integer, default=1)

    extraction_status: Mapped[str] = mapped_column(String(32), default="extracted", index=True)  # discovered, extracted, parsed, failed
    ai_processed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    source: Mapped["MarketSource"] = relationship("MarketSource", back_populates="articles")
    versions: Mapped[list["MarketArticleVersion"]] = relationship("MarketArticleVersion", back_populates="article", cascade="all, delete-orphan", order_by="MarketArticleVersion.version_number.desc()")
    events: Mapped[list["MarketEvent"]] = relationship("MarketEvent", back_populates="article", cascade="all, delete-orphan")


class MarketArticleVersion(Base):
    __tablename__ = "market_article_versions"
    __table_args__ = (
        UniqueConstraint("article_id", "version_number", name="uq_article_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    article_id: Mapped[str] = mapped_column(ForeignKey("market_articles.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    headline: Mapped[str] = mapped_column(String(500), nullable=False)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    diff_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    article: Mapped["MarketArticle"] = relationship("MarketArticle", back_populates="versions")


class MarketCompany(Base):
    __tablename__ = "market_companies"
    __table_args__ = (
        Index("ix_market_companies_domain", "domain"),
        Index("ix_market_companies_normalized_name", "normalized_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    industry: Mapped[str] = mapped_column(String(100), default="Automotive")
    business_segment: Mapped[str | None] = mapped_column(String(100), nullable=True)  # oem, supplier, logistics_fleet, dealership_aftermarket, manufacturing
    country: Mapped[str] = mapped_column(String(8), default="IN")
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parent_company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    aliases: Mapped[list] = mapped_column(JSON, default=list)

    # CRM linkage
    is_new: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    gtm_lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True)
    match_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    approval_status: Mapped[str] = mapped_column(String(32), default="pending_review", index=True)  # matched_existing, pending_review, approved, dismissed
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    events: Mapped[list["MarketEvent"]] = relationship("MarketEvent", back_populates="company", cascade="all, delete-orphan")
    opportunities: Mapped[list["OpportunitySignal"]] = relationship("OpportunitySignal", back_populates="company", cascade="all, delete-orphan")


class MarketEvent(Base):
    __tablename__ = "market_events"
    __table_args__ = (
        Index("ix_market_events_category", "event_category"),
        Index("ix_market_events_date", "event_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    article_id: Mapped[str] = mapped_column(ForeignKey("market_articles.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("market_companies.id", ondelete="CASCADE"), nullable=False, index=True)

    event_category: Mapped[str] = mapped_column(String(100), nullable=False)  # manufacturing_expansion, warehouse_expansion, fleet_expansion, dealership_expansion, investment_contract, sustainability_regulation
    event_title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    business_implication: Mapped[str | None] = mapped_column(Text, nullable=True)
    operational_problem: Mapped[str | None] = mapped_column(Text, nullable=True)

    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str] = mapped_column(String(8), default="IN")
    event_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    supporting_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.85)
    raw_ai_payload: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    article: Mapped["MarketArticle"] = relationship("MarketArticle", back_populates="events")
    company: Mapped["MarketCompany"] = relationship("MarketCompany", back_populates="events")
    opportunities: Mapped[list["OpportunitySignal"]] = relationship("OpportunitySignal", back_populates="event", cascade="all, delete-orphan")


class ProductCatalog(Base):
    __tablename__ = "product_catalogs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)  # TWMS, LOSS_TRACKER_IM, VDI, FLEET_MGMT, MCE, CARBON_MGMT
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    official_url: Mapped[str] = mapped_column(Text, nullable=False)
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    business_area: Mapped[str] = mapped_column(String(100), nullable=False)  # Logistics, Manufacturing, Fleet & Mobility, Aftermarket, ESG

    features: Mapped[list] = mapped_column(JSON, default=list)
    problems_solved: Mapped[list] = mapped_column(JSON, default=list)
    target_industries: Mapped[list] = mapped_column(JSON, default=list)
    target_company_segments: Mapped[list] = mapped_column(JSON, default=list)
    potential_buyer_roles: Mapped[list] = mapped_column(JSON, default=list)
    relevant_business_events: Mapped[list] = mapped_column(JSON, default=list)

    priority: Mapped[int] = mapped_column(Integer, default=1)  # 1=Strategic Priority, 2=Standard, 3=Secondary
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    matching_weights: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    rules: Mapped[list["ProductMatchRule"]] = relationship("ProductMatchRule", back_populates="product", cascade="all, delete-orphan")
    opportunities: Mapped[list["OpportunitySignal"]] = relationship("OpportunitySignal", back_populates="product", cascade="all, delete-orphan")


class ProductMatchRule(Base):
    __tablename__ = "product_match_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    product_id: Mapped[str] = mapped_column(ForeignKey("product_catalogs.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    event_categories: Mapped[list] = mapped_column(JSON, default=list)
    positive_keywords: Mapped[list] = mapped_column(JSON, default=list)
    negative_keywords: Mapped[list] = mapped_column(JSON, default=list)
    industry_filters: Mapped[list] = mapped_column(JSON, default=list)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    product: Mapped["ProductCatalog"] = relationship("ProductCatalog", back_populates="rules")


class OpportunitySignal(Base):
    __tablename__ = "opportunity_signals"
    __table_args__ = (
        Index("ix_opportunity_signals_scores", "market_signal_score", "sales_readiness_score"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("market_events.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("market_companies.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("product_catalogs.id", ondelete="CASCADE"), nullable=False, index=True)

    # Explainable Dual Scoring
    market_signal_score: Mapped[float] = mapped_column(Float, nullable=False)  # 0 to 100
    sales_readiness_score: Mapped[float] = mapped_column(Float, nullable=False)  # 0 to 100
    score_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    score_explanation: Mapped[str] = mapped_column(Text, nullable=False)

    suggested_buyer_roles: Mapped[list] = mapped_column(JSON, default=list)
    suggested_next_action: Mapped[str] = mapped_column(Text, nullable=False)

    priority_level: Mapped[str] = mapped_column(String(20), default="medium", index=True)  # high, medium, low
    review_status: Mapped[str] = mapped_column(String(32), default="new", index=True)  # new, reviewed, approved, dismissed, converted
    assigned_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    event: Mapped["MarketEvent"] = relationship("MarketEvent", back_populates="opportunities")
    company: Mapped["MarketCompany"] = relationship("MarketCompany", back_populates="opportunities")
    product: Mapped["ProductCatalog"] = relationship("ProductCatalog", back_populates="opportunities")
    alerts: Mapped[list["MarketAlert"]] = relationship("MarketAlert", back_populates="opportunity", cascade="all, delete-orphan")


class MarketAlert(Base):
    __tablename__ = "market_alerts"
    __table_args__ = (
        Index("ix_market_alerts_is_read", "is_read"),
        Index("ix_market_alerts_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunity_signals.id", ondelete="CASCADE"), nullable=False, index=True)
    alert_type: Mapped[str] = mapped_column(String(64), default="high_priority_opportunity")  # high_priority_opportunity, existing_lead_update, new_company_discovered, watchlist_update
    headline: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="high")  # high, medium, low

    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    is_dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    target_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    opportunity: Mapped["OpportunitySignal"] = relationship("OpportunitySignal", back_populates="alerts")


class CompanyWatchlist(Base):
    __tablename__ = "company_watchlists"
    __table_args__ = (
        UniqueConstraint("user_id", "company_domain", name="uq_watchlist_user_domain"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    company_domain: Mapped[str] = mapped_column(String(255), nullable=False)
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"), nullable=True)
    notify_on_events: Mapped[list] = mapped_column(JSON, default=list)  # all, investments, expansion, logistics, manufacturing
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class MarketFeedback(Base):
    __tablename__ = "market_feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunity_signals.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    feedback_type: Mapped[str] = mapped_column(String(50), nullable=False)  # relevant, irrelevant, already_known, wrong_company, wrong_product, converted
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class MarketWebhookSubscription(Base):
    __tablename__ = "market_webhook_subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), default="Sales Alert Webhook")
    target_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    secret_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    events: Mapped[list] = mapped_column(JSON, default=lambda: ["high_priority_opportunity", "new_company_discovered", "existing_lead_update"])
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
