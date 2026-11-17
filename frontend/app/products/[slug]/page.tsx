"use client";

import { use, useEffect, useState } from "react";
import ProductWorkspace from "../../../components/product-workspace";
import { fetchProducts, fetchProductOverview, type ProductOverview } from "../../../lib/products";

export default function ProductPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const [overview, setOverview] = useState<ProductOverview | null>(null);
  const [productId, setProductId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setOverview(null);
    setError(null);
    fetchProducts("active").then((products) => {
      const p = products.find((x) => x.slug === slug);
      if (!p) { setError("Product not found."); setLoading(false); return; }
      setProductId(p.id);
      return fetchProductOverview(p.id).then(setOverview);
    }).catch((e: Error) => setError(e.message)).finally(() => setLoading(false));
  }, [slug]);

  const totalMessages = overview
    ? Object.values(overview.messages_by_status).reduce((a, b) => a + b, 0)
    : 0;
  const sentMessages = overview?.messages_by_status?.smtp_accepted ?? 0;
  const draftMessages = overview?.messages_by_status?.draft ?? 0;
  const approvedMessages = overview?.messages_by_status?.approved ?? 0;

  return (
    <ProductWorkspace slug={slug} section="overview">
      {loading ? (
        <div className="empty-state"><p>Loading overview…</p></div>
      ) : error ? (
        <div className="alert">{error}</div>
      ) : overview ? (
        <>
          <div className="page-heading">
            <div>
              <p className="eyebrow">PRODUCT OVERVIEW</p>
              <h1>Dashboard</h1>
            </div>
          </div>
          <div className="stats">
            <div>
              <strong>{overview.associated_companies}</strong>
              <span>Associated companies</span>
            </div>
            <div>
              <strong>{overview.active_contacts}</strong>
              <span>Active contacts</span>
            </div>
            <div>
              <strong>{overview.campaigns_count}</strong>
              <span>Campaigns</span>
            </div>
            <div>
              <strong>{totalMessages}</strong>
              <span>Total messages</span>
            </div>
            <div>
              <strong>{sentMessages}</strong>
              <span>SMTP accepted</span>
            </div>
            <div>
              <strong>{draftMessages}</strong>
              <span>Drafts</span>
            </div>
            <div>
              <strong>{overview.replies_count}</strong>
              <span>Replies</span>
            </div>
            <div>
              <strong>{overview.meeting_tasks_open}</strong>
              <span>Meeting tasks open</span>
            </div>
          </div>
        </>
      ) : null}
    </ProductWorkspace>
  );
}