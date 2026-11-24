"use client";

import { useEffect, useRef, useState } from "react";
import UiIcon from "./ui-icon";
import { getApiBase } from "../lib/api-config";

const API = getApiBase();

export type Recipient = {
  id: string;
  lead_id: string;
  contact_id: string | null;
  company_name: string;
  recipient_name: string;
  title: string | null;
  email: string;
  source: string;
  is_key_decision_maker: boolean;
  suppressed: boolean;
};

type Attachment = {
  id: string;
  filename: string;
  size_bytes: number;
};

type TemplateOption = {
  id: string;
  name: string;
  subject: string;
  body: string;
};

const DEFAULT_TEMPLATES: TemplateOption[] = [
  {
    id: "solwer-twms",
    name: "DENSO Solwer TWMS Outreach (Default)",
    subject: "{{company}}’s logistics costs",
    body: `Hi {{First Name}},

Are transport and warehouse costs increasing at {{company}}?

For manufacturers managing multiple plants, warehouses, and transporters, - manual coordination, limited shipment visibility, and poor vehicle utilization can increase operation costs.

DENSO's Solwer TWMS helps digitize and optimize inbound and outbound operations, from raw material movement to finished goods delivery and e-POD.

With vehicle selection, load optimization, route planning, and real-time shipment visibility, the platform offers potential transport cost savings of up to 20–30%.

Built on DENSO's 75+ years of manufacturing experience, Solwer can also be customized around your existing processes and ERP.

Would you be open to a quick 15-minute discussion?`,
  },
  {
    id: "vehicle-inspection",
    name: "Vehicle Digital Inspection Platform",
    subject: "Digitizing Vehicle Inspection & Fleet Operations for {{company}}",
    body: `Hi {{First Name}},

Managing vehicle health, pre-trip inspection, and yard dispatch at {{company}} often involves manual checklists and paper logs.

DENSO's Vehicle Digital Inspection platform provides automated mobile inspection, AI-assisted defect recognition, and instant compliance reporting across fleets and depots.

With automated workflows and real-time condition tracking, our platform helps reduce inspection cycle times by up to 40% and prevents costly on-road breakdowns.

Would you be open to a brief 15-minute conversation this week to explore how this fits {{company}}'s operations?`,
  },
  {
    id: "short-intro",
    name: "Short Fleet Operations Inquiry",
    subject: "Quick question regarding {{company}}'s transport operations",
    body: `Hi {{First Name}},

I wanted to reach out briefly regarding transport and yard management at {{company}}.

We help commercial fleets and manufacturers reduce turnaround delays and transport costs by 20–30% through DENSO's logistics suite.

Could we connect for a brief 10-minute introductory call this week?`,
  },
];

export default function BulkOutreachModal({
  productId,
  productName,
  isOpen,
  onClose,
  onSuccess,
  initialSelectedIds,
}: {
  productId?: string | null;
  productName?: string;
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
  initialSelectedIds?: string[];
}) {
  const [recipients, setRecipients] = useState<Recipient[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [sourceFilter, setSourceFilter] = useState<"all" | "contact" | "lead">("all");
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  // Template & Composer State
  const [selectedTemplateId, setSelectedTemplateId] = useState("solwer-twms");
  const [subject, setSubject] = useState(DEFAULT_TEMPLATES[0].subject);
  const [body, setBody] = useState(DEFAULT_TEMPLATES[0].body);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const [showPreview, setShowPreview] = useState(false);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const applyFormatting = (prefix: string, suffix: string = "", placeholder: string = "") => {
    const el = textareaRef.current;
    if (!el) {
      setBody(prev => prev + prefix + (placeholder || "") + suffix);
      return;
    }
    const start = el.selectionStart;
    const end = el.selectionEnd;
    const currentText = body;

    if (start !== end) {
      // User selected text: wrap that text
      const selected = currentText.substring(start, end);
      const replacement = prefix + selected + suffix;
      const next = currentText.substring(0, start) + replacement + currentText.substring(end);
      setBody(next);
      setTimeout(() => {
        el.focus();
        el.setSelectionRange(start + prefix.length, start + prefix.length + selected.length);
      }, 10);
    } else {
      // No text selected: insert prefix + placeholder + suffix cleanly
      const insertText = prefix + placeholder + suffix;
      const next = currentText.substring(0, start) + insertText + currentText.substring(end);
      setBody(next);
      setTimeout(() => {
        el.focus();
        const newCursor = start + prefix.length;
        el.setSelectionRange(newCursor, newCursor + placeholder.length);
      }, 10);
    }
  };

  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);
    setError("");
    setNotice("");
    const url = `${API}/outreach/recipients${productId ? `?product_id=${encodeURIComponent(productId)}` : ""}`;
    fetch(url, { cache: "no-store" })
      .then(async res => {
        if (!res.ok) throw new Error("Could not load recipients.");
        const data = await res.json();
        const list = (data.recipients || []) as Recipient[];
        setRecipients(list);
        if (initialSelectedIds && initialSelectedIds.length > 0) {
          setSelectedIds(initialSelectedIds);
        } else {
          // By default select all unsuppressed recipients
          setSelectedIds(list.filter(r => !r.suppressed).map(r => r.id));
        }
      })
      .catch(err => setError(err instanceof Error ? err.message : "Failed to load recipients."))
      .finally(() => setLoading(false));
  }, [isOpen, productId, initialSelectedIds]);

  if (!isOpen) return null;

  const handleTemplateChange = (tplId: string) => {
    setSelectedTemplateId(tplId);
    const found = DEFAULT_TEMPLATES.find(t => t.id === tplId);
    if (found) {
      setSubject(found.subject);
      setBody(found.body);
    }
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
        const errJson = await res.json().catch(() => null);
        throw new Error(errJson?.detail || "Upload failed.");
      }
      const data = await res.json();
      setAttachments(prev => [
        ...prev,
        { id: data.id, filename: data.filename_safe, size_bytes: data.size_bytes },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload collateral.");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const removeAttachment = (id: string) => {
    setAttachments(prev => prev.filter(a => a.id !== id));
  };

  const filteredRecipients = recipients.filter(r => {
    if (sourceFilter === "contact" && r.source !== "Saved Contact") return false;
    if (sourceFilter === "lead" && r.source !== "Company Lead") return false;
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      r.company_name.toLowerCase().includes(q) ||
      r.recipient_name.toLowerCase().includes(q) ||
      r.email.toLowerCase().includes(q) ||
      (r.title && r.title.toLowerCase().includes(q))
    );
  });

  const toggleSelect = (id: string) => {
    setSelectedIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    );
  };

  const selectAllFiltered = () => {
    const idsToAdd = filteredRecipients.filter(r => !r.suppressed).map(r => r.id);
    setSelectedIds(prev => Array.from(new Set([...prev, ...idsToAdd])));
  };

  const deselectAllFiltered = () => {
    const idsToRemove = new Set(filteredRecipients.map(r => r.id));
    setSelectedIds(prev => prev.filter(id => !idsToRemove.has(id)));
  };

  const handleSendBulk = async () => {
    const chosen = recipients.filter(r => selectedIds.includes(r.id) && !r.suppressed);
    if (chosen.length === 0) {
      setError("Please select at least one recipient.");
      return;
    }
    if (!subject.trim() || !body.trim()) {
      setError("Subject and body cannot be empty.");
      return;
    }

    setSending(true);
    setError("");
    setNotice("");
    try {
      const res = await fetch(`${API}/outreach/bulk-send`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          recipients: chosen.map(r => ({
            lead_id: r.lead_id,
            contact_id: r.contact_id,
            email: r.email,
            recipient_name: r.recipient_name,
            company_name: r.company_name,
          })),
          subject: subject.trim(),
          body: body.trim(),
          attachment_ids: attachments.map(a => a.id),
          send_now: true,
          idempotency_key: typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `dispatch-${Date.now()}-${Math.random().toString(36).substring(2)}`,
        }),
      });
      if (!res.ok) {
        const errJson = await res.json().catch(() => null);
        throw new Error(errJson?.detail || "Bulk send failed.");
      }
      const data = await res.json();
      setNotice(
        `✓ Successfully dispatched outreach to ${data.count} lead(s) separately with ${attachments.length} collateral attachment(s)!`
      );
      onSuccess?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to dispatch bulk emails.");
    } finally {
      setSending(false);
    }
  };

  const firstSelected = recipients.find(r => selectedIds.includes(r.id));
  const previewCompany = firstSelected?.company_name || "VRL Logistics";
  const previewName = firstSelected?.recipient_name ? firstSelected.recipient_name.split(" ")[0] : "Vijay";
  const previewSubject = subject.replace(/\{\{company\}\}/gi, previewCompany).replace(/\{\{company_name\}\}/gi, previewCompany).replace(/\{\{First Name\}\}/gi, previewName).replace(/\{\{contact_first_name\}\}/gi, previewName);
  const previewBody = body.replace(/\{\{company\}\}/gi, previewCompany).replace(/\{\{company_name\}\}/gi, previewCompany).replace(/\{\{First Name\}\}/gi, previewName).replace(/\{\{contact_first_name\}\}/gi, previewName);

  return (
    <div className="modal-backdrop" style={{
      position: "fixed",
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      backgroundColor: "rgba(15, 23, 42, 0.65)",
      backdropFilter: "blur(4px)",
      zIndex: 9999,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: "20px",
    }}>
      <div className="modal-content" style={{
        background: "#ffffff",
        width: "100%",
        maxWidth: "1180px",
        height: "90vh",
        maxHeight: "920px",
        borderRadius: "12px",
        boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.25)",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}>
        {/* Modal Header */}
        <div style={{
          padding: "16px 24px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          background: "#fafafa",
        }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span className="feature-label">
                <UiIcon name="mail" size={16} /> BULK EMAIL OUTREACH
              </span>
              {productName && (
                <span className="status-pill neutral" style={{ fontSize: "11px" }}>
                  {productName}
                </span>
              )}
            </div>
            <h2 style={{ margin: "4px 0 0", fontSize: "20px", color: "#0f172a" }}>
              Email All Prospect Leads &amp; Contacts
            </h2>
          </div>
          <button
            type="button"
            className="secondary"
            onClick={onClose}
            style={{ padding: "6px 12px", fontSize: "16px", cursor: "pointer", border: "none", background: "transparent" }}
          >
            ✕
          </button>
        </div>

        {/* Notices & Errors */}
        {error && (
          <div role="alert" className="alert" style={{ margin: "12px 24px 0", background: "#fef2f2", color: "#991b1b", borderColor: "#fecaca" }}>
            {error}
          </div>
        )}
        {notice && (
          <div role="status" className="notice" style={{ margin: "12px 24px 0", background: "#ecfdf5", color: "#065f46", borderColor: "#a7f3d0" }}>
            <UiIcon name="check" size={18} />
            {notice}
          </div>
        )}

        {/* Two-Column Body */}
        <div style={{
          flex: 1,
          display: "grid",
          gridTemplateColumns: "440px 1fr",
          overflow: "hidden",
          borderBottom: "1px solid var(--border)",
        }}>
          {/* Left Column: Recipient Selection */}
          <div style={{
            borderRight: "1px solid var(--border)",
            display: "flex",
            flexDirection: "column",
            background: "#f8fafc",
            overflow: "hidden",
          }}>
            {/* Search & Filter Bar */}
            <div style={{ padding: "14px 16px", borderBottom: "1px solid var(--border)", background: "#ffffff" }}>
              <input
                type="search"
                placeholder="Search companies, contacts, emails..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                style={{ margin: 0, padding: "8px 12px", fontSize: "13px" }}
              />

              <div style={{ display: "flex", gap: "6px", marginTop: "10px", alignItems: "center" }}>
                <button
                  type="button"
                  className={`status-pill ${sourceFilter === "all" ? "positive" : "neutral"}`}
                  style={{ cursor: "pointer", border: "1px solid #cbd5e1" }}
                  onClick={() => setSourceFilter("all")}
                >
                  All ({recipients.length})
                </button>
                <button
                  type="button"
                  className={`status-pill ${sourceFilter === "contact" ? "positive" : "neutral"}`}
                  style={{ cursor: "pointer", border: "1px solid #cbd5e1" }}
                  onClick={() => setSourceFilter("contact")}
                >
                  Contacts ({recipients.filter(r => r.source === "Saved Contact").length})
                </button>
                <button
                  type="button"
                  className={`status-pill ${sourceFilter === "lead" ? "positive" : "neutral"}`}
                  style={{ cursor: "pointer", border: "1px solid #cbd5e1" }}
                  onClick={() => setSourceFilter("lead")}
                >
                  Lead Emails ({recipients.filter(r => r.source === "Company Lead").length})
                </button>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "10px" }}>
                <span style={{ fontSize: "12px", fontWeight: 600, color: selectedIds.length > 0 ? "#0284c7" : "#64748b" }}>
                  {selectedIds.length} of {recipients.length} selected
                </span>
                <div style={{ display: "flex", gap: "6px" }}>
                  <button type="button" className="secondary" style={{ padding: "3px 8px", fontSize: "11px" }} onClick={selectAllFiltered}>
                    Select all
                  </button>
                  <button type="button" className="secondary" style={{ padding: "3px 8px", fontSize: "11px" }} onClick={deselectAllFiltered}>
                    Deselect
                  </button>
                </div>
              </div>
            </div>

            {/* Recipient Checklist */}
            <div style={{ flex: 1, overflowY: "auto", padding: "10px 12px" }}>
              {loading ? (
                <p style={{ textAlign: "center", color: "#64748b", padding: "20px" }}>Loading prospect emails…</p>
              ) : filteredRecipients.length === 0 ? (
                <p style={{ textAlign: "center", color: "#64748b", padding: "20px" }}>No matching prospect emails found.</p>
              ) : (
                filteredRecipients.map(r => {
                  const isChecked = selectedIds.includes(r.id);
                  return (
                    <label
                      key={r.id}
                      style={{
                        display: "flex",
                        alignItems: "flex-start",
                        gap: "10px",
                        padding: "8px 10px",
                        marginBottom: "6px",
                        background: isChecked ? "#f0fdf4" : "#ffffff",
                        border: `1px solid ${isChecked ? "#86efac" : "#e2e8f0"}`,
                        borderRadius: "6px",
                        cursor: r.suppressed ? "not-allowed" : "pointer",
                        opacity: r.suppressed ? 0.5 : 1,
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={isChecked}
                        disabled={r.suppressed}
                        onChange={() => toggleSelect(r.id)}
                        style={{ marginTop: "3px", width: "auto" }}
                      />
                      <div style={{ flex: 1, minWidth: 0, fontSize: "13px" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "4px" }}>
                          <strong style={{ color: "#0f172a", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                            {r.company_name}
                          </strong>
                          <span style={{ fontSize: "10px", color: r.source === "Saved Contact" ? "#0284c7" : "#64748b" }}>
                            {r.source}
                          </span>
                        </div>
                        <div style={{ color: "#334155", fontSize: "12px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                          {r.recipient_name} {r.title ? `· ${r.title}` : ""}
                        </div>
                        <div style={{ color: "#0284c7", fontSize: "12px", fontWeight: 500, wordBreak: "break-all" }}>
                          {r.email}
                        </div>
                      </div>
                    </label>
                  );
                })
              )}
            </div>
          </div>

          {/* Right Column: Template Composer & Editor */}
          <div style={{ display: "flex", flexDirection: "column", background: "#ffffff", overflowY: "auto", padding: "20px 24px" }}>
            {/* Template Selector */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "10px", marginBottom: "14px" }}>
              <div style={{ flex: 1, minWidth: "220px" }}>
                <label style={{ margin: 0, fontSize: "12px", color: "#475569" }}>
                  Select Base Template:
                  <select
                    value={selectedTemplateId}
                    onChange={e => handleTemplateChange(e.target.value)}
                    style={{ marginTop: "4px", padding: "6px 10px", fontSize: "13px" }}
                  >
                    {DEFAULT_TEMPLATES.map(t => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <button
                type="button"
                className="secondary"
                style={{ fontSize: "12px", padding: "6px 12px", alignSelf: "flex-end" }}
                onClick={() => setShowPreview(v => !v)}
              >
                {showPreview ? "✏️ Edit Template" : "👁️ Preview Personalized"}
              </button>
            </div>

            {showPreview ? (
              /* Preview Mode */
              <div style={{ background: "#f8fafc", padding: "16px", borderRadius: "8px", border: "1px solid #cbd5e1", flex: 1 }}>
                <p style={{ margin: 0, fontSize: "12px", color: "#64748b" }}>
                  Live Personalized Preview for: <strong>{previewCompany}</strong> ({previewName})
                </p>
                <div style={{ marginTop: "12px" }}>
                  <strong>Subject:</strong> <span style={{ color: "#0f172a" }}>{previewSubject}</span>
                </div>
                <hr style={{ margin: "12px 0", borderColor: "#e2e8f0" }} />
                <pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit", fontSize: "14px", lineHeight: "1.6", margin: 0, color: "#1e293b" }}>
                  {previewBody}
                </pre>
                {attachments.length > 0 && (
                  <div style={{ marginTop: "16px", paddingTop: "12px", borderTop: "1px dashed #cbd5e1" }}>
                    <strong style={{ fontSize: "12px", color: "#475569" }}>Collaterals Attached ({attachments.length}):</strong>
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
              <div style={{ display: "flex", flexDirection: "column", flex: 1 }}>
                <label style={{ fontSize: "13px", fontWeight: 600 }}>
                  Subject Line
                  <input
                    value={subject}
                    onChange={e => setSubject(e.target.value)}
                    placeholder="e.g. {{company}}’s logistics costs"
                    style={{ marginTop: "4px" }}
                  />
                </label>

                {/* Toolbar */}
                <div className="composer-toolbar" style={{ marginTop: "12px" }}>
                  <button type="button" className="toolbar-btn" onClick={() => applyFormatting("**", "**")} title="Bold (Ctrl+B)">
                    <strong>B</strong>
                  </button>
                  <button type="button" className="toolbar-btn" onClick={() => applyFormatting("*", "*")} title="Italic (Ctrl+I)">
                    <em>I</em>
                  </button>
                  <button type="button" className="toolbar-btn" onClick={() => applyFormatting("\n• ", "")} title="Bullet List">
                    • List
                  </button>
                  <span className="toolbar-divider" />
                  <button type="button" className="toolbar-btn" onClick={() => applyFormatting("{{company}}", "")} title="Insert Company Variable">
                    {"{company}"}
                  </button>
                  <button type="button" className="toolbar-btn" onClick={() => applyFormatting("{{First Name}}", "")} title="Insert First Name Variable">
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
                    📎 {uploading ? "Uploading..." : "Attach Collateral"}
                  </button>
                  <input
                    type="file"
                    ref={fileInputRef}
                    style={{ display: "none" }}
                    accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg"
                    onChange={handleFileUpload}
                  />
                </div>

                <label style={{ fontSize: "13px", fontWeight: 600, marginTop: "10px", flex: 1, display: "flex", flexDirection: "column" }}>
                  Email Template Body
                  <textarea
                    ref={textareaRef}
                    value={body}
                    rows={12}
                    onChange={e => setBody(e.target.value)}
                    style={{ marginTop: "4px", fontFamily: "inherit", lineHeight: "1.6", flex: 1 }}
                  />
                </label>

                {/* Attachments Area */}
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
              </div>
            )}
          </div>
        </div>

        {/* Modal Footer */}
        <div style={{
          padding: "16px 24px",
          background: "#fafafa",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "12px",
        }}>
          <p style={{ margin: 0, fontSize: "13px", color: "#64748b" }}>
            Dispatches personalized 1-on-1 emails separately to each of the{" "}
            <strong>{selectedIds.length}</strong> selected recipient(s) with collateral attachments.
          </p>

          <div style={{ display: "flex", gap: "10px" }}>
            <button type="button" className="secondary" onClick={onClose} disabled={sending}>
              Close
            </button>
            <button
              type="button"
              className="btn-send"
              disabled={sending || selectedIds.length === 0 || !subject.trim() || !body.trim()}
              onClick={handleSendBulk}
              style={{ padding: "10px 22px", fontSize: "14px", display: "inline-flex", alignItems: "center", gap: "8px" }}
            >
              <UiIcon name="mail" size={16} />
              {sending
                ? `Sending to ${selectedIds.length} recipients...`
                : `Send Email to All Selected Leads (${selectedIds.length})`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
