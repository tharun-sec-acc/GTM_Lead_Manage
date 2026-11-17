"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  associateProductLead,
  fetchLeads,
  fetchProductLeads,
  removeProductLead,
  updateProductLead,
  type LeadSummary,
  type ProductLead,
} from "../lib/products";
import { useProduct } from "./product-workspace";
import UiIcon from "./ui-icon";

const STAGES = ["prospect", "engaged", "qualified", "proposal", "negotiation", "won", "lost", "on_hold"];
const PRIORITIES = ["high", "medium", "low"];

export default function ProductCompanies() {
  const product = useProduct();
  const [leads, setLeads] = useState<ProductLead[]>([]);
  const [allLeads, setAllLeads] = useState<LeadSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [query, setQuery] = useState("");
  const [stageFilter, setStageFilter] = useState("all");
  const [associateId, setAssociateId] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setLeads([]);
    setAllLeads([]);
    Promise.all([fetchProductLeads(product.id), fetchLeads()])
      .then(([productLeads, masterLeads]) => {
        if (controller.signal.aborted) return;
        setLeads(productLeads);
        setAllLeads(masterLeads);
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted) setMessage(error.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [product.id]);

  const associatedIds = useMemo(() => new Set(leads.map((lead) => lead.lead_id)), [leads]);
  const availableLeads = useMemo(
    () => allLeads.filter((lead) => !associatedIds.has(lead.id)),
    [allLeads, associatedIds],
  );

  const visible = leads
    .filter((lead) => stageFilter === "all" || lead.stage === stageFilter)
    .filter((lead) =>
      `${lead.company_name ?? ""} ${lead.domain ?? ""} ${lead.industry ?? ""} ${lead.location ?? ""}`
        .toLowerCase()
        .includes(query.toLowerCase()),
    );

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setMessage("");
    try {
      await action();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unexpected error.");
    } finally {
      setBusy(false);
    }
  }

  function associate() {
    const lead = availableLeads.find((item) => item.id === associateId);
    if (!lead) return;
    void run(async () => {
      const created = await associateProductLead(product.id, lead.id);
      setLeads((current) => [created, ...current]);
      setAllLeads((current) => current);
      setAssociateId("");
      setMessage(`${lead.company_name} was associated with ${product.name}.`);
    });
  }

  function update(leadId: string, patch: { stage?: string; priority?: string }) {
    void run(async () => {
      const updated = await updateProductLead(product.id, leadId, patch);
      setLeads((current) => current.map((item) => (item.lead_id === leadId ? updated : item)));
    });
  }

  function remove(lead: ProductLead) {
    if (!window.confirm(`Remove ${lead.company_name ?? "this company"} from ${product.name}? The master company and its history are kept.`)) {
      return;
    }
    void run(async () => {
      await removeProductLead(product.id, lead.lead_id);
      setLeads((current) => current.filter((item) => item.lead_id !== lead.lead_id));
    });
  }

  return (
    <section>
      <div className="page-heading">
        <div>
          <p className="eyebrow">COMPANIES</p>
          <h1>Companies &amp; leads</h1>
          <p>Master companies are shared. This list is the sales context for {product.name} only.</p>
        </div>
      </div>

      {message && <div role="alert" className="alert">{message}</div>}

      <div className="detail">
        <h3>Associate an existing company</h3>
        <p className="field-help">
          Reuses the master company record instead of importing a duplicate. New companies arrive through Import.
        </p>
        <div className="actions">
          <select aria-label="Company to associate" value={associateId} onChange={(event) => setAssociateId(event.target.value)}>
            <option value="">Select a company…</option>
            {availableLeads.map((lead) => (
              <option key={lead.id} value={lead.id}>
                {lead.company_name}{lead.domain ? ` · ${lead.domain}` : ""}
              </option>
            ))}
          </select>
          <button disabled={busy || !associateId} onClick={associate}>Associate company</button>
        </div>
      </div>

      <div className="company-toolbar">
        <div className="report-search">
          <UiIcon name="search" size={18} />
          <input
            type="search"
            aria-label="Search product companies"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search company, domain, industry or location…"
          />
        </div>
        <label>
          Stage
          <select value={stageFilter} onChange={(event) => setStageFilter(event.target.value)}>
            <option value="all">All stages</option>
            {STAGES.map((stage) => <option key={stage} value={stage}>{stage.replace(/_/g, " ")}</option>)}
          </select>
        </label>
      </div>

      {loading ? (
        <div className="empty-state"><p>Loading companies…</p></div>
      ) : leads.length === 0 ? (
        <div className="empty-state">
          <UiIcon name="companies" size={26} />
          <h3>No companies in this product yet</h3>
          <p>Import a workbook or associate an existing master company above.</p>
        </div>
      ) : (
        <>
          <p className="result-count">{visible.length} of {leads.length} associated companies</p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Company</th>
                  <th>Contacts</th>
                  <th>Stage</th>
                  <th>Priority</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {visible.map((lead) => (
                  <tr key={lead.id}>
                    <td>
                      <Link className="company-name-link" href={`/leads/${encodeURIComponent(lead.lead_id)}`}>
                        <span className="company-avatar small">{(lead.company_name ?? "??").slice(0, 2).toUpperCase()}</span>
                        <span>
                          {lead.company_name ?? "Unknown company"}
                          <small>{lead.domain || "Domain not confirmed"}</small>
                        </span>
                      </Link>
                    </td>
                    <td>{lead.active_contact_count ?? 0}</td>
                    <td>
                      <select
                        aria-label={`Stage for ${lead.company_name ?? lead.lead_id}`}
                        value={lead.stage}
                        disabled={busy}
                        onChange={(event) => update(lead.lead_id, { stage: event.target.value })}
                      >
                        {STAGES.map((stage) => <option key={stage} value={stage}>{stage.replace(/_/g, " ")}</option>)}
                      </select>
                    </td>
                    <td>
                      <select
                        aria-label={`Priority for ${lead.company_name ?? lead.lead_id}`}
                        value={lead.priority}
                        disabled={busy}
                        onChange={(event) => update(lead.lead_id, { priority: event.target.value })}
                      >
                        {PRIORITIES.map((priority) => <option key={priority} value={priority}>{priority}</option>)}
                      </select>
                    </td>
                    <td>
                      <div className="company-row-actions">
                        <Link className="button-link secondary" href={`/leads/${encodeURIComponent(lead.lead_id)}`}>Lead 360</Link>
                        <button className="secondary" disabled={busy} onClick={() => remove(lead)}>Remove</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {visible.length === 0 && (
            <div className="empty-state"><h3>No matching companies</h3><p>Try a different search or stage.</p></div>
          )}
        </>
      )}
    </section>
  );
}
