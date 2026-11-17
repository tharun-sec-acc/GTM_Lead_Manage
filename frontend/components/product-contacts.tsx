"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchProductContacts, type ProductContact } from "../lib/products";
import { useProduct } from "./product-workspace";
import UiIcon from "./ui-icon";

export default function ProductContacts() {
  const product = useProduct();
  const [contacts, setContacts] = useState<ProductContact[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

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

  return (
    <section>
      <div className="page-heading">
        <div>
          <p className="eyebrow">CONTACTS</p>
          <h1>Contacts</h1>
          <p>Active saved contacts for companies associated with {product.name}. Contacts are shared across products.</p>
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
        <span className="result-count">{visible.length} of {contacts.length} contacts</span>
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
                <th>Name</th>
                <th>Company</th>
                <th>Title</th>
                <th>Email</th>
                <th>Verification</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((contact) => (
                <tr key={contact.id}>
                  <td>
                    <strong>{contact.name || "Name unavailable"}</strong>
                    {contact.is_key_decision_maker && <span className="badge">Decision maker</span>}
                  </td>
                  <td><Link href={`/leads/${encodeURIComponent(contact.lead_id)}`}>{contact.company_name}</Link></td>
                  <td>{contact.title || "—"}</td>
                  <td>{contact.email || "Unavailable"}</td>
                  <td><span className="badge">{contact.verification_status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!loading && contacts.length > 0 && visible.length === 0 && (
        <div className="empty-state"><h3>No matching contacts</h3><p>Try a different search.</p></div>
      )}
    </section>
  );
}
