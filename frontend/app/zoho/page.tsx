"use client";

import { useEffect, useState } from "react";
import UiIcon from "../../components/ui-icon";
import {
  fetchZohoConnection,
  verifyZohoConnection,
  fetchZohoAuthUrl,
  disconnectZoho,
  fetchZohoFieldMappings,
  updateZohoFieldMapping,
  triggerZohoSync,
  fetchZohoSyncJobs,
  fetchZohoSyncLogs,
  fetchZohoConflicts,
  resolveZohoConflict,
  type ZohoConnectionStatus,
  type ZohoVerifyResult,
  type ZohoFieldMappingItem,
  type ZohoSyncJobItem,
  type ZohoSyncLogItem,
  type ZohoSyncConflictItem,
} from "../../lib/zoho";

export default function ZohoCrmPage() {
  const [connection, setConnection] = useState<ZohoConnectionStatus | null>(null);
  const [mappings, setMappings] = useState<ZohoFieldMappingItem[]>([]);
  const [jobs, setJobs] = useState<ZohoSyncJobItem[]>([]);
  const [logs, setLogs] = useState<ZohoSyncLogItem[]>([]);
  const [conflicts, setConflicts] = useState<ZohoSyncConflictItem[]>([]);

  const [activeTab, setActiveTab] = useState<"mappings" | "jobs" | "logs" | "conflicts">("mappings");
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [verifyDetails, setVerifyDetails] = useState<ZohoVerifyResult | null>(null);
  const [syncing, setSyncing] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const [selectedModuleFilter, setSelectedModuleFilter] = useState("all");

  const isConnected = Boolean(connection?.is_connected ?? connection?.connected);
  const orgName = connection?.org_name || connection?.zoho_org_name || "Zoho Organization";
  const orgId = connection?.org_id || connection?.zoho_org_id || "—";
  const userEmail = connection?.user_email || connection?.zoho_user_email || "Authenticated User";
  const apiDomain = connection?.api_domain || "https://www.zohoapis.in";

  const loadAllData = async () => {
    try {
      setLoading(true);
      setErrorMsg("");
      const [conn, mapList, jobList, logList, confList] = await Promise.all([
        fetchZohoConnection().catch(() => ({ is_connected: false, connected: false })),
        fetchZohoFieldMappings().catch(() => []),
        fetchZohoSyncJobs().catch(() => []),
        fetchZohoSyncLogs(40).catch(() => []),
        fetchZohoConflicts().catch(() => []),
      ]);
      setConnection(conn);
      setMappings(mapList);
      setJobs(jobList);
      setLogs(logList);
      setConflicts(confList);
    } catch (err: any) {
      setErrorMsg(err?.message || "Failed to load Zoho CRM integration data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      if (params.get("connected") === "true") {
        setStatusMsg("Zoho CRM OAuth 2.0 authorization completed successfully! Live API connection active.");
      } else if (params.get("error")) {
        setErrorMsg(`Zoho OAuth authorization failed: ${params.get("error")}`);
      }
    }
    loadAllData();
  }, []);

  const handleVerifyConnection = async () => {
    try {
      setVerifying(true);
      setErrorMsg("");
      setStatusMsg("");
      const result = await verifyZohoConnection();
      setVerifyDetails(result);
      if (result.success) {
        setStatusMsg(result.message || "Zoho CRM live API connection verified successfully!");
        loadAllData();
      } else {
        setErrorMsg(result.message || "Verification failed.");
      }
    } catch (err: any) {
      setErrorMsg(err?.message || "Verification request failed.");
    } finally {
      setVerifying(false);
    }
  };

  const handleConnect = async () => {
    try {
      const { authorization_url } = await fetchZohoAuthUrl();
      if (authorization_url) {
        window.location.href = authorization_url;
      }
    } catch (err: any) {
      setErrorMsg(err?.message || "Failed to start Zoho OAuth flow.");
    }
  };

  const handleDisconnect = async () => {
    if (!confirm("Are you sure you want to disconnect Zoho CRM? Outbound and inbound synchronization will be suspended.")) {
      return;
    }
    try {
      await disconnectZoho();
      setStatusMsg("Zoho CRM disconnected successfully.");
      setVerifyDetails(null);
      loadAllData();
    } catch (err: any) {
      setErrorMsg(err?.message || "Failed to disconnect Zoho CRM.");
    }
  };

  const handleTriggerSync = async (type: "outbound" | "inbound" | "reconcile") => {
    try {
      setSyncing(type);
      setStatusMsg("");
      setErrorMsg("");
      const res = await triggerZohoSync(type);
      setStatusMsg(`Sync initiated successfully! Job ID: ${res.job_id || "running in background"}`);
      setTimeout(() => loadAllData(), 2000);
    } catch (err: any) {
      setErrorMsg(err?.message || "Sync failed to start.");
    } finally {
      setSyncing(null);
    }
  };

  const handleToggleMapping = async (m: ZohoFieldMappingItem) => {
    try {
      const updated = await updateZohoFieldMapping(m.id, { is_active: !m.is_active });
      setMappings((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
    } catch (err: any) {
      setErrorMsg(err?.message || "Failed to update mapping.");
    }
  };

  const handleChangeDirection = async (id: string, dir: any) => {
    try {
      const updated = await updateZohoFieldMapping(id, { sync_direction: dir });
      setMappings((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
    } catch (err: any) {
      setErrorMsg(err?.message || "Failed to update sync direction.");
    }
  };

  const handleChangeConflictPolicy = async (id: string, policy: any) => {
    try {
      const updated = await updateZohoFieldMapping(id, { conflict_policy: policy });
      setMappings((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
    } catch (err: any) {
      setErrorMsg(err?.message || "Failed to update conflict policy.");
    }
  };

  const handleResolveConflict = async (id: string, resolution: "use_gtm" | "use_zoho") => {
    try {
      await resolveZohoConflict(id, resolution);
      setStatusMsg(`Conflict resolved using ${resolution === "use_gtm" ? "GTM" : "Zoho"} value.`);
      loadAllData();
    } catch (err: any) {
      setErrorMsg(err?.message || "Failed to resolve conflict.");
    }
  };

  const filteredMappings = mappings.filter((m) => {
    if (selectedModuleFilter === "all") return true;
    return m.zoho_module.toLowerCase() === selectedModuleFilter.toLowerCase();
  });

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto", padding: "24px 20px" }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24, flexWrap: "wrap", gap: 16 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <h1 style={{ margin: 0, fontSize: 26, fontWeight: 700 }}>Zoho CRM Integration</h1>
              <span
                style={{
                  fontSize: 11,
                  padding: "4px 12px",
                  borderRadius: 12,
                  fontWeight: 700,
                  textTransform: "uppercase",
                  background: isConnected ? "#dcfce7" : "#fee2e2",
                  color: isConnected ? "#15803d" : "#b91c1c",
                  border: `1px solid ${isConnected ? "#86efac" : "#fca5a5"}`,
                }}
              >
                {isConnected ? "● CONNECTED" : "○ DISCONNECTED"}
              </span>
            </div>
            <p style={{ margin: "6px 0 0", color: "#64748b", fontSize: 14 }}>
              Two-way synchronization between GTMProspecting AI intelligence and Zoho CRM system of record.
            </p>
          </div>

          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {/* Verify Connection Button */}
            <button
              type="button"
              disabled={verifying}
              onClick={handleVerifyConnection}
              style={{
                padding: "8px 16px",
                borderRadius: 6,
                border: "1px solid #16a34a",
                background: "#f0fdf4",
                color: "#166534",
                fontSize: 13,
                fontWeight: 600,
                cursor: verifying ? "wait" : "pointer",
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
              }}
              title="Test and verify live communication with Zoho CRM API v8"
            >
              <UiIcon name="check" size={15} />
              {verifying ? "Verifying…" : "Verify Connection"}
            </button>

            {isConnected ? (
              <button
                type="button"
                onClick={handleDisconnect}
                style={{
                  padding: "8px 16px",
                  borderRadius: 6,
                  border: "1px solid #fecaca",
                  background: "#fff",
                  color: "#dc2626",
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Disconnect Zoho
              </button>
            ) : (
              <button
                type="button"
                onClick={handleConnect}
                style={{
                  padding: "8px 18px",
                  borderRadius: 6,
                  border: "none",
                  background: "var(--red)",
                  color: "#fff",
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                <UiIcon name="link" size={15} /> Connect Zoho CRM
              </button>
            )}

            <button
              type="button"
              onClick={loadAllData}
              style={{
                padding: "8px 14px",
                borderRadius: 6,
                border: "1px solid #cbd5e1",
                background: "#fff",
                color: "#334155",
                fontSize: 13,
                fontWeight: 600,
                cursor: "pointer",
                display: "inline-flex",
                alignItems: "center",
                gap: 5,
              }}
            >
              <UiIcon name="refresh" size={14} /> Refresh
            </button>
          </div>
        </div>

        {/* Notifications & Live Verification Banner */}
        {statusMsg && (
          <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", color: "#166534", padding: "12px 16px", borderRadius: 8, marginBottom: 16, fontSize: 13 }}>
            <strong>✓ Live API Status:</strong> {statusMsg}
          </div>
        )}
        {errorMsg && (
          <div style={{ background: "#fef2f2", border: "1px solid #fecaca", color: "#991b1b", padding: "12px 16px", borderRadius: 8, marginBottom: 16, fontSize: 13 }}>
            ⚠️ {errorMsg}
          </div>
        )}

        {/* Connection & Sync Control Cards */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 16, marginBottom: 24 }}>
          {/* Organization Details Card */}
          <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, padding: 18, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <span style={{ fontSize: 12, fontWeight: 700, color: "#64748b", textTransform: "uppercase" }}>CRM Connection Info</span>
              <span style={{ fontSize: 12, color: "#0284c7", fontWeight: 600 }}>API v8</span>
            </div>
            {isConnected ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                  <span style={{ color: "#64748b" }}>Organization Name:</span>
                  <strong style={{ color: "#0f172a" }}>{orgName}</strong>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                  <span style={{ color: "#64748b" }}>Org ID (ZGID):</span>
                  <code style={{ fontSize: 12, background: "#f1f5f9", padding: "2px 8px", borderRadius: 4, fontWeight: 600 }}>{orgId}</code>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                  <span style={{ color: "#64748b" }}>User Account:</span>
                  <span style={{ color: "#0f172a", fontWeight: 500 }}>{userEmail}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                  <span style={{ color: "#64748b" }}>API Domain:</span>
                  <span style={{ fontSize: 12, color: "#64748b" }}>{apiDomain}</span>
                </div>
                {verifyDetails?.time_zone && (
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                    <span style={{ color: "#64748b" }}>Time Zone:</span>
                    <span style={{ fontSize: 12, color: "#0f172a" }}>{verifyDetails.time_zone}</span>
                  </div>
                )}
                {verifyDetails?.trial_type && (
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                    <span style={{ color: "#64748b" }}>Plan / License:</span>
                    <span style={{ fontSize: 12, color: "#16a34a", fontWeight: 600, textTransform: "capitalize" }}>{verifyDetails.trial_type}</span>
                  </div>
                )}
                <div style={{ paddingTop: 8, borderTop: "1px solid #f1f5f9" }}>
                  <button
                    type="button"
                    onClick={handleVerifyConnection}
                    disabled={verifying}
                    style={{
                      width: "100%",
                      padding: "6px 12px",
                      borderRadius: 6,
                      border: "1px solid #cbd5e1",
                      background: "#f8fafc",
                      fontSize: 12,
                      fontWeight: 600,
                      color: "#334155",
                      cursor: "pointer",
                    }}
                  >
                    {verifying ? "Testing API…" : "⚡ Test Live API Handshake"}
                  </button>
                </div>
              </div>
            ) : (
              <div style={{ padding: "12px 0", textAlign: "center", color: "#64748b" }}>
                <p style={{ margin: 0, fontSize: 13 }}>Zoho CRM is currently not connected.</p>
                <p style={{ margin: "4px 0 12px", fontSize: 12 }}>Authorize GTMProspecting to sync contacts, leads, deals, notes, and bookings.</p>
                <button
                  type="button"
                  onClick={handleConnect}
                  style={{
                    background: "var(--red)",
                    color: "#fff",
                    border: "none",
                    padding: "7px 16px",
                    borderRadius: 6,
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  Authorize Zoho CRM
                </button>
              </div>
            )}
          </div>

          {/* Sync Trigger Card */}
          <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, padding: 18, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <span style={{ fontSize: 12, fontWeight: 700, color: "#64748b", textTransform: "uppercase" }}>Manual Sync Triggers</span>
              <span style={{ fontSize: 12, color: "#16a34a", fontWeight: 600 }}>Active Celery Workers</span>
            </div>
            <p style={{ margin: "0 0 14px", fontSize: 13, color: "#475569" }}>
              Execute immediate batch synchronization across Accounts, Contacts, Leads, Deals, Tasks, and Events.
            </p>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <button
                type="button"
                disabled={!isConnected || syncing !== null}
                onClick={() => handleTriggerSync("outbound")}
                style={{
                  padding: "8px 14px",
                  borderRadius: 6,
                  border: "1px solid #cbd5e1",
                  background: "#f8fafc",
                  color: "#0f172a",
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: isConnected ? "pointer" : "not-allowed",
                  opacity: isConnected ? 1 : 0.6,
                }}
              >
                {syncing === "outbound" ? "Syncing…" : "↑ Push Outbound"}
              </button>
              <button
                type="button"
                disabled={!isConnected || syncing !== null}
                onClick={() => handleTriggerSync("inbound")}
                style={{
                  padding: "8px 14px",
                  borderRadius: 6,
                  border: "1px solid #cbd5e1",
                  background: "#f8fafc",
                  color: "#0f172a",
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: isConnected ? "pointer" : "not-allowed",
                  opacity: isConnected ? 1 : 0.6,
                }}
              >
                {syncing === "inbound" ? "Syncing…" : "↓ Pull Inbound"}
              </button>
              <button
                type="button"
                disabled={!isConnected || syncing !== null}
                onClick={() => handleTriggerSync("reconcile")}
                style={{
                  padding: "8px 16px",
                  borderRadius: 6,
                  border: "1px solid var(--red)",
                  background: "var(--red)",
                  color: "#fff",
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: isConnected ? "pointer" : "not-allowed",
                  opacity: isConnected ? 1 : 0.6,
                }}
              >
                {syncing === "reconcile" ? "Reconciling…" : "⇄ Full Reconcile"}
              </button>
            </div>
            <div style={{ marginTop: 12, fontSize: 11, color: "#94a3b8" }}>
              Note: Sync actions dispatch asynchronous POST background jobs with idempotency keys.
            </div>
          </div>
        </div>

        {/* Tab Navigation */}
        <div style={{ display: "flex", borderBottom: "1px solid #e2e8f0", marginBottom: 20, gap: 8 }}>
          {[
            { id: "mappings", label: `Field Mappings (${mappings.length})` },
            { id: "jobs", label: `Sync Jobs (${jobs.length})` },
            { id: "logs", label: `Audit Logs (${logs.length})` },
            { id: "conflicts", label: `Conflicts (${conflicts.filter((c) => c.resolution_status === "unresolved").length})` },
          ].map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setActiveTab(t.id as any)}
              style={{
                padding: "10px 16px",
                border: "none",
                background: "none",
                fontSize: 14,
                fontWeight: 600,
                cursor: "pointer",
                color: activeTab === t.id ? "var(--red)" : "#64748b",
                borderBottom: `2px solid ${activeTab === t.id ? "var(--red)" : "transparent"}`,
              }}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Tab 1: Field Mappings Table */}
        {activeTab === "mappings" && (
          <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, padding: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14, flexWrap: "wrap", gap: 10 }}>
              <div style={{ fontSize: 13, color: "#64748b" }}>
                Admin-managed attribute mapping table across GTM entities and Zoho CRM modules.
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span style={{ fontSize: 12, color: "#64748b" }}>Module:</span>
                <select
                  value={selectedModuleFilter}
                  onChange={(e) => setSelectedModuleFilter(e.target.value)}
                  style={{ fontSize: 12, padding: "4px 8px", borderRadius: 6, border: "1px solid #cbd5e1" }}
                >
                  <option value="all">All Modules</option>
                  <option value="Accounts">Accounts</option>
                  <option value="Contacts">Contacts</option>
                  <option value="Leads">Leads</option>
                  <option value="Deals">Deals</option>
                  <option value="Tasks">Tasks</option>
                  <option value="Events">Events</option>
                </select>
              </div>
            </div>

            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, textAlign: "left" }}>
                <thead>
                  <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0" }}>
                    <th style={{ padding: "10px 12px", color: "#475569" }}>Zoho Module</th>
                    <th style={{ padding: "10px 12px", color: "#475569" }}>GTM Entity</th>
                    <th style={{ padding: "10px 12px", color: "#475569" }}>GTM Field</th>
                    <th style={{ padding: "10px 12px", color: "#475569" }}>Zoho CRM Field</th>
                    <th style={{ padding: "10px 12px", color: "#475569" }}>Sync Direction</th>
                    <th style={{ padding: "10px 12px", color: "#475569" }}>Conflict Policy</th>
                    <th style={{ padding: "10px 12px", color: "#475569" }}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredMappings.map((m) => (
                    <tr key={m.id} style={{ borderBottom: "1px solid #f1f5f9" }}>
                      <td style={{ padding: "10px 12px", fontWeight: 600 }}>{m.zoho_module}</td>
                      <td style={{ padding: "10px 12px", color: "#64748b" }}>{m.gtm_entity}</td>
                      <td style={{ padding: "10px 12px", fontFamily: "monospace", fontSize: 12 }}>{m.gtm_field}</td>
                      <td style={{ padding: "10px 12px", fontFamily: "monospace", fontSize: 12, color: "#0284c7" }}>{m.zoho_field}</td>
                      <td style={{ padding: "10px 12px" }}>
                        <select
                          value={m.sync_direction}
                          onChange={(e) => handleChangeDirection(m.id, e.target.value)}
                          style={{ fontSize: 12, padding: "2px 6px", borderRadius: 4, border: "1px solid #cbd5e1" }}
                        >
                          <option value="bidirectional">Bidirectional (⇄)</option>
                          <option value="gtm_to_zoho">Outbound (GTM → Zoho)</option>
                          <option value="zoho_to_gtm">Inbound (Zoho → GTM)</option>
                        </select>
                      </td>
                      <td style={{ padding: "10px 12px" }}>
                        <select
                          value={m.conflict_policy}
                          onChange={(e) => handleChangeConflictPolicy(m.id, e.target.value)}
                          style={{ fontSize: 12, padding: "2px 6px", borderRadius: 4, border: "1px solid #cbd5e1" }}
                        >
                          <option value="crm_wins">Zoho CRM Wins</option>
                          <option value="gtm_wins">GTM Wins</option>
                          <option value="newest_wins">Latest Timestamp</option>
                        </select>
                      </td>
                      <td style={{ padding: "10px 12px" }}>
                        <button
                          type="button"
                          onClick={() => handleToggleMapping(m)}
                          style={{
                            padding: "2px 8px",
                            borderRadius: 10,
                            fontSize: 11,
                            fontWeight: 600,
                            cursor: "pointer",
                            border: `1px solid ${m.is_active ? "#86efac" : "#cbd5e1"}`,
                            background: m.is_active ? "#dcfce7" : "#f1f5f9",
                            color: m.is_active ? "#15803d" : "#64748b",
                          }}
                        >
                          {m.is_active ? "Active" : "Inactive"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab 2: Sync Jobs Table */}
        {activeTab === "jobs" && (
          <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, padding: 16 }}>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, textAlign: "left" }}>
                <thead>
                  <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0" }}>
                    <th style={{ padding: "10px 12px", color: "#475569" }}>Job ID</th>
                    <th style={{ padding: "10px 12px", color: "#475569" }}>Type</th>
                    <th style={{ padding: "10px 12px", color: "#475569" }}>Status</th>
                    <th style={{ padding: "10px 12px", color: "#475569" }}>Processed</th>
                    <th style={{ padding: "10px 12px", color: "#475569" }}>Succeeded</th>
                    <th style={{ padding: "10px 12px", color: "#475569" }}>Failed</th>
                    <th style={{ padding: "10px 12px", color: "#475569" }}>Started At</th>
                    <th style={{ padding: "10px 12px", color: "#475569" }}>Finished At</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.length === 0 ? (
                    <tr>
                      <td colSpan={8} style={{ padding: 20, textAlign: "center", color: "#64748b" }}>
                        No sync jobs recorded yet. Click &apos;Push Outbound&apos; or &apos;Pull Inbound&apos; above to trigger a job.
                      </td>
                    </tr>
                  ) : (
                    jobs.map((j) => (
                      <tr key={j.id} style={{ borderBottom: "1px solid #f1f5f9" }}>
                        <td style={{ padding: "10px 12px", fontFamily: "monospace", fontSize: 12 }}>{j.id.slice(0, 8)}…</td>
                        <td style={{ padding: "10px 12px", fontWeight: 600 }}>{j.job_type}</td>
                        <td style={{ padding: "10px 12px" }}>
                          <span
                            style={{
                              padding: "2px 8px",
                              borderRadius: 10,
                              fontSize: 11,
                              fontWeight: 700,
                              background: j.status === "completed" ? "#dcfce7" : j.status === "failed" ? "#fee2e2" : "#fef3c7",
                              color: j.status === "completed" ? "#15803d" : j.status === "failed" ? "#b91c1c" : "#b45309",
                            }}
                          >
                            {j.status}
                          </span>
                        </td>
                        <td style={{ padding: "10px 12px" }}>{j.records_processed}</td>
                        <td style={{ padding: "10px 12px", color: "#16a34a", fontWeight: 600 }}>{j.records_succeeded}</td>
                        <td style={{ padding: "10px 12px", color: j.records_failed > 0 ? "#dc2626" : "#64748b", fontWeight: 600 }}>
                          {j.records_failed}
                        </td>
                        <td style={{ padding: "10px 12px", fontSize: 12, color: "#64748b" }}>
                          {new Date(j.started_at).toLocaleString()}
                        </td>
                        <td style={{ padding: "10px 12px", fontSize: 12, color: "#64748b" }}>
                          {j.finished_at ? new Date(j.finished_at).toLocaleString() : "—"}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab 3: Audit Logs Table */}
        {activeTab === "logs" && (
          <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, padding: 16 }}>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, textAlign: "left" }}>
                <thead>
                  <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0" }}>
                    <th style={{ padding: "10px 12px", color: "#475569" }}>Time</th>
                    <th style={{ padding: "10px 12px", color: "#475569" }}>Module</th>
                    <th style={{ padding: "10px 12px", color: "#475569" }}>Entity</th>
                    <th style={{ padding: "10px 12px", color: "#475569" }}>Action</th>
                    <th style={{ padding: "10px 12px", color: "#475569" }}>Status</th>
                    <th style={{ padding: "10px 12px", color: "#475569" }}>Message</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.length === 0 ? (
                    <tr>
                      <td colSpan={6} style={{ padding: 20, textAlign: "center", color: "#64748b" }}>
                        No audit logs available yet.
                      </td>
                    </tr>
                  ) : (
                    logs.map((l) => (
                      <tr key={l.id} style={{ borderBottom: "1px solid #f1f5f9" }}>
                        <td style={{ padding: "10px 12px", fontSize: 12, color: "#64748b" }}>
                          {new Date(l.created_at).toLocaleTimeString()}
                        </td>
                        <td style={{ padding: "10px 12px", fontWeight: 600 }}>{l.zoho_module}</td>
                        <td style={{ padding: "10px 12px", color: "#64748b" }}>{l.entity_type}</td>
                        <td style={{ padding: "10px 12px", fontFamily: "monospace", fontSize: 12 }}>{l.action}</td>
                        <td style={{ padding: "10px 12px" }}>
                          <span
                            style={{
                              padding: "2px 6px",
                              borderRadius: 4,
                              fontSize: 11,
                              fontWeight: 700,
                              background: l.status === "success" ? "#dcfce7" : "#fee2e2",
                              color: l.status === "success" ? "#15803d" : "#b91c1c",
                            }}
                          >
                            {l.status}
                          </span>
                        </td>
                        <td style={{ padding: "10px 12px", color: "#334155" }}>{l.message || "—"}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab 4: Conflict Resolution Panel */}
        {activeTab === "conflicts" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {conflicts.length === 0 ? (
              <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, padding: 32, textAlign: "center", color: "#64748b" }}>
                <div style={{ fontSize: 32, marginBottom: 8 }}>✓</div>
                <h3 style={{ margin: 0, color: "#0f172a" }}>No Sync Conflicts</h3>
                <p style={{ margin: "4px 0 0", fontSize: 13 }}>All records between GTMProspecting and Zoho CRM are perfectly aligned.</p>
              </div>
            ) : (
              conflicts.map((c) => (
                <div key={c.id} style={{ background: "#fff", border: "1px solid #fecaca", borderRadius: 10, padding: 18, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: 12, background: "#fee2e2", color: "#b91c1c", padding: "2px 8px", borderRadius: 10, fontWeight: 700 }}>
                        Conflict: {c.field_name}
                      </span>
                      <span style={{ fontSize: 13, fontWeight: 600 }}>{c.zoho_module} Record: {c.zoho_record_id}</span>
                    </div>
                    <span style={{ fontSize: 12, color: "#64748b" }}>{new Date(c.created_at).toLocaleString()}</span>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, margin: "14px 0" }}>
                    <div style={{ background: "#f8fafc", padding: 12, borderRadius: 8, border: "1px solid #e2e8f0" }}>
                      <span style={{ fontSize: 11, fontWeight: 700, color: "#64748b", textTransform: "uppercase" }}>GTM Prospecting Value:</span>
                      <div style={{ marginTop: 4, fontSize: 13, fontWeight: 600, color: "#0f172a" }}>{c.gtm_value || "(empty)"}</div>
                    </div>
                    <div style={{ background: "#f8fafc", padding: 12, borderRadius: 8, border: "1px solid #e2e8f0" }}>
                      <span style={{ fontSize: 11, fontWeight: 700, color: "#64748b", textTransform: "uppercase" }}>Zoho CRM Value:</span>
                      <div style={{ marginTop: 4, fontSize: 13, fontWeight: 600, color: "#0284c7" }}>{c.zoho_value || "(empty)"}</div>
                    </div>
                  </div>

                  {c.resolution_status === "unresolved" ? (
                    <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
                      <button
                        type="button"
                        onClick={() => handleResolveConflict(c.id, "use_gtm")}
                        style={{
                          padding: "6px 14px",
                          borderRadius: 6,
                          border: "1px solid #cbd5e1",
                          background: "#fff",
                          color: "#0f172a",
                          fontSize: 12,
                          fontWeight: 600,
                          cursor: "pointer",
                        }}
                      >
                        Keep GTM Value
                      </button>
                      <button
                        type="button"
                        onClick={() => handleResolveConflict(c.id, "use_zoho")}
                        style={{
                          padding: "6px 14px",
                          borderRadius: 6,
                          border: "none",
                          background: "#0284c7",
                          color: "#fff",
                          fontSize: 12,
                          fontWeight: 600,
                          cursor: "pointer",
                        }}
                      >
                        Accept Zoho Value
                      </button>
                    </div>
                  ) : (
                    <div style={{ fontSize: 12, color: "#16a34a", fontWeight: 600, textAlign: "right" }}>
                      ✓ Resolved ({c.resolution_status}) by {c.resolved_by || "user"}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        )}
      </div>
  );
}
