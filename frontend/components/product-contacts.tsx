"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchProductContacts, type ProductContact } from "../lib/products";
import BulkOutreachModal from "./bulk-outreach-modal";
import { useProduct } from "./product-workspace";
import UiIcon from "./ui-icon";

export default function ProductContacts() {
  const product = useProduct();
  const [contacts, setContacts] = useState<ProductContact[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [showBulkModal, setShowBulkModal] = useState(false);
  const [modalPreselect, setModalPreselect] = useState<string[] | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setContacts([]);
    fetchProductContacts(product.id)
      .then((items) => { if (!cancelled) setContacts(items); })
      .catch((error: Error) => { if (!cancelled) setError(error.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [product.id]);

  const visible = contacts.filter((contact) =>
    `${contact.name ?? ""} ${contact.company_name} ${contact.email ?? ""} ${contact.title ?? ""}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );

  const reachableVisible = visible.filter((c) => Boolean(c.email && c.email.trim()));

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (reachableVisible.length === 0) return;
    const allSelected = reachableVisible.every((c) => selectedIds.has(c.id));
    if (allSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(reachableVisible.map((c) => c.id)));
    }
  };

  const handleOpenSelected = () => {
    const preselected = Array.from(selectedIds).map((id) => `contact_${id}`);
    setModalPreselect(preselected);
    setShowBulkModal(true);
  };

  const handleOpenAll = () => {
    setModalPreselect(undefined);
    setShowBulkModal(true);
  };

  return (
    <section>
      <div className="page-heading">
        <div>
          <p className="eyebrow">CONTACTS</p>
          <h1>Contacts &amp; Outreach</h1>
          <p>
            Saved decision-makers and contacts for companies associated with {product.name}.
            Select contacts below or launch bulk outreach to email leads separately.
          </p>
        </div>
        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          {selectedIds.size > 0 && (
            <button
              type="button"
              className="button-link"
              onClick={handleOpenSelected}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "8px",
                background: "#0f172a",
                color: "#fff",
                padding: "9px 18px",
                fontSize: "14px",
                borderRadius: "8px",
                cursor: "pointer",
                fontWeight: 600,
              }}
            >
              <UiIcon name="mail" size={16} /> Send Email to Selected ({selectedIds.size})
            </button>
          )}
          <button
            type="button"
            className="button-link"
            onClick={handleOpenAll}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              padding: "9px 18px",
              fontSize: "14px",
              cursor: "pointer",
            }}
          >
            <UiIcon name="mail" size={16} /> ✉️ Email All Leads / Bulk Outreach
          </button>
        </div>
      </div>

      {error && <div role="alert" className="alert">{error}</div>}

      <div className="company-toolbar">
        <div className="report-search">
          <UiIcon name="search" size={18} />
          <input
            type="search"
            aria-label="Search contacts"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search name, company, title or email…"
          />
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
          {selectedIds.size > 0 && (
            <span style={{ fontSize: "13px", fontWeight: 600, color: "#dc2626" }}>
              ✓ {selectedIds.size} selected
              <button
                type="button"
                onClick={() => setSelectedIds(new Set())}
                style={{
                  background: "none",
                  border: "none",
                  color: "#64748b",
                  textDecoration: "underline",
                  cursor: "pointer",
                  marginLeft: "8px",
                  fontSize: "12px",
                }}
              >
                Clear
              </button>
            </span>
          )}
          <span className="result-count">{visible.length} of {contacts.length} contacts</span>
        </div>
      </div>

      {loading ? (
        <div className="empty-state"><p>Loading contacts…</p></div>
      ) : contacts.length === 0 ? (
        <div className="empty-state">
          <UiIcon name="companies" size={26} />
          <h3>No contacts yet</h3>
          <p>Open a company's Lead 360 profile to search Apollo or add a contact manually.</p>
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th style={{ width: "44px", textAlign: "center" }}>
                  <input
                    type="checkbox"
                    aria-label="Select all contacts"
                    checked={reachableVisible.length > 0 && reachableVisible.every((c) => selectedIds.has(c.id))}
                    onChange={toggleSelectAll}
                    style={{ width: "16px", height: "16px", cursor: "pointer" }}
                  />
                </th>
                <th>Name</th>
                <th>Company</th>
                <th>Title</th>
                <th>Email</th>
                <th>Verification</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((contact) => {
                const hasEmail = Boolean(contact.email && contact.email.trim());
                const isSelected = selectedIds.has(contact.id);
                return (
                  <tr
                    key={contact.id}
                    style={{ background: isSelected ? "#fef2f2" : undefined }}
                  >
                    <td style={{ textAlign: "center" }}>
                      <input
                        type="checkbox"
                        aria-label={`Select ${contact.name || contact.email || "contact"}`}
                        checked={isSelected}
                        disabled={!hasEmail}
                        onChange={() => toggleSelect(contact.id)}
                        style={{ width: "16px", height: "16px", cursor: hasEmail ? "pointer" : "not-allowed" }}
                      />
                    </td>
                    <td>
                      <strong>{contact.name || "Name unavailable"}</strong>
                      {contact.is_key_decision_maker && <span className="badge">Decision maker</span>}
                    </td>
                    <td><Link href={`/leads/${encodeURIComponent(contact.lead_id)}`}>{contact.company_name}</Link></td>
                    <td>{contact.title || "—"}</td>
                    <td>
                      {hasEmail ? (
                        <span style={{ fontFamily: "monospace", fontSize: "13px" }}>{contact.email}</span>
                      ) : (
                        <span style={{ color: "#94a3b8", fontStyle: "italic" }}>No email address</span>
                      )}
                    </td>
                    <td><span className="badge">{contact.verification_status}</span></td>
                    <td>
                      {hasEmail ? (
                        <button
                          type="button"
                          className="button-link secondary"
                          style={{ fontSize: "12px", padding: "4px 10px", cursor: "pointer" }}
                          onClick={() => {
                            setModalPreselect([`contact_${contact.id}`]);
                            setShowBulkModal(true);
                          }}
                        >
                          ✉️ Email
                        </button>
                      ) : (
                        <Link
                          href={`/leads/${encodeURIComponent(contact.lead_id)}`}
                          className="button-link secondary"
                          style={{ fontSize: "12px", padding: "4px 10px" }}
                        >
                          View lead
                        </Link>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {!loading && contacts.length > 0 && visible.length === 0 && (
        <div className="empty-state"><h3>No matching contacts</h3><p>Try a different search.</p></div>
      )}

      <BulkOutreachModal
        isOpen={showBulkModal}
        productId={product.id}
        productName={product.name}
        initialSelectedIds={modalPreselect}
        onClose={() => setShowBulkModal(false)}
      />
    </section>
  );
}
