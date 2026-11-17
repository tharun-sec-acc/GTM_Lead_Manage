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
  return <details className="citation-details"><summary><UiIcon name="link" size={14} /> {citations.length} supporting {citations.length === 1 ? "source" : "sources"}</summary>
    {citations.map((citation, index) => <div className="citation-card" key={`${citation.source_id}:${index}`}>
      <a href={safeSourceUrl(citation.url)} target="_blank" rel="noopener noreferrer">{citation.title || citation.url}<UiIcon name="external" size={13} /></a>
      {citation.excerpt && <blockquote>{citation.excerpt}</blockquote>}
      <small>{label(citation.reliability)} · Retrieved {displayDate(citation.retrieved_at)}
        {citation.published_at && <> · Published {displayDate(citation.published_at)}</>}
        {citation.page_number !== null && <> · Page {citation.page_number}</>}</small>
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
    const url = URL.createObjectURL(new Blob([JSON.stringify({ report, facts, sources, exported_at: new Date().toISOString(),
      included_facts: facts.length, total_facts: factsTotal, included_sources: sources.length, total_sources: sourcesTotal }, null, 2)], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url; link.download = `company-research-${report.id}.json`; link.click(); URL.revokeObjectURL(url);
  }

  return <section className="research-report">
    <div className="section-title"><div><p className="eyebrow">THE EVIDENCE, ORGANIZED</p><h2>Company intelligence report</h2>
      <p>{report ? `Report version ${report.version} · ${displayDate(report.created_at)}` : "Partial findings appear as research progresses. A final report is not ready yet."}</p></div>
      <button className="secondary" disabled={!report} onClick={exportReport}><UiIcon name="file" size={16} /> Export JSON</button></div>
    {report?.summary && <div className="executive-summary"><span className="icon-tile"><UiIcon name="spark" /></span><div><h3>Executive summary</h3><p>{report.summary}</p>
      <small>Read the cited findings below before using this summary. Confidence is not proof.</small></div></div>}
    {!!report?.limitations.length && <details className="research-limitations"><summary>Coverage & limitations ({report.limitations.length})</summary>
      <ul>{report.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul></details>}
    <div className="report-tabbar" role="tablist" aria-label="Report views">
      <button role="tab" id="findings-tab" aria-selected={tab === "findings"} aria-controls="report-panel" onClick={() => setTab("findings")}>Research findings <span>{factsTotal}</span></button>
      <button role="tab" id="sources-tab" aria-selected={tab === "sources"} aria-controls="report-panel" onClick={() => setTab("sources")}>Sources & citations <span>{sourcesTotal}</span></button>
    </div>
    <div className="report-search"><UiIcon name="search" size={18} /><input type="search" aria-label="Search report findings and sources" placeholder="Search findings, names, figures or source passages..." value={query} onChange={event => setQuery(event.target.value)} /></div>
    <div id="report-panel" role="tabpanel" aria-labelledby={`${tab}-tab`}>
      {tab === "findings" ? <>
        <div className="category-tabs" aria-label="Research categories">{researchCategories.map(([value, name]) =>
          <button key={value} aria-pressed={category === value} onClick={() => setCategory(value)}>{name}</button>)}</div>
        <div className="report-filters">
          <label>Evidence source<select value={sourceId} onChange={event => setSourceId(event.target.value)}><option value="">All loaded sources</option>{sources.map(source => <option value={source.id} key={source.id}>{source.title || source.domain}</option>)}</select></label>
          <label>Verification status<select value={verification} onChange={event => setVerification(event.target.value)}><option value="">All statuses</option>{statuses.map(status => <option key={status} value={status}>{label(status)}</option>)}</select></label>
          {(category === "financial" || category === "all") && <label>Financial period<select value={period} onChange={event => setPeriod(event.target.value)}><option value="">All reporting periods</option>{periods.map(value => <option key={value}>{value}</option>)}</select></label>}
          {category === "news" && <><label>Published from<input type="date" value={newsFrom} max={newsTo || undefined} onChange={event => setNewsFrom(event.target.value)} /></label>
            <label>Published to<input type="date" value={newsTo} min={newsFrom || undefined} onChange={event => setNewsTo(event.target.value)} /></label></>}
        </div>
        {category === "news" && (newsFrom || newsTo) && <p className="muted">Undated news is excluded while date filters are applied. Dates are source-reported, not inferred.</p>}
        <p className="result-count">{filtered.length} matching findings · {facts.length} of {factsTotal} loaded</p>
        {financials.length > 0 && <div className="financial-table"><h3>Reported financial information</h3><p>Original values, units and entity scopes are retained. Missing details are not estimates.</p>
          <div className="table-wrap"><table><thead><tr><th>Metric / entity scope</th><th>Reported value</th><th>Period</th><th>Evidence</th></tr></thead><tbody>
            {financials.map(fact => <tr key={fact.id}><td><strong>{label(fact.field_name)}</strong><small>{fact.entity_scope || "Entity scope not available"}</small></td>
              <td>{fact.value}<small>{[fact.currency, fact.unit].filter(Boolean).join(" · ") || "Currency / unit not available"}</small></td>
              <td>{fact.reporting_period || "Not available"}</td><td><span className={`status-pill ${statusTone(fact.verification_status)}`}>{label(fact.verification_status)}</span><CitationList citations={fact.citations} /></td></tr>)}
          </tbody></table></div></div>}
        <div className="findings-grid">{otherFacts.map(fact => <article className="finding-card" key={fact.id}>
          <div className="finding-meta"><span>{researchCategories.find(([value]) => value === fact.category)?.[1] || label(fact.category)}</span>
            <span className={`status-pill ${statusTone(fact.verification_status)}`}>{label(fact.verification_status)}</span></div>
          <h3>{label(fact.field_name)}</h3><p>{fact.value}</p>
          {fact.entity_scope && <small>Entity scope: {fact.entity_scope}</small>}
          {fact.reporting_period && <small>Reporting period: {fact.reporting_period}</small>}
          {fact.citations.length ? <CitationList citations={fact.citations} /> : <p className="evidence-warning">No supporting citation. Do not treat this as a verified fact.</p>}
        </article>)}</div>
        {!filtered.length && <div className="empty-state"><UiIcon name="file" size={30} /><h3>{facts.length ? "No findings match these filters" : "No supported findings yet"}</h3>
          <p>{facts.length ? "Try a different category, source or search term." : "Missing information is not filled with generated claims. Check agent status and source availability."}</p></div>}
        {!!report?.sections.length && <details className="coverage-details"><summary>Research section coverage</summary><div className="coverage-grid">{report.sections.map(section =>
          <div key={section.category}><strong>{section.title}</strong><span className={`status-pill ${statusTone(section.status)}`}>{label(section.status)}</span><p>{section.text}</p></div>)}</div></details>}
        {facts.length < factsTotal && <button className="secondary" disabled={loadingMore} onClick={onMoreFacts}>Load more findings ({factsTotal - facts.length} remaining)</button>}
      </> : <>
        <p className="result-count">{visibleSources.length} matching sources · {sources.length} of {sourcesTotal} loaded</p>
        <div className="source-list">{visibleSources.map(source => <article key={source.id} className="source-card"><span className="source-icon"><UiIcon name="file" /></span><div>
          <div className="finding-meta"><span>{source.domain}</span><span className="status-pill neutral">{label(source.reliability)}</span></div>
          <h3><a href={safeSourceUrl(source.url)} target="_blank" rel="noopener noreferrer">{source.title || source.url} <UiIcon name="external" size={14} /></a></h3>
          <p>{source.excerpt || "No excerpt retained."}</p><small>{source.publisher || "Publisher not available"} · Retrieved {displayDate(source.retrieved_at)}
            {source.published_at && <> · Published {displayDate(source.published_at)}</>} · {label(source.retrieval_method)}</small>
          <details><summary>Source provenance</summary><p className="source-url">{source.url}</p><small>Content hash: {source.content_hash}</small></details>
        </div></article>)}</div>
        {!visibleSources.length && <div className="empty-state"><UiIcon name="link" size={30} /><h3>No matching sources</h3><p>Sources appear only after a successful retrieval. No citations are invented.</p></div>}
        {sources.length < sourcesTotal && <button className="secondary" disabled={loadingMore} onClick={onMoreSources}>Load more sources ({sourcesTotal - sources.length} remaining)</button>}
      </>}
    </div>
    <p className="report-footer"><UiIcon name="link" size={15} /> Evidence-backed does not mean independently audited. Review source passages and entity identity before using findings.</p>
    {(facts.length < factsTotal || sources.length < sourcesTotal) && <p className="muted">Search, filters and JSON export include loaded records only. Load the remaining records for a complete export.</p>}
  </section>;
}
