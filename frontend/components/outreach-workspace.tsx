"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import DirectOutreachPanel from "./direct-outreach-panel";
import LeadConversationWorkspace from "./lead-conversation-workspace";
import RecipientPicker from "./recipient-picker";
import ResearchFactPicker from "./research-fact-picker";
import UiIcon from "./ui-icon";

const API = "http://localhost:8000";
type Lead = { id: string; company_name: string; email: string | null };
type Campaign = { id: string; name: string; mode: "manual" | "automatic"; delays: number[]; status: string };
type Event = { event_type: string; event_time: string };
type Message = {
  id: string; step_number: number; subject: string; body: string; status: string;
  due_at: string | null; sent_at: string | null; approved_at: string | null;
  message_id: string; last_error: string | null; manual_reply: boolean; events: Event[];
};
type Reply = { id: string; sender: string | null; subject: string | null; body: string; classification: string | null };
type Enrollment = {
  id: string; lead_id: string; company_name: string; contact_id: string | null; contact_name: string | null;
  recipient: string; status: string; reply_blocked: boolean;
  messages: Message[]; replies: Reply[];
};
type Detail = Campaign & { sequence_approved_at: string | null; enrollments: Enrollment[] };
type Mailbox = { last_success_at: string | null; last_error: string | null };
type MailCapacity = {
  window_hours: number; configured_limit: number; attempts_counted: number;
  remaining_application_budget: number; sending_enabled: boolean; note: string;
  unsubscribe_enabled: boolean; tracking_enabled: boolean; tracking_configured: boolean; tracking_note: string;
};
type BedrockStatus = { configured: boolean; region: string | null; model_id: string | null; note: string };
type InferenceProfile = { id: string; arn: string; name: string; type: string; regions: string[] };
type ProfilePage = { profiles: InferenceProfile[]; next_token: string | null };
type SalesTask = { id: string; title: string; status: string };
type Analytics = {
  recipient_count: number; active_recipient_count: number; stopped_recipient_count: number;
  suppressed_recipient_count: number; replied_recipient_count: number;
  accepted_recipient_count: number; accepted_email_count: number;
  opened_recipient_count: number; clicked_recipient_count: number;
  reply_rate_percent: number | null; open_rate_percent: number | null; click_rate_percent: number | null;
  engagement_note: string;
};
type Attachment = { id: string; filename: string; size_bytes: number; mime_type: string; created_at: string };
type ReceivedReplyItem = {
  id: string;
  sender: string | null;
  recipient: string | null;
  company_name: string | null;
  contact_name: string | null;
  subject: string | null;
  body: string;
  body_snippet: string;
  classification: string;
  received_at: string;
  original_email_id: string | null;
  original_subject: string | null;
  original_step: number | null;
  enrollment_id: string | null;
};
type MailboxAnalytics = {
  mailbox_address: string;
  total_sent: number;
  total_received: number;
  total_matched_replies: number;
  reply_rate_percent: number;
  classification_counts: Record<string, number>;
  recent_received: ReceivedReplyItem[];
};

const DEFAULT_SOLWER_CONTEXT = `DENSO Solwer TWMS (Transport & Warehouse Management System). Digitizes inbound & outbound operations, vehicle selection, load optimization, route planning, real-time tracking, e-POD, and ERP integration (SAP). Delivers potential transport cost savings of up to 20-30%, urgent shipment reduction of 5-25%, and invoicing labor reduction of 10-30%.

Target ICP: PAN India manufacturers, ₹100 Cr+ revenue, 30+ employees, 2-3+ factories/warehouses/dispatch hubs.
Priority Industries: Automotive & Auto Components, Industrial Manufacturing & Engineering.
Decision Makers: Head/VP Supply Chain, Logistics, Operations, Plant Heads, CIO/IT.`;

function getSolwerDefaultCopy(step: number, companyName: string = "your company", contactName: string = "there") {
  const safeComp = companyName || "your company";
  const firstName = contactName ? contactName.split(" ")[0] : "there";
  if (step === 0) {
    return {
      subject: `${safeComp}’s logistics costs`,
      body: `Hi ${firstName},\n\nAre transport and warehouse costs increasing at ${safeComp}?\n\nFor manufacturers managing multiple plants, warehouses, and transporters, - manual coordination, limited shipment visibility, and poor vehicle utilization can increase operation costs.\n\nDENSO's Solwer TWMS helps digitize and optimize inbound and outbound operations, from raw material movement to finished goods delivery and e-POD.\n\nWith vehicle selection, load optimization, route planning, and real-time shipment visibility, the platform offers potential transport cost savings of up to 20–30%.\n\nBuilt on DENSO's 75+ years of manufacturing experience, Solwer can also be customized around your existing processes and ERP.\n\nWould you be open to a quick 15-minute discussion?`,
    };
  } else if (step === 1) {
    return {
      subject: `Re: ${safeComp}’s logistics costs`,
      body: `Hi ${firstName},\n\nDid you get a chance to go through my last email? If not, I'll keep it short.\n\nWe could help ${safeComp} reduce transportation costs.\n\nSolwer helps your team select the right vehicles, improve truck capacity utilization, and plan efficient delivery routes.\n\nSolwer gives you end-to-end visibility; this means fewer underutilized trucks, fewer trips, and better control over transportation costs.\n\nThe platform also supports both in-house fleets and third-party transporters.\n\nWould you be open to exploring how this could work for ${safeComp}?`,
    };
  } else if (step === 2) {
    return {
      subject: `Re: ${safeComp}’s logistics costs`,
      body: `Hi ${firstName},\n\nI understand you might be busy with your schedule. I'll keep it short.\n\nEven with SAP or another ERP in place, manufacturers can still have gaps in day-to-day warehouse and transport operations.\n\nSolwer can work alongside existing systems to help ${safeComp} digitize processes such as inventory movement, picking, dispatch, and delivery tracking.\n\nWe first understand your requirements and existing processes, then customize Solwer to fit your manufacturing and logistics operations.\n\nThis helps your team improve visibility without having to replace its ERP.\n\nWould a short conversation make sense?`,
    };
  } else {
    return {
      subject: `Re: ${safeComp}’s logistics costs`,
      body: `Hi ${firstName},\n\nFor manufacturers managing multiple locations, tracking deliveries and coordinating transporters can involve several teams and manual follow-ups.\n\nSolwer helps ${safeComp} manage these activities through a centralized platform.\n\nYour team can track vehicle movements, monitor consignments, receive safety alerts, and automate proof-of-delivery and invoice generation.\n\nAccording to DENSO's estimates, Solwer can potentially reduce urgent shipment costs by 5–25% through better planning and invoicing labour costs by 10–30% through automation.\n\nWould you be available for a quick 15-minute call to explore this for ${safeComp}?`,
    };
  }
}

async function request<T>(path: string, method = "GET", data?: unknown): Promise<T> {
  const response = await fetch(API + path, {
    method,
    ...(data === undefined ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : `Request failed (${response.status}).`);
  }
  return response.json() as Promise<T>;
}

function ComposerToolbar({
  onInsert,
  onAttachClick,
  uploading,
}: {
  onInsert: (text: string) => void;
  onAttachClick: () => void;
  uploading: boolean;
}) {
  return (
    <div className="composer-toolbar">
      <button type="button" className="toolbar-btn" onClick={() => onInsert("****")} title="Bold">
        <strong>B</strong>
      </button>
      <button type="button" className="toolbar-btn" onClick={() => onInsert("**")} title="Italic">
        <em>I</em>
      </button>
      <button type="button" className="toolbar-btn" onClick={() => onInsert("[Link](https://)")} title="Add Link">
        🔗 Link
      </button>
      <button type="button" className="toolbar-btn" onClick={() => onInsert("\n• ")} title="Bullet List">
        • List
      </button>
      <span className="toolbar-divider" />
      <button type="button" className="toolbar-btn" onClick={() => onInsert("{{company}}")} title="Insert Company Variable">
        {"{company}"}
      </button>
      <button type="button" className="toolbar-btn" onClick={() => onInsert("{{First Name}}")} title="Insert Contact Variable">
        {"{First Name}"}
      </button>
      <span className="toolbar-divider" />
      <button
        type="button"
        className="toolbar-btn"
        disabled={uploading}
        onClick={onAttachClick}
        style={{ color: "#0284c7" }}
        title="Attach File (PDF, DOCX, Deck)"
      >
        <UiIcon name="link" size={14} /> {uploading ? "Uploading..." : "Attach File"}
      </button>
    </div>
  );
}

function AttachmentList({
  attachments,
  onDelete,
  editable,
}: {
  attachments: Attachment[];
  onDelete: (id: string) => void;
  editable: boolean;
}) {
  if (attachments.length === 0) return null;
  return (
    <div className="attachment-area">
      <span style={{ fontSize: "12px", color: "#64748b", fontWeight: 600 }}>Attachments ({attachments.length}):</span>
      {attachments.map(att => (
        <span key={att.id} className="attachment-pill">
          <span>📄 {att.filename}</span>
          <span style={{ color: "#94a3b8", fontSize: "11px" }}>({Math.round(att.size_bytes / 1024)} KB)</span>
          {editable && (
            <button
              type="button"
              className="attachment-pill-remove"
              onClick={() => onDelete(att.id)}
              title="Remove attachment"
            >
              ×
            </button>
          )}
        </span>
      ))}
    </div>
  );
}

function MasterDraftEditor({
  message,
  companyName,
  contactName,
  busy,
  act,
  onSendSuccess,
}: {
  message: Message;
  companyName?: string;
  contactName?: string | null;
  busy: boolean;
  act: (action: () => Promise<unknown>) => void;
  onSendSuccess: () => void;
}) {
  const fallback = getSolwerDefaultCopy(0, companyName, contactName || "there");
  const [subject, setSubject] = useState(message.subject || fallback.subject);
  const [body, setBody] = useState(message.body || fallback.body);
  const [link, setLink] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    setSubject(message.subject || fallback.subject);
    setBody(message.body || fallback.body);
  }, [message.subject, message.body, fallback.subject, fallback.body]);

  useEffect(() => {
    request<Attachment[]>(`/messages/${message.id}/attachments`)
      .then(setAttachments)
      .catch(() => {});
  }, [message.id]);

  const editable = ["draft", "approved", "failed", "rejected"].includes(message.status);
  const isDirty = subject !== message.subject || body !== message.body;

  async function handleFileUpload(file: File) {
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API}/messages/${message.id}/attachments`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => null);
        throw new Error(errData?.detail || `Upload failed (${res.status})`);
      }
      const uploaded = (await res.json()) as Attachment;
      setAttachments(prev => [...prev, uploaded]);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to upload file.");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function deleteAttachment(id: string) {
    try {
      const res = await fetch(`${API}/messages/${message.id}/attachments/${id}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error("Delete failed");
      setAttachments(prev => prev.filter(a => a.id !== id));
    } catch {
      alert("Could not remove attachment.");
    }
  }

  return (
    <div className="master-draft-card">
      <div className="master-draft-header">
        <div className="master-draft-badge">
          <UiIcon name="spark" size={16} /> MASTER INITIAL OUTREACH (STEP 0)
        </div>
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <span
            className={`status-pill ${
              message.status === "sent"
                ? "positive"
                : message.status === "approved"
                ? "positive"
                : message.status === "draft"
                ? "neutral"
                : "attention"
            }`}
          >
            {message.status.toUpperCase()}
          </span>
          {message.sent_at && (
            <span className="status-pill positive">
              ✓ Sent: {new Date(message.sent_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </span>
          )}
        </div>
      </div>

      {message.last_error && <p className="error">{message.last_error}</p>}

      <label>
        Email Subject
        <input
          value={subject}
          disabled={!editable}
          onChange={event => setSubject(event.target.value)}
          placeholder="Cold outreach subject line..."
        />
      </label>

      <label style={{ marginTop: "12px" }}>
        Email Body
        {editable && (
          <ComposerToolbar
            uploading={uploading}
            onAttachClick={() => fileInputRef.current?.click()}
            onInsert={tag => setBody(prev => prev + tag)}
          />
        )}
        <input
          type="file"
          ref={fileInputRef}
          style={{ display: "none" }}
          onChange={e => {
            const f = e.target.files?.[0];
            if (f) handleFileUpload(f);
          }}
        />
        <textarea
          className={editable ? "composer-textarea" : ""}
          value={body}
          disabled={!editable}
          rows={9}
          onChange={event => setBody(event.target.value)}
          placeholder="Personalized initial outreach email..."
        />
      </label>

      <AttachmentList attachments={attachments} onDelete={deleteAttachment} editable={editable} />

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "10px",
          marginTop: "14px",
        }}
      >
        <p style={{ margin: 0, fontSize: "13px" }}>
          {!subject.trim() || !body.trim()
            ? "Subject and body required before approval."
            : isDirty
            ? "⚠️ Unsaved changes. Click 'Save draft' before approving."
            : message.status === "sent"
            ? "✓ Sent and accepted. Follow-up sequence is active."
            : message.status === "approved"
            ? "✓ Saved email is approved and ready to send."
            : "Review and approve this email to enable sending."}
        </p>

        <div className="actions" style={{ margin: 0 }}>
          {editable && isDirty && (
            <button
              className="secondary"
              disabled={busy || !subject.trim() || !body.trim()}
              onClick={() =>
                act(() =>
                  request(`/messages/${message.id}`, "PUT", { subject, body })
                )
              }
            >
              Save draft
            </button>
          )}

          {editable && message.status !== "approved" && !isDirty && (
            <button
              disabled={busy || !subject.trim() || !body.trim()}
              onClick={() =>
                act(() =>
                  request(`/messages/${message.id}/approve`, "POST", { subject, body })
                )
              }
            >
              <UiIcon name="check" size={16} /> Approve cold email
            </button>
          )}

          {message.status === "approved" && !isDirty && (
            <button
              className="btn-send"
              disabled={busy}
              onClick={() =>
                act(async () => {
                  await request(`/messages/${message.id}/send-now`, "POST");
                  onSendSuccess();
                })
              }
            >
              <UiIcon name="mail" size={16} /> Send email now
            </button>
          )}

          {editable && message.status !== "rejected" && (
            <button
              className="secondary"
              disabled={busy}
              onClick={() => act(() => request(`/messages/${message.id}/reject`, "POST"))}
            >
              Reject
            </button>
          )}
        </div>
      </div>

      {editable && (
        <details style={{ marginTop: "14px" }}>
          <summary>Add approved click-tracking link</summary>
          <label>
            HTTPS URL already present in saved draft
            <input value={link} onChange={event => setLink(event.target.value)} placeholder="https://..." />
          </label>
          <button
            className="secondary"
            disabled={busy || !link || isDirty}
            onClick={() =>
              act(async () => {
                await request(`/messages/${message.id}/tracking-links`, "POST", { destination: link });
                setLink("");
              })
            }
          >
            Add link & require reapproval
          </button>
        </details>
      )}

      {message.events.length > 0 && (
        <p style={{ fontSize: "12px", color: "#64748b", marginTop: "10px" }}>
          Delivery events: {message.events.map(event => event.event_type).join(" · ")}
        </p>
      )}
    </div>
  );
}

function FollowUpStepEditor({
  message,
  companyName,
  contactName,
  delayDays,
  busy,
  act,
}: {
  message: Message;
  companyName?: string;
  contactName?: string | null;
  delayDays?: number;
  busy: boolean;
  act: (action: () => Promise<unknown>) => void;
}) {
  const fallback = getSolwerDefaultCopy(message.step_number, companyName, contactName || "there");
  const [subject, setSubject] = useState(message.subject || fallback.subject);
  const [body, setBody] = useState(message.body || fallback.body);
  const [open, setOpen] = useState(false);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    setSubject(message.subject || fallback.subject);
    setBody(message.body || fallback.body);
  }, [message.subject, message.body, fallback.subject, fallback.body]);

  useEffect(() => {
    if (open) {
      request<Attachment[]>(`/messages/${message.id}/attachments`)
        .then(setAttachments)
        .catch(() => {});
    }
  }, [message.id, open]);

  const editable = ["draft", "approved", "failed", "rejected"].includes(message.status);
  const isDirty = subject !== message.subject || body !== message.body;

  async function handleFileUpload(file: File) {
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API}/messages/${message.id}/attachments`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => null);
        throw new Error(errData?.detail || `Upload failed (${res.status})`);
      }
      const uploaded = (await res.json()) as Attachment;
      setAttachments(prev => [...prev, uploaded]);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to upload file.");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function deleteAttachment(id: string) {
    try {
      const res = await fetch(`${API}/messages/${message.id}/attachments/${id}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error("Delete failed");
      setAttachments(prev => prev.filter(a => a.id !== id));
    } catch {
      alert("Could not remove attachment.");
    }
  }

  return (
    <div className="sequence-step-card">
      <div className="sequence-step-indicator" />
      <div className="sequence-step-header">
        <div className="sequence-step-title">
          <span>Follow-up #{message.step_number}</span>
          {delayDays !== undefined && <span className="delay-tag">+{delayDays} days after previous</span>}
          <span
            className={`status-pill ${
              message.status === "sent"
                ? "positive"
                : message.status === "approved"
                ? "positive"
                : message.status === "draft"
                ? "neutral"
                : "attention"
            }`}
          >
            {message.status.toUpperCase()}
          </span>
        </div>
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          {message.due_at && (
            <small style={{ color: "#64748b" }}>Due: {new Date(message.due_at).toLocaleDateString()}</small>
          )}
          {message.sent_at && (
            <small style={{ color: "#059669", fontWeight: 600 }}>Sent: {new Date(message.sent_at).toLocaleDateString()}</small>
          )}
          <button
            type="button"
            className="secondary icon-button"
            onClick={() => setOpen(!open)}
            aria-label="Toggle editor"
          >
            <UiIcon name={open ? "arrow" : "spark"} size={14} />
          </button>
        </div>
      </div>

      {message.last_error && <p className="error">{message.last_error}</p>}

      {!open ? (
        <div
          onClick={() => setOpen(true)}
          style={{
            cursor: "pointer",
            background: "#f8fafc",
            padding: "10px 14px",
            borderRadius: "8px",
            border: "1px solid #e2e8f0",
          }}
        >
          <strong style={{ fontSize: "14px", color: "#1e293b", display: "block" }}>
            {subject || "(No subject drafted yet)"}
          </strong>
          <p
            style={{
              margin: "4px 0 0",
              fontSize: "13px",
              color: "#64748b",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {body || "Click to expand and edit this follow-up draft..."}
          </p>
        </div>
      ) : (
        <div>
          <label>
            Follow-up Subject
            <input value={subject} disabled={!editable} onChange={event => setSubject(event.target.value)} />
          </label>
          <label style={{ marginTop: "12px" }}>
            Follow-up Body
            {editable && (
              <ComposerToolbar
                uploading={uploading}
                onAttachClick={() => fileInputRef.current?.click()}
                onInsert={tag => setBody(prev => prev + tag)}
              />
            )}
            <input
              type="file"
              ref={fileInputRef}
              style={{ display: "none" }}
              onChange={e => {
                const f = e.target.files?.[0];
                if (f) handleFileUpload(f);
              }}
            />
            <textarea
              className={editable ? "composer-textarea" : ""}
              value={body}
              disabled={!editable}
              rows={6}
              onChange={event => setBody(event.target.value)}
            />
          </label>

          <AttachmentList attachments={attachments} onDelete={deleteAttachment} editable={editable} />

          {editable && (
            <div className="actions">
              <button
                className="secondary"
                disabled={busy || !subject.trim() || !body.trim() || !isDirty}
                onClick={() =>
                  act(() =>
                    request(`/messages/${message.id}`, "PUT", { subject, body })
                  )
                }
              >
                Save draft
              </button>
              <button
                disabled={busy || message.status === "approved" || isDirty || !subject.trim() || !body.trim()}
                onClick={() =>
                  act(() =>
                    request(`/messages/${message.id}/approve`, "POST", { subject, body })
                  )
                }
              >
                Approve follow-up
              </button>
              {message.status === "approved" && (
                <button
                  className="btn-send"
                  disabled={busy}
                  onClick={() => act(() => request(`/messages/${message.id}/send-now`, "POST"))}
                >
                  Send follow-up now
                </button>
              )}
              <button
                className="secondary"
                disabled={busy || message.status === "rejected"}
                onClick={() => act(() => request(`/messages/${message.id}/reject`, "POST"))}
              >
                Reject
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function InboundMailAnalyticsCard({
  analytics,
  mailbox,
  syncing,
  onSync,
  busy,
  act,
}: {
  analytics: MailboxAnalytics | null;
  mailbox: Mailbox | null;
  syncing: boolean;
  onSync: () => void;
  busy: boolean;
  act: (action: () => Promise<unknown>) => void;
}) {
  const [filter, setFilter] = useState("all");
  const [expandedReplyId, setExpandedReplyId] = useState<string | null>(null);

  const replies = analytics?.recent_received || [];
  const filtered = filter === "all" ? replies : replies.filter(r => r.classification === filter);

  const lastSyncStr = mailbox?.last_success_at
    ? new Date(mailbox.last_success_at).toLocaleString()
    : "Connected (polling every 60s)";

  return (
    <div className="inbound-analytics-card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "12px" }}>
        <div>
          <span className="feature-label">
            <UiIcon name="mail" size={16} /> AI-POWERED SALES ENGAGEMENT &amp; LEAD CONVERSATION WORKSPACE
          </span>
          <h3 style={{ margin: "4px 0 0", fontSize: "20px" }}>
            Connected Mailbox: <span style={{ color: "var(--red)" }}>{analytics?.mailbox_address || "tharunjs012003@gmail.com"}</span>
          </h3>
          <p style={{ margin: "4px 0 0", color: "#64748b", fontSize: "13px" }}>
            <span style={{ display: "inline-block", width: "8px", height: "8px", borderRadius: "50%", background: "#16a34a", marginRight: "6px" }} />
            Connected · Last checked {lastSyncStr}
          </p>
        </div>

        <button className="secondary" disabled={syncing || busy} onClick={onSync} style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}>
          <UiIcon name="spark" size={16} /> {syncing ? "Syncing Gmail..." : "Sync / Check Inbox Now"}
        </button>
      </div>

      <div className="inbound-stat-grid">
        <div className="inbound-stat-box">
          <strong>{analytics?.total_sent ?? 0}</strong>
          <span>Outreach Sent</span>
        </div>
        <div className="inbound-stat-box">
          <strong>{analytics?.total_matched_replies ?? (analytics?.recent_received?.length ?? 0)}</strong>
          <span>Sales Replies</span>
        </div>
        <div className="inbound-stat-box">
          <strong>{analytics?.reply_rate_percent ?? 0}%</strong>
          <span>Reply Rate</span>
        </div>
        <div className="inbound-stat-box featured">
          <strong>{(analytics?.classification_counts?.meeting_requested ?? 0) + (analytics?.classification_counts?.demo_requested ?? 0)}</strong>
          <span>📅 Meetings &amp; Demos</span>
        </div>
        <div className="inbound-stat-box">
          <strong>{analytics?.classification_counts?.interested ?? 0}</strong>
          <span>💡 High Interest</span>
        </div>
        <div className="inbound-stat-box" style={{ background: "#f8fafc" }}>
          <strong>{(analytics?.classification_counts?.hard_bounce ?? 0) + (analytics?.classification_counts?.bounce_review ?? 0)}</strong>
          <span>🤖 Bounces (Filtered)</span>
        </div>
      </div>

      {/* 3-Panel Lead Conversation Workspace */}
      <LeadConversationWorkspace onRefreshStats={onSync} />

      {/* Collapsible Raw Email Audit Trail */}
      <details style={{ marginTop: "24px", border: "1px solid #e2e8f0", borderRadius: "8px", padding: "12px 16px", background: "#f8fafc" }}>
        <summary style={{ cursor: "pointer", fontWeight: 600, fontSize: "13px", color: "#64748b" }}>
          View Raw Inbound Delivery Audit Logs ({replies.length} items recorded)
        </summary>

        {/* Filter pills */}
      <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", margin: "16px 0 8px" }}>
        <button
          type="button"
          className={`status-pill ${filter === "all" ? "positive" : "neutral"}`}
          style={{ cursor: "pointer", border: "none" }}
          onClick={() => setFilter("all")}
        >
          All Received ({replies.length})
        </button>
        <button
          type="button"
          className={`status-pill ${filter === "meeting_requested" ? "positive" : "neutral"}`}
          style={{ cursor: "pointer", border: "none" }}
          onClick={() => setFilter("meeting_requested")}
        >
          Meetings ({analytics?.classification_counts?.meeting_requested ?? 0})
        </button>
        <button
          type="button"
          className={`status-pill ${filter === "interested" ? "ai" : "neutral"}`}
          style={{ cursor: "pointer", border: "none" }}
          onClick={() => setFilter("interested")}
        >
          Interested ({analytics?.classification_counts?.interested ?? 0})
        </button>
        <button
          type="button"
          className={`status-pill ${filter === "not_interested" ? "attention" : "neutral"}`}
          style={{ cursor: "pointer", border: "none" }}
          onClick={() => setFilter("not_interested")}
        >
          Not Interested ({analytics?.classification_counts?.not_interested ?? 0})
        </button>
      </div>

      {/* Received Mail Table */}
      {filtered.length === 0 ? (
        <p style={{ color: "#64748b", margin: "20px 0" }}>No inbound emails matching this filter.</p>
      ) : (
        <table className="inbound-feed-table">
          <thead>
            <tr>
              <th>Sender / Company</th>
              <th>Subject / Thread</th>
              <th>Sentiment & Intent</th>
              <th>Date & Time</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(r => (
              <tr key={r.id}>
                <td>
                  <strong>{r.contact_name || r.company_name || r.sender || "Unknown Sender"}</strong>
                  <small style={{ display: "block", color: "#64748b" }}>{r.sender}</small>
                  {r.company_name && <small style={{ display: "block", color: "var(--red)", fontWeight: 600 }}>{r.company_name}</small>}
                </td>
                <td>
                  <strong style={{ fontSize: "14px", color: "#1e293b" }}>{r.subject || "(No subject)"}</strong>
                  {r.original_subject && (
                    <small style={{ display: "block", color: "#64748b" }}>In reply to: {r.original_subject}</small>
                  )}
                  <p style={{ margin: "4px 0 0", color: "#475569", fontSize: "13px" }}>
                    {expandedReplyId === r.id ? r.body : r.body_snippet}
                  </p>
                  {r.body.length > 250 && (
                    <button
                      type="button"
                      className="secondary"
                      style={{ padding: "2px 6px", fontSize: "11px", marginTop: "4px" }}
                      onClick={() => setExpandedReplyId(expandedReplyId === r.id ? null : r.id)}
                    >
                      {expandedReplyId === r.id ? "Show less" : "Show full email"}
                    </button>
                  )}
                </td>
                <td>
                  <span
                    className={`status-pill ${
                      r.classification === "meeting_requested"
                        ? "positive"
                        : r.classification === "interested"
                        ? "ai"
                        : r.classification === "not_interested"
                        ? "attention"
                        : "neutral"
                    }`}
                  >
                    {r.classification.replace("_", " ").toUpperCase()}
                  </span>
                </td>
                <td>
                  <small style={{ color: "#64748b" }}>
                    {new Date(r.received_at).toLocaleDateString()}{" "}
                    {new Date(r.received_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </small>
                </td>
                <td>
                  <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    <button
                      className="secondary"
                      style={{ padding: "4px 8px", fontSize: "12px" }}
                      disabled={busy}
                      onClick={() => act(() => request(`/replies/${r.id}/classify`, "POST"))}
                    >
                      Classify AI
                    </button>
                    {r.classification === "meeting_requested" && (
                      <Link className="button-link" href="/meetings" style={{ padding: "4px 8px", fontSize: "12px" }}>
                        View Meeting
                      </Link>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      </details>
    </div>
  );
}

function ReplyCard({ reply, busy, act }: { reply: Reply; busy: boolean; act: (action: () => Promise<unknown>) => void }) {
  const [subject, setSubject] = useState(`Re: ${reply.subject || ""}`);
  const [body, setBody] = useState("");
  return (
    <div className="detail" style={{ borderLeft: "4px solid #6366f1" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
        <p style={{ margin: 0 }}>
          <strong>{reply.sender || "Unknown sender"}</strong>
        </p>
        <span
          className={`status-pill ${
            reply.classification === "meeting_requested" ? "positive" : reply.classification === "interested" ? "ai" : "neutral"
          }`}
        >
          {reply.classification ? reply.classification.replace("_", " ").toUpperCase() : "UNCLASSIFIED"}
        </span>
      </div>
      <p style={{ fontWeight: 600, margin: "4px 0" }}>{reply.subject}</p>
      <pre>{reply.body}</pre>
      <div className="actions">
        <button className="secondary" disabled={busy} onClick={() => act(() => request(`/replies/${reply.id}/classify`, "POST"))}>
          <UiIcon name="spark" size={14} /> Classify with Bedrock
        </button>
      </div>
      <details>
        <summary>Draft response to prospect</summary>
        <label>
          Subject
          <input value={subject} onChange={event => setSubject(event.target.value)} />
        </label>
        <label>
          Body
          <textarea value={body} onChange={event => setBody(event.target.value)} />
        </label>
        <div className="actions">
          <button
            className="secondary"
            disabled={busy}
            onClick={() =>
              act(async () => {
                const suggestion = await request<{ subject: string; body: string }>(
                  `/replies/${reply.id}/suggest-response`,
                  "POST"
                );
                setSubject(suggestion.subject);
                setBody(suggestion.body);
              })
            }
          >
            Suggest with Bedrock
          </button>
          <button
            disabled={busy || !subject.trim() || !body.trim()}
            onClick={() =>
              act(async () => {
                await request(`/replies/${reply.id}/draft-response`, "POST", { subject, body });
                setBody("");
              })
            }
          >
            Create response draft
          </button>
        </div>
      </details>
    </div>
  );
}

export default function OutreachWorkspace({
  leadId: fixedLeadId,
  contactVersion = "",
  onActivity,
}: {
  leadId?: string;
  contactVersion?: string;
  onActivity?: () => void;
}) {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [selected, setSelected] = useState("");
  const [detail, setDetail] = useState<Detail | null>(null);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [mailbox, setMailbox] = useState<Mailbox | null>(null);
  const [mailboxAnalytics, setMailboxAnalytics] = useState<MailboxAnalytics | null>(null);
  const [syncingInbox, setSyncingInbox] = useState(false);
  const [capacity, setCapacity] = useState<MailCapacity | null>(null);
  const [bedrock, setBedrock] = useState<BedrockStatus | null>(null);
  const [profiles, setProfiles] = useState<InferenceProfile[]>([]);
  const [nextProfileToken, setNextProfileToken] = useState<string | null>(null);
  const [profileId, setProfileId] = useState("");
  const [profileError, setProfileError] = useState("");
  const [loadingProfiles, setLoadingProfiles] = useState(false);
  const [unmatched, setUnmatched] = useState<Reply[]>([]);
  const [tasks, setTasks] = useState<SalesTask[]>([]);
  const [name, setName] = useState("");
  const [mode, setMode] = useState("manual");
  const [delays, setDelays] = useState("3,4,5");
  const [context, setContext] = useState(DEFAULT_SOLWER_CONTEXT);
  const [researchCompany, setResearchCompany] = useState("");
  const [researchFacts, setResearchFacts] = useState<Record<string, string[]>>({});
  const [suppression, setSuppression] = useState("");
  const [bounceRecipient, setBounceRecipient] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  // Simulation state
  const [simBody, setSimBody] = useState(
    "Hi, thank you for reaching out. We would be interested in learning more about Solwer TWMS. Can we schedule a meeting next week?"
  );
  const [simType, setSimType] = useState("meeting_requested");

  const refresh = useCallback(async () => {
    const [
      campaignData,
      leadData,
      mailboxData,
      capacityData,
      unmatchedData,
      taskData,
      analyticsData,
      bedrockData,
      mailboxAnalyticsData,
    ] = await Promise.all([
      request<Campaign[]>("/campaigns"),
      request<Lead[]>("/leads"),
      request<Mailbox>("/mailbox/status"),
      request<MailCapacity>("/mailbox/capacity"),
      request<Reply[]>("/replies/unmatched"),
      request<SalesTask[]>("/sales-tasks"),
      selected ? request<Analytics>(`/campaigns/${selected}/analytics`) : Promise.resolve(null),
      request<BedrockStatus>("/integrations/bedrock/status"),
      request<MailboxAnalytics>("/mailbox/analytics").catch(() => null),
    ]);
    setCampaigns(campaignData);
    setLeads(leadData);
    setMailbox(mailboxData);
    setCapacity(capacityData);
    setUnmatched(unmatchedData);
    setTasks(taskData);
    setAnalytics(analyticsData);
    setBedrock(bedrockData);
    if (mailboxAnalyticsData) setMailboxAnalytics(mailboxAnalyticsData);
    if (selected) setDetail(await request<Detail>(`/campaigns/${selected}`));
  }, [selected]);

  useEffect(() => {
    refresh().catch(reason => setError(reason instanceof Error ? reason.message : "Could not load."));
    const timer = setInterval(
      () => refresh().catch(reason => setError(reason instanceof Error ? reason.message : "Could not refresh.")),
      15000
    );
    return () => clearInterval(timer);
  }, [refresh]);

  function act(action: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    setNotice("");
    void action()
      .then(() => refresh())
      .catch(reason => setError(reason instanceof Error ? reason.message : "Request failed."))
      .finally(() => setBusy(false));
  }

  async function syncInbox() {
    setSyncingInbox(true);
    setError("");
    try {
      const res = await request<{ success: boolean; message: string }>("/mailbox/sync", "POST");
      if (res.success) {
        setNotice("Inbox synchronized with Gmail! Inbound messages retrieved and analyzed.");
      } else {
        setError(res.message || "Inbox sync failed.");
      }
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sync failed.");
    } finally {
      setSyncingInbox(false);
    }
  }

  async function loadProfiles(nextToken?: string) {
    setLoadingProfiles(true);
    setProfileError("");
    try {
      const result = await request<ProfilePage>(
        "/integrations/bedrock/profiles" + (nextToken ? `?next_token=${encodeURIComponent(nextToken)}` : "")
      );
      setProfiles(current =>
        Array.from(new Map([...(nextToken ? current : []), ...result.profiles].map(profile => [profile.arn, profile])).values())
      );
      setNextProfileToken(result.next_token);
      if (!nextToken) setProfileId("");
      if (!result.profiles.length && !nextToken)
        setProfileError("AWS returned no active inference profiles in this region.");
    } catch (reason) {
      setProfileError(reason instanceof Error ? reason.message : "Could not load AWS inference profiles.");
    } finally {
      setLoadingProfiles(false);
    }
  }

  const enrollments = detail?.enrollments.filter(item => !fixedLeadId || item.lead_id === fixedLeadId) ?? [];
  const messages = enrollments.flatMap(item => item.messages);
  const campaignLeadIds = Array.from(new Set(enrollments.map(item => item.lead_id)));
  const researchLeadId =
    fixedLeadId ||
    (campaignLeadIds.includes(researchCompany) ? researchCompany : campaignLeadIds.length === 1 ? campaignLeadIds[0] : "");

  if (fixedLeadId) {
    const fixedLead = leads.find(item => item.id === fixedLeadId);
    return (
      <div className="outreach-workspace">
        <DirectOutreachPanel
          leadId={fixedLeadId}
          companyName={fixedLead?.company_name || ""}
          contactVersion={contactVersion}
          onActivity={onActivity}
        />
      </div>
    );
  }

  return (
    <div className="outreach-workspace">
      {!fixedLeadId && (
        <header>
          <div>
            <p className="eyebrow">DENSO / SALES INTELLIGENCE</p>
            <h1>Outreach & Follow-Up Automation</h1>
            <p>Personalized GTM outreach. Pre-drafted with LeadRoad &lt;&gt; DENSO Solwer TWMS copy. Grounded in verified company intelligence.</p>
          </div>
          <Link className="button-link secondary" href="/">
            <UiIcon name="companies" size={16} /> Company workspace
          </Link>
        </header>
      )}

      {error && (
        <div role="alert" className="alert" style={{ background: "#fef2f2", color: "#991b1b", borderColor: "#fecaca" }}>
          {error}
        </div>
      )}
      {notice && (
        <div role="status" className="notice">
          <UiIcon name="check" size={18} />
          {notice}
        </div>
      )}

      <ol className="workflow-steps">
        <li><strong>1. Select Outreach Target</strong> — Choose target company and contacts</li>
        <li><strong>2. Add Recipients</strong> — Drafts are automatically populated with DENSO Solwer TWMS copy</li>
        <li><strong>3. Review &amp; Edit</strong> — Attach collaterals, customize with Bedrock AI, and approve</li>
        <li><strong>4. Send Email Now</strong> — Dispatch cold outreach directly from connected mailbox</li>
        <li><strong>5. Inbound Tracking</strong> — Automated reply tracking, sentiment categorization, and calendar sync</li>
      </ol>

      {!fixedLeadId && (
        <div className="stats">
          <div>
            <strong>{messages.filter(m => m.due_at && ["draft", "approved"].includes(m.status)).length}</strong>
            <span>Scheduled follow-ups</span>
          </div>
          <div>
            <strong>{mailboxAnalytics?.total_sent ?? messages.filter(m => m.status === "sent").length}</strong>
            <span>Sent outreach emails</span>
          </div>
          <div>
            <strong>{mailboxAnalytics?.total_received ?? detail?.enrollments.filter(item => item.reply_blocked).length ?? 0}</strong>
            <span>Inbound replies caught</span>
          </div>
          <div>
            <strong>{tasks.filter(t => t.status === "open").length}</strong>
            <span>Open meeting tasks</span>
          </div>
        </div>
      )}

      {/* Campaign creation removed for now per user instruction */}

      {/* Section: Active Campaigns */}
      <section>
        <div className="section-title">
          <div>
            <h2>Campaigns</h2>
            <p>Each recipient receives an independent, 1-on-1 personalized email thread.</p>
          </div>
        </div>

        {campaigns.length === 0 ? (
          <p>No campaigns yet.</p>
        ) : (
          <div className="list">
            {campaigns.map(campaign => (
              <button
                key={campaign.id}
                className={`list-item ${selected === campaign.id ? "selected" : ""}`}
                disabled={busy}
                onClick={() => {
                  setSelected(campaign.id);
                  setDetail(null);
                }}
              >
                <div>
                  <strong style={{ fontSize: "15px", color: "#0f172a" }}>{campaign.name}</strong>
                  <small style={{ color: "#64748b", display: "block" }}>
                    Mode: {campaign.mode} · Delays: {campaign.delays.join(", ")} days
                  </small>
                </div>
                <span className={`status-pill ${campaign.status === "active" ? "positive" : "neutral"}`}>
                  {campaign.status.toUpperCase()}
                </span>
              </button>
            ))}
          </div>
        )}

        {detail && (
          <div style={{ marginTop: "24px" }}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                flexWrap: "wrap",
                gap: "12px",
                borderBottom: "1px solid var(--border)",
                paddingBottom: "16px",
              }}
            >
              <div>
                <h3 style={{ margin: 0, fontSize: "20px" }}>{detail.name}</h3>
                <p style={{ margin: "4px 0 0", color: "#64748b" }}>
                  Mode: {detail.mode} · Delays: {detail.delays.join(", ") || "none"} days after previous
                </p>
              </div>
              <div className="actions" style={{ margin: 0 }}>
                {detail.status !== "active" ? (
                  <button disabled={busy} onClick={() => act(() => request(`/campaigns/${detail.id}/activate`, "POST"))}>
                    <UiIcon name="check" size={16} /> Activate campaign
                  </button>
                ) : (
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() => act(() => request(`/campaigns/${detail.id}/pause`, "POST"))}
                  >
                    Pause campaign
                  </button>
                )}

                {detail.mode === "automatic" &&
                  detail.delays.length > 0 &&
                  (!fixedLeadId || enrollments.length === detail.enrollments.length) && (
                    <button
                      className="secondary"
                      disabled={busy}
                      onClick={() =>
                        act(() =>
                          request(`/campaigns/${detail.id}/approve-sequence`, "POST", {
                            messages: detail.enrollments
                              .flatMap(item => item.messages)
                              .filter(
                                message =>
                                  !message.manual_reply &&
                                  message.step_number > 0 &&
                                  ["draft", "approved", "failed"].includes(message.status)
                              )
                              .map(message => ({ id: message.id, subject: message.subject, body: message.body })),
                          })
                        )
                      }
                    >
                      Approve entire follow-up sequence
                    </button>
                  )}
              </div>
            </div>

            {/* Recipient Picker: Always visible so users can select contacts and enroll recipients anytime */}
            <RecipientPicker
              campaignId={detail.id}
              leads={leads}
              fixedLeadId={fixedLeadId}
              contactVersion={contactVersion}
              enrolledEmails={detail.enrollments.map(item => item.recipient)}
              busy={busy}
              act={act}
              onAdded={count =>
                setNotice(`${count} recipient(s) enrolled! Drafts automatically populated with LeadRoad <> DENSO Solwer TWMS copy.`)
              }
            />

            {/* AI Customization & Grounding Section */}
            <div className="detail" style={{ margin: "24px 0", borderLeft: "4px solid var(--red)" }}>
              <div className="section-title">
                <div>
                  <span className="feature-label">
                    <UiIcon name="spark" size={16} /> BEDROCK AI DRAFT GENERATOR & PROMPT GROUNDING
                  </span>
                  <h3 style={{ marginTop: "4px" }}>LeadRoad &lt;&gt; DENSO Solwer TWMS Outreach System</h3>
                </div>
                <span className="status-pill ai">
                  {bedrock?.model_id?.includes("claude") ? "CLAUDE 3.5 SONNET ACTIVE" : "AI ENGINE READY"}
                </span>
              </div>

              <p style={{ color: "#475569" }}>
                Model: <strong>{bedrock?.model_id || "us.anthropic.claude-3-5-sonnet-20241022-v2:0"}</strong> · Region:{" "}
                <strong>{bedrock?.region || "us-east-1"}</strong>
              </p>

              <label>
                Approved campaign context, ICP criteria & talking points
                <textarea
                  value={context}
                  rows={4}
                  placeholder="Paste specific value proposition, pain point, or custom talking points. Drafts are automatically pre-populated."
                  onChange={event => setContext(event.target.value)}
                />
              </label>

              {!fixedLeadId && campaignLeadIds.length > 1 && (
                <label>
                  Select company to inspect cited evidence
                  <select value={researchLeadId} onChange={event => setResearchCompany(event.target.value)}>
                    <option value="">Choose a company</option>
                    {campaignLeadIds.map(id => (
                      <option key={id} value={id}>
                        {leads.find(item => item.id === id)?.company_name || id}
                      </option>
                    ))}
                  </select>
                </label>
              )}

              {researchLeadId && (
                <ResearchFactPicker
                  key={researchLeadId}
                  leadId={researchLeadId}
                  selected={researchFacts[researchLeadId] || []}
                  onChange={ids => setResearchFacts(current => ({ ...current, [researchLeadId]: ids }))}
                />
              )}

              {enrollments.length > 0 && (
                <div style={{ marginTop: "16px", display: "flex", gap: "10px", alignItems: "center" }}>
                  <button
                    disabled={busy}
                    onClick={() => {
                      act(async () => {
                        for (const enrollment of enrollments) {
                          await request(`/enrollments/${enrollment.id}/generate`, "POST", {
                            context,
                            inference_profile_id: profileId || null,
                            research_fact_ids: researchFacts[enrollment.lead_id] || [],
                          });
                        }
                        setNotice(`Drafts customized with Bedrock AI for all ${enrollments.length} recipients!`);
                      });
                    }}
                  >
                    <UiIcon name="spark" size={16} />{" "}
                    {busy ? "Customizing drafts..." : `Regenerate/Refine with AI for all ${enrollments.length} recipients`}
                  </button>
                </div>
              )}
            </div>

            {/* Recipients List & Threads */}
            <h3 style={{ fontSize: "20px", marginTop: "32px", marginBottom: "16px" }}>
              Campaign Recipients ({enrollments.length})
            </h3>

            {enrollments.length === 0 && (
              <p style={{ color: "#64748b" }}>Select contacts in the section above to enroll them into this campaign.</p>
            )}

            {enrollments.map(enrollment => {
              const orderedMessages = [...enrollment.messages].sort((a, b) => a.step_number - b.step_number);
              const masterDraft = orderedMessages.find(m => m.step_number === 0 && !m.manual_reply);
              const followUps = orderedMessages.filter(m => m.step_number > 0 && !m.manual_reply);
              const hasMeetingReply = enrollment.replies.some(
                r => r.classification === "meeting_requested" || r.classification === "interested"
              );

              return (
                <details className="recipient-thread" key={enrollment.id} open={true}>
                  <summary>
                    <strong>{enrollment.contact_name || enrollment.recipient}</strong> · {enrollment.company_name} ·
                    <span
                      className={`status-pill ${
                        enrollment.status === "active"
                          ? "positive"
                          : enrollment.reply_blocked
                          ? "attention"
                          : "neutral"
                      }`}
                      style={{ marginLeft: "8px" }}
                    >
                      {enrollment.reply_blocked ? "REPLY RECEIVED" : enrollment.status.toUpperCase()}
                    </span>
                  </summary>

                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      flexWrap: "wrap",
                      gap: "12px",
                      margin: "16px 0",
                      borderBottom: "1px solid var(--border)",
                      paddingBottom: "12px",
                    }}
                  >
                    <div>
                      <h4 style={{ margin: 0, fontSize: "16px" }}>
                        {enrollment.company_name}
                        {enrollment.contact_name ? ` · ${enrollment.contact_name}` : ""}
                      </h4>
                      <small style={{ color: "#64748b" }}>Target email: {enrollment.recipient}</small>
                    </div>
                    <div className="actions" style={{ margin: 0 }}>
                      <button
                        className="secondary"
                        disabled={busy}
                        onClick={() => {
                          act(async () => {
                            await request(`/enrollments/${enrollment.id}/generate`, "POST", {
                              context,
                              inference_profile_id: profileId || null,
                              research_fact_ids: researchFacts[enrollment.lead_id] || [],
                            });
                            setNotice(`Drafts customized for ${enrollment.recipient}. Review below.`);
                          });
                        }}
                      >
                        <UiIcon name="spark" size={15} /> Regenerate with AI
                      </button>
                      {enrollment.status === "active" ? (
                        <button
                          className="secondary"
                          disabled={busy}
                          onClick={() => act(() => request(`/enrollments/${enrollment.id}/stop`, "POST"))}
                        >
                          Stop recipient
                        </button>
                      ) : (
                        <button
                          className="secondary"
                          disabled={busy}
                          onClick={() => act(() => request(`/enrollments/${enrollment.id}/resume`, "POST"))}
                        >
                          Resume recipient
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Inbound Meeting Alert Banner */}
                  {hasMeetingReply && (
                    <div className="meeting-alert-card">
                      <div className="meeting-alert-icon">
                        <UiIcon name="calendar" size={24} />
                      </div>
                      <div className="meeting-alert-content">
                        <h4>Meeting Requested by Prospect!</h4>
                        <p>
                          The prospect responded positively to your outreach. Automatic follow-up emails have been paused to protect
                          relationship credibility.
                        </p>
                        <Link className="button-link" href="/meetings">
                          Open Calendar &amp; Meeting Organizer <UiIcon name="arrow" size={16} />
                        </Link>
                      </div>
                    </div>
                  )}

                  {enrollment.reply_blocked && !hasMeetingReply && (
                    <div className="reply-paused-banner">
                      <UiIcon name="link" size={16} />
                      <span>Automatic follow-ups paused: Inbound reply received from prospect.</span>
                    </div>
                  )}

                  {/* Step 0: Featured Master Draft Card on Top */}
                  {masterDraft && (
                    <MasterDraftEditor
                      message={masterDraft}
                      companyName={enrollment.company_name}
                      contactName={enrollment.contact_name}
                      busy={busy}
                      act={act}
                      onSendSuccess={() =>
                        setNotice(`Cold outreach email dispatched to ${enrollment.recipient}! Follow-up #1 scheduled.`)
                      }
                    />
                  )}

                  {/* Subsequent Follow-up Steps Timeline */}
                  {followUps.length > 0 && (
                    <div style={{ marginTop: "24px" }}>
                      <h4 style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "16px" }}>
                        <UiIcon name="clock" size={18} /> Subsequent Follow-up Sequence ({followUps.length} steps)
                      </h4>
                      <div className="sequence-timeline">
                        {followUps.map((msg, idx) => (
                          <FollowUpStepEditor
                            key={msg.id}
                            message={msg}
                            companyName={enrollment.company_name}
                            contactName={enrollment.contact_name}
                            delayDays={detail.delays[idx]}
                            busy={busy}
                            act={act}
                          />
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Inbound Conversations & Prospect Replies */}
                  <div style={{ marginTop: "28px", borderTop: "1px solid var(--border)", paddingTop: "18px" }}>
                    <h4 style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "16px" }}>
                      <UiIcon name="mail" size={18} /> Inbound Conversation &amp; Reply Detection
                    </h4>

                    {enrollment.replies.length === 0 ? (
                      <p style={{ color: "#64748b", fontSize: "14px" }}>No replies received from this recipient yet.</p>
                    ) : (
                      enrollment.replies.map(reply => <ReplyCard key={reply.id} reply={reply} busy={busy} act={act} />)
                    )}

                    {/* Simulation Sandbox for Inbound Replies */}
                    <div className="simulate-reply-box">
                      <details>
                        <summary style={{ fontWeight: 600, color: "#475569" }}>
                          🧪 Test Inbound Reply Simulation (Local Pilot Testing)
                        </summary>
                        <p style={{ fontSize: "13px", color: "#64748b", margin: "8px 0" }}>
                          Simulate how the system catches incoming prospect emails, parses intent with Bedrock, halts follow-ups, and logs calendar tasks.
                        </p>
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: "12px", marginTop: "10px" }}>
                          <label>
                            Response Intent
                            <select
                              value={simType}
                              onChange={e => {
                                setSimType(e.target.value);
                                if (e.target.value === "meeting_requested") {
                                  setSimBody(
                                    "Hi, thank you for reaching out. We would be interested in learning more about Solwer TWMS. Can we schedule a meeting next week?"
                                  );
                                } else if (e.target.value === "interested") {
                                  setSimBody("Thanks for reaching out! Could you send over a spec sheet or deck on Solwer?");
                                } else {
                                  setSimBody("Not interested at this time, please remove me.");
                                }
                              }}
                            >
                              <option value="meeting_requested">Meeting Requested</option>
                              <option value="interested">Interested / Info Request</option>
                              <option value="not_interested">Not Interested</option>
                            </select>
                          </label>
                          <label>
                            Simulated Prospect Message
                            <input value={simBody} onChange={e => setSimBody(e.target.value)} />
                          </label>
                        </div>
                        <div style={{ marginTop: "12px" }}>
                          <button
                            className="secondary"
                            disabled={busy}
                            onClick={() =>
                              act(async () => {
                                await request(`/enrollments/${enrollment.id}/simulate-reply`, "POST", {
                                  body: simBody,
                                  classification: simType,
                                });
                                setNotice(`Inbound reply received from ${enrollment.recipient}! Sequence halted, task created.`);
                              })
                            }
                          >
                            Simulate Incoming Reply
                          </button>
                        </div>
                      </details>
                    </div>
                  </div>
                </details>
              );
            })}
          </div>
        )}
      </section>

      {/* Section: Dedicated Inbound Mail Tracking & Received Mail Analytics */}
      {!fixedLeadId && (
        <section>
          <InboundMailAnalyticsCard
            analytics={mailboxAnalytics}
            mailbox={mailbox}
            syncing={syncingInbox}
            onSync={syncInbox}
            busy={busy}
            act={act}
          />
        </section>
      )}

      {/* Section: Open Sales Tasks */}
      {!fixedLeadId && (
        <section>
          <div className="section-title">
            <div>
              <h2>Sales Tasks &amp; Meeting Coordination</h2>
              <p>Actions triggered by inbound replies or positive prospect engagement.</p>
            </div>
            <Link className="button-link secondary" href="/meetings">
              <UiIcon name="calendar" size={16} /> Calendar Availability
            </Link>
          </div>

          {tasks.filter(task => task.status === "open").length === 0 ? (
            <p style={{ color: "#64748b" }}>No open meeting tasks at this time.</p>
          ) : (
            tasks
              .filter(task => task.status === "open")
              .map(task => (
                <div className="candidate" key={task.id}>
                  <div>
                    <strong style={{ fontSize: "15px", color: "#0f172a" }}>{task.title}</strong>
                    <small style={{ color: "#64748b", display: "block" }}>Action required: Schedule discovery meeting</small>
                  </div>
                  <button disabled={busy} onClick={() => act(() => request(`/sales-tasks/${task.id}/complete`, "POST"))}>
                    Mark completed
                  </button>
                </div>
              ))
          )}
        </section>
      )}
    </div>
  );
}
