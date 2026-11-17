"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchProductSalesTasks, type ProductSalesTask } from "../lib/products";
import { useProduct } from "./product-workspace";
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
      .then((items) => { if (!cancelled) setTasks(items); })
      .catch((error: Error) => { if (!cancelled) setError(error.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [product.id]);

  const open = tasks.filter((task) => task.status === "open");
  const completed = tasks.filter((task) => task.status !== "open");

  return (
    <section>
      <div className="page-heading">
        <div>
          <p className="eyebrow">MEETINGS</p>
          <h1>Meeting requests</h1>
          <p>
            Replies classified as meeting requests become sales tasks attributed to {product.name} through
            their campaign. These are requests to arrange a meeting, not scheduled meetings.
          </p>
        </div>
      </div>

      {error && <div role="alert" className="alert">{error}</div>}

      <div className="actions">
        <Link className="button-link secondary" href="/meetings">Check organizer availability</Link>
      </div>
      <p className="field-help">
        Booking, Outlook events, Teams join links and invitations are not implemented. Availability shown
        elsewhere is informational.
      </p>

      {loading ? (
        <div className="empty-state"><p>Loading tasks…</p></div>
      ) : tasks.length === 0 ? (
        <div className="empty-state">
          <UiIcon name="calendar" size={26} />
          <h3>No meeting-request tasks for this product</h3>
          <p>Tasks appear when a matched reply is classified as a meeting request.</p>
        </div>
      ) : (
        <>
          <h3>Open ({open.length})</h3>
          {open.length === 0 ? <p>No open meeting tasks.</p> : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Company</th><th>Reply</th><th>Classification</th><th>Created</th><th /></tr></thead>
                <tbody>
                  {open.map((task) => (
                    <tr key={task.id}>
                      <td><Link href={`/leads/${encodeURIComponent(task.lead_id)}`}>{task.company_name}</Link></td>
                      <td>{task.subject || task.sender || "Reply"}</td>
                      <td><span className="badge">{task.classification || "unclassified"}</span></td>
                      <td>{new Date(task.created_at).toLocaleString()}</td>
                      <td><Link className="button-link secondary" href="/followups">Open outreach</Link></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {completed.length > 0 && (
            <>
              <h3>Completed ({completed.length})</h3>
              <div className="list">
                {completed.map((task) => (
                  <div className="list-item" key={task.id}>
                    <span>{task.company_name} · {task.subject || task.title}</span>
                    <span className="badge">{task.status}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}
