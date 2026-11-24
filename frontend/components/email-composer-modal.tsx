"use client";

import React, { useEffect, useState } from "react";
import { useAuth } from "../lib/auth-context";

interface EmailAccount {
  id: string;
  provider: "google" | "microsoft";
  account_email: string;
  display_name: string;
  is_default: boolean;
  status: string;
}

interface EmailComposerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSent?: (result: any) => void;
  leadId?: string;
  contactId?: string;
  defaultRecipient?: string;
  defaultSubject?: string;
}

export default function EmailComposerModal({
  isOpen,
  onClose,
  onSent,
  leadId,
  contactId,
  defaultRecipient = "",
  defaultSubject = "",
}: EmailComposerModalProps) {
  const { fetchWithAuth } = useAuth();
  const [accounts, setAccounts] = useState<EmailAccount[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string>("");
  const [recipient, setRecipient] = useState<string>(defaultRecipient);
  const [cc, setCc] = useState<string>("");
  const [bcc, setBcc] = useState<string>("");
  const [subject, setSubject] = useState<string>(defaultSubject);
  const [bodyHtml, setBodyHtml] = useState<string>("");
  const [showPreview, setShowPreview] = useState<boolean>(false);
  const [isSending, setIsSending] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setRecipient(defaultRecipient);
      setSubject(defaultSubject);
      setErrorMsg(null);
      setSuccessMsg(null);
      loadAccounts();
    }
  }, [isOpen, defaultRecipient, defaultSubject]);

  const loadAccounts = async () => {
    try {
      const res = await fetchWithAuth("/api/email-accounts");
      if (res.ok) {
        const data: EmailAccount[] = await res.json();
        const active = data.filter(a => a.status === "connected");
        setAccounts(active);
        const def = active.find(a => a.is_default) || active[0];
        if (def) {
          setSelectedAccountId(def.id);
        }
      }
    } catch {
      // offline
    }
  };

  if (!isOpen) return null;

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAccountId) {
      setErrorMsg("Please select an authorized email sender account.");
      return;
    }
    if (!recipient.trim() || !subject.trim() || !bodyHtml.trim()) {
      setErrorMsg("Recipient, subject, and message body are required.");
      return;
    }

    setIsSending(true);
    setErrorMsg(null);

    const ccList = cc.split(",").map(c => c.trim()).filter(Boolean);
    const bccList = bcc.split(",").map(b => b.trim()).filter(Boolean);

    try {
      const res = await fetchWithAuth("/api/email-accounts/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          account_id: selectedAccountId,
          lead_id: leadId || null,
          contact_id: contactId || null,
          recipient: recipient.trim(),
          subject: subject.trim(),
          body_html: bodyHtml.trim(),
          cc: ccList,
          bcc: bccList,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to send email");
      }

      setSuccessMsg(`Email successfully dispatched via ${data.sender_email}! Saved to your Sent folder.`);
      if (onSent) onSent(data);
      setTimeout(() => {
        onClose();
      }, 1800);
    } catch (err: any) {
      setErrorMsg(err.message || "An error occurred while sending.");
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div style={{
      position: "fixed",
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      backgroundColor: "rgba(0, 0, 0, 0.75)",
      backdropFilter: "blur(6px)",
      zIndex: 1000,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: "16px",
    }}>
      <div style={{
        backgroundColor: "#0f172a",
        border: "1px solid rgba(255, 255, 255, 0.12)",
        borderRadius: "16px",
        width: "100%",
        maxWidth: "680px",
        maxHeight: "90vh",
        display: "flex",
        flexDirection: "column",
        boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.7)",
      }}>
        {/* Modal Header */}
        <div style={{
          padding: "20px 24px",
          borderBottom: "1px solid rgba(255, 255, 255, 0.08)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <div style={{ width: "32px", height: "32px", borderRadius: "8px", background: "rgba(99, 102, 241, 0.2)", display: "flex", alignItems: "center", justifyContent: "center" }}>
              ✉️
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: "1.15rem", fontWeight: "700", color: "#f8fafc" }}>
                Send Customer Email
              </h3>
              <span style={{ fontSize: "0.8rem", color: "#94a3b8" }}>
                Sent directly through your connected Gmail or Outlook account
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              color: "#94a3b8",
              fontSize: "1.3rem",
              cursor: "pointer",
            }}
          >
            ✕
          </button>
        </div>

        {/* Modal Body */}
        <form onSubmit={handleSend} style={{ padding: "24px", overflowY: "auto", display: "flex", flexDirection: "column", gap: "16px" }}>
          {errorMsg && (
            <div style={{ padding: "10px 14px", borderRadius: "8px", backgroundColor: "rgba(239, 68, 68, 0.15)", color: "#f87171", fontSize: "0.88rem", border: "1px solid rgba(239, 68, 68, 0.3)" }}>
              ⚠️ {errorMsg}
            </div>
          )}

          {successMsg && (
            <div style={{ padding: "10px 14px", borderRadius: "8px", backgroundColor: "rgba(16, 185, 129, 0.15)", color: "#34d399", fontSize: "0.88rem", border: "1px solid rgba(16, 185, 129, 0.3)" }}>
              ✅ {successMsg}
            </div>
          )}

          {/* Sender Account */}
          <div>
            <label style={{ display: "block", fontSize: "0.82rem", fontWeight: "600", color: "#cbd5e1", marginBottom: "6px" }}>
              From (Authorized Account) *
            </label>
            {accounts.length === 0 ? (
              <div style={{ padding: "12px", borderRadius: "8px", backgroundColor: "rgba(234, 179, 8, 0.1)", border: "1px solid rgba(234, 179, 8, 0.3)", color: "#facc15", fontSize: "0.85rem" }}>
                No connected email accounts found. Please go to <a href="/settings/email-accounts" target="_blank" style={{ color: "#ffffff", textDecoration: "underline" }}>Settings &gt; Email Accounts</a> to connect your Gmail or Outlook.
              </div>
            ) : (
              <select
                value={selectedAccountId}
                onChange={e => setSelectedAccountId(e.target.value)}
                style={{
                  width: "100%",
                  padding: "10px 12px",
                  borderRadius: "8px",
                  backgroundColor: "#1e293b",
                  border: "1px solid rgba(255, 255, 255, 0.15)",
                  color: "#ffffff",
                  fontSize: "0.9rem",
                }}
              >
                {accounts.map(a => (
                  <option key={a.id} value={a.id}>
                    {a.account_email} ({a.provider === "google" ? "Gmail" : "Outlook"}) {a.is_default ? "• Default" : ""}
                  </option>
                ))}
              </select>
            )}
          </div>

          {/* Recipient */}
          <div>
            <label style={{ display: "block", fontSize: "0.82rem", fontWeight: "600", color: "#cbd5e1", marginBottom: "6px" }}>
              To (Customer Recipient) *
            </label>
            <input
              type="email"
              required
              value={recipient}
              onChange={e => setRecipient(e.target.value)}
              placeholder="lead@company.com"
              style={{
                width: "100%",
                padding: "10px 12px",
                borderRadius: "8px",
                backgroundColor: "#1e293b",
                border: "1px solid rgba(255, 255, 255, 0.15)",
                color: "#ffffff",
                fontSize: "0.9rem",
              }}
            />
          </div>

          {/* CC / BCC fields toggle */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
            <div>
              <label style={{ display: "block", fontSize: "0.78rem", color: "#94a3b8", marginBottom: "4px" }}>CC (comma separated)</label>
              <input
                type="text"
                value={cc}
                onChange={e => setCc(e.target.value)}
                placeholder="colleague@domain.com"
                style={{
                  width: "100%",
                  padding: "8px 10px",
                  borderRadius: "6px",
                  backgroundColor: "#1e293b",
                  border: "1px solid rgba(255, 255, 255, 0.1)",
                  color: "#ffffff",
                  fontSize: "0.85rem",
                }}
              />
            </div>
            <div>
              <label style={{ display: "block", fontSize: "0.78rem", color: "#94a3b8", marginBottom: "4px" }}>BCC (comma separated)</label>
              <input
                type="text"
                value={bcc}
                onChange={e => setBcc(e.target.value)}
                placeholder="crm-archive@domain.com"
                style={{
                  width: "100%",
                  padding: "8px 10px",
                  borderRadius: "6px",
                  backgroundColor: "#1e293b",
                  border: "1px solid rgba(255, 255, 255, 0.1)",
                  color: "#ffffff",
                  fontSize: "0.85rem",
                }}
              />
            </div>
          </div>

          {/* Subject */}
          <div>
            <label style={{ display: "block", fontSize: "0.82rem", fontWeight: "600", color: "#cbd5e1", marginBottom: "6px" }}>
              Subject *
            </label>
            <input
              type="text"
              required
              value={subject}
              onChange={e => setSubject(e.target.value)}
              placeholder="e.g. Exploring Solutions for Your Automotive Manufacturing Pipeline"
              style={{
                width: "100%",
                padding: "10px 12px",
                borderRadius: "8px",
                backgroundColor: "#1e293b",
                border: "1px solid rgba(255, 255, 255, 0.15)",
                color: "#ffffff",
                fontSize: "0.9rem",
              }}
            />
          </div>

          {/* Body */}
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
              <label style={{ fontSize: "0.82rem", fontWeight: "600", color: "#cbd5e1" }}>
                Email Content (HTML / Text) *
              </label>
              <button
                type="button"
                onClick={() => setShowPreview(!showPreview)}
                style={{
                  background: "none",
                  border: "none",
                  color: "#818cf8",
                  fontSize: "0.78rem",
                  cursor: "pointer",
                  fontWeight: "600",
                }}
              >
                {showPreview ? "Edit Content" : "Preview Output"}
              </button>
            </div>

            {showPreview ? (
              <div
                style={{
                  minHeight: "180px",
                  padding: "14px",
                  borderRadius: "8px",
                  backgroundColor: "#ffffff",
                  color: "#0f172a",
                  overflowY: "auto",
                  border: "1px solid rgba(255, 255, 255, 0.2)",
                  fontSize: "0.9rem",
                }}
                dangerouslySetInnerHTML={{ __html: bodyHtml || "<p style='color: #64748b;'>No content entered.</p>" }}
              />
            ) : (
              <textarea
                required
                rows={7}
                value={bodyHtml}
                onChange={e => setBodyHtml(e.target.value)}
                placeholder="<p>Hi Alex,</p><p>I noticed your company recently expanded your factory operations...</p>"
                style={{
                  width: "100%",
                  padding: "10px 12px",
                  borderRadius: "8px",
                  backgroundColor: "#1e293b",
                  border: "1px solid rgba(255, 255, 255, 0.15)",
                  color: "#ffffff",
                  fontSize: "0.9rem",
                  fontFamily: "inherit",
                }}
              />
            )}
          </div>

          {/* Actions */}
          <div style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: "12px",
            marginTop: "12px",
            borderTop: "1px solid rgba(255, 255, 255, 0.08)",
            paddingTop: "16px",
          }}>
            <button
              type="button"
              onClick={onClose}
              disabled={isSending}
              style={{
                padding: "9px 18px",
                borderRadius: "8px",
                backgroundColor: "rgba(255, 255, 255, 0.05)",
                color: "#e2e8f0",
                border: "1px solid rgba(255, 255, 255, 0.12)",
                fontSize: "0.9rem",
                fontWeight: "600",
                cursor: "pointer",
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSending || accounts.length === 0}
              style={{
                padding: "9px 24px",
                borderRadius: "8px",
                background: accounts.length === 0 ? "#475569" : "linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)",
                color: "#ffffff",
                border: "none",
                fontSize: "0.9rem",
                fontWeight: "700",
                cursor: accounts.length === 0 ? "not-allowed" : "pointer",
                boxShadow: "0 4px 14px rgba(79, 70, 229, 0.4)",
              }}
            >
              {isSending ? "Sending via OAuth..." : "Send Email Now 🚀"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
