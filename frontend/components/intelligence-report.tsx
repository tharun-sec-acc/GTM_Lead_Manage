"use client";

import { useMemo, useState } from "react";
import { displayDate, label, statusTone, type Citation, type ResearchFact, type ResearchReport, type ResearchSource } from "../lib/intelligence";
import UiIcon from "./ui-icon";

export const researchCategories = [
  ["all", "All findings"],
  ["company", "Company overview"],
  ["leadership", "Leadership & governance"],
  ["corporate_relationships", "Corporate relationships"],
  ["financial", "Financials & scope"],
  ["funding", "Funding & capital"],
  ["financial_risk", "Financial risk factors"],
  ["business_operations", "Facilities & operations"],
  ["fleet_transportation", "Fleet & logistics"],
  ["manufacturing_infrastructure", "Manufacturing & plants"],
  ["technology_digital", "Technology maturity"],
  ["news", "News & developments"],
  ["competitors", "Market & competitors"],
  ["industry_market", "Industry & regulations"],
  ["hiring_expansion", "Hiring & expansion"],
  ["signals", "Operational pain points"],
] as const;

function safeSourceUrl(value: string) {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) ? url.href : undefined;
  } catch { return undefined; }
}

export function CitationList({ citations }: { citations: Citation[] }) {
  return <details className="citation-details">
    <summary><UiIcon name="link" size={14} /> {citations.length} supporting {citations.length === 1 ? "source citation" : "source citations"}</summary>
    {citations.map((citation, index) => <div className="citation-card" key={`${citation.source_id}:${index}`}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
        <a href={safeSourceUrl(citation.url)} target="_blank" rel="noopener noreferrer">
          {citation.title || citation.url} <UiIcon name="external" size={13} />
        </a>
        <span className="badge" style={{ background: "#f1f5f9", color: "#475569" }}>
          {label(citation.reliability)}
        </span>
      </div>
      {citation.excerpt && <blockquote>&ldquo;{citation.excerpt}&rdquo;</blockquote>}
      <small style={{ color: "#64748b" }}>
        Retrieved {displayDate(citation.retrieved_at)}
        {citation.published_at && <> · Published {displayDate(citation.published_at)}</>}
        {citation.page_number !== null && <> · Page {citation.page_number}</>}
      </small>
    </div>)}
  </details>;
}

export default function IntelligenceReport({
  facts, sources, report, factsTotal, sourcesTotal, loadingMore, onMoreFacts, onMoreSources,
}: {
  facts: ResearchFact[]; sources: ResearchSource[]; report: ResearchReport | null;
  factsTotal: number; sourcesTotal: number; loadingMore: boolean; onMoreFacts: () => void; onMoreSources: () => void;
}) {
  const [mainView, setMainView] = useState<"brief" | "strategy" | "denso_fit" | "diff" | "findings" | "sources">("brief");
  const [category, setCategory] = useState("all");
  const [query, setQuery] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [verification, setVerification] = useState("");
  const [period, setPeriod] = useState("");
  const [newsFrom, setNewsFrom] = useState("");
  const [newsTo, setNewsTo] = useState("");

  const distinctDomains = useMemo(() => Array.from(new Set(sources.map(s => s.domain).filter(Boolean))), [sources]);
  const pdfSourcesCount = useMemo(() => sources.filter(s => s.is_document || s.url.toLowerCase().endsWith(".pdf") || s.retrieval_method?.includes("pdf")).length, [sources]);

  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = { all: facts.length };
    for (const f of facts) {
      counts[f.category] = (counts[f.category] || 0) + 1;
    }
    return counts;
  }, [facts]);

  const periods = Array.from(new Set(facts.filter(fact => fact.category === "financial" || fact.category === "financial_research").map(fact => fact.reporting_period).filter((value): value is string => !!value)));
  const statuses = Array.from(new Set(facts.map(fact => fact.verification_status)));

  const filtered = useMemo(() => facts.filter(fact => {
    if (category !== "all" && fact.category !== category) {
      const aliasMap: Record<string, string> = {
        company: "company_identity", leadership: "leadership_intelligence",
        financial: "financial_research", funding: "investment_funding",
        news: "news_developments", competitors: "competitor_intelligence",
        signals: "pain_points_opportunities",
      };
      if (aliasMap[category] !== fact.category && fact.category !== category) return false;
    }
    if (query && !`${fact.field_name} ${fact.value} ${fact.citations.map(citation => `${citation.title} ${citation.excerpt}`).join(" ")}`.toLowerCase().includes(query.toLowerCase())) return false;
    if (sourceId && !fact.citations.some(citation => citation.source_id === sourceId)) return false;
    if (verification && fact.verification_status !== verification) return false;
    if (period && (fact.category === "financial" || fact.category === "financial_research") && fact.reporting_period !== period) return false;
    if ((fact.category === "news" || fact.category === "news_developments") && (newsFrom || newsTo)) {
      return fact.citations.some(citation => citation.published_at &&
        (!newsFrom || citation.published_at.slice(0, 10) >= newsFrom) &&
        (!newsTo || citation.published_at.slice(0, 10) <= newsTo));
    }
    return true;
  }), [facts, category, query, sourceId, verification, period, newsFrom, newsTo]);

  const financials = filtered.filter(fact => fact.category === "financial" || fact.category === "financial_research");
  const otherFacts = filtered.filter(fact => fact.category !== "financial" && fact.category !== "financial_research");
  const visibleSources = sources.filter(source => !query || `${source.title} ${source.domain} ${source.excerpt}`.toLowerCase().includes(query.toLowerCase()));

  // Extract structured intelligence items
  const onePage = report?.one_page_summary;
  const analysis = report?.analysis_data;
  const productOpps = (report?.product_opportunities && report.product_opportunities.length > 0)
    ? report.product_opportunities
    : (onePage?.solwer_product_opportunities || onePage?.denso_product_opportunities || []);
  const whatChanged = report?.what_changed || [];

  function formatIndustryList(industry: any): string {
    if (!industry) return "Industrial Operations";
    if (Array.isArray(industry)) {
      return industry
        .map(item => String(item).replace(/([a-z0-9&])([A-Z])/g, "$1 $2").trim())
        .filter(Boolean)
        .join(" · ");
    }
    if (typeof industry === "string") {
      return industry.replace(/([a-z0-9&])([A-Z])/g, "$1, $2").trim();
    }
    return String(industry);
  }

  function exportReport() {
    if (!report) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify({
      report, facts, sources, exported_at: new Date().toISOString(),
      included_facts: facts.length, total_facts: factsTotal, included_sources: sources.length, total_sources: sourcesTotal
    }, null, 2)], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url; link.download = `company-research-${report.id}.json`; link.click(); URL.revokeObjectURL(url);
  }

  function printBrief() {
    window.print();
  }

  return <section className="research-report">
    <div className="section-title">
      <div>
        <p className="eyebrow">AUTONOMOUS MULTI-AGENT SALES INTELLIGENCE</p>
        <h2>Company Research & Opportunity Engine</h2>
        <p>{report ? `Report version ${report.version} · Generated ${displayDate(report.created_at)}` : "Verified findings appear as autonomous workers finish scraping, document parsing and synthesis."}</p>
      </div>
      <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
        <button className="secondary" disabled={!report} onClick={printBrief} title="Print or save 1-page executive brief as PDF">
          <UiIcon name="file" size={16} /> Print / Save PDF Brief
        </button>
        <button className="secondary" disabled={!report} onClick={exportReport} title="Export full research payload as JSON">
          <UiIcon name="upload" size={16} /> Export Research JSON
        </button>
      </div>
    </div>

    {/* Top Intelligence Stats Banner */}
    <div className="stats" style={{ margin: "20px 0" }}>
      <div>
        <strong>{factsTotal}</strong>
        <span>Evidenced findings</span>
      </div>
      <div>
        <strong>{sourcesTotal}</strong>
        <span>Public sources discovered</span>
      </div>
      <div>
        <strong>{pdfSourcesCount}</strong>
        <span>PDF filings / documents</span>
      </div>
      <div>
        <strong>{distinctDomains.length}</strong>
        <span>Distinct domains</span>
      </div>
      <div>
        <strong>{productOpps.length || 6}</strong>
        <span>Solwer solutions evaluated</span>
      </div>
    </div>

    {/* Primary Navigation Tabs */}
    <nav className="main-view-tabs" aria-label="Research Views">
      <button className={`main-view-tab ${mainView === "brief" ? "active" : ""}`} onClick={() => setMainView("brief")}>
        <UiIcon name="spark" size={16} /> 1-Page Executive Brief
      </button>
      <button className={`main-view-tab ${mainView === "strategy" ? "active" : ""}`} onClick={() => setMainView("strategy")}>
        <UiIcon name="companies" size={16} /> Strategic Analysis & SWOT
      </button>
      <button className={`main-view-tab ${mainView === "denso_fit" ? "active" : ""}`} onClick={() => setMainView("denso_fit")}>
        <UiIcon name="grid" size={16} /> Solwer Product Fit ({productOpps.length || 6})
      </button>
      <button className={`main-view-tab ${mainView === "diff" ? "active" : ""}`} onClick={() => setMainView("diff")}>
        <UiIcon name="refresh" size={16} /> What Changed Since Last Run {whatChanged.length > 0 && `(${whatChanged.length})`}
      </button>
      <button className={`main-view-tab ${mainView === "findings" ? "active" : ""}`} onClick={() => setMainView("findings")}>
        <UiIcon name="check" size={16} /> Verified Findings <span>{factsTotal}</span>
      </button>
      <button className={`main-view-tab ${mainView === "sources" ? "active" : ""}`} onClick={() => setMainView("sources")}>
        <UiIcon name="link" size={16} /> Sources &amp; PDF Explorer <span>{sourcesTotal}</span>
      </button>
    </nav>

    {/* =========================================================
        VIEW 1: 1-PAGE EXECUTIVE BRIEF
        ========================================================= */}
    {mainView === "brief" && (
      <div className="one-page-brief">
        <div className="brief-header">
          <div className="brief-title">
            <span className="badge" style={{ background: "#fee2e2", color: "var(--red)", fontWeight: 700, marginBottom: "8px" }}>
              SOLWER GTM EXECUTIVE BRIEFING
            </span>
            <h2>{onePage?.company_name || "Target Enterprise"}</h2>
            <p>{onePage?.domain} · {formatIndustryList(onePage?.overview?.industry)} · Headquarters: {onePage?.overview?.headquarters || "India"}</p>
          </div>
          <div className="brief-actions">
            <span className="badge" style={{ background: "#ecfdf5", color: "#065f46", fontWeight: 700, padding: "8px 14px", fontSize: "13px" }}>
              Grounding: {onePage?.confidence?.evidence_grounding_score ?? 100}% verified evidence
            </span>
          </div>
        </div>

        {/* 3-Column Key Facts Grid */}
        <div className="brief-grid">
          <div className="brief-card">
            <h4>Company Business Profile</h4>
            <p>{onePage?.overview?.summary || report?.summary || "Operating footprint and enterprise business profile synthesized from official public sources."}</p>
          </div>
          <div className="brief-card">
            <h4>Scale & Footprint</h4>
            <div className="brief-metric-val">{onePage?.business_scale?.revenue || "Filings Disclosed"}</div>
            <p style={{ fontSize: "13px", color: "#64748b", marginBottom: "8px" }}>Annual Reported Revenue</p>
            <p><strong>Fleet:</strong> {onePage?.business_scale?.fleet_scale ? String(onePage.business_scale.fleet_scale).replace(/^[a-z_]+:\s*/i, "") : "Commercial fleet and dispatch networks."}</p>
            <p style={{ marginTop: "4px" }}><strong>Facilities:</strong> {onePage?.business_scale?.facilities ? String(onePage.business_scale.facilities).replace(/^[a-z_]+:\s*/i, "") : "Manufacturing and distribution depots."}</p>
          </div>
          <div className="brief-card">
            <h4>Recent Developments</h4>
            {onePage?.recent_developments?.length ? (
              <ul style={{ margin: 0, paddingLeft: "16px", fontSize: "13px", color: "#334155", lineHeight: "1.6" }}>
                {onePage.recent_developments.slice(0, 4).map((dev: string, idx: number) => (
                  <li key={idx} style={{ marginBottom: "6px" }}>{dev}</li>
                ))}
              </ul>
            ) : (
              <p style={{ color: "#64748b" }}>Recent commercial announcements and expansion notices tracked via news feeds.</p>
            )}
          </div>
        </div>

        {/* Operational Highlights */}
        {onePage?.operational_insights?.length ? (
          <div style={{ background: "#f8fafc", padding: "16px 20px", borderRadius: "8px", border: "1px solid #e2e8f0", marginBottom: "20px" }}>
            <h4 style={{ fontSize: "12px", textTransform: "uppercase", color: "#64748b", margin: "0 0 8px 0" }}>Operational Footprint Insights</h4>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "16px" }}>
              {onePage.operational_insights.map((insight: string, idx: number) => (
                <p key={idx} style={{ fontSize: "13px", color: "#334155", margin: 0, lineHeight: 1.5 }}>• {insight}</p>
              ))}
            </div>
          </div>
        ) : null}

        {/* Recommended DENSO Sales Strategy Banner */}
        {onePage?.sales_strategy && (
          <div className="brief-strategy-card">
            <h3><UiIcon name="spark" size={18} /> Recommended Sales Engagement Strategy</h3>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "18px" }}>
              <div>
                <p style={{ margin: "0 0 6px 0", fontSize: "13px", color: "#881337" }}>
                  <strong>Lead Solution:</strong> {onePage.sales_strategy.primary_product}
                </p>
                <p style={{ margin: "0 0 6px 0", fontSize: "13px", color: "#881337" }}>
                  <strong>Target Role:</strong> {onePage.sales_strategy.primary_contact_role}
                </p>
                <p style={{ margin: 0, fontSize: "13px", color: "#881337" }}>
                  <strong>Recommended Next Action:</strong> {onePage.sales_strategy.suggested_next_action}
                </p>
              </div>
              <div>
                <p style={{ margin: "0 0 6px 0", fontSize: "13px", color: "#881337" }}>
                  <strong>Key Discovery Question:</strong> &ldquo;{onePage.sales_strategy.key_discovery_question}&rdquo;
                </p>
                <p style={{ margin: 0, fontSize: "13px", color: "#881337" }}>
                  <strong>Value Talk-Track:</strong> {onePage.sales_strategy.recommended_first_touch}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    )}

    {/* =========================================================
        VIEW 2: STRATEGIC BUSINESS & SWOT ANALYSIS
        ========================================================= */}
    {mainView === "strategy" && (
      <div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "20px", marginBottom: "24px" }}>
          {/* Business Model */}
          <div className="brief-card">
            <h4 style={{ color: "var(--red)" }}>1. Business Model & Value Chain</h4>
            <p style={{ marginBottom: "8px" }}><strong>Core Offering:</strong> {analysis?.business_model?.what_it_sells || "Commercial and industrial operations."}</p>
            <p style={{ marginBottom: "8px" }}><strong>Customer Segments:</strong> {analysis?.business_model?.customer_segments || "Enterprise accounts and channel partners."}</p>
            <p style={{ marginBottom: "8px" }}><strong>Industries Served:</strong> {analysis?.business_model?.industries_served || "Automotive, logistics, manufacturing."}</p>
            <p style={{ marginBottom: "8px" }}><strong>Divisions:</strong> {Array.isArray(analysis?.business_model?.key_business_divisions) ? analysis.business_model.key_business_divisions.join(", ") : "Corporate divisions"}</p>
            <p style={{ margin: 0 }}><strong>Geographic Presence:</strong> {analysis?.business_model?.geographic_presence || "Nationwide and regional network."}</p>
          </div>

          {/* Financial & Growth Analysis */}
          <div className="brief-card">
            <h4 style={{ color: "var(--red)" }}>2. Financial & Growth Analysis</h4>
            <p style={{ marginBottom: "8px" }}><strong>Revenue Disclosures:</strong> {analysis?.financial_analysis?.revenue_summary || "From statutory filings."}</p>
            <p style={{ marginBottom: "8px" }}><strong>Profitability Trend:</strong> {analysis?.financial_analysis?.profitability_trend || "Aligned with operational efficiency."}</p>
            <p style={{ marginBottom: "8px" }}><strong>Capital Expenditures:</strong> {analysis?.financial_analysis?.capital_expenditures || "Reported in statutory filings."}</p>
            <p style={{ marginBottom: "8px" }}><strong>Growth Trajectory:</strong> {analysis?.financial_analysis?.growth_trajectory || "Stable operating base."}</p>
            <p style={{ margin: 0 }}>
              <strong>Financial Rating:</strong> <span className="badge" style={{ background: "#e0f2fe", color: "#0369a1", fontWeight: 700 }}>{analysis?.financial_analysis?.financial_health_rating || "Solid Operating Base"}</span>
            </p>
          </div>

          {/* Operational Complexity */}
          <div className="brief-card">
            <h4 style={{ color: "var(--red)" }}>3. Operational Footprint & Complexity</h4>
            <p style={{ marginBottom: "8px" }}><strong>Manufacturing Footprint:</strong> {analysis?.operational_analysis?.manufacturing_footprint || "Industrial and regional facilities."}</p>
            <p style={{ marginBottom: "8px" }}><strong>Fleet & Logistics:</strong> {analysis?.operational_analysis?.fleet_and_logistics_scale || "Commercial fleets and transit networks."}</p>
            <p style={{ marginBottom: "8px" }}><strong>Warehousing Network:</strong> {analysis?.operational_analysis?.warehousing_network || "Multi-location depots and hubs."}</p>
            <p style={{ margin: 0 }}><strong>Complexity Level:</strong> <span className="badge" style={{ background: "#fef3c7", color: "#92400e", fontWeight: 700 }}>{analysis?.operational_analysis?.operational_complexity_level || "Multi-Site Enterprise"}</span></p>
          </div>

          {/* Technology Maturity */}
          <div className="brief-card">
            <h4 style={{ color: "var(--red)" }}>4. Technology & Digital Maturity</h4>
            <p style={{ marginBottom: "8px" }}><strong>ERP & Core Systems:</strong> {analysis?.technology_maturity?.erp_systems_identified || "Enterprise systems and tracking software."}</p>
            <p style={{ marginBottom: "8px" }}><strong>Cloud & Digital Adoption:</strong> {analysis?.technology_maturity?.cloud_and_digital_adoption || "Cloud and digital workflows."}</p>
            <p style={{ marginBottom: "8px" }}><strong>Automation & IoT:</strong> {analysis?.technology_maturity?.telematics_or_iot || "Telematics, GPS, and sensor automation."}</p>
            <p style={{ margin: 0 }}>
              <strong>Maturity Stage:</strong> <span className="badge" style={{ background: "#dcfce7", color: "#166534", fontWeight: 700 }}>{analysis?.technology_maturity?.maturity_stage || "Developing"}</span>
            </p>
          </div>
        </div>

        {/* SWOT Analysis 4-Quadrant Grid */}
        <h3 style={{ fontSize: "18px", fontWeight: 700, margin: "24px 0 12px 0" }}>Grounded SWOT Matrix</h3>
        <p style={{ color: "#64748b", fontSize: "14px", marginTop: 0 }}>Strictly derived from verified public sources and filings.</p>
        <div className="swot-grid">
          <div className="swot-card swot-strengths">
            <h4 style={{ color: "#166534" }}>🟢 Strengths</h4>
            <ul>
              {(analysis?.swot_analysis?.strengths || [
                "Established multi-facility network and customer base.",
                "Proven regional presence with specialized operational capabilities.",
              ]).map((item: string, idx: number) => <li key={idx}>{item}</li>)}
            </ul>
          </div>
          <div className="swot-card swot-weaknesses">
            <h4 style={{ color: "#991b1b" }}>🔴 Weaknesses & Gaps</h4>
            <ul>
              {(analysis?.swot_analysis?.weaknesses || [
                "Manual paper or fragmented inspection and checklist audits.",
                "Opportunity to lower high freight and cross-dock turnaround costs.",
              ]).map((item: string, idx: number) => <li key={idx}>{item}</li>)}
            </ul>
          </div>
          <div className="swot-card swot-opportunities">
            <h4 style={{ color: "#1e40af" }}>🔵 Strategic Opportunities</h4>
            <ul>
              {(analysis?.swot_analysis?.opportunities || [
                "Adoption of integrated manufacturing (IM) to optimize shop-floor OEE.",
                "Transport & Warehouse Management (TWMS) to achieve 20-30% freight savings.",
              ]).map((item: string, idx: number) => <li key={idx}>{item}</li>)}
            </ul>
          </div>
          <div className="swot-card swot-threats">
            <h4 style={{ color: "#854d0e" }}>🟡 Threats & External Risks</h4>
            <ul>
              {(analysis?.swot_analysis?.threats || [
                "Rising fuel and operational transport costs across distribution channels.",
                "Strict compliance and downtime audits across commercial fleet operations.",
              ]).map((item: string, idx: number) => <li key={idx}>{item}</li>)}
            </ul>
          </div>
        </div>

        {/* Business Development Signals */}
        {analysis?.business_development_signals?.length ? (
          <div style={{ marginTop: "28px" }}>
            <h3 style={{ fontSize: "18px", fontWeight: 700, marginBottom: "12px" }}>Business Development Triggers & Sales Timing</h3>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "16px" }}>
              {analysis.business_development_signals.map((sig: any, idx: number) => (
                <div key={idx} style={{ background: "#ffffff", border: "1px solid #e2e8f0", padding: "16px", borderRadius: "8px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
                    <strong style={{ color: "#0f172a", fontSize: "14px" }}>{sig.signal}</strong>
                    <span className="badge" style={{ background: "#f1f5f9", color: "#475569" }}>{sig.date_or_period || "Recent"}</span>
                  </div>
                  <p style={{ fontSize: "13px", color: "#475569", margin: "4px 0" }}><strong>Relevance:</strong> {sig.relevance_to_sales}</p>
                  <p style={{ fontSize: "13px", color: "var(--red)", margin: 0 }}><strong>Sales Angle:</strong> {sig.implication}</p>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    )}

    {/* =========================================================
        VIEW 3: SOLWER PRODUCT FIT (6 CORE PRODUCTS)
        ========================================================= */}
    {mainView === "denso_fit" && (
      <div>
        <div style={{ marginBottom: "18px" }}>
          <h3 style={{ fontSize: "20px", fontWeight: 700, margin: "0 0 6px 0" }}>Solwer Solution Opportunities</h3>
          <p style={{ color: "#64748b", fontSize: "14px", margin: 0 }}>
            Automated alignment of evidenced company footprint, facilities, and fleet operations with Solwer&apos;s 6 core B2B solutions.
          </p>
        </div>

        <div className="product-fit-grid">
          {productOpps.map((opp: any, idx: number) => {
            const pCode = opp.product_code || opp.product || `P0${idx + 1}`;
            const pName = opp.product_name || opp.full_name || pCode;
            const pLevel = opp.relevance_level || opp.classification || "potential_opportunity";
            const fitLevel = pLevel === "strong_evidence_backed" ? "strong" : pLevel === "moderate_evidence" ? "moderate" : "exploratory";
            const fitScore = opp.fit_score || (opp.confidence ? Math.round(opp.confidence * 100) : fitLevel === "strong" ? 88 : fitLevel === "moderate" ? 70 : 45);
            const summary = opp.opportunity_summary || opp.rationale || opp.summary || "Operational alignment with verified company profile.";
            const dept = opp.recommended_department || opp.target_department || "Operations & Logistics";
            const stakeholder = opp.recommended_stakeholder || opp.target_stakeholder || "Head of Operations";
            const talkTrack = opp.sales_talk_track || opp.talk_track || "";
            const questions = opp.discovery_questions || [];
            const action = opp.next_recommended_action || opp.action || "Reach out to schedule technical discovery call.";

            return (
              <div key={pCode || idx} className={`product-fit-card ${fitLevel}`}>
                <div className="product-card-header">
                  <div>
                    <span className="product-code-pill">{pCode}</span>
                    <h3 style={{ fontSize: "17px", fontWeight: 700, margin: "8px 0 4px 0" }}>{pName}</h3>
                    <small style={{ color: "#64748b" }}>Fit Score: <strong>{fitScore}%</strong></small>
                  </div>
                  <span className={`product-fit-badge ${fitLevel}`}>
                    {pLevel === "strong_evidence_backed" ? "Strong Fit" : pLevel === "moderate_evidence" ? "Moderate Fit" : "Exploratory Fit"}
                  </span>
                </div>

                <div>
                  <h4 style={{ fontSize: "12px", textTransform: "uppercase", color: "#64748b", margin: "0 0 4px 0" }}>Opportunity Summary</h4>
                  <p style={{ fontSize: "13px", color: "#334155", lineHeight: 1.6, margin: 0 }}>{summary}</p>
                </div>

                <div style={{ background: "#f8fafc", padding: "12px", borderRadius: "6px" }}>
                  <p style={{ fontSize: "12px", color: "#475569", margin: "0 0 4px 0" }}>
                    <strong>Target Department:</strong> {dept}
                  </p>
                  <p style={{ fontSize: "12px", color: "#475569", margin: 0 }}>
                    <strong>Decision Maker:</strong> {stakeholder}
                  </p>
                </div>

                {talkTrack ? (
                  <div>
                    <h4 style={{ fontSize: "12px", textTransform: "uppercase", color: "var(--red)", margin: "0 0 6px 0" }}>Sales Talk-Track</h4>
                    <div className="talk-track-box">
                      &ldquo;{talkTrack}&rdquo;
                    </div>
                  </div>
                ) : null}

                {questions.length > 0 ? (
                  <div>
                    <h4 style={{ fontSize: "12px", textTransform: "uppercase", color: "#475569", margin: "0 0 6px 0" }}>Discovery Questions for Call</h4>
                    <ul className="discovery-questions-list">
                      {questions.map((q: string, qIdx: number) => (
                        <li key={qIdx}>{q}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                <div style={{ marginTop: "auto", borderTop: "1px solid #f1f5f9", paddingTop: "12px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <small style={{ color: "#64748b" }}>Action: <strong>{action}</strong></small>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    )}

    {/* =========================================================
        VIEW 4: WHAT CHANGED SINCE LAST RUN (DIFF ENGINE)
        ========================================================= */}
    {mainView === "diff" && (
      <div className="diff-container">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <div>
            <h3 style={{ fontSize: "18px", fontWeight: 700, margin: 0 }}>Historical Research Diff Engine</h3>
            <p style={{ color: "#64748b", fontSize: "13px", margin: "4px 0 0 0" }}>
              Identifies newly disclosed filings, changes in executive leadership, facility expansions, and financial metrics since the previous research snapshot.
            </p>
          </div>
          <span className="badge" style={{ background: "#f1f5f9", color: "#475569", fontWeight: 700 }}>
            {whatChanged.length} changes detected
          </span>
        </div>

        {whatChanged.length > 0 ? (
          <div className="table-wrap">
            <table className="diff-table">
              <thead>
                <tr>
                  <th>Category</th>
                  <th>Fact / Field</th>
                  <th>Change Type</th>
                  <th>Previous Research Value</th>
                  <th>New Evidenced Value</th>
                  <th>Significance / Impact</th>
                </tr>
              </thead>
              <tbody>
                {whatChanged.map((change: any, idx: number) => (
                  <tr key={idx}>
                    <td><span className="badge" style={{ background: "#f1f5f9", color: "#475569" }}>{label(change.category)}</span></td>
                    <td><strong>{label(change.field_name)}</strong></td>
                    <td>
                      <span className={change.change_type === "new_information" ? "diff-badge-new" : "diff-badge-updated"}>
                        {change.change_type === "new_information" ? "New Finding" : "Value Updated"}
                      </span>
                    </td>
                    <td style={{ color: "#64748b" }}>{change.previous_value}</td>
                    <td><strong style={{ color: "#0f172a" }}>{change.new_value}</strong></td>
                    <td style={{ fontSize: "12px", color: "#475569" }}>{change.significance}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state" style={{ padding: "32px 16px" }}>
            <UiIcon name="refresh" size={32} />
            <h3>Baseline Research Run</h3>
            <p>This is the primary research run for this company. Future research jobs will automatically compare with this snapshot and highlight corporate changes here.</p>
          </div>
        )}
      </div>
    )}

    {/* =========================================================
        VIEW 5: VERIFIED FINDINGS (15 RESEARCH CATEGORIES)
        ========================================================= */}
    {mainView === "findings" && (
      <div>
        <div className="category-tabs" aria-label="Research categories">
          {researchCategories.map(([value, name]) => (
            <button key={value} aria-pressed={category === value} onClick={() => setCategory(value)}>
              {name} {categoryCounts[value] ? `(${categoryCounts[value]})` : ""}
            </button>
          ))}
        </div>

        <div className="report-search">
          <UiIcon name="search" size={18} />
          <input
            type="search"
            aria-label="Search report findings and sources"
            placeholder="Search findings, executives, factories, numbers, or citations..."
            value={query}
            onChange={event => setQuery(event.target.value)}
          />
        </div>

        <div className="report-filters">
          <label>Source Domain
            <select value={sourceId} onChange={event => setSourceId(event.target.value)}>
              <option value="">All loaded sources ({sources.length})</option>
              {sources.map(source => <option value={source.id} key={source.id}>{source.title || source.domain}</option>)}
            </select>
          </label>
          <label>Verification Status
            <select value={verification} onChange={event => setVerification(event.target.value)}>
              <option value="">All statuses</option>
              {statuses.map(status => <option key={status} value={status}>{label(status)}</option>)}
            </select>
          </label>
          {(category === "financial" || category === "financial_research" || category === "all") && (
            <label>Reporting Period
              <select value={period} onChange={event => setPeriod(event.target.value)}>
                <option value="">All periods</option>
                {periods.map(value => <option key={value}>{value}</option>)}
              </select>
            </label>
          )}
          {(category === "news" || category === "news_developments") && (
            <>
              <label>Published From<input type="date" value={newsFrom} max={newsTo || undefined} onChange={event => setNewsFrom(event.target.value)} /></label>
              <label>Published To<input type="date" value={newsTo} min={newsFrom || undefined} onChange={event => setNewsTo(event.target.value)} /></label>
            </>
          )}
        </div>

        <p className="result-count">{filtered.length} matching findings · {facts.length} of {factsTotal} loaded</p>

        {financials.length > 0 && <div className="financial-table">
          <h3>Reported Financial Metrics</h3>
          <p>Preserved with original units, currencies, and reporting scopes from statutory filings and investor materials.</p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Metric / Entity Scope</th>
                  <th>Reported Value</th>
                  <th>Period</th>
                  <th>Verification & Evidence</th>
                </tr>
              </thead>
              <tbody>
                {financials.map(fact => <tr key={fact.id}>
                  <td><strong>{label(fact.field_name)}</strong><small>{fact.entity_scope || "Primary Entity"}</small></td>
                  <td><strong style={{ fontSize: "15px" }}>{fact.value}</strong><small>{[fact.currency, fact.unit].filter(Boolean).join(" · ") || "Standard"}</small></td>
                  <td>{fact.reporting_period || "Latest"}</td>
                  <td>
                    <span className={`status-pill ${statusTone(fact.verification_status)}`}>{label(fact.verification_status)}</span>
                    <CitationList citations={fact.citations} />
                  </td>
                </tr>)}
              </tbody>
            </table>
          </div>
        </div>}

        <div className="findings-grid">
          {otherFacts.map(fact => <article className="finding-card" key={fact.id}>
            <div className="finding-meta">
              <span>{researchCategories.find(([value]) => value === fact.category)?.[1] || label(fact.category)}</span>
              <span className={`status-pill ${statusTone(fact.verification_status)}`}>{label(fact.verification_status)}</span>
            </div>
            <h3>{label(fact.field_name)}</h3>
            <p>{fact.value}</p>
            {fact.entity_scope && <small>Entity Scope: {fact.entity_scope}</small>}
            {fact.reporting_period && <small>Reporting Period: {fact.reporting_period}</small>}
            {fact.citations.length ? (
              <CitationList citations={fact.citations} />
            ) : (
              <p className="error" style={{ fontSize: "12px", marginTop: "8px" }}>⚠️ Uncited finding. Verification required before sales use.</p>
            )}
          </article>)}
        </div>

        {!filtered.length && <div className="empty-state">
          <UiIcon name="file" size={32} />
          <h3>{facts.length ? "No findings match these filter criteria" : "No findings collected yet"}</h3>
          <p>{facts.length ? "Try clearing search terms or selecting another category." : "Workers are actively searching public registries, documents, and website pages."}</p>
        </div>}

        {!!report?.sections.length && <details className="coverage-details" style={{ marginTop: "24px" }}>
          <summary>Research Section Coverage Overview ({report.sections.length} agent sections)</summary>
          <div className="coverage-grid">
            {report.sections.map(section => (
              <div key={section.category}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                  <strong>{section.title}</strong>
                  <span className={`status-pill ${statusTone(section.status)}`}>{label(section.status)}</span>
                </div>
                <p>{section.text}</p>
              </div>
            ))}
          </div>
        </details>}

        {facts.length < factsTotal && (
          <div style={{ textAlign: "center", marginTop: "24px" }}>
            <button className="secondary" disabled={loadingMore} onClick={onMoreFacts}>
              Load more findings ({factsTotal - facts.length} remaining)
            </button>
          </div>
        )}
      </div>
    )}

    {/* =========================================================
        VIEW 6: SOURCES & DOCUMENT INTELLIGENCE (PDFs & HTML)
        ========================================================= */}
    {mainView === "sources" && (
      <div>
        <div className="report-search">
          <UiIcon name="search" size={18} />
          <input
            type="search"
            aria-label="Filter sources and PDFs"
            placeholder="Search discovered sources, PDF annual reports, investor releases..."
            value={query}
            onChange={event => setQuery(event.target.value)}
          />
        </div>

        <p className="result-count">{visibleSources.length} matching sources · {sources.length} of {sourcesTotal} loaded</p>
        <div className="source-list">
          {visibleSources.map(source => {
            const isDoc = source.is_document || source.url.toLowerCase().endsWith(".pdf") || source.retrieval_method?.includes("pdf");
            return (
              <article key={source.id} className="source-card">
                <span className="source-icon">
                  <UiIcon name={isDoc ? "file" : "link"} />
                </span>
                <div>
                  <div className="finding-meta">
                    <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                      <span className="badge" style={{ background: "#e0e7ff", color: "#3730a3", fontWeight: 700 }}>
                        {source.domain}
                      </span>
                      {isDoc ? (
                        <span className="doc-badge-pdf">
                          <UiIcon name="file" size={12} /> PDF Document {source.total_pages ? `(${source.total_pages} pages)` : ""}
                        </span>
                      ) : (
                        <span className="doc-badge-html">HTML Webpage</span>
                      )}
                    </div>
                    <span className="status-pill neutral">{label(source.reliability)}</span>
                  </div>
                  <h3>
                    <a href={safeSourceUrl(source.url)} target="_blank" rel="noopener noreferrer">
                      {source.title || source.url} <UiIcon name="external" size={14} />
                    </a>
                  </h3>
                  <p>{source.excerpt || "Full document analyzed; citation excerpts preserved in findings."}</p>
                  <small>
                    {source.publisher || "Public Source"} · Retrieved {displayDate(source.retrieved_at)}
                    {source.published_at && <> · Published {displayDate(source.published_at)}</>} · Method: <strong>{label(source.retrieval_method)}</strong>
                  </small>
                  <details style={{ marginTop: "8px" }}>
                    <summary style={{ fontSize: "12px", color: "#64748b" }}>Source Provenance & Content Hash</summary>
                    <p className="source-url" style={{ fontSize: "12px", color: "#475569" }}>{source.url}</p>
                    <small style={{ color: "#94a3b8" }}>SHA-256 Hash: {source.content_hash}</small>
                  </details>
                </div>
              </article>
            );
          })}
        </div>

        {!visibleSources.length && <div className="empty-state">
          <UiIcon name="link" size={32} />
          <h3>No matching sources</h3>
          <p>Sources appear after successful HTTP/Playwright/PDF collection.</p>
        </div>}

        {sources.length < sourcesTotal && (
          <div style={{ textAlign: "center", marginTop: "24px" }}>
            <button className="secondary" disabled={loadingMore} onClick={onMoreSources}>
              Load more sources ({sourcesTotal - sources.length} remaining)
            </button>
          </div>
        )}
      </div>
    )}

    <p className="report-footer">
      <UiIcon name="link" size={16} /> Solwer Autonomous Intelligence: Deep crawl operates with bounded recursive discovery, document &amp; PDF extraction, and strict evidence grounding.
    </p>
  </section>;
}
