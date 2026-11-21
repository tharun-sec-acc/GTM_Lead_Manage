"use client";

import React, { useEffect, useState } from "react";
import UiIcon from "../../components/ui-icon";
import {
  fetchMarketOverview,
  fetchMarketFeed,
  fetchOpportunities,
  approveOpportunity,
  dismissOpportunity,
  fetchDiscoveredCompanies,
  approveDiscoveredCompany,
  dismissDiscoveredCompany,
  fetchSources,
  testSourceDiscovery,
  crawlSourceNow,
  fetchMarketAlerts,
  markAlertRead,
  dismissAlert,
  fetchWatchlists,
  createWatchlist,
  deleteWatchlist,
  fetchProductCatalog,
  fetchMarketWebhooks,
  createMarketWebhook,
  deleteMarketWebhook,
  testMarketWebhook,
  triggerMarketWebhook,
  type MarketIntelligenceOverview,
  type MarketArticleItem,
  type OpportunitySignalItem,
  type DiscoveredCompanyItem,
  type MarketSourceItem,
  type MarketAlertItem,
  type WatchlistItem,
  type ProductCatalogItem,
  type MarketWebhookSubscriptionItem,
  type MarketWebhookResponse,
} from "../../lib/market-intelligence";

export default function MarketIntelligencePage() {
  const [activeTab, setActiveTab] = useState<"overview" | "feed" | "opportunities" | "companies" | "sources" | "watchlists" | "alerts">("overview");

  // State
  const [overview, setOverview] = useState<MarketIntelligenceOverview | null>(null);
  const [articles, setArticles] = useState<MarketArticleItem[]>([]);
  const [opportunities, setOpportunities] = useState<OpportunitySignalItem[]>([]);
  const [companies, setCompanies] = useState<DiscoveredCompanyItem[]>([]);
  const [sources, setSources] = useState<MarketSourceItem[]>([]);
  const [alerts, setAlerts] = useState<MarketAlertItem[]>([]);
  const [watchlists, setWatchlists] = useState<WatchlistItem[]>([]);
  const [products, setProducts] = useState<ProductCatalogItem[]>([]);

  // Webhooks & Simulator State
  const [webhookSubs, setWebhookSubs] = useState<MarketWebhookSubscriptionItem[]>([]);
  const [webhookModalOpen, setWebhookModalOpen] = useState(false);
  const [webhookSubmitting, setWebhookSubmitting] = useState(false);
  const [webhookResult, setWebhookResult] = useState<MarketWebhookResponse | null>(null);
  const [newSubName, setNewSubName] = useState("");
  const [newSubUrl, setNewSubUrl] = useState("");
  const [newSubSecret, setNewSubSecret] = useState("");
  const [addingSub, setAddingSub] = useState(false);
  const [pingStatus, setPingStatus] = useState<Record<string, { status: string; loading?: boolean }>>({});

  // Simulation Presets
  const simulationPresets = [
    {
      label: "Tata Motors TWMS 12-Plant Tender",
      headline: "Tata Motors Commercial Vehicles floats ₹250 Cr tender for nationwide TWMS yard and warehouse management",
      company_name: "Tata Motors Commercial Vehicles",
      domain: "tatamotors.com",
      event_category: "warehouse_expansion",
      publisher: "Automotive Procurement Daily",
      body_text: "Tata Motors is procuring automated transport and warehouse management software across 12 assembly and regional depot locations in India to automate yard check-in, dispatch, and dock scheduling.",
    },
    {
      label: "Mahindra Chakan Loss Tracker & OEE Expansion",
      headline: "Mahindra & Mahindra invests ₹400 Cr at Chakan plant deploying smart factory loss tracking and OEE Kaizen",
      company_name: "Mahindra & Mahindra Chakan Plant",
      domain: "mahindra.com",
      event_category: "manufacturing_expansion",
      publisher: "Manufacturing Automation Review",
      body_text: "Mahindra & Mahindra Ltd is upgrading Chakan assembly lines with real-time scrap reduction, downtime classification, and OEE visibility dashboards to eliminate bottleneck losses.",
    },
    {
      label: "Delhivery 2,500 EV Trucks VDI Inspection",
      headline: "Delhivery adds 2,500 commercial electric vehicles requiring digital vehicle condition and pre-trip checklists",
      company_name: "Delhivery Logistics",
      domain: "delhivery.com",
      event_category: "fleet_expansion",
      publisher: "Logistics Fleet Express",
      body_text: "Delhivery is expanding its express parcel fleet by 2,500 EV trucks and requires smartphone-based digital vehicle inspections, tire and body defect detection, and automated maintenance tickets.",
    },
    {
      label: "Ashok Leyland Decarbonization Carbon Footprint",
      headline: "Ashok Leyland commits to Net-Zero logistics emissions baseline and BRSR Scope 1-3 reporting",
      company_name: "Ashok Leyland Ltd",
      domain: "ashokleyland.com",
      event_category: "esg_netzero",
      publisher: "Clean Mobility India",
      body_text: "Ashok Leyland has launched a nationwide supply chain sustainability initiative to measure freight emissions, optimize inter-depot vehicle routes, and comply with SEBI BRSR Core decarbonization mandates.",
    },
  ];

  const [simPresetIdx, setSimPresetIdx] = useState(0);
  const [simHeadline, setSimHeadline] = useState(simulationPresets[0].headline);
  const [simCompany, setSimCompany] = useState(simulationPresets[0].company_name);
  const [simDomain, setSimDomain] = useState(simulationPresets[0].domain);
  const [simCategory, setSimCategory] = useState(simulationPresets[0].event_category);
  const [simPublisher, setSimPublisher] = useState(simulationPresets[0].publisher);
  const [simBody, setSimBody] = useState(simulationPresets[0].body_text);

  const applyPreset = (idx: number) => {
    setSimPresetIdx(idx);
    const p = simulationPresets[idx];
    setSimHeadline(p.headline);
    setSimCompany(p.company_name);
    setSimDomain(p.domain);
    setSimCategory(p.event_category);
    setSimPublisher(p.publisher);
    setSimBody(p.body_text);
    setWebhookResult(null);
  };

  // Intelligence Drilldown Modal (Click on any number to view news and where Solwer helps)
  const [drilldown, setDrilldown] = useState<{
    isOpen: boolean;
    type: "signals_today" | "high_priority" | "new_companies" | "product_opportunities";
    title: string;
    subtitle: string;
    product?: ProductCatalogItem;
    productOpportunities?: OpportunitySignalItem[];
  } | null>(null);

  // Filters & Loading
  const [loading, setLoading] = useState(true);
  const [feedCategory, setFeedCategory] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [productFilter, setProductFilter] = useState("all");
  const [priorityFilter, setPriorityFilter] = useState("all");
  const [companyStatusFilter, setCompanyStatusFilter] = useState("all");
  const [actionNotice, setActionNotice] = useState("");
  const [testingSourceId, setTestingSourceId] = useState<string | null>(null);
  const [crawlingSourceId, setCrawlingSourceId] = useState<string | null>(null);

  // Watchlist form
  const [watchName, setWatchName] = useState("");
  const [watchDomain, setWatchDomain] = useState("");
  const [addingWatch, setAddingWatch] = useState(false);

  const loadAll = async () => {
    try {
      setLoading(true);
      const [ov, art, opp, comp, src, al, wl, prod, subs] = await Promise.all([
        fetchMarketOverview().catch(() => null),
        fetchMarketFeed(feedCategory, searchQuery).catch(() => []),
        fetchOpportunities(productFilter, priorityFilter, companyStatusFilter, undefined, undefined, 200).catch(() => []),
        fetchDiscoveredCompanies().catch(() => []),
        fetchSources().catch(() => []),
        fetchMarketAlerts().catch(() => []),
        fetchWatchlists().catch(() => []),
        fetchProductCatalog().catch(() => []),
        fetchMarketWebhooks().catch(() => []),
      ]);

      setOverview(ov);
      setArticles(art);
      setOpportunities(opp);
      setCompanies(comp);
      setSources(src);
      setAlerts(al);
      setWatchlists(wl);
      setProducts(prod);
      setWebhookSubs(subs);
    } catch (err: any) {
      console.error("Error loading market intelligence:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, [feedCategory, productFilter, priorityFilter, companyStatusFilter]);

  const showNotice = (msg: string) => {
    setActionNotice(msg);
    setTimeout(() => setActionNotice(""), 4000);
  };

  const handleApproveOpp = async (id: string) => {
    try {
      await approveOpportunity(id);
      showNotice("Opportunity approved for sales outreach.");
      setOpportunities((prev) => prev.map((o) => (o.id === id ? { ...o, review_status: "approved" } : o)));
    } catch {
      alert("Failed to approve opportunity.");
    }
  };

  const handleDismissOpp = async (id: string) => {
    try {
      await dismissOpportunity(id);
      showNotice("Opportunity dismissed.");
      setOpportunities((prev) => prev.filter((o) => o.id !== id));
    } catch {
      alert("Failed to dismiss opportunity.");
    }
  };

  const handleApproveCompany = async (id: string) => {
    try {
      const res = await approveDiscoveredCompany(id);
      showNotice(res.message);
      setCompanies((prev) =>
        prev.map((c) => (c.id === id ? { ...c, approval_status: "approved", is_new: false, gtm_lead_id: res.lead_id } : c))
      );
    } catch {
      alert("Failed to approve company.");
    }
  };

  const handleDismissCompany = async (id: string) => {
    try {
      await dismissDiscoveredCompany(id);
      showNotice("Company dismissed.");
      setCompanies((prev) => prev.map((c) => (c.id === id ? { ...c, approval_status: "dismissed" } : c)));
    } catch {
      alert("Failed to dismiss company.");
    }
  };

  const handleTestSource = async (s: MarketSourceItem) => {
    try {
      setTestingSourceId(s.id);
      const res = await testSourceDiscovery(s.id);
      showNotice(`Source tested: status is ${res.validation_status}. News URL: ${res.discovered_news_url || "Homepage"}`);
      const updatedSources = await fetchSources();
      setSources(updatedSources);
    } catch (e: any) {
      alert(`Test failed: ${e?.message || e}`);
    } finally {
      setTestingSourceId(null);
    }
  };

  const handleCrawlSource = async (s: MarketSourceItem) => {
    try {
      setCrawlingSourceId(s.id);
      const res = await crawlSourceNow(s.id);
      showNotice(`Crawl completed! Discovered ${res.articles_discovered} links, extracted ${res.new_articles} new articles.`);
      loadAll();
    } catch (e: any) {
      alert(`Crawl failed: ${e?.message || e}`);
    } finally {
      setCrawlingSourceId(null);
    }
  };

  const handleMarkAlertRead = async (id: string) => {
    try {
      await markAlertRead(id);
      setAlerts((prev) => prev.map((a) => (a.id === id ? { ...a, is_read: true } : a)));
    } catch {
      // ignore
    }
  };

  const handleAddWatchlist = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!watchName || !watchDomain) return;
    try {
      setAddingWatch(true);
      const created = await createWatchlist(watchName, watchDomain);
      setWatchlists((prev) => [...prev, created]);
      setWatchName("");
      setWatchDomain("");
      showNotice(`Added ${created.company_name} to watchlist.`);
    } catch {
      alert("Failed to add to watchlist.");
    } finally {
      setAddingWatch(false);
    }
  };

  const handleTriggerSimulation = async () => {
    try {
      setWebhookSubmitting(true);
      const resp = await triggerMarketWebhook({
        headline: simHeadline,
        company_name: simCompany,
        domain: simDomain,
        event_category: simCategory,
        publisher: simPublisher,
        body_text: simBody,
      });
      setWebhookResult(resp);
      showNotice(`⚡ Webhook signal processed! ${resp.opportunities_count} opportunities & ${resp.alerts_count} alerts generated.`);
      await loadAll();
    } catch (err: any) {
      alert("Webhook trigger failed: " + err.message);
    } finally {
      setWebhookSubmitting(false);
    }
  };

  const handleAddSubscription = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSubUrl.trim()) return;
    try {
      setAddingSub(true);
      const created = await createMarketWebhook({
        name: newSubName.trim() || "Sales Alert Webhook",
        target_url: newSubUrl.trim(),
        secret_token: newSubSecret.trim() || undefined,
        events: ["high_priority_opportunity", "new_company_discovered", "existing_lead_update"],
      });
      setWebhookSubs((prev) => [created, ...prev]);
      setNewSubName("");
      setNewSubUrl("");
      setNewSubSecret("");
      showNotice("Webhook subscription registered successfully.");
    } catch (err: any) {
      alert("Failed to add webhook: " + err.message);
    } finally {
      setAddingSub(false);
    }
  };

  const handleDeleteSubscription = async (id: string) => {
    try {
      await deleteMarketWebhook(id);
      setWebhookSubs((prev) => prev.filter((s) => s.id !== id));
      showNotice("Webhook subscription removed.");
    } catch (err: any) {
      alert("Failed to delete webhook: " + err.message);
    }
  };

  const handleTestPing = async (sub: MarketWebhookSubscriptionItem) => {
    try {
      setPingStatus((prev) => ({ ...prev, [sub.id]: { status: "Pinging...", loading: true } }));
      const result = await testMarketWebhook({ target_url: sub.target_url, secret_token: sub.secret_token || undefined });
      if (result.success) {
        setPingStatus((prev) => ({ ...prev, [sub.id]: { status: `✓ 200 OK (${result.duration_ms}ms)` } }));
      } else {
        setPingStatus((prev) => ({ ...prev, [sub.id]: { status: `✗ Failed: ${result.error || `HTTP ${result.status_code}`}` } }));
      }
    } catch (err: any) {
      setPingStatus((prev) => ({ ...prev, [sub.id]: { status: `✗ Error: ${err.message}` } }));
    }
  };

  const unreadAlertsCount = alerts.filter((a) => !a.is_read).length;

  return (
    <div style={{ maxWidth: 1280, margin: "0 auto", padding: "20px 24px" }}>
        {/* Top Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20, flexWrap: "wrap", gap: 14 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <h1 style={{ margin: 0, fontSize: 26, color: "#0f172a", fontWeight: 700 }}>
                Automotive Market Intelligence &amp; Opportunity Detection
              </h1>
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 700,
                  textTransform: "uppercase",
                  background: "#dbeafe",
                  color: "#1d4ed8",
                  padding: "3px 10px",
                  borderRadius: 12,
                }}
              >
                Autonomous Radar
              </span>
            </div>
            <p style={{ margin: "6px 0 0", color: "#64748b", fontSize: 14 }}>
              Continuous monitoring across 62 Indian automotive, logistics, OEM, supplier, and dealership websites with explainable Solwer product opportunity scoring.
            </p>
          </div>

          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            {actionNotice && (
              <span style={{ fontSize: 13, background: "#ecfdf5", color: "#065f46", border: "1px solid #a7f3d0", padding: "6px 12px", borderRadius: 6, fontWeight: 600 }}>
                ✓ {actionNotice}
              </span>
            )}
            <button
              type="button"
              onClick={() => {
                setWebhookResult(null);
                setWebhookModalOpen(true);
              }}
              style={{
                padding: "8px 16px",
                borderRadius: 6,
                border: "none",
                background: "linear-gradient(135deg, #1e293b 0%, #0f172a 100%)",
                color: "#ffffff",
                fontSize: 13,
                fontWeight: 600,
                cursor: "pointer",
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
              }}
            >
              <span>⚡</span> Trigger Webhook Signal
            </button>
            <button
              type="button"
              onClick={loadAll}
              style={{
                padding: "8px 16px",
                borderRadius: 6,
                border: "1px solid #cbd5e1",
                background: "#ffffff",
                color: "#334155",
                fontSize: 13,
                fontWeight: 600,
                cursor: "pointer",
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              <UiIcon name="refresh" size={14} /> Refresh Radar
            </button>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div style={{ display: "flex", gap: 6, borderBottom: "1px solid #e2e8f0", marginBottom: 24, overflowX: "auto" }}>
          {[
            { key: "overview", label: "📊 Overview" },
            { key: "feed", label: `📰 Live Market Feed (${articles.length})` },
            { key: "opportunities", label: `🎯 Qualified Opportunities (${opportunities.length})` },
            { key: "companies", label: `🏢 Discovered Companies (${companies.length})` },
            { key: "sources", label: `🌐 Source Management (${sources.length})` },
            { key: "watchlists", label: `📌 Watchlists (${watchlists.length})` },
            { key: "alerts", label: `🔔 Notifications (${unreadAlertsCount} unread)` },
          ].map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveTab(tab.key as any)}
              style={{
                padding: "10px 18px",
                border: "none",
                background: "transparent",
                borderBottom: activeTab === tab.key ? "3px solid var(--red)" : "3px solid transparent",
                color: activeTab === tab.key ? "var(--red)" : "#475569",
                fontWeight: activeTab === tab.key ? 700 : 500,
                fontSize: 14,
                cursor: "pointer",
                whiteSpace: "nowrap",
                transition: "all 0.15s ease",
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* TAB 1: OVERVIEW */}
        {activeTab === "overview" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
            {/* 4 Stat Cards */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 16 }}>
              {/* Card 1: Signals Detected Today */}
              <div
                onClick={() =>
                  setDrilldown({
                    isOpen: true,
                    type: "signals_today",
                    title: `Signals & News Detected Today (${articles.length})`,
                    subtitle: "All market announcements, tenders, and business developments detected across monitored sources today.",
                  })
                }
                style={{
                  background: "#ffffff",
                  borderRadius: 10,
                  border: "1px solid #e2e8f0",
                  padding: "18px 20px",
                  boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
                  cursor: "pointer",
                  transition: "transform 0.15s ease, box-shadow 0.15s ease",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: "#64748b", textTransform: "uppercase" }}>Signals Detected Today</span>
                  <span style={{ fontSize: 11, fontWeight: 700, color: "#2563eb", background: "#eff6ff", padding: "1px 6px", borderRadius: 4 }}>
                    Click to view news &rarr;
                  </span>
                </div>
                <div style={{ fontSize: 28, fontWeight: 800, color: "#0f172a", marginTop: 4 }}>
                  {overview?.signals_today ?? 0}
                </div>
                <small style={{ color: "#16a34a", fontWeight: 600 }}>Autonomous real-time updates</small>
              </div>

              {/* Card 2: High-Priority Opportunities */}
              <div
                onClick={() =>
                  setDrilldown({
                    isOpen: true,
                    type: "high_priority",
                    title: `High-Priority Qualified Opportunities (${opportunities.filter((o) => o.priority_level === "high").length})`,
                    subtitle: "Opportunities scored ≥ 80/100 readiness where Solwer products solve active operational problems.",
                  })
                }
                style={{
                  background: "#ffffff",
                  borderRadius: 10,
                  border: "1px solid #fecaca",
                  padding: "18px 20px",
                  boxShadow: "0 1px 3px rgba(225,29,72,0.08)",
                  cursor: "pointer",
                  transition: "transform 0.15s ease, box-shadow 0.15s ease",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: "#64748b", textTransform: "uppercase" }}>High-Priority Opportunities</span>
                  <span style={{ fontSize: 11, fontWeight: 700, color: "var(--red)", background: "#fff1f2", padding: "1px 6px", borderRadius: 4 }}>
                    Click to view &rarr;
                  </span>
                </div>
                <div style={{ fontSize: 28, fontWeight: 800, color: "var(--red)", marginTop: 4 }}>
                  {overview?.high_priority_opportunities ?? 0}
                </div>
                <small style={{ color: "#475569" }}>Scored &ge; 80/100 readiness</small>
              </div>

              {/* Card 3: New Companies Discovered */}
              <div
                onClick={() =>
                  setDrilldown({
                    isOpen: true,
                    type: "new_companies",
                    title: `Newly Discovered Companies (${companies.filter((c) => c.is_new).length})`,
                    subtitle: "Companies identified through news signals, tenders, or plant expansions that are not yet in CRM.",
                  })
                }
                style={{
                  background: "#ffffff",
                  borderRadius: 10,
                  border: "1px solid #bae6fd",
                  padding: "18px 20px",
                  boxShadow: "0 1px 3px rgba(2,132,199,0.08)",
                  cursor: "pointer",
                  transition: "transform 0.15s ease, box-shadow 0.15s ease",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: "#64748b", textTransform: "uppercase" }}>New Companies Discovered</span>
                  <span style={{ fontSize: 11, fontWeight: 700, color: "#0284c7", background: "#f0f9ff", padding: "1px 6px", borderRadius: 4 }}>
                    Click to view &rarr;
                  </span>
                </div>
                <div style={{ fontSize: 28, fontWeight: 800, color: "#0284c7", marginTop: 4 }}>
                  {overview?.new_companies_discovered ?? 0}
                </div>
                <small style={{ color: "#0369a1" }}>Pending sales verification: {overview?.pending_approvals ?? 0}</small>
              </div>

              {/* Card 4: Monitored Sources Active */}
              <div
                onClick={() => setActiveTab("sources")}
                style={{
                  background: "#ffffff",
                  borderRadius: 10,
                  border: "1px solid #bbf7d0",
                  padding: "18px 20px",
                  boxShadow: "0 1px 3px rgba(22,163,74,0.08)",
                  cursor: "pointer",
                  transition: "transform 0.15s ease, box-shadow 0.15s ease",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: "#64748b", textTransform: "uppercase" }}>Monitored Sources Active</span>
                  <span style={{ fontSize: 11, fontWeight: 700, color: "#16a34a", background: "#f0fdf4", padding: "1px 6px", borderRadius: 4 }}>
                    Manage sources &rarr;
                  </span>
                </div>
                <div style={{ fontSize: 28, fontWeight: 800, color: "#16a34a", marginTop: 4 }}>
                  {overview?.sources_active ?? 60} / {overview?.sources_total ?? 62}
                </div>
                <small style={{ color: "#475569" }}>All 62 Indian websites configured</small>
              </div>
            </div>

            {/* Solwer Product Opportunities Grid */}
            <div style={{ background: "#ffffff", borderRadius: 12, border: "1px solid #e2e8f0", padding: 22, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                <div>
                  <h3 style={{ margin: 0, fontSize: 17, color: "#0f172a" }}>Opportunities by Solwer Product</h3>
                  <small style={{ color: "#64748b" }}>Click on any product number or card to inspect the matching news and where Solwer directly helps.</small>
                </div>
                <button
                  type="button"
                  onClick={() => setActiveTab("opportunities")}
                  style={{ fontSize: 13, color: "var(--red)", background: "transparent", border: "none", fontWeight: 700, cursor: "pointer" }}
                >
                  View All Qualified Opportunities &rarr;
                </button>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 14 }}>
                {products.map((p) => {
                  const count = overview?.opportunities_by_product[p.code] || 0;
                  const localOpps = opportunities.filter((o) => o.product_code === p.code);
                  return (
                    <div
                      key={p.id}
                      onClick={async () => {
                        setDrilldown({
                          isOpen: true,
                          type: "product_opportunities",
                          title: `${p.name} — News & Opportunity Breakdown`,
                          subtitle: `Showing ${count || localOpps.length} active market events where Solwer ${p.name} directly solves operational problems.`,
                          product: p,
                          productOpportunities: localOpps.length > 0 ? localOpps : undefined,
                        });
                        try {
                          const fetched = await fetchOpportunities(p.code, undefined, undefined, undefined, undefined, 100);
                          setDrilldown({
                            isOpen: true,
                            type: "product_opportunities",
                            title: `${p.name} — News & Opportunity Breakdown`,
                            subtitle: `Showing ${fetched.length} active market events where Solwer ${p.name} directly solves operational problems.`,
                            product: p,
                            productOpportunities: fetched,
                          });
                        } catch (err) {
                          console.error("Failed loading product opportunities:", err);
                        }
                      }}
                      style={{
                        padding: 16,
                        borderRadius: 10,
                        border: "1px solid #e2e8f0",
                        background: count > 0 ? "#f8fafc" : "#ffffff",
                        cursor: "pointer",
                        transition: "all 0.15s ease",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                        <span style={{ fontSize: 11, fontWeight: 700, color: "var(--red)", textTransform: "uppercase" }}>
                          {p.business_area}
                        </span>
                        <span
                          style={{
                            fontSize: 13,
                            fontWeight: 800,
                            background: count > 0 ? "#fee2e2" : "#f1f5f9",
                            color: count > 0 ? "var(--red)" : "#64748b",
                            padding: "3px 10px",
                            borderRadius: 12,
                            boxShadow: count > 0 ? "0 1px 2px rgba(225,29,72,0.15)" : "none",
                            cursor: "pointer",
                          }}
                        >
                          {count} {count === 1 ? "Opportunity" : "Opportunities"}
                        </span>
                      </div>
                      <strong style={{ fontSize: 15, color: "#0f172a", display: "block" }}>{p.name}</strong>
                      <p style={{ margin: "6px 0 0", fontSize: 12, color: "#64748b", lineHeight: 1.4 }}>
                        {p.description.slice(0, 100)}…
                      </p>
                      <div style={{ marginTop: 10, display: "flex", justifyContent: "flex-end" }}>
                        <span style={{ fontSize: 11, fontWeight: 700, color: "var(--red)" }}>
                          Click to view news &amp; where it helps &rarr;
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: LIVE MARKET FEED */}
        {activeTab === "feed" && (
          <div>
            {/* Feed Filters */}
            <div style={{ display: "flex", gap: 10, marginBottom: 20, flexWrap: "wrap", alignItems: "center" }}>
              <input
                type="text"
                placeholder="Search headlines or companies…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
                  padding: "8px 14px",
                  borderRadius: 8,
                  border: "1px solid #cbd5e1",
                  fontSize: 14,
                  minWidth: 260,
                }}
              />
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {[
                  { id: "all", label: "All Sources" },
                  { id: "automotive_news", label: "Auto News" },
                  { id: "logistics_fleet", label: "Logistics & Fleet" },
                  { id: "oem", label: "OEMs" },
                  { id: "supplier", label: "Suppliers" },
                  { id: "dealership", label: "Dealerships" },
                  { id: "association", label: "Associations" },
                  { id: "government", label: "Government/Tenders" },
                ].map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => setFeedCategory(c.id)}
                    style={{
                      padding: "6px 12px",
                      borderRadius: 20,
                      fontSize: 12,
                      fontWeight: 600,
                      border: feedCategory === c.id ? "1px solid var(--red)" : "1px solid #cbd5e1",
                      background: feedCategory === c.id ? "#fee2e2" : "#ffffff",
                      color: feedCategory === c.id ? "var(--red)" : "#475569",
                      cursor: "pointer",
                    }}
                  >
                    {c.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Articles Stream */}
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {articles.length === 0 ? (
                <div style={{ background: "#ffffff", padding: 36, textAlign: "center", borderRadius: 10, border: "1px solid #e2e8f0" }}>
                  <p style={{ margin: 0, color: "#64748b" }}>No articles found matching filters. Trigger a crawl from the Source Management tab.</p>
                </div>
              ) : (
                articles.map((art) => (
                  <div
                    key={art.id}
                    style={{
                      background: "#ffffff",
                      borderRadius: 10,
                      border: "1px solid #e2e8f0",
                      padding: "16px 20px",
                      boxShadow: "0 1px 3px rgba(0,0,0,0.03)",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6, gap: 12 }}>
                      <div>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                          <span style={{ fontSize: 11, fontWeight: 700, color: "#0284c7", background: "#e0f2fe", padding: "1px 8px", borderRadius: 6 }}>
                            {art.publisher}
                          </span>
                          <span style={{ fontSize: 12, color: "#64748b" }}>
                            {art.published_at ? new Date(art.published_at).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" }) : "Today"}
                          </span>
                        </div>
                        <h4 style={{ margin: 0, fontSize: 16, color: "#0f172a", fontWeight: 700 }}>
                          {art.headline}
                        </h4>
                      </div>
                      <a
                        href={art.canonical_url}
                        target="_blank"
                        rel="noreferrer"
                        style={{
                          fontSize: 12,
                          color: "var(--red)",
                          fontWeight: 600,
                          textDecoration: "none",
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 4,
                          whiteSpace: "nowrap",
                        }}
                      >
                        Original Source &rarr;
                      </a>
                    </div>
                    <p style={{ margin: "8px 0 0", fontSize: 13, color: "#475569", lineHeight: 1.5 }}>
                      {art.body_preview || art.summary}
                    </p>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* TAB 3: QUALIFIED OPPORTUNITIES */}
        {activeTab === "opportunities" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {/* Filter pills */}
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
              <select
                value={productFilter}
                onChange={(e) => setProductFilter(e.target.value)}
                style={{ padding: "6px 12px", borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 13, background: "#fff" }}
              >
                <option value="all">All Solwer Products</option>
                <option value="TWMS">TWMS (Transport &amp; Warehouse)</option>
                <option value="LOSS_TRACKER_IM">Loss Tracker / IM (OEE &amp; KAIZEN)</option>
                <option value="VDI">Vehicle Digital Inspection (VDI)</option>
                <option value="FLEET_MGMT">Fleet Management</option>
                <option value="MCE">Mobility Aftermarket (MCE)</option>
                <option value="CARBON_MGMT">Carbon Footprint Management</option>
              </select>

              <select
                value={priorityFilter}
                onChange={(e) => setPriorityFilter(e.target.value)}
                style={{ padding: "6px 12px", borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 13, background: "#fff" }}
              >
                <option value="all">All Priorities</option>
                <option value="high">High Priority (&ge;80)</option>
                <option value="medium">Medium Priority (60-79)</option>
                <option value="low">Low Priority (&lt;60)</option>
              </select>
            </div>

            {/* Opportunities List */}
            {opportunities.length === 0 ? (
              <div style={{ background: "#ffffff", padding: 36, textAlign: "center", borderRadius: 10, border: "1px solid #e2e8f0" }}>
                <p style={{ margin: 0, color: "#64748b" }}>No opportunities match current filters.</p>
              </div>
            ) : (
              opportunities.map((opp) => (
                <div
                  key={opp.id}
                  style={{
                    background: "#ffffff",
                    borderRadius: 12,
                    border: opp.priority_level === "high" ? "1px solid #fca5a5" : "1px solid #e2e8f0",
                    padding: 22,
                    boxShadow: "0 1px 4px rgba(0,0,0,0.04)",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12, flexWrap: "wrap", gap: 10 }}>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                        <span style={{ fontSize: 12, fontWeight: 700, background: "#fee2e2", color: "var(--red)", padding: "2px 8px", borderRadius: 6 }}>
                          {opp.product_name}
                        </span>
                        <span style={{ fontSize: 12, fontWeight: 600, color: opp.is_new_company ? "#0284c7" : "#16a34a" }}>
                          {opp.is_new_company ? "★ Newly Discovered Company" : "✓ Existing CRM Account"}
                        </span>
                      </div>
                      <h3 style={{ margin: 0, fontSize: 18, color: "#0f172a" }}>
                        {opp.company_name} {opp.company_domain ? `(${opp.company_domain})` : ""}
                      </h3>
                      <small style={{ color: "#64748b" }}>Event: {opp.event_title}</small>
                    </div>

                    {/* Dual Scores Badge */}
                    <div style={{ display: "flex", gap: 8 }}>
                      <div style={{ background: "#f8fafc", border: "1px solid #cbd5e1", padding: "6px 12px", borderRadius: 8, textAlign: "center" }}>
                        <span style={{ fontSize: 10, fontWeight: 700, color: "#64748b", textTransform: "uppercase", display: "block" }}>Market Signal</span>
                        <strong style={{ fontSize: 16, color: "#0f172a" }}>{opp.market_signal_score.toFixed(0)}/100</strong>
                      </div>
                      <div style={{ background: "#f0fdf4", border: "1px solid #86efac", padding: "6px 12px", borderRadius: 8, textAlign: "center" }}>
                        <span style={{ fontSize: 10, fontWeight: 700, color: "#166534", textTransform: "uppercase", display: "block" }}>Sales Readiness</span>
                        <strong style={{ fontSize: 16, color: "#15803d" }}>{opp.sales_readiness_score.toFixed(0)}/100</strong>
                      </div>
                    </div>
                  </div>

                  {/* Explainable Reasoning */}
                  <div style={{ background: "#f8fafc", padding: "12px 16px", borderRadius: 8, border: "1px solid #e2e8f0", marginBottom: 14 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: "#475569", textTransform: "uppercase", marginBottom: 4 }}>
                      Explainable Scoring Analysis:
                    </div>
                    <p style={{ margin: 0, fontSize: 13, color: "#1e293b", lineHeight: 1.5 }}>
                      {opp.score_explanation}
                    </p>
                  </div>

                  {/* Action recommendation & buyer roles */}
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 14 }}>
                    <div style={{ background: "#eff6ff", padding: 12, borderRadius: 8, border: "1px solid #bfdbfe" }}>
                      <span style={{ fontSize: 11, fontWeight: 700, color: "#1e40af", textTransform: "uppercase" }}>Recommended Next Action:</span>
                      <p style={{ margin: "4px 0 0", fontSize: 13, color: "#1e3a8a", fontWeight: 600 }}>{opp.suggested_next_action}</p>
                    </div>
                    <div style={{ background: "#f8fafc", padding: 12, borderRadius: 8, border: "1px solid #e2e8f0" }}>
                      <span style={{ fontSize: 11, fontWeight: 700, color: "#475569", textTransform: "uppercase" }}>Target Decision-Maker Roles:</span>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
                        {opp.suggested_buyer_roles.map((r, i) => (
                          <span key={i} style={{ fontSize: 11, background: "#ffffff", border: "1px solid #cbd5e1", padding: "2px 8px", borderRadius: 12, fontWeight: 600, color: "#334155" }}>
                            {r}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Controls */}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: 10, borderTop: "1px solid #f1f5f9" }}>
                    <span style={{ fontSize: 12, color: "#64748b" }}>Status: {opp.review_status}</span>
                    <div style={{ display: "flex", gap: 8 }}>
                      <button
                        type="button"
                        onClick={() => handleDismissOpp(opp.id)}
                        style={{ padding: "6px 14px", borderRadius: 6, border: "1px solid #cbd5e1", background: "#fff", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                      >
                        Dismiss
                      </button>
                      <button
                        type="button"
                        onClick={() => handleApproveOpp(opp.id)}
                        style={{ padding: "6px 14px", borderRadius: 6, border: "none", background: "var(--red)", color: "#fff", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                      >
                        ✓ Approve for Outreach
                      </button>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {/* TAB 4: DISCOVERED COMPANIES */}
        {activeTab === "companies" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <p style={{ margin: 0, fontSize: 14, color: "#64748b" }}>
              Companies identified through market news. New companies require human approval before being promoted to sales leads.
            </p>
            {companies.map((c) => (
              <div
                key={c.id}
                style={{
                  background: "#ffffff",
                  borderRadius: 10,
                  border: "1px solid #e2e8f0",
                  padding: "16px 20px",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  flexWrap: "wrap",
                  gap: 12,
                }}
              >
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                    <span style={{ fontSize: 11, fontWeight: 700, background: c.is_new ? "#e0f2fe" : "#dcfce7", color: c.is_new ? "#0284c7" : "#15803d", padding: "1px 8px", borderRadius: 6 }}>
                      {c.is_new ? "Newly Discovered" : "Existing Account"}
                    </span>
                    <span style={{ fontSize: 12, color: "#64748b" }}>Status: {c.approval_status}</span>
                  </div>
                  <h4 style={{ margin: 0, fontSize: 16, color: "#0f172a" }}>
                    {c.company_name} {c.domain ? `(${c.domain})` : ""}
                  </h4>
                  <small style={{ color: "#64748b" }}>
                    Industry: {c.industry} · Location: {c.location || "India"} · Associated Events: {c.events_count} · Opportunities: {c.opportunities_count}
                  </small>
                </div>

                <div style={{ display: "flex", gap: 8 }}>
                  {c.approval_status === "pending_review" && (
                    <>
                      <button
                        type="button"
                        onClick={() => handleDismissCompany(c.id)}
                        style={{ padding: "6px 12px", borderRadius: 6, border: "1px solid #cbd5e1", background: "#fff", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                      >
                        Dismiss
                      </button>
                      <button
                        type="button"
                        onClick={() => handleApproveCompany(c.id)}
                        style={{ padding: "6px 14px", borderRadius: 6, border: "none", background: "#16a34a", color: "#fff", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                      >
                        ✓ Promote to CRM Lead
                      </button>
                    </>
                  )}
                  {c.gtm_lead_id && (
                    <a
                      href={`/leads/${c.gtm_lead_id}`}
                      style={{ padding: "6px 14px", borderRadius: 6, border: "1px solid #cbd5e1", background: "#f8fafc", color: "#0f172a", fontSize: 12, fontWeight: 600, textDecoration: "none" }}
                    >
                      Open Lead 360 &rarr;
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* TAB 5: SOURCE MANAGEMENT (62 TARGETS) */}
        {activeTab === "sources" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <p style={{ margin: 0, fontSize: 14, color: "#64748b" }}>
                All 62 Indian and global monitoring targets. Inspect and crawl any website autonomously using Playwright.
              </p>
            </div>

            <div style={{ background: "#ffffff", borderRadius: 10, border: "1px solid #e2e8f0", overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0", textAlign: "left" }}>
                    <th style={{ padding: "10px 14px", color: "#475569" }}>Source Name</th>
                    <th style={{ padding: "10px 14px", color: "#475569" }}>Category</th>
                    <th style={{ padding: "10px 14px", color: "#475569" }}>Status</th>
                    <th style={{ padding: "10px 14px", color: "#475569" }}>Articles Discovered</th>
                    <th style={{ padding: "10px 14px", color: "#475569" }}>Discovered News URL</th>
                    <th style={{ padding: "10px 14px", color: "#475569" }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {sources.map((s) => (
                    <tr key={s.id} style={{ borderBottom: "1px solid #f1f5f9" }}>
                      <td style={{ padding: "12px 14px" }}>
                        <strong>{s.name}</strong>
                        <div style={{ fontSize: 11, color: "#64748b" }}>{s.domain}</div>
                      </td>
                      <td style={{ padding: "12px 14px", color: "#475569" }}>
                        <span style={{ fontSize: 11, background: "#f1f5f9", padding: "2px 6px", borderRadius: 4, fontWeight: 600 }}>
                          {s.source_category.replace("_", " ")}
                        </span>
                      </td>
                      <td style={{ padding: "12px 14px" }}>
                        <span
                          style={{
                            fontSize: 11,
                            fontWeight: 700,
                            padding: "2px 8px",
                            borderRadius: 10,
                            background: s.validation_status === "validated" ? "#dcfce7" : "#fee2e2",
                            color: s.validation_status === "validated" ? "#15803d" : "#b91c1c",
                          }}
                        >
                          {s.validation_status}
                        </span>
                      </td>
                      <td style={{ padding: "12px 14px", fontWeight: 600 }}>
                        {s.articles_discovered}
                      </td>
                      <td style={{ padding: "12px 14px", color: "#64748b", fontSize: 12, maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {s.discovered_news_url || "—"}
                      </td>
                      <td style={{ padding: "12px 14px" }}>
                        <div style={{ display: "flex", gap: 6 }}>
                          <button
                            type="button"
                            disabled={testingSourceId === s.id}
                            onClick={() => handleTestSource(s)}
                            style={{ padding: "4px 8px", borderRadius: 6, border: "1px solid #cbd5e1", background: "#fff", fontSize: 11, fontWeight: 600, cursor: "pointer" }}
                          >
                            {testingSourceId === s.id ? "Testing…" : "Discover"}
                          </button>
                          <button
                            type="button"
                            disabled={crawlingSourceId === s.id}
                            onClick={() => handleCrawlSource(s)}
                            style={{ padding: "4px 8px", borderRadius: 6, border: "none", background: "var(--red)", color: "#fff", fontSize: 11, fontWeight: 600, cursor: "pointer" }}
                          >
                            {crawlingSourceId === s.id ? "Crawling…" : "Crawl Now"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* TAB 6: WATCHLISTS */}
        {activeTab === "watchlists" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            {/* Add Watchlist Form */}
            <form onSubmit={handleAddWatchlist} style={{ background: "#ffffff", padding: 18, borderRadius: 10, border: "1px solid #e2e8f0", display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: "#334155" }}>
                Company Name
                <input
                  type="text"
                  required
                  placeholder="e.g. Tata Motors"
                  value={watchName}
                  onChange={(e) => setWatchName(e.target.value)}
                  style={{ display: "block", marginTop: 4, padding: "8px 12px", borderRadius: 6, border: "1px solid #cbd5e1", fontSize: 13 }}
                />
              </label>
              <label style={{ fontSize: 12, fontWeight: 600, color: "#334155" }}>
                Company Domain
                <input
                  type="text"
                  required
                  placeholder="e.g. tatamotors.com"
                  value={watchDomain}
                  onChange={(e) => setWatchDomain(e.target.value)}
                  style={{ display: "block", marginTop: 4, padding: "8px 12px", borderRadius: 6, border: "1px solid #cbd5e1", fontSize: 13 }}
                />
              </label>
              <button
                type="submit"
                disabled={addingWatch}
                style={{ padding: "9px 18px", borderRadius: 6, border: "none", background: "var(--red)", color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer" }}
              >
                + Add to Watchlist
              </button>
            </form>

            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {watchlists.map((w) => (
                <div key={w.id} style={{ background: "#ffffff", padding: "14px 18px", borderRadius: 8, border: "1px solid #e2e8f0", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <strong>{w.company_name}</strong> ({w.company_domain})
                    <div style={{ fontSize: 11, color: "#64748b" }}>Active notification triggers on investments, plants, and fleet expansions.</div>
                  </div>
                  <button
                    type="button"
                    onClick={async () => {
                      await deleteWatchlist(w.id);
                      setWatchlists((prev) => prev.filter((x) => x.id !== w.id));
                    }}
                    style={{ padding: "4px 10px", borderRadius: 6, border: "1px solid #cbd5e1", background: "#fff", fontSize: 11, color: "#b91c1c", cursor: "pointer" }}
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* TAB 7: NOTIFICATIONS & WEBHOOKS */}
        {activeTab === "alerts" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
            {/* Top Inbound Webhook Integration Banner */}
            <div
              style={{
                background: "linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%)",
                border: "1px solid #cbd5e1",
                borderRadius: 12,
                padding: "20px 24px",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                flexWrap: "wrap",
                gap: 16,
              }}
            >
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                  <span style={{ fontSize: 18 }}>⚡</span>
                  <strong style={{ fontSize: 16, color: "#0f172a" }}>Automated Inbound Webhook Signal Ingestion</strong>
                  <span style={{ fontSize: 11, fontWeight: 700, background: "#dcfce7", color: "#166534", padding: "2px 8px", borderRadius: 999 }}>
                    ACTIVE LISTENER
                  </span>
                </div>
                <p style={{ margin: 0, fontSize: 13, color: "#475569", maxWidth: 760 }}>
                  External crawlers, tender scrapers, and news feeds can push automotive business developments directly to this endpoint. GTMProspecting will automatically classify the event, resolve the company, match relevant Solwer products, calculate dual readiness scores, and trigger real-time sales alerts.
                </p>
                <div style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 8 }}>
                  <code style={{ background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: 6, padding: "4px 10px", fontSize: 12, color: "#0f172a", fontFamily: "monospace" }}>
                    POST http://localhost:8000/api/market-intelligence/webhook
                  </code>
                  <button
                    type="button"
                    onClick={() => {
                      navigator.clipboard.writeText("http://localhost:8000/api/market-intelligence/webhook");
                      showNotice("Webhook URL copied to clipboard.");
                    }}
                    style={{ padding: "4px 10px", borderRadius: 6, border: "1px solid #cbd5e1", background: "#ffffff", fontSize: 11, fontWeight: 600, cursor: "pointer" }}
                  >
                    Copy URL
                  </button>
                </div>
              </div>

              <div style={{ display: "flex", gap: 10 }}>
                <button
                  type="button"
                  onClick={() => {
                    setWebhookResult(null);
                    setWebhookModalOpen(true);
                  }}
                  style={{
                    padding: "10px 18px",
                    borderRadius: 8,
                    border: "none",
                    background: "var(--red, #e11d48)",
                    color: "#ffffff",
                    fontSize: 13,
                    fontWeight: 600,
                    cursor: "pointer",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                    boxShadow: "0 2px 4px rgba(225,29,72,0.2)",
                  }}
                >
                  <span>⚡</span> Simulate Inbound Signal
                </button>
              </div>
            </div>

            {/* Outbound Webhook Subscriptions (Slack, MS Teams, CRMs) */}
            <div style={{ background: "#ffffff", borderRadius: 12, border: "1px solid #e2e8f0", padding: "20px 24px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                <div>
                  <h3 style={{ margin: 0, fontSize: 16, color: "#0f172a" }}>Outbound Webhook Destinations</h3>
                  <p style={{ margin: "4px 0 0", fontSize: 13, color: "#64748b" }}>
                    Automatically dispatch real-time opportunity alerts to Slack incoming webhooks, Microsoft Teams channels, Zapier, or external CRMs.
                  </p>
                </div>
              </div>

              {/* Add Webhook Form */}
              <form onSubmit={handleAddSubscription} style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap", marginBottom: 20, padding: 14, background: "#f8fafc", borderRadius: 8, border: "1px solid #e2e8f0" }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: "#334155", flex: "1 1 200px" }}>
                  Destination Name
                  <input
                    type="text"
                    required
                    placeholder="e.g. Sales Team Slack Channel"
                    value={newSubName}
                    onChange={(e) => setNewSubName(e.target.value)}
                    style={{ width: "100%", display: "block", marginTop: 4, padding: "7px 10px", borderRadius: 6, border: "1px solid #cbd5e1", fontSize: 13 }}
                  />
                </label>
                <label style={{ fontSize: 12, fontWeight: 600, color: "#334155", flex: "2 1 320px" }}>
                  Destination Webhook URL (Slack / Teams / CRM)
                  <input
                    type="url"
                    required
                    placeholder="https://hooks.slack.com/services/... or https://outlook.office.com/webhook/..."
                    value={newSubUrl}
                    onChange={(e) => setNewSubUrl(e.target.value)}
                    style={{ width: "100%", display: "block", marginTop: 4, padding: "7px 10px", borderRadius: 6, border: "1px solid #cbd5e1", fontSize: 13 }}
                  />
                </label>
                <label style={{ fontSize: 12, fontWeight: 600, color: "#334155", flex: "1 1 180px" }}>
                  Secret Token (optional)
                  <input
                    type="text"
                    placeholder="HMAC secret token"
                    value={newSubSecret}
                    onChange={(e) => setNewSubSecret(e.target.value)}
                    style={{ width: "100%", display: "block", marginTop: 4, padding: "7px 10px", borderRadius: 6, border: "1px solid #cbd5e1", fontSize: 13 }}
                  />
                </label>
                <button
                  type="submit"
                  disabled={addingSub}
                  style={{ padding: "8px 16px", borderRadius: 6, border: "none", background: "#1e293b", color: "#ffffff", fontSize: 13, fontWeight: 600, cursor: "pointer", whiteSpace: "nowrap" }}
                >
                  {addingSub ? "Adding..." : "+ Add Webhook"}
                </button>
              </form>

              {/* Subscriptions List */}
              {webhookSubs.length === 0 ? (
                <div style={{ textAlign: "center", padding: "20px 0", color: "#64748b", fontSize: 13 }}>
                  No external webhook destinations registered yet. High-priority alerts will be stored in-app. Add a Slack or Teams webhook above to enable cross-platform push notifications.
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {webhookSubs.map((sub) => {
                    const statusInfo = pingStatus[sub.id];
                    return (
                      <div
                        key={sub.id}
                        style={{
                          background: "#ffffff",
                          border: "1px solid #e2e8f0",
                          borderRadius: 8,
                          padding: "12px 16px",
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          flexWrap: "wrap",
                          gap: 12,
                        }}
                      >
                        <div>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <strong style={{ fontSize: 14, color: "#0f172a" }}>{sub.name}</strong>
                            <span style={{ fontSize: 11, background: sub.is_active ? "#dcfce7" : "#fee2e2", color: sub.is_active ? "#15803d" : "#b91c1c", padding: "1px 6px", borderRadius: 6, fontWeight: 600 }}>
                              {sub.is_active ? "ACTIVE" : "INACTIVE"}
                            </span>
                            {sub.last_status_code && (
                              <span style={{ fontSize: 11, background: sub.last_status_code >= 200 && sub.last_status_code < 300 ? "#ecfdf5" : "#fef2f2", color: sub.last_status_code >= 200 && sub.last_status_code < 300 ? "#059669" : "#dc2626", padding: "1px 6px", borderRadius: 6 }}>
                                HTTP {sub.last_status_code}
                              </span>
                            )}
                          </div>
                          <div style={{ fontSize: 12, color: "#64748b", marginTop: 4, fontFamily: "monospace" }}>
                            {sub.target_url}
                          </div>
                          {sub.last_dispatched_at && (
                            <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 2 }}>
                              Last dispatched: {new Date(sub.last_dispatched_at).toLocaleString()}
                            </div>
                          )}
                          {sub.last_error && (
                            <div style={{ fontSize: 11, color: "#dc2626", marginTop: 2 }}>
                              Error: {sub.last_error}
                            </div>
                          )}
                        </div>

                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          {statusInfo && (
                            <span style={{ fontSize: 12, fontWeight: 600, color: statusInfo.status.startsWith("✓") ? "#16a34a" : "#dc2626" }}>
                              {statusInfo.status}
                            </span>
                          )}
                          <button
                            type="button"
                            onClick={() => handleTestPing(sub)}
                            style={{ padding: "6px 12px", borderRadius: 6, border: "1px solid #cbd5e1", background: "#ffffff", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                          >
                            ⚡ Test Ping
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDeleteSubscription(sub.id)}
                            style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid #fecaca", background: "#fef2f2", color: "#dc2626", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Live Notifications Stream */}
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
                <h3 style={{ margin: 0, fontSize: 16, color: "#0f172a" }}>
                  Live Market Alerts Stream ({alerts.length})
                </h3>
              </div>

              {alerts.length === 0 ? (
                <div style={{ background: "#ffffff", padding: 36, textAlign: "center", borderRadius: 10, border: "1px solid #e2e8f0" }}>
                  <p style={{ margin: 0, color: "#64748b" }}>No triggered notifications at this time. Click &quot;Simulate Inbound Signal&quot; above to test real-time opportunity alerts.</p>
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  {alerts.map((al) => (
                    <div
                      key={al.id}
                      style={{
                        background: al.is_read ? "#ffffff" : "#f0fdf4",
                        border: al.is_read ? "1px solid #e2e8f0" : "1px solid #86efac",
                        borderRadius: 10,
                        padding: 16,
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        gap: 12,
                        boxShadow: al.is_read ? "none" : "0 1px 3px rgba(34,197,94,0.1)",
                      }}
                    >
                      <div style={{ flex: 1 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                          <span
                            style={{
                              fontSize: 11,
                              fontWeight: 700,
                              background: al.priority === "high" ? "#fee2e2" : "#fef3c7",
                              color: al.priority === "high" ? "var(--red)" : "#d97706",
                              padding: "2px 8px",
                              borderRadius: 6,
                            }}
                          >
                            {al.priority.toUpperCase()}
                          </span>
                          <span style={{ fontSize: 11, background: "#f1f5f9", color: "#475569", padding: "2px 6px", borderRadius: 4 }}>
                            {al.alert_type.replace(/_/g, " ").toUpperCase()}
                          </span>
                          <span style={{ fontSize: 12, color: "#64748b" }}>
                            {new Date(al.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                          </span>
                        </div>
                        <strong style={{ fontSize: 15, color: "#0f172a" }}>{al.headline}</strong>
                        <p style={{ margin: "4px 0 0", fontSize: 13, color: "#475569", lineHeight: "1.5" }}>{al.summary}</p>
                      </div>

                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <button
                          type="button"
                          onClick={() => {
                            if (!al.is_read) handleMarkAlertRead(al.id);
                            setActiveTab("opportunities");
                          }}
                          style={{ padding: "6px 12px", borderRadius: 6, border: "1px solid #cbd5e1", background: "#ffffff", color: "#0f172a", fontSize: 12, fontWeight: 600, cursor: "pointer", whiteSpace: "nowrap" }}
                        >
                          View Opportunity →
                        </button>
                        {!al.is_read && (
                          <button
                            type="button"
                            onClick={() => handleMarkAlertRead(al.id)}
                            style={{ padding: "6px 12px", borderRadius: 6, border: "1px solid #86efac", background: "#ecfdf5", color: "#166534", fontSize: 12, fontWeight: 600, cursor: "pointer", whiteSpace: "nowrap" }}
                          >
                            ✓ Mark Read
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* WEBHOOK SIMULATOR MODAL */}
        {webhookModalOpen && (
          <div
            style={{
              position: "fixed",
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              backgroundColor: "rgba(15, 23, 42, 0.65)",
              backdropFilter: "blur(4px)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              zIndex: 9999,
              padding: 16,
            }}
          >
            <div
              style={{
                background: "#ffffff",
                borderRadius: 16,
                maxWidth: 680,
                width: "100%",
                maxHeight: "90vh",
                overflowY: "auto",
                boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.2)",
                padding: 24,
              }}
            >
              {/* Modal Header */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 20 }}>⚡</span>
                    <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "#0f172a" }}>
                      Inbound Automotive Signal Webhook Simulator
                    </h2>
                  </div>
                  <p style={{ margin: "4px 0 0", fontSize: 13, color: "#64748b" }}>
                    Simulate an automated signal payload to verify end-to-end event extraction, Solwer product matching, explainable scoring, and instant alert notification.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setWebhookModalOpen(false)}
                  style={{ border: "none", background: "transparent", fontSize: 22, color: "#94a3b8", cursor: "pointer", padding: "0 4px" }}
                >
                  ✕
                </button>
              </div>

              {/* Preset Selector */}
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: "#475569", textTransform: "uppercase", marginBottom: 8 }}>
                  Select an Automotive Scenario Preset:
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {simulationPresets.map((p, idx) => (
                    <button
                      key={p.label}
                      type="button"
                      onClick={() => applyPreset(idx)}
                      style={{
                        padding: "6px 12px",
                        borderRadius: 20,
                        border: simPresetIdx === idx ? "1.5px solid var(--red)" : "1px solid #cbd5e1",
                        background: simPresetIdx === idx ? "#fff1f2" : "#ffffff",
                        color: simPresetIdx === idx ? "var(--red)" : "#334155",
                        fontSize: 12,
                        fontWeight: simPresetIdx === idx ? 700 : 500,
                        cursor: "pointer",
                      }}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Form Fields */}
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, color: "#334155", display: "block", marginBottom: 4 }}>
                    Signal Headline / Tender Title
                  </label>
                  <input
                    type="text"
                    value={simHeadline}
                    onChange={(e) => setSimHeadline(e.target.value)}
                    style={{ width: "100%", padding: "8px 12px", borderRadius: 6, border: "1px solid #cbd5e1", fontSize: 13 }}
                  />
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                  <div>
                    <label style={{ fontSize: 12, fontWeight: 600, color: "#334155", display: "block", marginBottom: 4 }}>
                      Company Name
                    </label>
                    <input
                      type="text"
                      value={simCompany}
                      onChange={(e) => setSimCompany(e.target.value)}
                      style={{ width: "100%", padding: "8px 12px", borderRadius: 6, border: "1px solid #cbd5e1", fontSize: 13 }}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: 12, fontWeight: 600, color: "#334155", display: "block", marginBottom: 4 }}>
                      Domain
                    </label>
                    <input
                      type="text"
                      value={simDomain}
                      onChange={(e) => setSimDomain(e.target.value)}
                      style={{ width: "100%", padding: "8px 12px", borderRadius: 6, border: "1px solid #cbd5e1", fontSize: 13 }}
                    />
                  </div>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                  <div>
                    <label style={{ fontSize: 12, fontWeight: 600, color: "#334155", display: "block", marginBottom: 4 }}>
                      Event Category
                    </label>
                    <select
                      value={simCategory}
                      onChange={(e) => setSimCategory(e.target.value)}
                      style={{ width: "100%", padding: "8px 12px", borderRadius: 6, border: "1px solid #cbd5e1", fontSize: 13, background: "#fff" }}
                    >
                      <option value="warehouse_expansion">Warehouse / Logistics Expansion (TWMS)</option>
                      <option value="manufacturing_expansion">Manufacturing / Plant Expansion (Loss Tracker)</option>
                      <option value="fleet_expansion">Commercial Fleet Expansion (VDI / Fleet)</option>
                      <option value="esg_netzero">ESG / Decarbonization (Carbon Mgmt)</option>
                      <option value="aftermarket_network">Aftermarket Dealership Network (MCE)</option>
                    </select>
                  </div>
                  <div>
                    <label style={{ fontSize: 12, fontWeight: 600, color: "#334155", display: "block", marginBottom: 4 }}>
                      Publisher Source
                    </label>
                    <input
                      type="text"
                      value={simPublisher}
                      onChange={(e) => setSimPublisher(e.target.value)}
                      style={{ width: "100%", padding: "8px 12px", borderRadius: 6, border: "1px solid #cbd5e1", fontSize: 13 }}
                    />
                  </div>
                </div>

                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, color: "#334155", display: "block", marginBottom: 4 }}>
                    Signal Body / Context Details
                  </label>
                  <textarea
                    rows={3}
                    value={simBody}
                    onChange={(e) => setSimBody(e.target.value)}
                    style={{ width: "100%", padding: "8px 12px", borderRadius: 6, border: "1px solid #cbd5e1", fontSize: 13, fontFamily: "inherit" }}
                  />
                </div>
              </div>

              {/* Simulation Output Result Box */}
              {webhookResult && (
                <div
                  style={{
                    marginTop: 16,
                    padding: 16,
                    background: "#f0fdf4",
                    border: "1px solid #86efac",
                    borderRadius: 10,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                    <span style={{ fontSize: 16 }}>✓</span>
                    <strong style={{ fontSize: 14, color: "#166534" }}>Webhook Successfully Triggered &amp; Evaluated!</strong>
                  </div>
                  <p style={{ margin: "0 0 10px", fontSize: 13, color: "#166534" }}>
                    Company <strong>{webhookResult.company.company_name}</strong> was {webhookResult.company.is_new ? "discovered as new lead" : "matched to CRM records"}.
                  </p>

                  <div style={{ fontSize: 12, fontWeight: 700, color: "#15803d", marginBottom: 6 }}>
                    MATCHED SOLWER PRODUCT OPPORTUNITIES ({webhookResult.opportunities_count}):
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
                    {webhookResult.opportunities.map((opp) => (
                      <div
                        key={opp.id}
                        style={{
                          background: "#ffffff",
                          border: "1px solid #bbf7d0",
                          borderRadius: 6,
                          padding: "6px 10px",
                          fontSize: 12,
                          color: "#166534",
                        }}
                      >
                        <strong>{opp.product_name}</strong> · Signal Score: <strong>{opp.market_signal_score}/100</strong> ({opp.priority_level.toUpperCase()})
                      </div>
                    ))}
                  </div>

                  <div style={{ display: "flex", gap: 10 }}>
                    <button
                      type="button"
                      onClick={() => {
                        setWebhookModalOpen(false);
                        setActiveTab("opportunities");
                      }}
                      style={{ padding: "6px 14px", borderRadius: 6, border: "none", background: "#166534", color: "#ffffff", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                    >
                      View in Qualified Opportunities →
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setWebhookModalOpen(false);
                        setActiveTab("alerts");
                      }}
                      style={{ padding: "6px 14px", borderRadius: 6, border: "1px solid #86efac", background: "#ffffff", color: "#166534", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                    >
                      View Triggered Alerts →
                    </button>
                  </div>
                </div>
              )}

              {/* Modal Actions */}
              <div style={{ marginTop: 20, display: "flex", justifyContent: "flex-end", gap: 10 }}>
                <button
                  type="button"
                  onClick={() => setWebhookModalOpen(false)}
                  style={{ padding: "8px 16px", borderRadius: 6, border: "1px solid #cbd5e1", background: "#ffffff", fontSize: 13, fontWeight: 600, cursor: "pointer" }}
                >
                  Close
                </button>
                <button
                  type="button"
                  disabled={webhookSubmitting}
                  onClick={handleTriggerSimulation}
                  style={{
                    padding: "8px 18px",
                    borderRadius: 6,
                    border: "none",
                    background: "var(--red, #e11d48)",
                    color: "#ffffff",
                    fontSize: 13,
                    fontWeight: 600,
                    cursor: "pointer",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                >
                  {webhookSubmitting ? "Processing AI Extraction..." : "⚡ Trigger Webhook Now"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* INTELLIGENCE DRILLDOWN MODAL (What are the news & where it helps) */}
        {drilldown && drilldown.isOpen && (
          <div
            style={{
              position: "fixed",
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              backgroundColor: "rgba(15, 23, 42, 0.7)",
              backdropFilter: "blur(5px)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              zIndex: 9999,
              padding: 20,
            }}
            onClick={() => setDrilldown(null)}
          >
            <div
              style={{
                background: "#ffffff",
                borderRadius: 16,
                maxWidth: 860,
                width: "100%",
                maxHeight: "88vh",
                overflowY: "auto",
                boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.25)",
                padding: "26px 28px",
              }}
              onClick={(e) => e.stopPropagation()}
            >
              {/* Modal Header */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 18, borderBottom: "1px solid #e2e8f0", paddingBottom: 14 }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ fontSize: 22 }}>
                      {drilldown.type === "product_opportunities" ? "🎯" : drilldown.type === "high_priority" ? "🔥" : drilldown.type === "new_companies" ? "🏢" : "📰"}
                    </span>
                    <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: "#0f172a" }}>
                      {drilldown.title}
                    </h2>
                  </div>
                  <p style={{ margin: "6px 0 0", fontSize: 13, color: "#64748b" }}>
                    {drilldown.subtitle}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setDrilldown(null)}
                  style={{ border: "none", background: "transparent", fontSize: 22, color: "#94a3b8", cursor: "pointer", padding: "0 4px" }}
                >
                  ✕
                </button>
              </div>

              {/* Mode A: Product Opportunities Breakdown */}
              {drilldown.type === "product_opportunities" && drilldown.product && (() => {
                const p = drilldown.product;
                const relevantOpps = drilldown.productOpportunities ?? opportunities.filter((o) => o.product_code === p.code);

                return (
                  <div>
                    {/* Product Capability Info Banner */}
                    <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 10, padding: "14px 18px", marginBottom: 20 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                        <span style={{ fontSize: 12, fontWeight: 700, color: "var(--red)", textTransform: "uppercase" }}>
                          Solwer Solution: {p.business_area}
                        </span>
                        {p.official_url && (
                          <a
                            href={p.official_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ fontSize: 12, color: "#2563eb", textDecoration: "none", fontWeight: 600 }}
                          >
                            Visit official product page ↗
                          </a>
                        )}
                      </div>
                      <p style={{ margin: "6px 0 10px", fontSize: 13, color: "#334155", lineHeight: 1.5 }}>
                        {p.description}
                      </p>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
                        <span style={{ fontSize: 11, fontWeight: 700, color: "#64748b" }}>Problems Solved:</span>
                        {(p.problems_solved || []).map((prob, i) => (
                          <span key={i} style={{ fontSize: 11, background: "#ffffff", border: "1px solid #cbd5e1", padding: "2px 8px", borderRadius: 12, color: "#334155" }}>
                            ✓ {prob}
                          </span>
                        ))}
                      </div>
                    </div>

                    {/* Matched News & Opportunity Cards */}
                    {relevantOpps.length === 0 ? (
                      <div style={{ padding: 30, textAlign: "center", color: "#64748b", background: "#f8fafc", borderRadius: 10 }}>
                        <p style={{ margin: 0, fontSize: 14 }}>No opportunities currently generated for {p.name}.</p>
                        <small style={{ display: "block", marginTop: 6, color: "#94a3b8" }}>
                          You can click &quot;Trigger Webhook Signal&quot; or crawl monitored sources to evaluate new automotive developments.
                        </small>
                      </div>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                        {relevantOpps.map((opp) => (
                          <div
                            key={opp.id}
                            style={{
                              border: opp.priority_level === "high" ? "1.5px solid #fca5a5" : "1px solid #e2e8f0",
                              borderRadius: 12,
                              background: opp.priority_level === "high" ? "#fffbfb" : "#ffffff",
                              padding: "18px 20px",
                              boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
                            }}
                          >
                            {/* Card Top Row: Company & Scores */}
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 10, marginBottom: 12 }}>
                              <div>
                                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                  <strong style={{ fontSize: 17, color: "#0f172a" }}>{opp.company_name}</strong>
                                  {opp.company_domain && (
                                    <span style={{ fontSize: 12, color: "#64748b", fontFamily: "monospace" }}>({opp.company_domain})</span>
                                  )}
                                  <span
                                    style={{
                                      fontSize: 10,
                                      fontWeight: 700,
                                      background: opp.is_new_company ? "#e0f2fe" : "#ecfdf5",
                                      color: opp.is_new_company ? "#0369a1" : "#15803d",
                                      padding: "2px 7px",
                                      borderRadius: 4,
                                    }}
                                  >
                                    {opp.is_new_company ? "NEW PROSPECT" : "EXISTING LEAD"}
                                  </span>
                                </div>
                              </div>

                              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                <span
                                  style={{
                                    fontSize: 11,
                                    fontWeight: 700,
                                    background: opp.priority_level === "high" ? "#fee2e2" : "#fef3c7",
                                    color: opp.priority_level === "high" ? "var(--red)" : "#d97706",
                                    padding: "3px 8px",
                                    borderRadius: 6,
                                  }}
                                >
                                  {opp.priority_level.toUpperCase()} PRIORITY
                                </span>
                                <span style={{ fontSize: 12, fontWeight: 800, background: "#f1f5f9", padding: "3px 8px", borderRadius: 6, color: "#0f172a" }}>
                                  Signal: {opp.market_signal_score}/100
                                </span>
                                <span style={{ fontSize: 12, fontWeight: 800, background: "#f0fdf4", color: "#166534", padding: "3px 8px", borderRadius: 6 }}>
                                  Readiness: {opp.sales_readiness_score}/100
                                </span>
                              </div>
                            </div>

                            {/* Section 1: The News Announcement */}
                            <div style={{ background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 8, padding: "12px 14px", marginBottom: 12 }}>
                              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                                <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "#64748b" }}>
                                  📰 Extracted Business News / Tender
                                </span>
                                <span style={{ fontSize: 11, color: "#94a3b8" }}>·</span>
                                <span style={{ fontSize: 11, color: "#475569", fontWeight: 600 }}>
                                  {opp.article_publisher || "Verified Automotive Source"}
                                </span>
                                {opp.location && (
                                  <>
                                    <span style={{ fontSize: 11, color: "#94a3b8" }}>·</span>
                                    <span style={{ fontSize: 11, color: "#64748b" }}>📍 {opp.location}</span>
                                  </>
                                )}
                              </div>
                              <h4 style={{ margin: "2px 0 6px", fontSize: 14, color: "#0f172a", fontWeight: 700 }}>
                                {opp.article_headline || opp.event_title}
                              </h4>
                              {opp.event_description && (
                                <p style={{ margin: 0, fontSize: 12, color: "#475569", lineHeight: 1.4 }}>
                                  {opp.event_description}
                                </p>
                              )}
                            </div>

                            {/* Section 2: Where Solwer Can Be Helpful */}
                            <div
                              style={{
                                background: "linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%)",
                                border: "1px solid #86efac",
                                borderRadius: 8,
                                padding: "14px 16px",
                                marginBottom: 14,
                              }}
                            >
                              <div style={{ fontSize: 12, fontWeight: 800, color: "#166534", textTransform: "uppercase", marginBottom: 8, display: "flex", alignItems: "center", gap: 6 }}>
                                <span>💡</span> Where Solwer {p.name} Directly Helps:
                              </div>

                              {/* Operational Problem */}
                              <div style={{ marginBottom: 8 }}>
                                <strong style={{ fontSize: 12, color: "#991b1b" }}>🚨 Operational Problem Identified in the News:</strong>
                                <p style={{ margin: "2px 0 0", fontSize: 12, color: "#334155", lineHeight: 1.45 }}>
                                  {opp.operational_problem || "The company announced expansion requiring automated workflow systems to eliminate bottlenecks and enforce turnaround times."}
                                </p>
                              </div>

                              {/* How Solwer Solves It */}
                              <div style={{ marginBottom: 8 }}>
                                <strong style={{ fontSize: 12, color: "#166534" }}>✨ Why Solwer is the Solution:</strong>
                                <p style={{ margin: "2px 0 0", fontSize: 12, color: "#334155", lineHeight: 1.45 }}>
                                  {opp.score_explanation || opp.business_implication || p.description}
                                </p>
                              </div>

                              {/* Recommended Pitch / Suggested Next Action */}
                              <div style={{ marginBottom: 8 }}>
                                <strong style={{ fontSize: 12, color: "#1e40af" }}>🎯 Recommended Sales Outreach Pitch:</strong>
                                <p style={{ margin: "2px 0 0", fontSize: 12, color: "#1e3a8a", fontWeight: 500, lineHeight: 1.45 }}>
                                  &quot;{opp.suggested_next_action}&quot;
                                </p>
                              </div>

                              {/* Target Buyer Roles */}
                              {opp.suggested_buyer_roles && opp.suggested_buyer_roles.length > 0 && (
                                <div style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 6, flexWrap: "wrap" }}>
                                  <span style={{ fontSize: 11, fontWeight: 700, color: "#475569" }}>Target Buyer Personas:</span>
                                  {opp.suggested_buyer_roles.map((role, idx) => (
                                    <span key={idx} style={{ fontSize: 11, background: "#ffffff", border: "1px solid #bbf7d0", padding: "1px 8px", borderRadius: 10, color: "#166534", fontWeight: 600 }}>
                                      👔 {role}
                                    </span>
                                  ))}
                                </div>
                              )}
                            </div>

                            {/* Card Actions */}
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
                              <div style={{ fontSize: 11, color: "#64748b" }}>
                                Status: <strong style={{ color: opp.review_status === "approved" ? "#16a34a" : "#0f172a" }}>{opp.review_status.toUpperCase()}</strong>
                              </div>
                              <div style={{ display: "flex", gap: 8 }}>
                                {opp.review_status !== "approved" && (
                                  <button
                                    type="button"
                                    onClick={() => handleApproveOpp(opp.id)}
                                    style={{
                                      padding: "6px 14px",
                                      borderRadius: 6,
                                      border: "none",
                                      background: "#16a34a",
                                      color: "#ffffff",
                                      fontSize: 12,
                                      fontWeight: 600,
                                      cursor: "pointer",
                                    }}
                                  >
                                    ✓ Approve for Outreach
                                  </button>
                                )}
                                <button
                                  type="button"
                                  onClick={() => {
                                    setDrilldown(null);
                                    setProductFilter(opp.product_code);
                                    setActiveTab("opportunities");
                                  }}
                                  style={{
                                    padding: "6px 14px",
                                    borderRadius: 6,
                                    border: "1px solid #cbd5e1",
                                    background: "#ffffff",
                                    color: "#0f172a",
                                    fontSize: 12,
                                    fontWeight: 600,
                                    cursor: "pointer",
                                  }}
                                >
                                  View in Qualified Opportunities &rarr;
                                </button>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })()}

              {/* Mode B: Signals & News Detected Today */}
              {drilldown.type === "signals_today" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  {articles.length === 0 ? (
                    <div style={{ padding: 30, textAlign: "center", color: "#64748b" }}>No news signals detected today.</div>
                  ) : (
                    articles.map((art) => {
                      const matchedOpps = opportunities.filter((o) => o.event_title.includes(art.headline) || art.headline.includes(o.event_title) || (o.company_name && art.headline.includes(o.company_name)));
                      return (
                        <div key={art.id} style={{ border: "1px solid #e2e8f0", borderRadius: 10, padding: 16, background: "#ffffff" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
                            <div>
                              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                                <span style={{ fontSize: 11, fontWeight: 700, color: "#2563eb", background: "#eff6ff", padding: "1px 6px", borderRadius: 4 }}>
                                  {art.publisher}
                                </span>
                                {art.published_at && (
                                  <span style={{ fontSize: 11, color: "#64748b" }}>{new Date(art.published_at).toLocaleDateString()}</span>
                                )}
                              </div>
                              <h4 style={{ margin: "4px 0", fontSize: 15, color: "#0f172a" }}>{art.headline}</h4>
                              <p style={{ margin: "4px 0 8px", fontSize: 12, color: "#475569", lineHeight: 1.45 }}>
                                {art.summary || art.body_preview || "News extracted from monitored automotive portal."}
                              </p>
                            </div>
                          </div>

                          {/* Where it helps breakdown */}
                          <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: 12, marginTop: 8 }}>
                            <div style={{ fontSize: 11, fontWeight: 700, color: "#0f172a", textTransform: "uppercase", marginBottom: 6 }}>
                              💡 Solwer Product Fit:
                            </div>
                            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                              {matchedOpps.length > 0 ? (
                                matchedOpps.map((mo) => (
                                  <span key={mo.id} style={{ fontSize: 11, background: "#ffffff", border: "1px solid #bbf7d0", padding: "3px 8px", borderRadius: 6, color: "#166534" }}>
                                    <strong>{mo.product_name}</strong> · Score: {mo.market_signal_score}/100
                                  </span>
                                ))
                              ) : (
                                <span style={{ fontSize: 11, color: "#64748b" }}>Applicable across Solwer logistics, fleet, and manufacturing lines.</span>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              )}

              {/* Mode C: High-Priority Opportunities */}
              {drilldown.type === "high_priority" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  {opportunities
                    .filter((o) => o.priority_level === "high")
                    .map((opp) => (
                      <div key={opp.id} style={{ border: "1.5px solid #fecaca", borderRadius: 12, background: "#fffbfb", padding: 18 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                          <strong style={{ fontSize: 16, color: "#0f172a" }}>
                            {opp.company_name} — {opp.product_name}
                          </strong>
                          <span style={{ fontSize: 11, fontWeight: 800, background: "#fee2e2", color: "var(--red)", padding: "2px 8px", borderRadius: 6 }}>
                            Score: {opp.market_signal_score}/100
                          </span>
                        </div>

                        {/* News */}
                        <div style={{ background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 8, padding: "10px 12px", marginBottom: 10 }}>
                          <span style={{ fontSize: 10, fontWeight: 700, color: "#64748b", textTransform: "uppercase" }}>Triggering News:</span>
                          <div style={{ fontSize: 13, fontWeight: 600, color: "#0f172a", marginTop: 2 }}>{opp.article_headline || opp.event_title}</div>
                        </div>

                        {/* Where it helps */}
                        <div style={{ background: "#f0fdf4", border: "1px solid #86efac", borderRadius: 8, padding: "12px 14px", marginBottom: 12 }}>
                          <div style={{ fontSize: 11, fontWeight: 700, color: "#166534", textTransform: "uppercase", marginBottom: 4 }}>
                            💡 Where Solwer Can Be Helpful:
                          </div>
                          <p style={{ margin: "2px 0 6px", fontSize: 12, color: "#334155", lineHeight: 1.45 }}>
                            <strong>Problem:</strong> {opp.operational_problem || "Manufacturing/supply chain expansion creating operational bottleneck."}
                          </p>
                          <p style={{ margin: "2px 0 0", fontSize: 12, color: "#1e3a8a", fontWeight: 600 }}>
                            <strong>Pitch:</strong> &quot;{opp.suggested_next_action}&quot;
                          </p>
                        </div>

                        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
                          <button
                            type="button"
                            onClick={() => {
                              setDrilldown(null);
                              setProductFilter(opp.product_code);
                              setActiveTab("opportunities");
                            }}
                            style={{ padding: "6px 14px", borderRadius: 6, border: "1px solid #cbd5e1", background: "#ffffff", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                          >
                            Open Full Opportunity &rarr;
                          </button>
                        </div>
                      </div>
                    ))}
                </div>
              )}

              {/* Mode D: Newly Discovered Companies */}
              {drilldown.type === "new_companies" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                  {companies
                    .filter((c) => c.is_new)
                    .map((comp) => {
                      const compOpps = opportunities.filter((o) => o.company_id === comp.id);
                      return (
                        <div key={comp.id} style={{ border: "1px solid #bae6fd", borderRadius: 10, padding: 16, background: "#ffffff" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                            <div>
                              <strong style={{ fontSize: 16, color: "#0f172a" }}>{comp.company_name}</strong>
                              {comp.domain && (
                                <span style={{ fontSize: 12, color: "#0284c7", marginLeft: 8, fontFamily: "monospace" }}>({comp.domain})</span>
                              )}
                              <div style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>
                                {comp.industry} · {comp.location || "India"} · Segment: {comp.business_segment || "Automotive Tier 1 / OEM"}
                              </div>
                            </div>
                            <span style={{ fontSize: 11, background: "#e0f2fe", color: "#0369a1", fontWeight: 700, padding: "2px 8px", borderRadius: 6 }}>
                              NEW DISCOVERY
                            </span>
                          </div>

                          {/* Opportunities for this company */}
                          <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: 12, marginTop: 10 }}>
                            <div style={{ fontSize: 11, fontWeight: 700, color: "#334155", textTransform: "uppercase", marginBottom: 6 }}>
                              💡 Where Solwer Can Help {comp.company_name}:
                            </div>
                            {compOpps.length > 0 ? (
                              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                {compOpps.map((co) => (
                                  <div key={co.id} style={{ fontSize: 12, color: "#1e293b" }}>
                                    <strong>{co.product_name}</strong>: {co.suggested_next_action}
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <div style={{ fontSize: 12, color: "#64748b" }}>
                                Identified as automotive prospect through verified industry publications.
                              </div>
                            )}
                          </div>

                          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 12 }}>
                            {comp.approval_status !== "approved" && (
                              <button
                                type="button"
                                onClick={() => handleApproveCompany(comp.id)}
                                style={{ padding: "6px 12px", borderRadius: 6, border: "none", background: "#0284c7", color: "#ffffff", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                              >
                                ✓ Approve as CRM Lead
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={() => handleDismissCompany(comp.id)}
                              style={{ padding: "6px 12px", borderRadius: 6, border: "1px solid #cbd5e1", background: "#ffffff", color: "#64748b", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                            >
                              Dismiss
                            </button>
                          </div>
                        </div>
                      );
                    })}
                </div>
              )}

              {/* Modal Footer */}
              <div style={{ marginTop: 22, display: "flex", justifyContent: "flex-end" }}>
                <button
                  type="button"
                  onClick={() => setDrilldown(null)}
                  style={{ padding: "8px 18px", borderRadius: 6, border: "1px solid #cbd5e1", background: "#ffffff", fontSize: 13, fontWeight: 600, cursor: "pointer" }}
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
  );
}
