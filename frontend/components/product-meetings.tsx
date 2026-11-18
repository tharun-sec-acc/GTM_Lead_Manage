"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchProductSalesTasks, type ProductSalesTask } from "../lib/products";
import { useProduct } from "./product-workspace";
import UnifiedMeetingsView from "./unified-meetings-view";
import UiIcon from "./ui-icon";

export default function ProductMeetings() {
  const product = useProduct();
  const [tasks, setTasks] = useState<ProductSalesTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setTasks([]);
    fetchProductSalesTasks(product.id)
      .then((items) => {
        if (!cancelled) setTasks(items);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [product.id]);

  const open = tasks.filter((task) => task.status === "open");
  const completed = tasks.filter((task) => task.status !== "open");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
      {/* Product-Specific Unified Meetings Workspace */}
      <UnifiedMeetingsView
        productId={product.id}
        title={`${product.name} — Meetings & Video Intelligence`}
        description={`Schedule, manage, and analyze Microsoft Teams and Google Meet conversations for ${product.name}.`}
      />

      {/* Prospect Reply Meeting Requests */}
      <section style={{ borderTop: "1px solid var(--border)", paddingTop: 24 }}>
        <div className="page-heading">
          <div>
            <p className="eyebrow">INBOUND REQUESTS</p>
            <h2>Inbound Meeting Requests ({open.length})</h2>
            <p>
              Prospect replies classified as meeting requests attributed to {product.name}. Convert these into scheduled Teams or Google Meet discussions above.
            </p>
          </div>
        </div>

        {error && <div role="alert" className="alert">{error}</div>}

        {loading ? (
          <div className="empty-state"><p>Loading tasks…</p></div>
        ) : tasks.length === 0 ? (
          <div className="empty-state" style={{ padding: 24, textAlign: "center", background: "#f8fafc", borderRadius: 8 }}>
            <UiIcon name="calendar" size={24} />
            <h4 style={{ margin: "8px 0 2px" }}>No pending meeting requests</h4>
            <p style={{ margin: 0, fontSize: 13, color: "var(--muted)" }}>Inbound requests from prospect replies appear here automatically.</p>
          </div>
        ) : (
          <>
            {open.length > 0 && (
              <div className="table-wrap" style={{ marginTop: 12 }}>
                <table>
                  <thead>
                    <tr>
                      <th>Company</th>
                      <th>Reply Subject</th>
                      <th>Classification</th>
                      <th>Received</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {open.map((task) => (
                      <tr key={task.id}>
                        <td>
                          <Link href={`/leads/${encodeURIComponent(task.lead_id)}`}>
                            <strong>{task.company_name}</strong>
                          </Link>
                        </td>
                        <td>{task.subject || task.sender || "Reply"}</td>
                        <td>
                          <span className="badge" style={{ background: "#ede9fe", color: "#6b21a8" }}>
                            {task.classification || "meeting_requested"}
                          </span>
                        </td>
                        <td>{new Date(task.created_at).toLocaleString([], { dateStyle: "short", timeStyle: "short" })}</td>
                        <td>
                          <Link className="button-link secondary" href="/followups" style={{ fontSize: 12, padding: "4px 8px" }}>
                            Open Thread
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {completed.length > 0 && (
              <details style={{ marginTop: 16 }}>
                <summary style={{ cursor: "pointer", fontSize: 13, color: "var(--muted)", fontWeight: 600 }}>
                  Completed Requests ({completed.length})
                </summary>
                <div className="list" style={{ marginTop: 8 }}>
                  {completed.map((task) => (
                    <div className="list-item" key={task.id} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", fontSize: 13 }}>
                      <span>{task.company_name} · {task.subject || task.title}</span>
                      <span className="badge" style={{ background: "#ecfdf5", color: "#065f46" }}>{task.status}</span>
                    </div>
                  ))}
                </div>
              </details>
            )}
          </>
        )}
      </section>
    </div>
  );
}
