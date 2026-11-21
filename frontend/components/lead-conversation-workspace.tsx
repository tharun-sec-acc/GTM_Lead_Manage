"use client";

import Link from "next/link";
import React, { useEffect, useRef, useState } from "react";
import UiIcon from "./ui-icon";

const API = "http://localhost:8000";

export type TimelineMessage = {
  id: string;
  type: "inbound" | "outbound";
  step_number: number | null;
  manual_reply: boolean;
  sender: string | null;
  recipient: string | null;
  subject: string | null;
  body: string;
  classification?: string;
  status?: string;
  timestamp: string | null;
  attachments?: string[];
};

export type ConversationIntelligence = {
  classification: string;
  is_sales_conversation: boolean;
  interest_level: "VERY_HIGH" | "HIGH" | "MEDIUM" | "LOW" | "NONE";
  sentiment: "POSITIVE" | "NEUTRAL" | "NEGATIVE" | "SKEPTICAL" | "CURIOUS";
  message_summary: string;
  questions_asked: string[];
  requirements: string[];
  objections: string[];
  recommended_action: string;
  suggested_followup_date: string | null;
  confidence: number;
};

export type LeadConversation = {
  id: string;
  enrollment_id: string | null;
  lead_id: string | null;
  company_name: string;
  contact_id: string | null;
  contact_name: string;
  contact_title: string | null;
  recipient_email: string;
  lifecycle_stage: string;
  is_sales_conversation: boolean;
  classification: string;
  interest_level: "VERY_HIGH" | "HIGH" | "MEDIUM" | "LOW" | "NONE";
  sentiment: "POSITIVE" | "NEUTRAL" | "NEGATIVE" | "SKEPTICAL" | "CURIOUS";
  follow_up_status: "FOLLOW_UP_REQUIRED" | "FOLLOW_UP_SCHEDULED" | "FOLLOW_UP_DUE" | "FOLLOW_UP_COMPLETED" | "WAITING_FOR_RESPONSE" | "CLOSED" | "DRAFT";
  message_count: number;
  sent_count: number;
  reply_count: number;
  last_message_at: string | null;
  last_message_snippet: string;
  last_message_direction: string;
  timeline: TimelineMessage[];
  intelligence: ConversationIntelligence;
  tasks: Array<{ id: string; title: string; status: string; created_at: string | null }>;
};

type Attachment = { id: string; filename: string; size_bytes: number };

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return "recently";
  const diff = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days}d ago`;
  return new Date(dateStr).toLocaleDateString();
}

function renderFormattedBody(body: string) {
  if (!body) return null;
  const paragraphs = body.split(/\n\s*\n/);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "10px", lineHeight: "1.6", fontSize: "14px", color: "#1e293b" }}>
      {paragraphs.map((p, idx) => {
        const trimmed = p.trim();
        const lines = trimmed.split("\n");
        const isList = lines.every(l => /^\s*([*\-•]|\d+\.)\s+/.test(l));

        if (isList) {
          return (
            <ul key={idx} style={{ margin: "4px 0", paddingLeft: "20px" }}>
              {lines.map((l, lIdx) => {
                const clean = l.replace(/^\s*([*\-•]|\d+\.)\s+/, "");
                return <li key={lIdx} style={{ marginBottom: "4px" }}>{renderInlineTokens(clean)}</li>;
              })}
            </ul>
          );
        }

        return (
          <p key={idx} style={{ margin: 0 }}>
            {lines.map((line, lIdx) => (
              <React.Fragment key={lIdx}>
                {renderInlineTokens(line)}
                {lIdx < lines.length - 1 && <br />}
              </React.Fragment>
            ))}
          </p>
        );
      })}
    </div>
  );
}

function renderInlineTokens(text: string) {
  const parts: React.ReactNode[] = [];
  let remaining = text;
  let keyIdx = 0;

  while (remaining.length > 0) {
    // Bold **text**
    const boldMatch = remaining.match(/\*\*(.+?)\*\*/);
    // Italic *text*
    const italicMatch = remaining.match(/(?<!\*)\*([^*]+?)\*(?!\*)/);

    let earliestIdx = remaining.length;
    let matchType: "bold" | "italic" | null = null;
    let matchedStr = "";
    let matchedContent = "";

    if (boldMatch && boldMatch.index !== undefined && boldMatch.index < earliestIdx) {
      earliestIdx = boldMatch.index;
      matchType = "bold";
      matchedStr = boldMatch[0];
      matchedContent = boldMatch[1];
    }
    if (italicMatch && italicMatch.index !== undefined && italicMatch.index < earliestIdx) {
      earliestIdx = italicMatch.index;
      matchType = "italic";
      matchedStr = italicMatch[0];
      matchedContent = italicMatch[1];
    }

    if (matchType && earliestIdx < remaining.length) {
      if (earliestIdx > 0) {
        parts.push(<span key={keyIdx++}>{remaining.substring(0, earliestIdx)}</span>);
      }
      if (matchType === "bold") {
        parts.push(<strong key={keyIdx++} style={{ fontWeight: 600, color: "#0f172a" }}>{matchedContent}</strong>);
      } else {
        parts.push(<em key={keyIdx++}>{matchedContent}</em>);
      }
      remaining = remaining.substring(earliestIdx + matchedStr.length);
    } else {
      parts.push(<span key={keyIdx++}>{remaining}</span>);
      break;
    }
  }

  return parts;
}

export default function LeadConversationWorkspace({
  productId,
  onRefreshStats,
}: {
  productId?: string;
  onRefreshStats?: () => void;
}) {
  const [categoryTab, setCategoryTab] = useState<"sales" | "followup" | "automated" | "all">("sales");
  const [search, setSearch] = useState("");
  const [conversations, setConversations] = useState<LeadConversation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Counts
  const [counts, setCounts] = useState({ total: 0, sales_count: 0, followup_count: 0, automated_count: 0 });

  // Quick Reply Composer State
  const [replySubject, setReplySubject] = useState("");
  const [replyBody, setReplyBody] = useState("");
  const [replyAttachments, setReplyAttachments] = useState<Attachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const [generatingDraft, setGeneratingDraft] = useState(false);
  const [sendingReply, setSendingReply] = useState(false);
  const [replyNotice, setReplyNotice] = useState("");
  const [replyError, setReplyError] = useState("");

  // Follow-up status edit state
  const [savingStatus, setSavingStatus] = useState(false);
  const [followupNote, setFollowupNote] = useState("");

  const replyTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  // Fetch conversations
  const loadConversations = async (tab = categoryTab, q = search, showSpinner = true) => {
    if (showSpinner) setLoading(true);
    setError("");
    try {
      const url = `${API}/conversations?category=${tab}${q ? `&search=${encodeURIComponent(q)}` : ""}${productId ? `&product_id=${encodeURIComponent(productId)}` : ""}`;
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) throw new Error("Could not load lead conversations.");
      const data = await res.json();
      const list = (data.conversations || []) as LeadConversation[];
      setConversations(list);
      setCounts({
        total: data.total || 0,
        sales_count: data.sales_count || 0,
        followup_count: data.followup_count || 0,
        automated_count: data.automated_count || 0,
      });

      // Default selection
      if (list.length > 0) {
        if (!selectedId || !list.some(c => c.id === selectedId)) {
          setSelectedId(list[0].id);
        }
      } else {
        setSelectedId(null);
      }
    } catch (err) {
      if (showSpinner) setError(err instanceof Error ? err.message : "Failed to load conversations.");
    } finally {
      if (showSpinner) setLoading(false);
    }
  };

  useEffect(() => {
    loadConversations(categoryTab, search, true);
    // Auto-refresh conversations every 8 seconds so incoming replies appear live
    const interval = setInterval(() => {
      loadConversations(categoryTab, search, false);
    }, 8000);
    return () => clearInterval(interval);
  }, [categoryTab, search]);

  const activeConversation = conversations.find(c => c.id === selectedId) || null;

  // Initialize reply composer when active conversation changes
  useEffect(() => {
    if (activeConversation) {
      const lastMsg = activeConversation.timeline[activeConversation.timeline.length - 1];
      const subj = lastMsg?.subject || `Outreach follow-up for ${activeConversation.company_name}`;
      setReplySubject(subj.startsWith("Re:") ? subj : `Re: ${subj}`);
      setReplyBody("");
      setReplyAttachments([]);
      setReplyNotice("");
      setReplyError("");
      setFollowupNote("");
    }
  }, [selectedId]);

  // Auto-scroll timeline to the latest message whenever active conversation changes or new messages arrive
  useEffect(() => {
    if (activeConversation && activeConversation.timeline.length > 0) {
      setTimeout(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
      }, 50);
    }
  }, [selectedId, activeConversation?.timeline.length]);

  // Formatting helpers for quick reply
  const applyReplyFormatting = (prefix: string, suffix: string = "", placeholder: string = "") => {
    const el = replyTextareaRef.current;
    if (!el) {
      setReplyBody(prev => prev + prefix + placeholder + suffix);
      return;
    }
    const start = el.selectionStart;
    const end = el.selectionEnd;
    const current = replyBody;
    if (start !== end) {
      const sel = current.substring(start, end);
      setReplyBody(current.substring(0, start) + prefix + sel + suffix + current.substring(end));
      setTimeout(() => {
        el.focus();
        el.setSelectionRange(start + prefix.length, start + prefix.length + sel.length);
      }, 10);
    } else {
      const insert = prefix + placeholder + suffix;
      setReplyBody(current.substring(0, start) + insert + current.substring(end));
      setTimeout(() => {
        el.focus();
        el.setSelectionRange(start + prefix.length, start + prefix.length + placeholder.length);
      }, 10);
    }
  };

  // Upload collateral to inline reply
  const handleReplyFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setReplyError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API}/attachments/upload`, { method: "POST", body: form });
      if (!res.ok) throw new Error("Upload failed.");
      const data = await res.json();
      setReplyAttachments(prev => [...prev, { id: data.id, filename: data.filename_safe, size_bytes: data.size_bytes }]);
    } catch (err) {
      setReplyError(err instanceof Error ? err.message : "Failed to upload collateral.");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  // Generate AI Reply Draft
  const handleGenerateAIDraft = async () => {
    if (!activeConversation || !activeConversation.enrollment_id) return;
    setGeneratingDraft(true);
    setReplyError("");
    try {
      const res = await fetch(`${API}/conversations/${activeConversation.enrollment_id}/generate-draft`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!res.ok) throw new Error("Could not generate AI draft.");
      const data = await res.json();
      if (data.subject) setReplySubject(data.subject);
      if (data.body) setReplyBody(data.body);
    } catch (err) {
      setReplyError(err instanceof Error ? err.message : "Draft generation failed.");
    } finally {
      setGeneratingDraft(false);
    }
  };

  // Send inline reply
  const handleSendReply = async () => {
    if (!activeConversation || !activeConversation.enrollment_id) return;
    if (!replySubject.trim() || !replyBody.trim()) {
      setReplyError("Subject and body cannot be empty.");
      return;
    }
    setSendingReply(true);
    setReplyError("");
    setReplyNotice("");
    try {
      const res = await fetch(`${API}/conversations/${activeConversation.enrollment_id}/reply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          subject: replySubject.trim(),
          body: replyBody.trim(),
          attachment_ids: replyAttachments.map(a => a.id),
          send_now: true,
        }),
      });
      if (!res.ok) {
        const errJson = await res.json().catch(() => null);
        throw new Error(errJson?.detail || "Failed to send reply.");
      }
      const updatedConv = await res.json();
      setReplyNotice("✓ Follow-up email dispatched successfully!");
      setReplyBody("");
      setReplyAttachments([]);

      // Update conversations list with fresh thread
      setConversations(prev => prev.map(c => c.id === updatedConv.id ? updatedConv : c));
      onRefreshStats?.();
    } catch (err) {
      setReplyError(err instanceof Error ? err.message : "Failed to dispatch email.");
    } finally {
      setSendingReply(false);
    }
  };

  // Update follow-up status
  const handleUpdateFollowupStatus = async (newStatus: string) => {
    if (!activeConversation || !activeConversation.enrollment_id) return;
    setSavingStatus(true);
    try {
      const res = await fetch(`${API}/conversations/${activeConversation.enrollment_id}/followup-status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          status: newStatus,
          note: followupNote.trim() || undefined,
        }),
      });
      if (!res.ok) throw new Error("Could not update follow-up status.");
      const updatedConv = await res.json();
      setConversations(prev => prev.map(c => c.id === updatedConv.id ? updatedConv : c));
      setFollowupNote("");
      onRefreshStats?.();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Update failed.");
    } finally {
      setSavingStatus(false);
    }
  };

  return (
    <div className="lead-conversation-workspace">
      {/* Workspace Header Tabs & Search */}
      <div className="conversation-header-bar">
        <div className="conversation-tabs">
          <button
            type="button"
            className={`conv-tab-btn ${categoryTab === "sales" ? "active" : ""}`}
            onClick={() => setCategoryTab("sales")}
          >
            <UiIcon name="fire" size={14} />
            <span>Sales Active</span>
            <span className="conv-tab-count">{counts.sales_count}</span>
          </button>
          <button
            type="button"
            className={`conv-tab-btn ${categoryTab === "followup" ? "active" : ""}`}
            onClick={() => setCategoryTab("followup")}
          >
            <UiIcon name="clock" size={14} />
            <span>Follow-ups Due</span>
            <span className="conv-tab-count">{counts.followup_count}</span>
          </button>
          <button
            type="button"
            className={`conv-tab-btn ${categoryTab === "all" ? "active" : ""}`}
            onClick={() => setCategoryTab("all")}
          >
            <UiIcon name="inbox" size={14} />
            <span>All Threads</span>
            <span className="conv-tab-count">{counts.total}</span>
          </button>
          <button
            type="button"
            className={`conv-tab-btn ${categoryTab === "automated" ? "active" : ""}`}
            onClick={() => setCategoryTab("automated")}
          >
            <UiIcon name="shield" size={14} />
            <span>Automated &amp; Bounces</span>
            <span className="conv-tab-count">{counts.automated_count}</span>
          </button>
        </div>

        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <div style={{ position: "relative", width: "240px" }}>
            <input
              type="search"
              placeholder="Search prospects, replies..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              onKeyDown={e => e.key === "Enter" && loadConversations(categoryTab, search)}
              style={{ width: "100%", padding: "7px 12px", fontSize: "13px", borderRadius: "6px" }}
            />
          </div>
          <button
            type="button"
            className="secondary"
            onClick={() => loadConversations(categoryTab, search)}
            style={{ padding: "7px 12px", fontSize: "13px" }}
          >
            <UiIcon name="refresh" size={14} /> Refresh
          </button>
        </div>
      </div>

      {error && <div className="callout error" style={{ margin: "12px 0" }}>{error}</div>}

      {/* 3-Panel Main Layout */}
      <div className="conv-three-panel-layout">
        {/* PANEL 1: LEFT - Prospect Conversation List */}
        <div className="conv-panel conv-left-list">
          <div className="conv-list-header">
            <span style={{ fontSize: "12px", fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.5px" }}>
              Prospect Conversations ({conversations.length})
            </span>
          </div>

          <div className="conv-list-items">
            {loading && <div style={{ padding: "20px", textAlign: "center", color: "#64748b" }}>Loading conversations...</div>}

            {!loading && conversations.length === 0 && (
              <div style={{ padding: "30px 20px", textAlign: "center", color: "#64748b" }}>
                <p style={{ margin: 0, fontWeight: 600 }}>No conversations in this filter.</p>
                <small style={{ color: "#94a3b8" }}>Prospect sales replies will appear here automatically.</small>
              </div>
            )}

            {conversations.map(conv => {
              const isSelected = conv.id === selectedId;
              const interest = conv.interest_level || "MEDIUM";
              const isPositive = ["VERY_HIGH", "HIGH"].includes(interest);
              const initials = conv.company_name
                .split(" ")
                .filter(Boolean)
                .slice(0, 2)
                .map(w => w[0])
                .join("")
                .toUpperCase() || "C";

              return (
                <div
                  key={conv.id}
                  className={`conv-card-item ${isSelected ? "selected" : ""} ${conv.is_sales_conversation ? "is-sales" : "is-bounce"}`}
                  onClick={() => setSelectedId(conv.id)}
                >
                  <div className="conv-card-main-row">
                    <div className="conv-avatar">{initials}</div>
                    <div className="conv-card-head-info">
                      <div className="conv-card-top">
                        <span className="conv-card-company">{conv.company_name}</span>
                        <span className="conv-card-time">{timeAgo(conv.last_message_at)}</span>
                      </div>
                      <div className="conv-card-contact">
                        <strong>{conv.contact_name}</strong>
                        {conv.contact_title && <span className="conv-card-role"> · {conv.contact_title}</span>}
                      </div>
                    </div>
                  </div>

                  <div className="conv-card-badges">
                    <span className={`conv-pill ${conv.classification.toLowerCase()}`}>
                      {conv.classification.replace(/_/g, " ")}
                    </span>
                    {conv.is_sales_conversation && isPositive && (
                      <span className="conv-pill-interest high">
                        <UiIcon name="fire" size={10} />
                        <span>{interest} Intent</span>
                      </span>
                    )}
                    {conv.intelligence?.recommended_action && (
                      <span className="conv-card-rec-pill">
                        <UiIcon name="target" size={10} />
                        <span>Action Ready</span>
                      </span>
                    )}
                  </div>

                  <div className="conv-card-snippet">
                    <span className="snippet-dir-icon">
                      <UiIcon name={conv.last_message_direction === "inbound" ? "inbox" : "send"} size={11} />
                    </span>
                    <span className="snippet-text">{conv.last_message_snippet || "No messages yet"}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* PANEL 2: CENTER - Chronological Timeline & Inline Composer */}
        <div className="conv-panel conv-center-timeline">
          {!activeConversation ? (
            <div style={{ padding: "60px 20px", textAlign: "center", color: "#64748b" }}>
              <h3>Select a Conversation</h3>
              <p>Choose any prospect from the left list to review communication timeline and follow up.</p>
            </div>
          ) : (
            <div className="conv-timeline-container">
              {/* Timeline Header */}
              <div className="conv-timeline-header">
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
                    <h2 style={{ margin: 0, fontSize: "20px" }}>{activeConversation.company_name}</h2>
                    {activeConversation.lead_id && (
                      <Link
                        href={`/leads/${activeConversation.lead_id}`}
                        className="badge-link"
                        style={{ fontSize: "12px", background: "#f1f5f9", padding: "3px 8px", borderRadius: "4px", color: "var(--red)" }}
                      >
                        Lead 360 →
                      </Link>
                    )}
                  </div>
                  <div style={{ fontSize: "13px", color: "#64748b", marginTop: "4px" }}>
                    <strong>{activeConversation.contact_name}</strong> · {activeConversation.recipient_email}
                  </div>
                </div>

                <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                  <span className={`status-pill ${activeConversation.is_sales_conversation ? "positive" : "neutral"}`}>
                    {activeConversation.classification.replace(/_/g, " ")}
                  </span>
                  <span className={`status-pill ${activeConversation.follow_up_status === "FOLLOW_UP_REQUIRED" ? "attention" : "neutral"}`}>
                    {activeConversation.follow_up_status.replace(/_/g, " ")}
                  </span>
                </div>
              </div>

              {/* AI Conversation Summary Callout */}
              {activeConversation.intelligence && (
                <div className="conv-ai-summary-callout">
                  <div className="conv-ai-callout-header">
                    <div className="conv-ai-callout-title">
                      <span className="conv-ai-spark-icon"><UiIcon name="spark" size={15} /></span>
                      <strong>AI Conversation Intelligence</strong>
                    </div>
                    <span className="conv-ai-model-pill">
                      Claude 3.5 Sonnet · {Math.round((activeConversation.intelligence.confidence || 0.9) * 100)}% Confidence
                    </span>
                  </div>

                  <p className="conv-ai-callout-summary">
                    {activeConversation.intelligence.message_summary}
                  </p>

                  <div className="conv-ai-chips-grid">
                    {activeConversation.intelligence.questions_asked?.length > 0 && (
                      <div className="conv-ai-chip-group">
                        <span className="conv-ai-chip-label">
                          <UiIcon name="target" size={12} /> Prospect Questions:
                        </span>
                        <ul className="conv-ai-chip-list">
                          {activeConversation.intelligence.questions_asked.map((q, i) => (
                            <li key={i}>{q}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {activeConversation.intelligence.requirements?.length > 0 && (
                      <div className="conv-ai-chip-group">
                        <span className="conv-ai-chip-label">
                          <UiIcon name="checkCircle" size={12} /> Stated Requirements:
                        </span>
                        <ul className="conv-ai-chip-list">
                          {activeConversation.intelligence.requirements.map((req, i) => (
                            <li key={i}>{req}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Chronological Message Thread */}
              <div className="conv-messages-scroll">
                {activeConversation.timeline.map((msg, index) => {
                  const isOutbound = msg.type === "outbound";

                  return (
                    <div key={msg.id || index} className={`conv-msg-bubble ${isOutbound ? "outbound" : "inbound"}`}>
                      <div className="conv-msg-header">
                        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                          <span className={`conv-direction-pill ${isOutbound ? "out" : "in"}`}>
                            <UiIcon name={isOutbound ? "send" : "inbox"} size={11} />
                            <span>{isOutbound ? "Outreach Dispatched" : "Prospect Response"}</span>
                          </span>
                          {isOutbound && msg.step_number !== null && (
                            <span style={{ fontSize: "11px", color: "#64748b", fontWeight: 600 }}>
                              Step {msg.step_number}
                            </span>
                          )}
                          {!isOutbound && msg.classification && (
                            <span className="conv-classification-tag">
                              {msg.classification.replace(/_/g, " ")}
                            </span>
                          )}
                        </div>
                        <span style={{ fontSize: "12px", color: "#64748b" }}>
                          {msg.timestamp ? new Date(msg.timestamp).toLocaleString() : ""}
                        </span>
                      </div>

                      <div className="conv-msg-subject">
                        <strong>Subject:</strong> {msg.subject || "(No subject)"}
                      </div>

                      <div className="conv-msg-body">
                        {renderFormattedBody(msg.body)}
                      </div>

                      {/* Attachments Chip */}
                      {msg.attachments && msg.attachments.length > 0 && (
                        <div className="conv-msg-attachments">
                          <span style={{ fontSize: "12px", fontWeight: 600, color: "#475569", display: "inline-flex", alignItems: "center", gap: "4px" }}>
                            <UiIcon name="paperclip" size={12} /> Collateral attached:
                          </span>
                          <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginTop: "4px" }}>
                            {msg.attachments.map((att, aIdx) => (
                              <span key={aIdx} className="conv-attachment-chip">
                                <UiIcon name="file" size={12} />
                                <span>{att}</span>
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
                <div ref={messagesEndRef} />
              </div>

              {/* Inline Quick Reply & Follow-up Composer */}
              {activeConversation.enrollment_id && (
                <div className="conv-composer-card">
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                    <strong style={{ fontSize: "14px", color: "#0f172a", display: "inline-flex", alignItems: "center", gap: "6px" }}>
                      <UiIcon name="mail" size={14} /> Reply &amp; Follow Up with {activeConversation.contact_name}
                    </strong>
                    <button
                      type="button"
                      className="secondary"
                      disabled={generatingDraft}
                      onClick={handleGenerateAIDraft}
                      style={{ padding: "5px 12px", fontSize: "12px", display: "inline-flex", alignItems: "center", gap: "6px", color: "#4338ca", fontWeight: 600 }}
                    >
                      <UiIcon name="spark" size={14} />
                      {generatingDraft ? "Generating Claude Draft..." : "Generate AI Reply Draft"}
                    </button>
                  </div>

                  {replyError && <div className="callout error" style={{ margin: "6px 0", fontSize: "12px" }}>{replyError}</div>}
                  {replyNotice && <div className="callout success" style={{ margin: "6px 0", fontSize: "12px" }}>{replyNotice}</div>}

                  <input
                    value={replySubject}
                    onChange={e => setReplySubject(e.target.value)}
                    placeholder="Subject line..."
                    style={{ marginBottom: "8px", fontSize: "13px" }}
                  />

                  {/* Formatting Toolbar */}
                  <div className="composer-toolbar" style={{ marginBottom: "8px" }}>
                    <button type="button" className="toolbar-btn" onClick={() => applyReplyFormatting("**", "**")} title="Bold">
                      <strong>B</strong>
                    </button>
                    <button type="button" className="toolbar-btn" onClick={() => applyReplyFormatting("*", "*")} title="Italic">
                      <em>I</em>
                    </button>
                    <button type="button" className="toolbar-btn" onClick={() => applyReplyFormatting("\n• ", "")} title="Bullet List">
                      • List
                    </button>
                    <span className="toolbar-divider" />
                    <button
                      type="button"
                      className="toolbar-btn"
                      disabled={uploading}
                      onClick={() => fileInputRef.current?.click()}
                      style={{ color: "#0284c7" }}
                      title="Attach Collateral"
                    >
                      <UiIcon name="paperclip" size={13} /> {uploading ? "Uploading..." : "Attach Collateral"}
                    </button>
                    <input
                      type="file"
                      ref={fileInputRef}
                      style={{ display: "none" }}
                      accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg"
                      onChange={handleReplyFileUpload}
                    />
                  </div>

                  <textarea
                    ref={replyTextareaRef}
                    value={replyBody}
                    onChange={e => setReplyBody(e.target.value)}
                    rows={6}
                    placeholder="Write personalized response, address prospect questions, or confirm meeting..."
                    style={{ fontSize: "13px", lineHeight: "1.6", fontFamily: "inherit" }}
                  />

                  {replyAttachments.length > 0 && (
                    <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginTop: "6px" }}>
                      {replyAttachments.map(att => (
                        <span key={att.id} className="conv-attachment-chip">
                          <UiIcon name="file" size={12} />
                          <span>{att.filename}</span>
                          <button
                            type="button"
                            onClick={() => setReplyAttachments(prev => prev.filter(x => x.id !== att.id))}
                            style={{ border: "none", background: "none", cursor: "pointer", marginLeft: "4px", color: "#dc2626" }}
                          >
                            ×
                          </button>
                        </span>
                      ))}
                    </div>
                  )}

                  <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "10px" }}>
                    <button
                      type="button"
                      className="btn-send"
                      disabled={sendingReply || !replySubject.trim() || !replyBody.trim()}
                      onClick={handleSendReply}
                      style={{ padding: "8px 18px", fontSize: "13px", display: "inline-flex", alignItems: "center", gap: "6px" }}
                    >
                      <UiIcon name="send" size={14} />
                      {sendingReply ? "Sending..." : "Send Reply Now"}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* PANEL 3: RIGHT - AI Sales Intelligence & Action Panel */}
        <div className="conv-panel conv-right-sidebar">
          {!activeConversation ? (
            <div style={{ padding: "40px 16px", color: "#64748b", textAlign: "center" }}>
              Select a conversation to inspect sales intelligence.
            </div>
          ) : (
            <div className="conv-sidebar-content">
              {/* Prospect Card */}
              <div className="conv-side-card">
                <span className="side-card-title">PROSPECT DETAILS</span>
                <h4 style={{ margin: "6px 0 2px", fontSize: "16px" }}>{activeConversation.company_name}</h4>
                <p style={{ margin: 0, fontSize: "13px", color: "#64748b" }}>
                  {activeConversation.contact_name}
                  {activeConversation.contact_title && ` · ${activeConversation.contact_title}`}
                </p>
                <p style={{ margin: "4px 0 0", fontSize: "12px", color: "#0284c7" }}>{activeConversation.recipient_email}</p>
                <div style={{ marginTop: "10px", display: "flex", gap: "6px", flexWrap: "wrap" }}>
                  <span className="conv-pill-static">Stage: {activeConversation.lifecycle_stage}</span>
                  <span className="conv-pill-static">Messages: {activeConversation.message_count}</span>
                </div>
              </div>

              {/* Buying Intent & Intelligence */}
              <div className="conv-side-card">
                <span className="side-card-title">BUYING INTENT &amp; SENTIMENT</span>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "8px" }}>
                  <span style={{ fontSize: "13px", color: "#64748b" }}>Interest Level:</span>
                  <span className={`conv-pill-interest ${activeConversation.interest_level.toLowerCase()}`}>
                    {activeConversation.interest_level}
                  </span>
                </div>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "8px" }}>
                  <span style={{ fontSize: "13px", color: "#64748b" }}>Sentiment:</span>
                  <span className="conv-pill-static" style={{ fontWeight: 600 }}>
                    {activeConversation.sentiment}
                  </span>
                </div>

                {activeConversation.intelligence?.recommended_action && (
                  <div className="conv-action-card">
                    <div className="conv-action-card-header">
                      <UiIcon name="target" size={13} />
                      <span>AI Recommended Next Action</span>
                    </div>
                    <p className="conv-action-card-body">
                      {activeConversation.intelligence.recommended_action}
                    </p>
                  </div>
                )}
              </div>

              {/* Follow-up Activity & Status Management */}
              <div className="conv-side-card">
                <span className="side-card-title">FOLLOW-UP ACTIVITY</span>

                <div style={{ marginTop: "8px" }}>
                  <label style={{ fontSize: "12px", color: "#64748b", fontWeight: 600 }}>
                    Current Follow-up Status
                    <select
                      value={activeConversation.follow_up_status}
                      onChange={e => handleUpdateFollowupStatus(e.target.value)}
                      disabled={savingStatus}
                      style={{ marginTop: "4px", width: "100%", fontSize: "13px" }}
                    >
                      <option value="FOLLOW_UP_REQUIRED">Follow-up Required</option>
                      <option value="FOLLOW_UP_SCHEDULED">Follow-up Scheduled</option>
                      <option value="FOLLOW_UP_DUE">Follow-up Due</option>
                      <option value="FOLLOW_UP_COMPLETED">Follow-up Completed</option>
                      <option value="WAITING_FOR_RESPONSE">Waiting for Response</option>
                    </select>
                  </label>
                </div>

                <div style={{ marginTop: "10px" }}>
                  <label style={{ fontSize: "12px", color: "#64748b", fontWeight: 600 }}>
                    Follow-up Note / Task
                    <input
                      value={followupNote}
                      onChange={e => setFollowupNote(e.target.value)}
                      placeholder="e.g. Discussed pricing; follow up Friday"
                      style={{ marginTop: "4px", width: "100%", fontSize: "12px" }}
                    />
                  </label>
                  <button
                    type="button"
                    className="secondary"
                    disabled={savingStatus || !followupNote.trim()}
                    onClick={() => handleUpdateFollowupStatus(activeConversation.follow_up_status)}
                    style={{ marginTop: "6px", width: "100%", fontSize: "12px", padding: "6px" }}
                  >
                    {savingStatus ? "Saving..." : "Save Note"}
                  </button>
                </div>
              </div>

              {/* Collateral & Solwer Assets Shortcut */}
              <div className="conv-side-card">
                <span className="side-card-title">SOLWER COLLATERAL</span>
                <p style={{ margin: "4px 0 8px", fontSize: "12px", color: "#64748b" }}>
                  Standard collateral approved for solutions outreach:
                </p>
                <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "12px", padding: "6px 8px", background: "#f8fafc", borderRadius: "4px", border: "1px solid #e2e8f0" }}>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: "5px" }}>
                      <UiIcon name="file" size={12} /> TWMS Overview Presentation.pdf
                    </span>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => setReplyBody(prev => prev + "\n\nI have attached our Solwer TWMS Overview Presentation for your review.")}
                      style={{ fontSize: "11px", padding: "2px 6px" }}
                    >
                      Reference
                    </button>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "12px", padding: "6px 8px", background: "#f8fafc", borderRadius: "4px", border: "1px solid #e2e8f0" }}>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: "5px" }}>
                      <UiIcon name="file" size={12} /> Solwer Manufacturing Case Study.pdf
                    </span>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => setReplyBody(prev => prev + "\n\nI have attached our Solwer Manufacturing Case Study detailing 20-30% transport savings.")}
                      style={{ fontSize: "11px", padding: "2px 6px" }}
                    >
                      Reference
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
