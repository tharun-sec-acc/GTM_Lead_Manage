"use client";

import { useMemo, useState } from "react";
import { displayDate, label, statusTone, type Citation, type ResearchFact, type ResearchReport, type ResearchSource } from "../lib/intelligence";
import UiIcon from "./ui-icon";

export const researchCategories = [
  ["all", "All findings"], ["company", "Company overview"], ["news", "News & developments"],
  ["financial", "Financials"], ["funding", "Funding"], ["leadership", "Leadership"],
  ["competitors", "Market & competitors"], ["signals", "Business signals"],
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

export default function IntelligenceReport({ facts, sources, report, factsTotal, sourcesTotal, loadingMore, onMoreFacts, onMoreSources }: {
  facts: ResearchFact[]; sources: ResearchSource[]; report: ResearchReport | null;
  factsTotal: number; sourcesTotal: number; loadingMore: boolean; onMoreFacts: () => void; onMoreSources: () => void;
}) {
  const [category, setCategory] = useState("all");
  const [query, setQuery] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [verification, setVerification] = useState("");
  const [period, setPeriod] = useState("");
  const [newsFrom, setNewsFrom] = useState("");
  const [newsTo, setNewsTo] = useState("");
  const [tab, setTab] = useState<"findings" | "sources">("findings");

  const distinctDomains = useMemo(() => Array.from(new Set(sources.map(s => s.domain).filter(Boolean))), [sources]);
  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = { all: facts.length };
    for (const f of facts) {
      counts[f.category] = (counts[f.category] || 0) + 1;
    }
    return counts;
  }, [facts]);

  const periods = Array.from(new Set(facts.filter(fact => fact.category === "financial").map(fact => fact.reporting_period).filter((value): value is string => !!value)));
  const statuses = Array.from(new Set(facts.map(fact => fact.verification_status)));

  const filtered = useMemo(() => facts.filter(fact => {
    if (category !== "all" && fact.category !== category) return false;
    if (query && !`${fact.field_name} ${fact.value} ${fact.citations.map(citation => `${citation.title} ${citation.excerpt}`).join(" ")}`.toLowerCase().includes(query.toLowerCase())) return false;
    if (sourceId && !fact.citations.some(citation => citation.source_id === sourceId)) return false;
    if (verification && fact.verification_status !== verification) return false;
    if (period && fact.category === "financial" && fact.reporting_period !== period) return false;
    if (fact.category === "news" && (newsFrom || newsTo)) {
      return fact.citations.some(citation => citation.published_at &&
        (!newsFrom || citation.published_at.slice(0, 10) >= newsFrom) &&
        (!newsTo || citation.published_at.slice(0, 10) <= newsTo));
    }
    return true;
  }), [facts, category, query, sourceId, verification, period, newsFrom, newsTo]);

  const financials = filtered.filter(fact => fact.category === "financial");
  const otherFacts = filtered.filter(fact => fact.category !== "financial");
  const visibleSources = sources.filter(source => !query || `${source.title} ${source.domain} ${source.excerpt}`.toLowerCase().includes(query.toLowerCase()));

  function exportReport() {
    if (!report) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify({
      report, facts, sources, exported_at: new Date().toISOString(),
      included_facts: facts.length, total_facts: factsTotal, included_sources: sources.length, total_sources: sourcesTotal
    }, null, 2)], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url; link.download = `company-research-${report.id}.json`; link.click(); URL.revokeObjectURL(url);
  }

  return <section className="research-report">
    <div className="section-title">
      <div>
        <p className="eyebrow">VERIFIED EVIDENCE REPOSITORY</p>
        <h2>Company Intelligence Report</h2>
        <p>{report ? `Report version ${report.version} · Generated ${displayDate(report.created_at)}` : "Verified findings appear as autonomous workers finish scraping and synthesis."}</p>
      </div>
      <button className="secondary" disabled={!report} onClick={exportReport}>
        <UiIcon name="file" size={16} /> Export Research JSON
      </button>
    </div>

    {/* Executive Metrics Overview */}
    <div className="stats" style={{ margin: "20px 0" }}>
      <div>
        <strong>{factsTotal}</strong>
        <span>Evidence-backed findings</span>
      </div>
      <div>
        <strong>{sourcesTotal}</strong>
        <span>Discovered public sources</span>
      </div>
      <div>
        <strong>{distinctDomains.length}</strong>
        <span>Distinct public domains</span>
      </div>
      <div>
        <strong>{Object.keys(categoryCounts).filter(k => k !== "all").length} / 7</strong>
        <span>Research categories covered</span>
      </div>
    </div>

    {report?.summary && <div className="executive-summary">
      <span className="icon-tile"><UiIcon name="spark" /></span>
      <div>
        <h3>Executive Intelligence Brief</h3>
        <p>{report.summary}</p>
        <small>Grounded in verified public sources. Every factual claim is paired with supporting citation excerpts.</small>
      </div>
    </div>}

    {!!report?.limitations.length && <details className="research-limitations">
      <summary>Research Scope & Discovery Limitations ({report.limitations.length})</summary>
      <ul>{report.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul>
    </details>}

    <div className="report-tabbar" role="tablist" aria-label="Report views">
      <button role="tab" id="findings-tab" aria-selected={tab === "findings"} aria-controls="report-panel" onClick={() => setTab("findings")}>
        Research Findings <span>{factsTotal}</span>
      </button>
      <button role="tab" id="sources-tab" aria-selected={tab === "sources"} aria-controls="report-panel" onClick={() => setTab("sources")}>
        Autonomous Sources & Citations <span>{sourcesTotal}</span>
      </button>
    </div>

    <div className="report-search">
      <UiIcon name="search" size={18} />
      <input type="search" aria-label="Search report findings and sources" placeholder="Filter findings, executives, numbers, patents, or citations..." value={query} onChange={event => setQuery(event.target.value)} />
    </div>

    <div id="report-panel" role="tabpanel" aria-labelledby={`${tab}-tab`}>
      {tab === "findings" ? <>
        <div className="category-tabs" aria-label="Research categories">
          {researchCategories.map(([value, name]) => (
            <button key={value} aria-pressed={category === value} onClick={() => setCategory(value)}>
              {name} {categoryCounts[value] ? `(${categoryCounts[value]})` : ""}
            </button>
          ))}
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
          {(category === "financial" || category === "all") && (
            <label>Reporting Period
              <select value={period} onChange={event => setPeriod(event.target.value)}>
                <option value="">All periods</option>
                {periods.map(value => <option key={value}>{value}</option>)}
              </select>
            </label>
          )}
          {category === "news" && (
            <>
              <label>Published From<input type="date" value={newsFrom} max={newsTo || undefined} onChange={event => setNewsFrom(event.target.value)} /></label>
              <label>Published To<input type="date" value={newsTo} min={newsFrom || undefined} onChange={event => setNewsTo(event.target.value)} /></label>
            </>
          )}
        </div>

        <p className="result-count">{filtered.length} matching findings · {facts.length} of {factsTotal} loaded</p>

        {financials.length > 0 && <div className="financial-table">
          <h3>Reported Financial Metrics</h3>
          <p>Preserved with original units, currencies, and reporting scopes from filings and investor materials.</p>
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
          <p>{facts.length ? "Try clearing search terms or selecting another category." : "Workers are actively searching public registries and website pages."}</p>
        </div>}

        {!!report?.sections.length && <details className="coverage-details" style={{ marginTop: "24px" }}>
          <summary>Research Section Coverage Overview</summary>
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
      </> : <>
        <p className="result-count">{visibleSources.length} matching sources · {sources.length} of {sourcesTotal} loaded</p>
        <div className="source-list">
          {visibleSources.map(source => <article key={source.id} className="source-card">
            <span className="source-icon"><UiIcon name="link" /></span>
            <div>
              <div className="finding-meta">
                <span className="badge" style={{ background: "#e0e7ff", color: "#3730a3", fontWeight: 700 }}>
                  {source.domain}
                </span>
                <span className="status-pill neutral">{label(source.reliability)}</span>
              </div>
              <h3>
                <a href={safeSourceUrl(source.url)} target="_blank" rel="noopener noreferrer">
                  {source.title || source.url} <UiIcon name="external" size={14} />
                </a>
              </h3>
              <p>{source.excerpt || "Full page analyzed; excerpt retained in citation links."}</p>
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
          </article>)}
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
      </>}
    </div>

    <p className="report-footer">
      <UiIcon name="link" size={16} /> DENSO Evidence Assurance: Autonomous internet discovery operates under strict SSRF protections, robot policies, and de-duplication rules.
    </p>
  </section>;
}
