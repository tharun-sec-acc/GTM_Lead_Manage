from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


class MarketSourceResponse(BaseModel):
    id: str
    name: str
    domain: str
    homepage_url: str
    discovered_news_url: Optional[str] = None
    discovered_feed_url: Optional[str] = None
    source_category: str
    industry: str
    country: str
    ingestion_method: str
    crawl_frequency_minutes: int
    priority: int
    enabled: bool
    validation_status: str
    last_crawl_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    articles_discovered: int
    articles_processed: int
    failed_requests: int
    last_error: Optional[str] = None
    created_at: datetime


class MarketSourceUpdate(BaseModel):
    enabled: Optional[bool] = None
    crawl_frequency_minutes: Optional[int] = None
    priority: Optional[int] = None
    source_category: Optional[str] = None
    industry: Optional[str] = None


class MarketArticleItem(BaseModel):
    id: str
    headline: str
    original_url: str
    canonical_url: str
    publisher: str
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    summary: Optional[str] = None
    body_preview: Optional[str] = None
    content_hash: str
    version_count: int
    source_id: str
    source_name: Optional[str] = None
    ai_processed: bool
    created_at: datetime


class MarketEventItem(BaseModel):
    id: str
    article_id: str
    company_id: str
    company_name: str
    company_domain: Optional[str] = None
    is_new_company: bool
    event_category: str
    event_title: str
    description: str
    business_implication: Optional[str] = None
    operational_problem: Optional[str] = None
    location: Optional[str] = None
    country: str
    event_date: Optional[datetime] = None
    supporting_evidence: Optional[str] = None
    confidence_score: float
    created_at: datetime


class ProductCatalogItem(BaseModel):
    id: str
    code: str
    name: str
    official_url: str
    business_area: str
    priority: int
    is_active: bool
    description: str
    features: list[str] = []
    problems_solved: list[str] = []
    target_industries: list[str] = []
    potential_buyer_roles: list[str] = []


class OpportunitySignalItem(BaseModel):
    id: str
    event_id: str
    event_title: str
    event_category: str
    event_description: Optional[str] = None
    operational_problem: Optional[str] = None
    business_implication: Optional[str] = None
    location: Optional[str] = None
    article_headline: Optional[str] = None
    article_publisher: Optional[str] = None
    article_url: Optional[str] = None
    company_id: str
    company_name: str
    company_domain: Optional[str] = None
    is_new_company: bool
    gtm_lead_id: Optional[str] = None
    product_id: str
    product_code: str
    product_name: str
    market_signal_score: float
    sales_readiness_score: float
    score_breakdown: dict[str, Any] = {}
    score_explanation: str
    suggested_buyer_roles: list[str] = []
    suggested_next_action: str
    priority_level: str
    review_status: str
    created_at: datetime


class DiscoveredCompanyItem(BaseModel):
    id: str
    company_name: str
    normalized_name: str
    domain: Optional[str] = None
    industry: str
    business_segment: Optional[str] = None
    country: str
    location: Optional[str] = None
    is_new: bool
    gtm_lead_id: Optional[str] = None
    match_confidence: float
    approval_status: str
    events_count: int
    opportunities_count: int
    created_at: datetime


class MarketAlertItem(BaseModel):
    id: str
    opportunity_id: str
    alert_type: str
    headline: str
    summary: str
    priority: str
    is_read: bool
    is_dismissed: bool
    read_at: Optional[datetime] = None
    created_at: datetime


class MarketIntelligenceOverview(BaseModel):
    signals_today: int
    signals_this_week: int
    total_articles: int
    high_priority_opportunities: int
    existing_companies_with_news: int
    new_companies_discovered: int
    pending_approvals: int
    opportunities_by_product: dict[str, int]
    opportunities_by_category: dict[str, int]
    sources_total: int
    sources_active: int
    sources_validated: int
    sources_failed: int
    last_crawl_time: Optional[datetime] = None


class WatchlistCreate(BaseModel):
    company_name: str
    company_domain: str
    lead_id: Optional[str] = None
    notify_on_events: list[str] = Field(default_factory=lambda: ["all"])


class WatchlistItem(BaseModel):
    id: str
    company_name: str
    company_domain: str
    lead_id: Optional[str] = None
    notify_on_events: list[str] = []
    is_active: bool
    created_at: datetime


class MarketWebhookInboundPayload(BaseModel):
    headline: str
    body_text: Optional[str] = None
    url: Optional[str] = None
    publisher: Optional[str] = "Market Intelligence Inbound Webhook"
    author: Optional[str] = None
    company_name: Optional[str] = None
    domain: Optional[str] = None
    event_category: Optional[str] = None
    secret_token: Optional[str] = None


class MarketWebhookSubscriptionCreate(BaseModel):
    name: str = "Sales Alert Webhook"
    target_url: str
    secret_token: Optional[str] = None
    events: list[str] = Field(default_factory=lambda: ["high_priority_opportunity", "new_company_discovered", "existing_lead_update"])
    is_active: bool = True


class MarketWebhookSubscriptionItem(BaseModel):
    id: str
    name: str
    target_url: str
    secret_token: Optional[str] = None
    events: list[str] = []
    is_active: bool
    last_dispatched_at: Optional[datetime] = None
    last_status_code: Optional[int] = None
    last_error: Optional[str] = None
    created_at: datetime


class MarketWebhookTestPayload(BaseModel):
    target_url: str
    secret_token: Optional[str] = None

