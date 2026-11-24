"use client";

import { useEffect, useRef, useState } from "react";
import UiIcon from "./ui-icon";
import { getApiBase } from "../lib/api-config";

const API = getApiBase();

type Contact = {
  id: string;
  name: string | null;
  title: string | null;
  email: string | null;
  is_key_decision_maker?: boolean;
};

type Attachment = {
  id: string;
  filename: string;
  size_bytes: number;
};

const DEFAULT_SOLWER_CONTEXT = `DENSO Solwer TWMS (Transport & Warehouse Management System). Digitizes inbound & outbound operations, vehicle selection, load optimization, route planning, real-time tracking, e-POD, and ERP integration (SAP). Delivers potential transport cost savings of up to 20-30%, urgent shipment reduction of 5-25%, and invoicing labor reduction of 10-30%.

Target ICP: PAN India manufacturers, ₹100 Cr+ revenue, 30+ employees, 2-3+ factories/warehouses/dispatch hubs.
Priority Industries: Automotive & Auto Components, Industrial Manufacturing & Engineering.
Decision Makers: Head/VP Supply Chain, Logistics, Operations, Plant Heads, CIO/IT.`;

function getDefaultCopy(company: string) {
  const safeComp = company || "{{company}}";
  return {
    subject: `${safeComp}’s logistics costs`,
    body: `Hi {{First Name}},

Are transport and warehouse costs increasing at ${safeComp}?

For manufacturers managing multiple plants, warehouses, and transporters, - manual coordination, limited shipment visibility, and poor vehicle utilization can increase operation costs.

DENSO's Solwer TWMS helps digitize and optimize inbound and outbound operations, from raw material movement to finished goods delivery and e-POD.

With vehicle selection, load optimization, route planning, and real-time shipment visibility, the platform offers potential transport cost savings of up to 20–30%.

Built on DENSO's 75+ years of manufacturing experience, Solwer can also be customized around your existing processes and ERP.

Would you be open to a quick 15-minute discussion?`,
  };
}

export default function DirectOutreachPanel({
  leadId,
  companyName,
  contactVersion = "",
  onActivity,
}: {
  leadId: string;
  companyName: string;
  contactVersion?: string;
  onActivity?: () => void;
}) {
  const initialCopy = getDefaultCopy(companyName);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [selectedContactIds, setSelectedContactIds] = useState<string[]>([]);
  const [subject, setSubject] = useState(initialCopy.subject);
  const [body, setBody] = useState(initialCopy.body);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [showAddContact, setShowAddContact] = useState(false);
  const [newName, setNewName] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [addingContact, setAddingContact] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const [aiContext, setAiContext] = useState(DEFAULT_SOLWER_CONTEXT);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const bodyTextareaRef = useRef<HTMLTextAreaElement | null>(null);

  const applyFormatting = (prefix: string, suffix: string = "") => {
    const el = bodyTextareaRef.current;
    if (!el) {
      setBody(prev => prev + prefix + suffix);
      return;
    }
    const start = el.selectionStart ?? 0;
    const end = el.selectionEnd ?? 0;
    const current = el.value;
    const selected = current.slice(start, end);
    const replacement = prefix + selected + suffix;
    const next = current.slice(0, start) + replacement + current.slice(end);
    setBody(next);
    setTimeout(() => {
      el.focus();
      const cursor = start + prefix.length + (selected ? selected.length : 0);
      el.setSelectionRange(cursor, cursor);
    }, 0);
  };

  const loadContacts = async () => {
    try {
      const res = await fetch(`${API}/leads/${encodeURIComponent(leadId)}/contacts`, { cache: "no-store" });
      if (!res.ok) throw new Error("Could not load company contacts.");
      const list = (await res.json()) as Contact[];
      setContacts(list);
      // Auto-select all contacts that have email
      setSelectedContactIds(list.filter(c => !!c.email).map(c => c.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load contacts.");
    }
  };

  useEffect(() => {
    loadContacts();
  }, [leadId, contactVersion]);

  useEffect(() => {
    setSubject(initialCopy.subject);
    setBody(initialCopy.body);
  }, [companyName]);

  const toggleContact = (id: string) => {
    setSelectedContactIds(prev =>
      prev.includes(id) ? prev.filter(cId => cId !== id) : [...prev, id]
    );
  };

  const selectAll = () => {
    setSelectedContactIds(contacts.filter(c => !!c.email).map(c => c.id));
  };

  const deselectAll = () => {
    setSelectedContactIds([]);
  };

  const insertVariable = (variableText: string) => {
    setBody(prev => prev + variableText);
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API}/attachments/upload`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const bodyErr = await res.json().catch(() => null);
        throw new Error(bodyErr?.detail || `Upload failed (${res.status})`);
      }
      const data = await res.json();
      setAttachments(prev => [...prev, {
        id: data.id,
        filename: data.filename_safe,
        size_bytes: data.size_bytes,
      }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload attachment.");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const removeAttachment = (id: string) => {
    setAttachments(prev => prev.filter(a => a.id !== id));
  };

  const handleAddContactInline = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    setAddingContact(true);
    setError("");
    try {
      const res = await fetch(`${API}/leads/${encodeURIComponent(leadId)}/contacts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newName.trim(),
          title: newTitle.trim() || null,
          email: newEmail.trim() || null,
        }),
      });
      if (!res.ok) {
        const bodyErr = await res.json().catch(() => null);
        throw new Error(bodyErr?.detail || "Could not save contact.");
      }
      const created = (await res.json()) as Contact;
      setContacts(prev => [...prev, created]);
      if (created.email) {
        setSelectedContactIds(prev => [...prev, created.id]);
      }
      setNewName("");
      setNewTitle("");
      setNewEmail("");
      setShowAddContact(false);
      onActivity?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add contact.");
    } finally {
      setAddingContact(false);
    }
  };

  const handleSendEmails = async () => {
    if (selectedContactIds.length === 0) {
      setError("Please select at least one contact to receive the email.");
      return;
    }
    if (!subject.trim() || !body.trim()) {
      setError("Subject and body cannot be empty.");
      return;
    }
    setSending(true);
    setError("");
    setSuccess("");
    try {
      const res = await fetch(`${API}/leads/${encodeURIComponent(leadId)}/direct-outreach`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          contact_ids: selectedContactIds,
          subject: subject.trim(),
          body: body.trim(),
          attachment_ids: attachments.map(a => a.id),
          send_now: true,
        }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => null);
        throw new Error(errData?.detail || `Send failed (${res.status})`);
      }
      const result = await res.json();
      setSuccess(
        `✓ Outreach successfully sent to ${result.count} contact(s) separately with ${attachments.length} collateral attachment(s)!`
      );
      // Trigger instant parent re-fetch of history and stats
      onActivity?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to dispatch emails.");
    } finally {
      setSending(false);
    }
  };

  const firstSelectedContact = contacts.find(c => selectedContactIds.includes(c.id));
  const previewFirstName = firstSelectedContact?.name ? firstSelectedContact.name.split(" ")[0] : "Vijay";
  const previewSubject = subject.replace(/\{\{company\}\}/gi, companyName).replace(/\{\{First Name\}\}/gi, previewFirstName);
  const previewBody = body.replace(/\{\{company\}\}/gi, companyName).replace(/\{\{First Name\}\}/gi, previewFirstName);

  return (
    <div className="direct-outreach-container">
      {error && (
        <div role="alert" className="alert" style={{ background: "#fef2f2", color: "#991b1b", borderColor: "#fecaca" }}>
          {error}
        </div>
      )}
      {success && (
        <div role="status" className="notice" style={{ background: "#ecfdf5", color: "#065f46", borderColor: "#a7f3d0" }}>
          <UiIcon name="check" size={18} />
          {success}
        </div>
      )}

      {/* Step 1: Decision Makers / Contact Selection */}
      <div className="detail" style={{ marginBottom: "20px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "10px", marginBottom: "12px" }}>
          <div>
            <h3 style={{ margin: 0, fontSize: "17px", color: "#0f172a" }}>
              1. Select Recipients for {companyName}
            </h3>
            <p style={{ margin: "2px 0 0", fontSize: "13px", color: "#64748b" }}>
              Check contacts to email. Each person receives an independent, 1-on-1 personalized outreach email thread.
            </p>
          </div>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <span style={{ fontSize: "13px", fontWeight: 600, color: selectedContactIds.length > 0 ? "#0284c7" : "#64748b" }}>
              {selectedContactIds.length} of {contacts.length} selected
            </span>
            <button type="button" className="secondary" style={{ padding: "4px 8px", fontSize: "12px" }} onClick={selectAll}>
              Select all
            </button>
            <button type="button" className="secondary" style={{ padding: "4px 8px", fontSize: "12px" }} onClick={deselectAll}>
              Deselect all
            </button>
            <button
              type="button"
              className="secondary"
              style={{ padding: "4px 8px", fontSize: "12px" }}
              onClick={() => setShowAddContact(v => !v)}
            >
              + Add Person
            </button>
          </div>
        </div>

        {/* Inline Add Person Form */}
        {showAddContact && (
          <form onSubmit={handleAddContactInline} style={{ background: "#f8fafc", padding: "12px", borderRadius: "6px", border: "1px solid #cbd5e1", marginBottom: "12px" }}>
            <strong style={{ fontSize: "13px" }}>Add person to {companyName}:</strong>
            <div className="grid" style={{ marginTop: "8px", gap: "10px" }}>
              <input
                required
                placeholder="Full Name"
                value={newName}
                onChange={e => setNewName(e.target.value)}
              />
              <input
                placeholder="Title / Designation"
                value={newTitle}
                onChange={e => setNewTitle(e.target.value)}
              />
              <input
                type="email"
                placeholder="Business Email"
                value={newEmail}
                onChange={e => setNewEmail(e.target.value)}
              />
            </div>
            <div style={{ marginTop: "8px", display: "flex", gap: "8px" }}>
              <button type="submit" disabled={addingContact || !newName.trim()} style={{ fontSize: "12px", padding: "6px 12px" }}>
                {addingContact ? "Adding..." : "Save & Select"}
              </button>
              <button type="button" className="secondary" style={{ fontSize: "12px", padding: "6px 12px" }} onClick={() => setShowAddContact(false)}>
                Cancel
              </button>
            </div>
          </form>
        )}

        {/* Contact Checklist Cards */}
        {contacts.length === 0 ? (
          <p style={{ color: "#64748b", fontSize: "14px" }}>
            No contacts recorded yet. Click &quot;+ Add Person&quot; above to add decision makers.
          </p>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "10px" }}>
            {contacts.map(c => {
              const isChecked = selectedContactIds.includes(c.id);
              const hasEmail = !!c.email;
              return (
                <label
                  key={c.id}
                  style={{
                    display: "flex",
                    alignItems: "flex-start",
                    gap: "10px",
                    padding: "10px 12px",
                    background: isChecked ? "#f0fdf4" : "#ffffff",
                    border: `1px solid ${isChecked ? "#86efac" : "#e2e8f0"}`,
                    borderRadius: "6px",
                    cursor: hasEmail ? "pointer" : "default",
                    opacity: hasEmail ? 1 : 0.7,
                  }}
                >
                  <input
                    type="checkbox"
                    checked={isChecked}
                    disabled={!hasEmail}
                    onChange={() => toggleContact(c.id)}
                    style={{ marginTop: "3px", width: "auto" }}
                  />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap" }}>
                      <strong style={{ fontSize: "14px", color: "#0f172a" }}>{c.name || "Unnamed"}</strong>
                      {c.is_key_decision_maker && (
                        <span className="status-pill positive" style={{ fontSize: "10px", padding: "1px 5px" }}>
                          Decision Maker
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: "12px", color: "#64748b", margin: "2px 0" }}>{c.title || "Title unavailable"}</div>
                    <div style={{ fontSize: "12px", color: hasEmail ? "#0284c7" : "#ef4444", fontWeight: 500 }}>
                      {c.email || "No email recorded"}
                    </div>
                  </div>
                </label>
              );
            })}
          </div>
        )}
      </div>

      {/* Step 2: Master Outreach Composer */}
      <div className="detail" style={{ borderLeft: "4px solid var(--red)" }}>
        <div className="section-title" style={{ marginBottom: "12px" }}>
          <div>
            <span className="feature-label">
              <UiIcon name="mail" size={16} /> LEADROAD &lt;&gt; DENSO SOLWER TWMS DIRECT OUTREACH
            </span>
            <h3 style={{ margin: "4px 0 0", fontSize: "18px" }}>
              2. Compose &amp; Send Outreach Email
            </h3>
          </div>
          <div style={{ display: "flex", gap: "8px" }}>
            <button
              type="button"
              className="secondary"
              style={{ fontSize: "12px", padding: "4px 10px" }}
              onClick={() => setShowPreview(v => !v)}
            >
              {showPreview ? "Edit Template" : "👁️ Preview Personalized"}
            </button>
          </div>
        </div>

        {showPreview ? (
          /* Personalized Preview Mode */
          <div style={{ background: "#f8fafc", padding: "16px", borderRadius: "8px", border: "1px solid #cbd5e1" }}>
            <p style={{ margin: 0, fontSize: "12px", color: "#64748b" }}>
              Preview for recipient: <strong>{firstSelectedContact?.name || "Recipient"}</strong> ({firstSelectedContact?.email || "recipient@company.com"})
            </p>
            <div style={{ marginTop: "12px" }}>
              <strong>Subject:</strong> <span style={{ color: "#0f172a" }}>{previewSubject}</span>
            </div>
            <hr style={{ margin: "12px 0", borderColor: "#e2e8f0" }} />
            <pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit", fontSize: "14px", lineHeight: "1.6", margin: 0, color: "#1e293b" }}>
              {previewBody}
            </pre>
            {attachments.length > 0 && (
              <div style={{ marginTop: "14px", paddingTop: "10px", borderTop: "1px dashed #cbd5e1" }}>
                <strong style={{ fontSize: "12px", color: "#475569" }}>Attached Collaterals ({attachments.length}):</strong>
                <div style={{ display: "flex", gap: "8px", marginTop: "6px", flexWrap: "wrap" }}>
                  {attachments.map(att => (
                    <span key={att.id} style={{ fontSize: "12px", background: "#ffffff", padding: "4px 8px", borderRadius: "4px", border: "1px solid #cbd5e1" }}>
                      📄 {att.filename} ({Math.round(att.size_bytes / 1024)} KB)
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          /* Editor Mode */
          <div>
            <label>
              Email Subject Line
              <input
                value={subject}
                onChange={e => setSubject(e.target.value)}
                placeholder="e.g. {{company}}’s logistics costs"
              />
            </label>

            {/* Formatting Toolbar */}
            <div className="composer-toolbar" style={{ marginTop: "12px" }}>
              <button type="button" className="toolbar-btn" onClick={() => applyFormatting("**", "**")} title="Bold">
                <strong>B</strong>
              </button>
              <button type="button" className="toolbar-btn" onClick={() => applyFormatting("*", "*")} title="Italic">
                <em>I</em>
              </button>
              <button type="button" className="toolbar-btn" onClick={() => applyFormatting("\n• ")} title="Bullet List">
                • List
              </button>
              <span className="toolbar-divider" />
              <button type="button" className="toolbar-btn" onClick={() => applyFormatting("{{company}}")} title="Insert Company Variable">
                {"{company}"}
              </button>
              <button type="button" className="toolbar-btn" onClick={() => applyFormatting("{{First Name}}")} title="Insert First Name Variable">
                {"{First Name}"}
              </button>
              <span className="toolbar-divider" />
              <button
                type="button"
                className="toolbar-btn"
                disabled={uploading}
                onClick={() => fileInputRef.current?.click()}
                style={{ color: "#0284c7" }}
                title="Attach Collateral (PDF, Deck, Document)"
              >
                📎 {uploading ? "Uploading..." : "Attach File"}
              </button>
              <input
                type="file"
                ref={fileInputRef}
                style={{ display: "none" }}
                accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg"
                onChange={handleFileUpload}
              />
            </div>

            <label>
              Email Body
              <textarea
                ref={bodyTextareaRef}
                value={body}
                rows={11}
                onChange={e => setBody(e.target.value)}
                style={{ fontFamily: "inherit", lineHeight: "1.6" }}
              />
            </label>

            {/* Uploaded Attachments Pill Area */}
            {attachments.length > 0 && (
              <div style={{ marginTop: "12px", padding: "10px 14px", background: "#f8fafc", borderRadius: "6px", border: "1px solid #e2e8f0" }}>
                <span style={{ fontSize: "12px", color: "#64748b", fontWeight: 600 }}>
                  Collaterals attached to this send ({attachments.length}):
                </span>
                <div style={{ display: "flex", gap: "8px", marginTop: "6px", flexWrap: "wrap" }}>
                  {attachments.map(att => (
                    <span
                      key={att.id}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "6px",
                        background: "#ffffff",
                        border: "1px solid #cbd5e1",
                        borderRadius: "4px",
                        padding: "4px 8px",
                        fontSize: "12px",
                      }}
                    >
                      <span>📄 {att.filename}</span>
                      <span style={{ color: "#94a3b8", fontSize: "11px" }}>({Math.round(att.size_bytes / 1024)} KB)</span>
                      <button
                        type="button"
                        onClick={() => removeAttachment(att.id)}
                        style={{ background: "none", border: "none", cursor: "pointer", color: "#ef4444", padding: "0 2px" }}
                        title="Remove attachment"
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Optional AI Prompt Grounding Details */}
            <details style={{ marginTop: "14px" }}>
              <summary style={{ cursor: "pointer", fontSize: "13px", color: "#475569", fontWeight: 500 }}>
                ✨ Bedrock AI Prompt Grounding (Claude 3.5 Sonnet context)
              </summary>
              <div style={{ marginTop: "10px", padding: "12px", background: "#faf5ff", borderRadius: "6px", border: "1px solid #e9d5ff" }}>
                <label style={{ margin: 0, fontSize: "12px" }}>
                  Product talking points &amp; ICP parameters
                  <textarea
                    value={aiContext}
                    rows={3}
                    onChange={e => setAiContext(e.target.value)}
                    style={{ fontSize: "12px", marginTop: "4px" }}
                  />
                </label>
              </div>
            </details>
          </div>
        )}

        {/* Action Buttons */}
        <div style={{ marginTop: "20px", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "12px", borderTop: "1px solid var(--border)", paddingTop: "16px" }}>
          <p style={{ margin: 0, fontSize: "13px", color: "#64748b" }}>
            Sending sends 1-on-1 personalized emails to each of the{" "}
            <strong>{selectedContactIds.length}</strong> selected recipient(s) directly from your connected mailbox.
          </p>

          <button
            type="button"
            className="btn-send"
            disabled={sending || selectedContactIds.length === 0 || !subject.trim() || !body.trim()}
            onClick={handleSendEmails}
            style={{
              padding: "10px 20px",
              fontSize: "15px",
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
            }}
          >
            <UiIcon name="mail" size={16} />
            {sending
              ? "Sending emails with attachments..."
              : `Send Email Now to Selected (${selectedContactIds.length})`}
          </button>
        </div>
      </div>
    </div>
  );
}
