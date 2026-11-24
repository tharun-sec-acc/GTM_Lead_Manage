"use client";

import React, { useEffect, useState } from "react";
import { useAuth } from "../../../lib/auth-context";
import { getApiBase } from "../../../lib/api-config";

const API_BASE = getApiBase();

export default function OrganizationSettingsPage() {
  const { organization, token, fetchWithAuth } = useAuth();
  const [orgData, setOrgData] = useState<any>(null);
  const [name, setName] = useState("");
  const [domain, setDomain] = useState("");
  const [saving, setSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    const fetchOrg = async () => {
      try {
        const res = await fetchWithAuth(`${API_BASE}/organizations/current`);
        if (res.ok) {
          const data = await res.json();
          setOrgData(data);
          setName(data.name || "");
          setDomain(data.domain || "");
        }
      } catch {
        // quiet catch
      }
    };
    fetchOrg();
  }, [organization?.id, token]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setStatusMsg(null);
    setErrorMsg(null);
    try {
      const res = await fetchWithAuth(`${API_BASE}/organizations/current`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, domain: domain.trim() || null }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Update failed" }));
        throw new Error(err.detail || "Failed to update organization");
      }
      const updated = await res.json();
      setOrgData(updated);
      setStatusMsg("Organization settings updated successfully.");
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to update organization.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "32px 24px" }}>
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: "#0f172a", margin: "0 0 8px 0" }}>
          Organization Settings
        </h1>
        <p style={{ fontSize: 14, color: "#64748b", margin: 0 }}>
          Manage your organization profile, multi-tenant workspace identity, and subscription tier.
        </p>
      </div>

      {statusMsg && (
        <div style={{ background: "#f0fdf4", color: "#166534", border: "1px solid #bbf7d0", padding: "12px 16px", borderRadius: 8, marginBottom: 24, fontSize: 14 }}>
          ✓ {statusMsg}
        </div>
      )}
      {errorMsg && (
        <div style={{ background: "#fef2f2", color: "#b91c1c", border: "1px solid #fecaca", padding: "12px 16px", borderRadius: 8, marginBottom: 24, fontSize: 14 }}>
          ⚠️ {errorMsg}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 24 }}>
        {/* Left: General Settings */}
        <div style={{ background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 12, padding: 24 }}>
          <h2 style={{ fontSize: 18, fontWeight: 600, color: "#1e293b", margin: "0 0 20px 0" }}>
            Workspace Profile
          </h2>
          <form onSubmit={handleSave} style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <div>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#334155", marginBottom: 6 }}>
                Organization Name
              </label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                style={{
                  width: "100%",
                  padding: "10px 14px",
                  border: "1px solid #cbd5e1",
                  borderRadius: 8,
                  fontSize: 14,
                  boxSizing: "border-box",
                }}
              />
            </div>

            <div>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#334155", marginBottom: 6 }}>
                Workspace Slug / URL Identifier
              </label>
              <input
                type="text"
                disabled
                value={orgData?.slug || ""}
                style={{
                  width: "100%",
                  padding: "10px 14px",
                  border: "1px solid #e2e8f0",
                  borderRadius: 8,
                  fontSize: 14,
                  color: "#64748b",
                  background: "#f8fafc",
                  boxSizing: "border-box",
                }}
              />
              <span style={{ fontSize: 12, color: "#94a3b8", marginTop: 4, display: "block" }}>
                Tenant identifier used for public booking links and API routing.
              </span>
            </div>

            <div>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#334155", marginBottom: 6 }}>
                Corporate Domain
              </label>
              <input
                type="text"
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                placeholder="e.g. cyberdyne.com"
                style={{
                  width: "100%",
                  padding: "10px 14px",
                  border: "1px solid #cbd5e1",
                  borderRadius: 8,
                  fontSize: 14,
                  boxSizing: "border-box",
                }}
              />
            </div>

            <button
              type="submit"
              disabled={saving}
              style={{
                alignSelf: "flex-start",
                padding: "10px 20px",
                background: saving ? "#94a3b8" : "#4f46e5",
                color: "#ffffff",
                border: "none",
                borderRadius: 8,
                fontSize: 14,
                fontWeight: 600,
                cursor: saving ? "not-allowed" : "pointer",
                marginTop: 8,
              }}
            >
              {saving ? "Saving..." : "Save Changes"}
            </button>
          </form>
        </div>

        {/* Right: Subscription & Tier */}
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div style={{ background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 12, padding: 24 }}>
            <h3 style={{ fontSize: 16, fontWeight: 600, color: "#1e293b", margin: "0 0 12px 0" }}>
              Current Subscription
            </h3>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
              <span style={{
                background: "#e0e7ff",
                color: "#4338ca",
                padding: "4px 12px",
                borderRadius: 999,
                fontSize: 12,
                fontWeight: 700,
                textTransform: "uppercase",
              }}>
                {orgData?.plan || "Pro"}
              </span>
              <span style={{ fontSize: 13, color: "#166534", fontWeight: 600 }}>Active</span>
            </div>
            <ul style={{ margin: 0, padding: "0 0 0 18px", fontSize: 13, color: "#475569", lineHeight: 1.8 }}>
              <li>Unlimited Leads & Contacts</li>
              <li>Autonomous AI Intelligence Agents</li>
              <li>Google Meet & MS Teams Integration</li>
              <li>Multi-Sheet Excel Deduplication</li>
              <li>Enterprise Zoho CRM v8 Sync</li>
            </ul>
          </div>

          <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 12, padding: 20 }}>
            <h4 style={{ fontSize: 14, fontWeight: 600, color: "#334155", margin: "0 0 8px 0" }}>
              Tenant Boundary
            </h4>
            <p style={{ fontSize: 12, color: "#64748b", margin: 0, lineHeight: 1.5 }}>
              All leads, campaigns, credentials, and meeting recordings are strictly isolated under Organization ID <code>{orgData?.id?.slice(0, 8)}...</code>.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
