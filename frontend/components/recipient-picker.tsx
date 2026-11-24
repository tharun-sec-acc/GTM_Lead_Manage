"use client";

import { useEffect, useState } from "react";
import UiIcon from "./ui-icon";
import { getApiBase } from "../lib/api-config";

type Lead = { id: string; company_name: string; email: string | null };
type Contact = { id: string; name: string | null; title: string | null; email: string | null };

export default function RecipientPicker({
  campaignId,
  leads,
  fixedLeadId,
  contactVersion,
  enrolledEmails,
  busy,
  act,
  onAdded,
}: {
  campaignId: string;
  leads: Lead[];
  fixedLeadId?: string;
  contactVersion: string;
  enrolledEmails: string[];
  busy: boolean;
  act: (action: () => Promise<unknown>) => void;
  onAdded: (count: number) => void;
}) {
  const [selectedLeadId, setSelectedLeadId] = useState("");
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [selectedContacts, setSelectedContacts] = useState<string[]>([]);
  const [manual, setManual] = useState("");
  const [includeImported, setIncludeImported] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Quick inline contact addition
  const [showAddForm, setShowAddForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [addingContact, setAddingContact] = useState(false);

  const leadId = fixedLeadId || selectedLeadId;
  const lead = leads.find(item => item.id === leadId);
  const enrolled = new Set(enrolledEmails.map(email => email.toLowerCase()));

  const loadContacts = async () => {
    if (!leadId) return;
    setLoading(true);
    try {
      const response = await fetch(`${getApiBase()}/leads/${encodeURIComponent(leadId)}/contacts`, {
        cache: "no-store",
      });
      if (!response.ok) throw new Error("Could not load saved contacts.");
      const items = (await response.json()) as Contact[];
      setContacts(items);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load contacts.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setContacts([]);
    setSelectedContacts([]);
    setManual("");
    setIncludeImported(false);
    setError("");
    void loadContacts();
  }, [leadId, contactVersion]);

  const selected = contacts.filter(contact => selectedContacts.includes(contact.id) && contact.email);
  const manualEmails = manual.split(/[\s,;]+/).filter(Boolean);
  const recipients = [
    ...selected.map(contact => ({ lead_id: leadId, contact_id: contact.id, recipient: contact.email! })),
    ...(includeImported && lead?.email ? [{ lead_id: leadId, contact_id: null, recipient: lead.email }] : []),
    ...manualEmails.map(email => ({ lead_id: leadId, contact_id: null, recipient: email })),
  ];
  const unique = new Map(recipients.map(item => [item.recipient.trim().toLowerCase(), item]));
  const duplicateCount = recipients.length - unique.size;

  async function handleQuickAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim() || !newEmail.trim()) return;
    setAddingContact(true);
    try {
      const res = await fetch(`${getApiBase()}/leads/${encodeURIComponent(leadId)}/contacts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newName.trim(), title: newTitle.trim() || null, email: newEmail.trim() }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => null);
        throw new Error(d?.detail || "Could not add contact.");
      }
      const created = (await res.json()) as Contact;
      setNewName("");
      setNewTitle("");
      setNewEmail("");
      setShowAddForm(false);
      await loadContacts();
      if (created.id) {
        setSelectedContacts(prev => [...prev, created.id]);
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to add contact.");
    } finally {
      setAddingContact(false);
    }
  }

  return (
    <div className="detail" style={{ borderLeft: "4px solid #0284c7", background: "#f8fafc", padding: "20px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px", flexWrap: "wrap", gap: "8px" }}>
        <span className="feature-label" style={{ color: "#0284c7", display: "inline-flex", alignItems: "center", gap: "6px" }}>
          <UiIcon name="companies" size={16} /> SELECT CONTACTS &amp; MAIL RECIPIENTS
        </span>
        <span className="status-pill ai">DECISION MAKER ENROLLMENT</span>
      </div>

      <h3 style={{ margin: "0 0 6px", fontSize: "18px", color: "#0f172a" }}>
        Select Recipients for {lead?.company_name || "Company"}
      </h3>
      <p style={{ margin: "0 0 16px", color: "#64748b", fontSize: "13px" }}>
        Check decision makers below or enter custom emails. Enrolled recipients will automatically receive personalized LeadRoad &lt;&gt; DENSO Solwer TWMS drafts.
      </p>

      {!fixedLeadId && (
        <label>
          Company
          <select value={selectedLeadId} onChange={event => setSelectedLeadId(event.target.value)}>
            <option value="">Choose a company</option>
            {leads.map(item => (
              <option key={item.id} value={item.id}>
                {item.company_name}
              </option>
            ))}
          </select>
        </label>
      )}

      {leadId && (
        <>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}

          {loading ? (
            <p style={{ color: "#64748b" }}>Loading saved company contacts...</p>
          ) : (
            <fieldset disabled={busy} style={{ background: "#ffffff", padding: "14px 18px", borderRadius: "8px", border: "1px solid #e2e8f0" }}>
              <legend style={{ fontWeight: 700, color: "#1e293b", padding: "0 6px" }}>
                Saved Decision Makers &amp; People ({contacts.length})
              </legend>

              {contacts.length === 0 && (
                <div style={{ padding: "8px 0" }}>
                  <p style={{ color: "#64748b", margin: "0 0 8px", fontSize: "14px" }}>
                    No contacts saved yet for this company. Add a key person below or paste their email address directly.
                  </p>
                  {!showAddForm && (
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => setShowAddForm(true)}
                      style={{ fontSize: "13px", padding: "6px 12px" }}
                    >
                      + Add New Contact Inline
                    </button>
                  )}
                </div>
              )}

              {contacts.map(contact => (
                <label className="recipient-option" key={contact.id} style={{ padding: "8px 0", borderBottom: "1px solid #f1f5f9" }}>
                  <input
                    type="checkbox"
                    checked={selectedContacts.includes(contact.id)}
                    disabled={!contact.email || enrolled.has(contact.email.toLowerCase())}
                    onChange={event =>
                      setSelectedContacts(current =>
                        event.target.checked ? [...current, contact.id] : current.filter(id => id !== contact.id)
                      )
                    }
                  />
                  <span>
                    <strong style={{ fontSize: "14px", color: "#0f172a" }}>{contact.name || "Unnamed contact"}</strong>
                    {contact.title ? ` · ${contact.title}` : ""}
                    <small style={{ display: "block", color: "#64748b" }}>
                      {contact.email || "Add an email to this contact first"}
                      {contact.email && enrolled.has(contact.email.toLowerCase()) && " · (Already enrolled in campaign)"}
                    </small>
                  </span>
                </label>
              ))}

              {lead?.email && (
                <label className="recipient-option" style={{ padding: "8px 0" }}>
                  <input
                    type="checkbox"
                    checked={includeImported}
                    disabled={enrolled.has(lead.email.toLowerCase())}
                    onChange={event => setIncludeImported(event.target.checked)}
                  />
                  <span>
                    <strong>Imported company general email</strong>
                    <small style={{ display: "block", color: "#64748b" }}>{lead.email}</small>
                  </span>
                </label>
              )}

              {contacts.length > 0 && !showAddForm && (
                <div style={{ marginTop: "10px" }}>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => setShowAddForm(true)}
                    style={{ fontSize: "12px", padding: "4px 8px" }}
                  >
                    + Add another contact to this company
                  </button>
                </div>
              )}

              {showAddForm && (
                <form
                  onSubmit={handleQuickAdd}
                  style={{
                    background: "#f8fafc",
                    padding: "12px",
                    borderRadius: "6px",
                    border: "1px dashed #cbd5e1",
                    marginTop: "10px",
                  }}
                >
                  <strong style={{ fontSize: "13px", display: "block", marginBottom: "8px", color: "#334155" }}>
                    Quick Add Person to Company
                  </strong>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "8px" }}>
                    <input
                      required
                      placeholder="Name (e.g. Rahul Sharma)"
                      value={newName}
                      onChange={e => setNewName(e.target.value)}
                      style={{ fontSize: "13px", padding: "6px" }}
                    />
                    <input
                      placeholder="Title (e.g. VP Logistics)"
                      value={newTitle}
                      onChange={e => setNewTitle(e.target.value)}
                      style={{ fontSize: "13px", padding: "6px" }}
                    />
                    <input
                      required
                      type="email"
                      placeholder="Business Email"
                      value={newEmail}
                      onChange={e => setNewEmail(e.target.value)}
                      style={{ fontSize: "13px", padding: "6px" }}
                    />
                  </div>
                  <div style={{ display: "flex", gap: "8px", marginTop: "8px" }}>
                    <button
                      type="submit"
                      disabled={addingContact || !newName.trim() || !newEmail.trim()}
                      style={{ fontSize: "12px", padding: "4px 10px" }}
                    >
                      {addingContact ? "Saving..." : "Save & Select"}
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => setShowAddForm(false)}
                      style={{ fontSize: "12px", padding: "4px 8px" }}
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              )}
            </fieldset>
          )}

          <label style={{ marginTop: "14px" }}>
            Or type/paste additional recipient email addresses
            <textarea
              value={manual}
              rows={2}
              onChange={event => setManual(event.target.value)}
              placeholder={"supplychain.head@company.com, logistics.vp@company.com\n(Comma, semicolon, or space-separated)"}
            />
          </label>

          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "10px",
              marginTop: "12px",
            }}
          >
            <p style={{ margin: 0, fontSize: "13px", color: "#475569" }}>
              <strong>{unique.size}</strong> recipient(s) ready to add.
            </p>

            <button
              disabled={busy || loading || unique.size === 0 || unique.size > 100 || duplicateCount > 0}
              onClick={() =>
                act(async () => {
                  const response = await fetch(
                    `${getApiBase()}/campaigns/${encodeURIComponent(campaignId)}/enrollments/bulk`,
                    {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ recipients: Array.from(unique.values()) }),
                    }
                  );
                  const body = await response.json();
                  if (!response.ok)
                    throw new Error(typeof body.detail === "string" ? body.detail : "Could not add recipients.");
                  setSelectedContacts([]);
                  setManual("");
                  setIncludeImported(false);
                  onAdded(body.added);
                })
              }
            >
              <UiIcon name="check" size={16} /> Enroll {unique.size || ""} Recipient{unique.size === 1 ? "" : "s"} into Campaign
            </button>
          </div>

          {duplicateCount > 0 && (
            <p role="alert" className="error" style={{ marginTop: "8px" }}>
              The same address is selected more than once. Remove duplicates before adding.
            </p>
          )}
        </>
      )}
    </div>
  );
}
