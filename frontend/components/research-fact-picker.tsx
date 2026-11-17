"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { intelligenceRequest as request, label, type JobSummary, type Page, type ResearchFact } from "../lib/intelligence";
import { CitationList } from "./intelligence-report";
import UiIcon from "./ui-icon";

export default function ResearchFactPicker({ leadId, selected, onChange }: {
  leadId: string; selected: string[]; onChange: (ids: string[]) => void;
}) {
  const [facts, setFacts] = useState<ResearchFact[]>([]);
  const [companyId, setCompanyId] = useState("");
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let active = true;
    setFacts([]); setCompanyId(""); setError(""); setTotal(0); setLoading(true);
    void request<Page<JobSummary>>(`/intelligence/research?lead_id=${encodeURIComponent(leadId)}&limit=1`).then(async history => {
      if (!active || !history.items.length) return;
      const id = history.items[0].company_id;
      const found = await request<Page<ResearchFact>>(`/intelligence/companies/${id}/facts?limit=100&offset=0`);
      if (active) { setCompanyId(id); setFacts(found.items); setTotal(found.total); }
    }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "Could not load research facts."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [leadId, version]);
  const eligible = facts.filter(fact => ["reported", "verified", "partially_verified"].includes(fact.verification_status) && fact.citations.length);
  return <details className="outreach-research-picker"><summary><UiIcon name="link" size={16} /> Add reviewed company intelligence <span className="count-badge">{selected.length} selected</span></summary>
    <p>Select up to 20 relevant, source-backed findings you have reviewed. The server validates that each finding belongs to this recipient&apos;s company. Selection never approves an email.</p>
    <div className="actions"><button type="button" className="secondary" disabled={loading} onClick={() => setVersion(value => value + 1)}><UiIcon name="refresh" size={14} /> Refresh facts</button>
      {selected.length > 0 && <button type="button" className="secondary" onClick={() => onChange([])}>Clear selected facts</button>}
      <Link href={`/leads/${encodeURIComponent(leadId)}#research`} className="text-link">Review company research <UiIcon name="external" size={14} /></Link></div>
    {error && <p role="alert" className="error">{error}</p>}
    {loading && <p>Loading saved evidence...</p>}
    {!loading && !error && !eligible.length && <p>No eligible cited facts are loaded for this company. Research it from Lead 360, then review the findings. Conflicting, unsupported and hypothesis-only claims cannot be selected.</p>}
    <div className="fact-picker-list">{eligible.map(fact => <div key={fact.id} className="fact-picker-item">
      <label className="recipient-option"><input type="checkbox" checked={selected.includes(fact.id)}
        disabled={!selected.includes(fact.id) && selected.length >= 20}
        onChange={event => onChange(event.target.checked ? [...selected, fact.id] : selected.filter(id => id !== fact.id))} />
        <span><strong>{label(fact.field_name)}</strong><small>{fact.value}</small><small>{label(fact.verification_status)}{fact.reporting_period ? ` · ${fact.reporting_period}` : ""}</small></span></label>
      <CitationList citations={fact.citations} />
    </div>)}</div>
    {facts.length < total && <button type="button" className="secondary" disabled={loading} onClick={() => {
      setLoading(true); setError("");
      void request<Page<ResearchFact>>(`/intelligence/companies/${companyId}/facts?limit=100&offset=${facts.length}`).then(found => {
        setFacts(current => [...current, ...found.items]); setTotal(found.total);
      }).catch(reason => setError(reason instanceof Error ? reason.message : "Could not load more evidence.")).finally(() => setLoading(false));
    }}>Load more saved facts</button>}
  </details>;
}
