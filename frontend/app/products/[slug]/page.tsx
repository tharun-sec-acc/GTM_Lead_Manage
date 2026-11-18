"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import ProductWorkspace from "../../../components/product-workspace";
import BulkOutreachModal from "../../../components/bulk-outreach-modal";
import UiIcon from "../../../components/ui-icon";
import { fetchProducts, fetchProductOverview, type ProductOverview } from "../../../lib/products";

export default function ProductPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const [overview, setOverview] = useState<ProductOverview | null>(null);
  const [productId, setProductId] = useState<string | null>(null);
  const [productName, setProductName] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showBulkModal, setShowBulkModal] = useState(false);

  useEffect(() => {
    setLoading(true);
    setOverview(null);
    setError(null);
    fetchProducts("active").then((products) => {
      const p = products.find((x) => x.slug === slug || (slug === "vehicle-digital-inspection" && x.slug === "vdi"));
      if (!p) { setError("Product not found."); setLoading(false); return; }
      setProductId(p.id);
      setProductName(p.name);
      return fetchProductOverview(p.id).then(setOverview);
    }).catch((e: Error) => setError(e.message)).finally(() => setLoading(false));
  }, [slug]);

  const reloadOverview = () => {
    if (productId) {
      fetchProductOverview(productId).then(setOverview).catch(() => {});
    }
  };

  const totalMessages = overview
    ? Object.values(overview.messages_by_status).reduce((a, b) => a + b, 0)
    : 0;
  const sentMessages = overview?.messages_by_status?.sent ?? overview?.messages_by_status?.smtp_accepted ?? 0;
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
            <div>
              <button
                type="button"
                className="button-link"
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "8px",
                  fontSize: "14px",
                  padding: "9px 18px",
                  boxShadow: "0 2px 8px rgba(220, 38, 38, 0.2)",
                  cursor: "pointer",
                }}
                onClick={() => setShowBulkModal(true)}
              >
                <UiIcon name="mail" size={16} /> ✉️ Email All Leads / Bulk Outreach
              </button>
            </div>
          </div>
          <BulkOutreachModal
            isOpen={showBulkModal}
            productId={productId}
            productName={productName}
            onClose={() => setShowBulkModal(false)}
            onSuccess={reloadOverview}
          />
          <div className="stats">
            <Link href={`/products/${slug}/companies`} className="stat-card" title="Click to view associated companies">
              <strong>{overview.associated_companies}</strong>
              <span>Associated companies</span>
              <small>Click to view companies</small>
            </Link>
            <Link href={`/products/${slug}/contacts`} className="stat-card" title="Click to view & select contacts">
              <strong>{overview.active_contacts}</strong>
              <span>Active contacts</span>
              <small>Click to select &amp; email</small>
            </Link>
            <Link href="/followups" className="stat-card" title="Click to view outreach messages">
              <strong>{totalMessages}</strong>
              <span>Total messages</span>
              <small>Click to view tracking</small>
            </Link>
            <Link href="/followups" className="stat-card" title="Click to view sent messages">
              <strong>{sentMessages}</strong>
              <span>SMTP accepted</span>
              <small>Click to view sent</small>
            </Link>
            <Link href="/followups" className="stat-card" title="Click to review drafts">
              <strong>{draftMessages}</strong>
              <span>Drafts</span>
              <small>Click to review</small>
            </Link>
            <Link href="/followups" className="stat-card" title="Click to view prospect replies">
              <strong>{overview.replies_count}</strong>
              <span>Replies</span>
              <small>Click to view inbox</small>
            </Link>
            <Link href={`/products/${slug}/meetings`} className="stat-card" title="Click to view open meeting tasks">
              <strong>{overview.meeting_tasks_open}</strong>
              <span>Meeting tasks open</span>
              <small>Click to view calendar</small>
            </Link>
          </div>
        </>
      ) : null}
    </ProductWorkspace>
  );
}