"use client";

import React, { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useAuth } from "../../../lib/auth-context";
import { getApiBase } from "../../../lib/api-config";

interface ConnectedEmailAccount {
  id: string;
  provider: "google" | "microsoft";
  display_name: string;
  account_email: string;
  status: string;
  is_default: boolean;
  scopes: string[];
  error_message?: string | null;
  last_sync_at?: string | null;
  last_synced_count?: number;
  updated_at?: string | null;
  is_owner: boolean;
}

function EmailAccountsContent() {
  const { fetchWithAuth, organization } = useAuth();
  const searchParams = useSearchParams();
  const [accounts, setAccounts] = useState<ConnectedEmailAccount[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const API_BASE = getApiBase();

  useEffect(() => {
    const success = searchParams.get("success");
    const error = searchParams.get("error");
    if (success === "google_connected") {
      setSuccessMsg("Google Gmail account connected successfully! You can now send emails from this address.");
    } else if (success === "microsoft_connected") {
      setSuccessMsg("Microsoft Outlook account connected successfully! You can now send emails from this address.");
    }
    if (error) {
      setErrorMsg(`Authorization error: ${decodeURIComponent(error)}`);
    }
  }, [searchParams]);

  const loadAccounts = async () => {
    setIsLoading(true);
    try {
      const res = await fetchWithAuth("/api/email-accounts");
      if (res.ok) {
        const data = await res.json();
        setAccounts(data);
      } else {
        setErrorMsg("Failed to load connected email accounts.");
      }
    } catch {
      setErrorMsg("Network error loading email accounts.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadAccounts();
  }, []);

  const handleSetDefault = async (id: string) => {
    try {
      const res = await fetchWithAuth(`/api/email-accounts/${id}/default`, { method: "POST" });
      if (res.ok) {
        setSuccessMsg("Default email sending account updated.");
        loadAccounts();
      }
    } catch {
      setErrorMsg("Failed to update default sender.");
    }
  };

  const handleDisconnect = async (id: string) => {
    if (!confirm("Are you sure you want to disconnect this email account? Direct email sending from this address will stop.")) return;
    try {
      const res = await fetchWithAuth(`/api/email-accounts/${id}/disconnect`, { method: "POST" });
      if (res.ok) {
        setSuccessMsg("Email account disconnected.");
        loadAccounts();
      }
    } catch {
      setErrorMsg("Failed to disconnect email account.");
    }
  };

  const handleSyncInbox = async (id: string) => {
    setSyncingId(id);
    setErrorMsg(null);
    try {
      const res = await fetchWithAuth(`/api/email-accounts/${id}/sync`, { method: "POST" });
      const data = await res.json();
      if (res.ok) {
        setSuccessMsg(`Inbox synchronized! Processed ${data.synced_count || 0} messages (${data.matched_replies || 0} customer replies matched).`);
        loadAccounts();
      } else {
        setErrorMsg(data.detail || "Inbox synchronization failed.");
      }
    } catch {
      setErrorMsg("Network error during inbox sync.");
    } finally {
      setSyncingId(null);
    }
  };

  return (
    <div style={{ maxWidth: "1000px", margin: "0 auto", padding: "32px 16px" }}>
      {/* Header */}
      <div style={{ marginBottom: "28px" }}>
        <h1 style={{ fontSize: "1.85rem", fontWeight: "700", color: "#f8fafc", margin: "0 0 8px 0" }}>
          Email Accounts &amp; Outreach Sending
        </h1>
        <p style={{ color: "#94a3b8", fontSize: "0.95rem", margin: 0 }}>
          Connect your personal or corporate Gmail and Microsoft Outlook accounts. Emails to your leads are sent directly through your authenticated accounts and saved to your real Sent folder.
        </p>
      </div>

      {/* Notifications */}
      {successMsg && (
        <div style={{
          backgroundColor: "rgba(16, 185, 129, 0.12)",
          border: "1px solid rgba(16, 185, 129, 0.3)",
          color: "#34d399",
          padding: "12px 16px",
          borderRadius: "8px",
          marginBottom: "20px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}>
          <span>✅ {successMsg}</span>
          <button onClick={() => setSuccessMsg(null)} style={{ background: "none", border: "none", color: "#34d399", cursor: "pointer" }}>✕</button>
        </div>
      )}

      {errorMsg && (
        <div style={{
          backgroundColor: "rgba(239, 68, 68, 0.12)",
          border: "1px solid rgba(239, 68, 68, 0.3)",
          color: "#f87171",
          padding: "12px 16px",
          borderRadius: "8px",
          marginBottom: "20px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}>
          <span>⚠️ {errorMsg}</span>
          <button onClick={() => setErrorMsg(null)} style={{ background: "none", border: "none", color: "#f87171", cursor: "pointer" }}>✕</button>
        </div>
      )}

      {/* Connection Buttons */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
        gap: "16px",
        marginBottom: "32px",
      }}>
        {/* Connect Gmail */}
        <div style={{
          backgroundColor: "rgba(255, 255, 255, 0.03)",
          border: "1px solid rgba(255, 255, 255, 0.08)",
          borderRadius: "12px",
          padding: "20px",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "14px" }}>
            <div style={{ width: "36px", height: "36px", borderRadius: "8px", backgroundColor: "rgba(239, 68, 68, 0.15)", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <span style={{ fontSize: "1.2rem" }}>📧</span>
            </div>
            <div>
              <div style={{ fontWeight: "600", color: "#f1f5f9" }}>Google Gmail / Workspace</div>
              <div style={{ fontSize: "0.8rem", color: "#94a3b8" }}>OAuth with gmail.send scope</div>
            </div>
          </div>
          <a
            href={`${API_BASE}/api/email-accounts/oauth/google/start`}
            style={{
              display: "block",
              textAlign: "center",
              padding: "10px",
              borderRadius: "8px",
              backgroundColor: "#ea4335",
              color: "#ffffff",
              textDecoration: "none",
              fontWeight: "600",
              fontSize: "0.9rem",
            }}
          >
            + Connect Gmail Account
          </a>
        </div>

        {/* Connect Outlook */}
        <div style={{
          backgroundColor: "rgba(255, 255, 255, 0.03)",
          border: "1px solid rgba(255, 255, 255, 0.08)",
          borderRadius: "12px",
          padding: "20px",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "14px" }}>
            <div style={{ width: "36px", height: "36px", borderRadius: "8px", backgroundColor: "rgba(37, 99, 235, 0.15)", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <span style={{ fontSize: "1.2rem" }}>📬</span>
            </div>
            <div>
              <div style={{ fontWeight: "600", color: "#f1f5f9" }}>Microsoft Outlook / 365</div>
              <div style={{ fontSize: "0.8rem", color: "#94a3b8" }}>Microsoft Graph Mail.Send</div>
            </div>
          </div>
          <a
            href={`${API_BASE}/api/email-accounts/oauth/microsoft/start`}
            style={{
              display: "block",
              textAlign: "center",
              padding: "10px",
              borderRadius: "8px",
              backgroundColor: "#0078d4",
              color: "#ffffff",
              textDecoration: "none",
              fontWeight: "600",
              fontSize: "0.9rem",
            }}
          >
            + Connect Outlook Account
          </a>
        </div>
      </div>

      {/* Connected Accounts List */}
      <div style={{
        backgroundColor: "rgba(255, 255, 255, 0.02)",
        border: "1px solid rgba(255, 255, 255, 0.08)",
        borderRadius: "12px",
        padding: "24px",
      }}>
        <h2 style={{ fontSize: "1.2rem", fontWeight: "600", color: "#f8fafc", margin: "0 0 16px 0" }}>
          Connected Sending Accounts ({accounts.length})
        </h2>

        {isLoading ? (
          <p style={{ color: "#94a3b8", fontSize: "0.9rem" }}>Loading connected accounts...</p>
        ) : accounts.length === 0 ? (
          <div style={{ textAlign: "center", padding: "36px 16px", color: "#94a3b8" }}>
            <div style={{ fontSize: "2rem", marginBottom: "12px" }}>📭</div>
            <p style={{ fontSize: "1.05rem", fontWeight: "600", color: "#e2e8f0", margin: "0 0 6px 0" }}>No email accounts connected yet</p>
            <p style={{ fontSize: "0.88rem", maxWidth: "440px", margin: "0 auto" }}>
              Connect your Gmail or Outlook account above to enable direct customer email sending from inside the lead management dashboard.
            </p>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            {accounts.map(acc => (
              <div
                key={acc.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "16px",
                  borderRadius: "8px",
                  backgroundColor: "rgba(255, 255, 255, 0.03)",
                  border: acc.is_default ? "1px solid rgba(99, 102, 241, 0.5)" : "1px solid rgba(255, 255, 255, 0.06)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
                  <span style={{ fontSize: "1.5rem" }}>{acc.provider === "google" ? "📧" : "📬"}</span>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span style={{ fontWeight: "600", color: "#ffffff", fontSize: "0.95rem" }}>{acc.account_email}</span>
                      {acc.is_default && (
                        <span style={{
                          fontSize: "0.7rem",
                          fontWeight: "700",
                          backgroundColor: "rgba(99, 102, 241, 0.2)",
                          color: "#818cf8",
                          border: "1px solid rgba(99, 102, 241, 0.4)",
                          padding: "2px 6px",
                          borderRadius: "4px",
                        }}>
                          DEFAULT SENDER
                        </span>
                      )}
                      <span style={{
                        fontSize: "0.7rem",
                        fontWeight: "600",
                        padding: "2px 6px",
                        borderRadius: "4px",
                        backgroundColor: acc.status === "connected" ? "rgba(16, 185, 129, 0.15)" : "rgba(239, 68, 68, 0.15)",
                        color: acc.status === "connected" ? "#34d399" : "#f87171",
                      }}>
                        {acc.status.toUpperCase()}
                      </span>
                    </div>
                    <div style={{ fontSize: "0.8rem", color: "#94a3b8", marginTop: "2px" }}>
                      {acc.display_name} • Scopes: {acc.scopes.join(", ") || "Send"}
                    </div>
                    <div style={{ fontSize: "0.75rem", color: "#64748b", marginTop: "4px", display: "flex", alignItems: "center", gap: "8px" }}>
                      <span>🕒 Last synced: {acc.last_sync_at ? new Date(acc.last_sync_at).toLocaleString() : "Never synced"}</span>
                      {acc.last_synced_count !== undefined && acc.last_synced_count > 0 && (
                        <span>• ({acc.last_synced_count} messages)</span>
                      )}
                    </div>
                  </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
                  <button
                    onClick={() => handleSyncInbox(acc.id)}
                    disabled={syncingId === acc.id || acc.status !== "connected"}
                    style={{
                      padding: "6px 12px",
                      borderRadius: "6px",
                      backgroundColor: syncingId === acc.id ? "rgba(99, 102, 241, 0.3)" : "rgba(99, 102, 241, 0.12)",
                      color: "#a5b4fc",
                      border: "1px solid rgba(99, 102, 241, 0.3)",
                      fontSize: "0.82rem",
                      cursor: syncingId === acc.id || acc.status !== "connected" ? "not-allowed" : "pointer",
                      display: "flex",
                      alignItems: "center",
                      gap: "6px",
                    }}
                  >
                    <span>🔄</span>
                    <span>{syncingId === acc.id ? "Syncing..." : "Sync Inbox"}</span>
                  </button>
                  {!acc.is_default && (
                    <button
                      onClick={() => handleSetDefault(acc.id)}
                      style={{
                        padding: "6px 12px",
                        borderRadius: "6px",
                        backgroundColor: "rgba(255, 255, 255, 0.06)",
                        color: "#e2e8f0",
                        border: "1px solid rgba(255, 255, 255, 0.12)",
                        fontSize: "0.82rem",
                        cursor: "pointer",
                      }}
                    >
                      Make Default
                    </button>
                  )}
                  <button
                    onClick={() => handleDisconnect(acc.id)}
                    style={{
                      padding: "6px 12px",
                      borderRadius: "6px",
                      backgroundColor: "rgba(239, 68, 68, 0.1)",
                      color: "#f87171",
                      border: "1px solid rgba(239, 68, 68, 0.25)",
                      fontSize: "0.82rem",
                      cursor: "pointer",
                    }}
                  >
                    Disconnect
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function EmailAccountsPage() {
  return (
    <Suspense fallback={<div style={{ padding: "40px", color: "#94a3b8" }}>Loading Email Accounts...</div>}>
      <EmailAccountsContent />
    </Suspense>
  );
}
