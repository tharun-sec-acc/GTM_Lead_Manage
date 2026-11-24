import { getApiBase } from "./api-config";

export const API = getApiBase();

export interface MarketIntelligenceOverview {
  signals_today: number;
  signals_this_week: number;
  total_articles: number;
  high_priority_opportunities: number;
  existing_companies_with_news: number;
  new_companies_discovered: number;
  pending_approvals: number;
  opportunities_by_product: Record<string, number>;
  opportunities_by_category: Record<string, number>;
  sources_total: number;
  sources_active: number;
  sources_validated: number;
  sources_failed: number;
  last_crawl_time: string | null;
}

export interface MarketArticleItem {
  id: string;
  headline: string;
  original_url: string;
  canonical_url: string;
  publisher: string;
  author?: string | null;
  published_at?: string | null;
  summary?: string | null;
  body_preview?: string | null;
  content_hash: string;
  version_count: number;
  source_id: string;
  source_name?: string | null;
  ai_processed: boolean;
  created_at: string;
}

export interface OpportunitySignalItem {
  id: string;
  event_id: string;
  event_title: string;
  event_category: string;
  event_description?: string | null;
  operational_problem?: string | null;
  business_implication?: string | null;
  location?: string | null;
  article_headline?: string | null;
  article_publisher?: string | null;
  article_url?: string | null;
  company_id: string;
  company_name: string;
  company_domain?: string | null;
  is_new_company: boolean;
  gtm_lead_id?: string | null;
  product_id: string;
  product_code: string;
  product_name: string;
  market_signal_score: number;
  sales_readiness_score: number;
  score_breakdown: Record<string, number>;
  score_explanation: string;
  suggested_buyer_roles: string[];
  suggested_next_action: string;
  priority_level: "high" | "medium" | "low";
  review_status: string;
  created_at: string;
}

export interface DiscoveredCompanyItem {
  id: string;
  company_name: string;
  normalized_name: string;
  domain?: string | null;
  industry: string;
  business_segment?: string | null;
  country: string;
  location?: string | null;
  is_new: boolean;
  gtm_lead_id?: string | null;
  match_confidence: number;
  approval_status: string;
  events_count: number;
  opportunities_count: number;
  created_at: string;
}

export interface MarketSourceItem {
  id: string;
  name: string;
  domain: string;
  homepage_url: string;
  discovered_news_url?: string | null;
  discovered_feed_url?: string | null;
  source_category: string;
  industry: string;
  country: string;
  ingestion_method: string;
  crawl_frequency_minutes: number;
  priority: number;
  enabled: boolean;
  validation_status: string;
  last_crawl_at?: string | null;
  last_success_at?: string | null;
  articles_discovered: number;
  articles_processed: number;
  failed_requests: number;
  last_error?: string | null;
  created_at: string;
}

export interface MarketAlertItem {
  id: string;
  opportunity_id: string;
  alert_type: string;
  headline: string;
  summary: string;
  priority: string;
  is_read: boolean;
  is_dismissed: boolean;
  read_at?: string | null;
  created_at: string;
}

export interface ProductCatalogItem {
  id: string;
  code: string;
  name: string;
  official_url: string;
  business_area: string;
  priority: number;
  is_active: boolean;
  description: string;
  features: string[];
  problems_solved: string[];
  target_industries: string[];
  potential_buyer_roles: string[];
}

export interface WatchlistItem {
  id: string;
  company_name: string;
  company_domain: string;
  lead_id?: string | null;
  notify_on_events: string[];
  is_active: boolean;
  created_at: string;
}

export async function fetchMarketOverview(): Promise<MarketIntelligenceOverview> {
  const res = await fetch(`${API}/api/market-intelligence/overview`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch market overview");
  return res.json();
}

export async function fetchMarketFeed(category?: string, search?: string): Promise<MarketArticleItem[]> {
  const params = new URLSearchParams();
  if (category && category !== "all") params.set("source_category", category);
  if (search) params.set("search", search);
  const res = await fetch(`${API}/api/market-intelligence/feed?${params.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch market feed");
  return res.json();
}

export async function fetchOpportunities(
  product?: string,
  priority?: string,
  companyStatus?: string,
  companyName?: string,
  leadId?: string,
  limit: number = 200,
): Promise<OpportunitySignalItem[]> {
  const params = new URLSearchParams();
  if (product && product !== "all") params.set("product", product);
  if (priority && priority !== "all") params.set("priority", priority);
  if (companyStatus && companyStatus !== "all") params.set("company_status", companyStatus);
  if (companyName) params.set("company_name", companyName);
  if (leadId) params.set("lead_id", leadId);
  params.set("limit", String(limit));
  const res = await fetch(`${API}/api/market-intelligence/opportunities?${params.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch opportunities");
  return res.json();
}

export async function approveOpportunity(id: string): Promise<{ message: string }> {
  const res = await fetch(`${API}/api/market-intelligence/opportunities/${id}/approve`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to approve opportunity");
  return res.json();
}

export async function dismissOpportunity(id: string): Promise<{ message: string }> {
  const res = await fetch(`${API}/api/market-intelligence/opportunities/${id}/dismiss`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to dismiss opportunity");
  return res.json();
}

export async function fetchDiscoveredCompanies(statusFilter?: string): Promise<DiscoveredCompanyItem[]> {
  const params = new URLSearchParams();
  if (statusFilter && statusFilter !== "all") params.set("status_filter", statusFilter);
  const res = await fetch(`${API}/api/market-intelligence/companies?${params.toString()}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch companies");
  return res.json();
}

export async function approveDiscoveredCompany(id: string): Promise<{ message: string; lead_id?: string }> {
  const res = await fetch(`${API}/api/market-intelligence/companies/${id}/approve`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to approve company");
  return res.json();
}

export async function dismissDiscoveredCompany(id: string): Promise<{ message: string }> {
  const res = await fetch(`${API}/api/market-intelligence/companies/${id}/dismiss`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to dismiss company");
  return res.json();
}

export async function fetchSources(): Promise<MarketSourceItem[]> {
  const res = await fetch(`${API}/api/market-intelligence/sources`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch sources");
  return res.json();
}

export async function testSourceDiscovery(sourceId: string): Promise<any> {
  const res = await fetch(`${API}/api/market-intelligence/sources/${sourceId}/test`, { method: "POST" });
  if (!res.ok) throw new Error("Source discovery test failed");
  return res.json();
}

export async function crawlSourceNow(sourceId: string): Promise<any> {
  const res = await fetch(`${API}/api/market-intelligence/sources/${sourceId}/crawl`, { method: "POST" });
  if (!res.ok) throw new Error("Crawl trigger failed");
  return res.json();
}

export async function updateSourceConfig(sourceId: string, update: Partial<MarketSourceItem>): Promise<MarketSourceItem> {
  const res = await fetch(`${API}/api/market-intelligence/sources/${sourceId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(update),
  });
  if (!res.ok) throw new Error("Failed to update source configuration");
  return res.json();
}

export async function fetchMarketAlerts(unreadOnly: boolean = false): Promise<MarketAlertItem[]> {
  const res = await fetch(`${API}/api/market-intelligence/alerts?unread_only=${unreadOnly}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch market alerts");
  return res.json();
}

export async function markAlertRead(alertId: string): Promise<{ message: string }> {
  const res = await fetch(`${API}/api/market-intelligence/alerts/${alertId}/read`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to mark alert as read");
  return res.json();
}

export async function dismissAlert(alertId: string): Promise<{ message: string }> {
  const res = await fetch(`${API}/api/market-intelligence/alerts/${alertId}/dismiss`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to dismiss alert");
  return res.json();
}

export async function fetchProductCatalog(): Promise<ProductCatalogItem[]> {
  const res = await fetch(`${API}/api/market-intelligence/products`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch product catalog");
  return res.json();
}

export async function fetchWatchlists(): Promise<WatchlistItem[]> {
  const res = await fetch(`${API}/api/market-intelligence/watchlists`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch watchlists");
  return res.json();
}

export async function createWatchlist(name: string, domain: string, leadId?: string): Promise<WatchlistItem> {
  const res = await fetch(`${API}/api/market-intelligence/watchlists`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ company_name: name, company_domain: domain, lead_id: leadId }),
  });
  if (!res.ok) throw new Error("Failed to add company to watchlist");
  return res.json();
}

export async function deleteWatchlist(id: string): Promise<{ message: string }> {
  const res = await fetch(`${API}/api/market-intelligence/watchlists/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete watchlist entry");
  return res.json();
}

// ---------------------------------------------------------------------------
// Webhook & Automated Notification Flow
// ---------------------------------------------------------------------------

export interface MarketWebhookInboundPayload {
  headline: string;
  body_text?: string;
  url?: string;
  publisher?: string;
  author?: string;
  company_name?: string;
  domain?: string;
  event_category?: string;
  secret_token?: string;
}

export interface MarketWebhookResponse {
  status: string;
  notification_triggered: boolean;
  message: string;
  article_id: string;
  event_id: string;
  company: {
    id: string;
    company_name: string;
    domain: string | null;
    is_new: boolean;
    approval_status: string;
  };
  opportunities_count: number;
  opportunities: Array<{
    id: string;
    product_code: string;
    product_name: string;
    market_signal_score: number;
    sales_readiness_score: number;
    priority_level: string;
    suggested_next_action: string;
  }>;
  alerts_count: number;
  alerts: Array<{
    id: string;
    headline: string;
    summary: string;
    priority: string;
  }>;
  outbound_dispatches: Array<{
    subscription_id: string;
    target_url: string;
    status_code: number;
    success: boolean;
    error?: string;
  }>;
}

export interface MarketWebhookSubscriptionItem {
  id: string;
  name: string;
  target_url: string;
  secret_token?: string | null;
  events: string[];
  is_active: boolean;
  last_dispatched_at?: string | null;
  last_status_code?: number | null;
  last_error?: string | null;
  created_at: string;
}

export interface MarketWebhookSubscriptionCreate {
  name: string;
  target_url: string;
  secret_token?: string;
  events?: string[];
  is_active?: boolean;
}

export async function triggerMarketWebhook(payload: MarketWebhookInboundPayload): Promise<MarketWebhookResponse> {
  const res = await fetch(`${API}/api/market-intelligence/webhook`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errorBody = await res.text();
    throw new Error(`Webhook trigger failed: ${errorBody || res.statusText}`);
  }
  return res.json();
}

export async function fetchMarketWebhooks(): Promise<MarketWebhookSubscriptionItem[]> {
  const res = await fetch(`${API}/api/market-intelligence/webhooks`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch webhook subscriptions");
  return res.json();
}

export async function createMarketWebhook(payload: MarketWebhookSubscriptionCreate): Promise<MarketWebhookSubscriptionItem> {
  const res = await fetch(`${API}/api/market-intelligence/webhooks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Failed to create webhook subscription");
  return res.json();
}

export async function deleteMarketWebhook(subscriptionId: string): Promise<{ message: string }> {
  const res = await fetch(`${API}/api/market-intelligence/webhooks/${subscriptionId}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete webhook subscription");
  return res.json();
}

export async function testMarketWebhook(payload: { target_url: string; secret_token?: string }): Promise<any> {
  const res = await fetch(`${API}/api/market-intelligence/webhooks/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Webhook test ping failed");
  return res.json();
}

