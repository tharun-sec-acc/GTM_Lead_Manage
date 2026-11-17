"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchGlobalOverview, type GlobalOverview } from "../lib/products";

export default function GlobalOverviewPanel() {
  const [data, setData] = useState<GlobalOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchGlobalOverview()
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="empty-state"><p>Loading global overview…</p></div>;
  if (error) return <div className="alert">{error}</div>;
  if (!data) return null;

  return (
    <div>
      <div className="page-heading">
        <div>
          <p className="eyebrow">GLOBAL OVERVIEW</p>
          <h1>All Products</h1>
          <p>Consolidated performance across all product workspaces.</p>
        </div>
      </div>

      <div className="stats">
        <div>
          <strong>{data.unique_companies}</strong>
          <span>Master companies</span>
        </div>
        <div>
          <strong>{data.product_associations}</strong>
          <span>Product associations</span>
        </div>
        <div>
          <strong>{data.product_associated_companies}</strong>
          <span>Companies in a product</span>
        </div>
        <div>
          <strong>{data.unique_contacts}</strong>
          <span>Active contacts</span>
        </div>
        <div>
          <strong>{data.product_associated_contacts}</strong>
          <span>Product contacts</span>
        </div>
        <div>
          <strong>{data.total_campaigns}</strong>
          <span>Campaigns</span>
        </div>
        <div>
          <strong>{data.total_messages}</strong>
          <span>Messages</span>
        </div>
        <div>
          <strong>{data.total_replies}</strong>
          <span>Replies</span>
        </div>
      </div>

      <section>
        <div className="section-title">
          <h2>By Product</h2>
          <p>{data.metrics_note}</p>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Product</th>
                <th>Status</th>
                <th>Companies</th>
                <th>Contacts</th>
                <th>Campaigns</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.per_product.map((p) => (
                <tr key={p.product_id}>
                  <td><strong>{p.product_name}</strong></td>
                  <td>
                    <span className={`status-pill ${p.status === "active" ? "positive" : "neutral"}`}>
                      {p.status}
                    </span>
                  </td>
                  <td>{p.associated_companies}</td>
                  <td>{p.active_contacts}</td>
                  <td>{p.campaigns_count}</td>
                  <td>
                    {p.status === "active" && (
                      <Link href={`/products/${p.slug}`} className="text-link">Open workspace →</Link>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}