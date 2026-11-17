"use client";

import { useEffect, useState } from "react";
import { fetchProductOverview, type ProductOverview } from "../lib/products";
import { useProduct } from "./product-workspace";

export default function ProductAnalytics() {
  const product = useProduct();
  const [overview, setOverview] = useState<ProductOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setOverview(null);
    fetchProductOverview(product.id, startDate || undefined, endDate || undefined)
      .then((data) => { if (!cancelled) setOverview(data); })
      .catch((error: Error) => { if (!cancelled) setError(error.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [product.id, startDate, endDate]);

  const messages = overview
    ? Object.entries(overview.messages_by_status).sort(([a], [b]) => a.localeCompare(b))
    : [];

  return (
    <section>
      <div className="page-heading">
        <div>
          <p className="eyebrow">ANALYTICS</p>
          <h1>Analytics</h1>
          <p>Persisted counts for {product.name}. No projections or estimated figures.</p>
        </div>
      </div>

      <div className="company-toolbar">
        <label>From<input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></label>
        <label>To<input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></label>
        <button className="secondary" onClick={() => { setStartDate(""); setEndDate(""); }}>Clear dates</button>
      </div>
      <p className="field-help">
        Dates filter campaigns, messages and replies. Company, contact and pipeline counts are current state.
      </p>

      {error && <div role="alert" className="alert">{error}</div>}
      {loading && <div className="empty-state"><p>Loading analytics…</p></div>}

      {overview && (
        <>
          <div className="stats">
            <div><strong>{overview.associated_companies}</strong><span>Associated companies</span></div>
            <div><strong>{overview.active_contacts}</strong><span>Active contacts</span></div>
            <div><strong>{overview.campaigns_count}</strong><span>Campaigns</span></div>
            <div><strong>{overview.contacted_companies}</strong><span>Companies contacted</span></div>
            <div><strong>{overview.contacted_company_percent ?? "—"}</strong><span>Contacted %</span></div>
            <div><strong>{overview.replies_count}</strong><span>Replies</span></div>
            <div><strong>{overview.meeting_tasks_open}</strong><span>Open meeting tasks</span></div>
            <div><strong>{overview.research_jobs_completed}/{overview.research_jobs}</strong><span>Research completed</span></div>
          </div>

          <div className="detail">
            <h3>Messages by status</h3>
            {messages.length === 0 ? <p>No messages in this range.</p> : (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Status</th><th>Messages</th></tr></thead>
                  <tbody>
                    {messages.map(([status, count]) => (
                      <tr key={status}><td>{status}</td><td>{count}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="detail">
            <h3>Pipeline</h3>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Stage</th><th>Companies</th></tr></thead>
                <tbody>
                  {Object.entries(overview.pipeline).map(([stage, count]) => (
                    <tr key={stage}><td>{stage.replace(/_/g, " ")}</td><td>{count}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <p className="field-help">{overview.metrics_note}</p>
        </>
      )}
    </section>
  );
}
