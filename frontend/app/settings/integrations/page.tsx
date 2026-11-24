"use client";

import React, { useEffect, useState } from "react";
import { useAuth } from "../../../lib/auth-context";
import { getApiBase } from "../../../lib/api-config";

const API_BASE = getApiBase();

interface IntegrationItem {
  provider: string;
  display_name: string;
  connected: boolean;
  status: string;
  account_email?: string;
  scopes?: string[];
  capabilities: string[];
  updated_at?: string | null;
  error_message?: string | null;
  connect_url?: string | null;
}

export default function IntegrationsSettingsPage() {
  const { organization, token, fetchWithAuth } = useAuth();
  const [integrations, setIntegrations] = useState<IntegrationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const loadStatus = async () => {
    try {
      const res = await fetchWithAuth(`${API_BASE}/api/integrations/status`);
      if (res.ok) {
        const data = await res.json();
        setIntegrations(data.integrations || []);
      }
    } catch {
      // quiet catch
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, [organization?.id, token]);

  const handleDisconnect = async (provider: string, displayName: string) => {
    if (!confirm(`Are you sure you want to disconnect ${displayName}? OAuth tokens will be revoked.`)) return;
    setStatusMsg(null);
    setErrorMsg(null);
    try {
      const res = await fetchWithAuth(`${API_BASE}/api/integrations/${provider}/disconnect`, {
        method: "POST",
      });
      if (res.ok) {
        setStatusMsg(`${displayName} has been disconnected.`);
        loadStatus();
      } else {
        const err = await res.json();
        setErrorMsg(err.detail || "Failed to disconnect provider.");
      }
    } catch {
      setErrorMsg("Failed to disconnect provider.");
    }
  };

  const getProviderIcon = (provider: string) => {
    switch (provider) {
      case "google":
        return "🌐";
      case "microsoft":
        return "💼";
      case "zoho":
        return "🔄";
      case "apollo":
        return "🚀";
      case "bedrock":
        return "⚡";
      default:
        return "🔌";
    }
  };

  return (
    <div style={{ maxWidth: 1000, margin: "0 auto", padding: "32px 24px" }}>
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: "#0f172a", margin: "0 0 8px 0" }}>
          External Integrations & OAuth Hub
        </h1>
        <p style={{ fontSize: 14, color: "#64748b", margin: 0 }}>
          Connect customer-owned email, calendar, meeting providers, and CRM channels to your organization.
        </p>
      </div>

      {statusMsg && (
        <div style={{ background: "#f0fdf4", color: "#166534", border: "1px solid #bbf7d0", padding: "12px 16px", borderRadius: 8, marginBottom: 20, fontSize: 14 }}>
          ✓ {statusMsg}
        </div>
      )}
      {errorMsg && (
        <div style={{ background: "#fef2f2", color: "#b91c1c", border: "1px solid #fecaca", padding: "12px 16px", borderRadius: 8, marginBottom: 20, fontSize: 14 }}>
          ⚠️ {errorMsg}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 20 }}>
        {integrations.map((item) => (
          <div
            key={item.provider}
            style={{
              background: "#ffffff",
              border: "1px solid #e2e8f0",
              borderRadius: 14,
              padding: 24,
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              boxShadow: "0 1px 3px rgba(0,0,0,0.02)",
            }}
          >
            <div style={{ display: "flex", alignItems: "flex-start", gap: 18, maxWidth: "70%" }}>
              <div style={{
                width: 48,
                height: 48,
                borderRadius: 12,
                background: "#f1f5f9",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 24,
                flexShrink: 0,
              }}>
                {getProviderIcon(item.provider)}
              </div>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
                  <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: "#0f172a" }}>
                    {item.display_name}
                  </h3>
                  <span style={{
                    padding: "2px 8px",
                    borderRadius: 999,
                    fontSize: 11,
                    fontWeight: 700,
                    textTransform: "uppercase",
                    background: item.connected ? "#dcfce7" : "#f1f5f9",
                    color: item.connected ? "#15803d" : "#64748b",
                  }}>
                    {item.status.toUpperCase()}
                  </span>
                </div>

                {item.account_email && (
                  <p style={{ margin: "0 0 8px 0", fontSize: 13, color: "#334155", fontWeight: 500 }}>
                    Connected Account: <code>{item.account_email}</code>
                  </p>
                )}

                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                  {item.capabilities.map((cap) => (
                    <span
                      key={cap}
                      style={{
                        background: "#f8fafc",
                        border: "1px solid #e2e8f0",
                        color: "#475569",
                        padding: "2px 8px",
                        borderRadius: 6,
                        fontSize: 11,
                        fontWeight: 500,
                      }}
                    >
                      {cap}
                    </span>
                  ))}
                </div>

                {item.error_message && (
                  <p style={{ margin: "8px 0 0 0", fontSize: 12, color: "#b91c1c" }}>
                    ⚠️ {item.error_message}
                  </p>
                )}
              </div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 8, alignItems: "flex-end" }}>
              {item.connected ? (
                <>
                  <button
                    onClick={() => handleDisconnect(item.provider, item.display_name)}
                    style={{
                      padding: "8px 14px",
                      background: "transparent",
                      border: "1px solid #fecaca",
                      color: "#dc2626",
                      borderRadius: 8,
                      fontSize: 13,
                      fontWeight: 600,
                      cursor: "pointer",
                    }}
                  >
                    Disconnect
                  </button>
                  {item.connect_url && (
                    <a
                      href={`${API_BASE}${item.connect_url}`}
                      style={{
                        fontSize: 12,
                        color: "#6366f1",
                        textDecoration: "none",
                        fontWeight: 500,
                      }}
                    >
                      Re-authorize
                    </a>
                  )}
                </>
              ) : (
                item.connect_url ? (
                  <a
                    href={`${API_BASE}${item.connect_url}`}
                    style={{
                      padding: "9px 18px",
                      background: "linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)",
                      color: "#ffffff",
                      borderRadius: 8,
                      fontSize: 13,
                      fontWeight: 600,
                      textDecoration: "none",
                      display: "inline-block",
                      boxShadow: "0 2px 4px rgba(79, 70, 229, 0.2)",
                    }}
                  >
                    Connect Account
                  </a>
                ) : (
                  <span style={{ fontSize: 12, color: "#94a3b8" }}>Configured via Environment</span>
                )
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
