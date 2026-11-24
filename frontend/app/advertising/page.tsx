"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useAuth } from "../../lib/auth-context";
import { getApiBase } from "../../lib/api-config";

const API_BASE = getApiBase();

interface ProviderInfo {
  provider: string;
  name: string;
  app_configured: boolean;
  capabilities: string[];
  writes_supported: boolean;
  requires: string[];
}

interface Connection {
  id: string;
  provider: string;
  external_account_id: string;
  account_name: string | null;
  status: string;
  has_credentials: boolean;
  last_synced_at: string | null;
  last_error: string | null;
}

interface CampaignRow {
  id: string;
  provider: string;
  external_id: string;
  name: string;
  status: string | null;
  currency: string;
  spend_cents: number;
  impressions: number;
  clicks: number;
  provider_leads: number;
  crm_leads: number;
  qualified_leads: number;
  opportunities: number;
  won_deals: number;
  won_value_cents: number;
  cost_per_lead_cents: number | null;
  cost_per_qualified_lead_cents: number | null;
  roas: number | null;
}

interface CampaignReport {
  campaigns: CampaignRow[];
  totals: {
    spend_cents: number;
    provider_leads: number;
    crm_leads: number;
    qualified_leads: number;
    opportunities: number;
    won_deals: number;
    won_value_cents: number;
    cost_per_lead_cents: number | null;
    cost_per_qualified_lead_cents: number | null;
  };
  attribution_model: string;
  caveat: string;
}

interface CaptureForm {
  id: string;
  name: string;
  slug: string;
  provider: string;
  provider_form_id: string | null;
  submission_count: number;
  is_active: boolean;
  requires_consent: boolean;
}

function money(cents: number | null, currency = "INR"): string {
  if (cents === null || cents === undefined) return "—";
  const symbol = currency === "INR" ? "₹" : `${currency} `;
  return `${symbol}${(cents / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

function when(value: string | null): string {
  if (!value) return "Never";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const panel: React.CSSProperties = {
  background: "#fff",
  border: "1px solid #e2e8f0",
  borderRadius: 12,
  padding: 20,
  marginBottom: 20,
};

const subtle: React.CSSProperties = { fontSize: 13, color: "#64748b", margin: 0 };

const input: React.CSSProperties = {
  padding: "8px 10px",
  borderRadius: 8,
  border: "1px solid #cbd5e1",
  fontSize: 13,
  width: "100%",
};

const th: React.CSSProperties = {
  textAlign: "left",
  fontSize: 11,
  textTransform: "uppercase",
  letterSpacing: "0.04em",
  color: "#64748b",
  padding: "8px 10px",
  borderBottom: "1px solid #e2e8f0",
  whiteSpace: "nowrap",
};

const td: React.CSSProperties = {
  padding: "10px",
  fontSize: 13,
  color: "#0f172a",
  borderBottom: "1px solid #f1f5f9",
  whiteSpace: "nowrap",
};

export default function AdvertisingPage() {
  const { organization, fetchWithAuth } = useAuth();
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [report, setReport] = useState<CampaignReport | null>(null);
  const [forms, setForms] = useState<CaptureForm[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [snippet, setSnippet] = useState<string | null>(null);
  const [connect, setConnect] = useState({
    provider: "meta",
    external_account_id: "",
    account_name: "",
    access_token: "",
  });
  const [formDraft, setFormDraft] = useState({
    name: "",
    slug: "",
    provider: "website",
    provider_form_id: "",
  });

  const role = organization?.role || "";
  const canManage = ["owner", "admin", "super_admin", "manager"].includes(role);

  const load = useCallback(async () => {
    try {
      const [providersRes, connectionsRes, reportRes, formsRes] = await Promise.all([
        fetchWithAuth(`${API_BASE}/advertising/providers`),
        fetchWithAuth(`${API_BASE}/advertising/connections`),
        fetchWithAuth(`${API_BASE}/advertising/reports/campaigns`),
        fetchWithAuth(`${API_BASE}/advertising/forms`),
      ]);
      if (providersRes.ok) setProviders(await providersRes.json());
      if (connectionsRes.ok) setConnections(await connectionsRes.json());
      if (reportRes.ok) setReport(await reportRes.json());
      if (formsRes.ok) setForms(await formsRes.json());
      setError(null);
    } catch {
      setError("Could not reach the advertising workspace.");
    } finally {
      setLoading(false);
    }
  }, [fetchWithAuth]);

  useEffect(() => {
    load();
  }, [load]);

  const saveConnection = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy("connect");
    setError(null);
    setStatus(null);
    try {
      const res = await fetchWithAuth(`${API_BASE}/advertising/connections`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: connect.provider,
          external_account_id: connect.external_account_id.trim(),
          account_name: connect.account_name.trim() || null,
          access_token: connect.access_token.trim() || null,
        }),
      });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.detail || "Could not save the account.");
      setStatus(
        payload.status === "connected"
          ? "Advertising account saved with encrypted credentials."
          : "Account saved. Add a provider-approved token to enable sync.",
      );
      setConnect({ provider: connect.provider, external_account_id: "", account_name: "", access_token: "" });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the account.");
    } finally {
      setBusy(null);
    }
  };

  const syncConnection = async (connection: Connection) => {
    setBusy(connection.id);
    setError(null);
    setStatus(null);
    try {
      const res = await fetchWithAuth(
        `${API_BASE}/advertising/connections/${connection.id}/sync`,
        { method: "POST" },
      );
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.detail || "Provider sync failed.");
      setStatus(
        `Synced ${payload.created + payload.updated} campaign(s) from ${connection.provider}.`,
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Provider sync failed.");
      await load();
    } finally {
      setBusy(null);
    }
  };

  const disconnect = async (connection: Connection) => {
    setBusy(connection.id);
    setError(null);
    try {
      const res = await fetchWithAuth(
        `${API_BASE}/advertising/connections/${connection.id}`,
        { method: "DELETE" },
      );
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.detail || "Could not disconnect the account.");
      setStatus("Credentials removed. Provider records are kept for reporting.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not disconnect the account.");
    } finally {
      setBusy(null);
    }
  };

  const createForm = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy("form");
    setError(null);
    setStatus(null);
    try {
      const res = await fetchWithAuth(`${API_BASE}/advertising/forms`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: formDraft.name.trim(),
          slug: formDraft.slug.trim(),
          provider: formDraft.provider,
          provider_form_id: formDraft.provider_form_id.trim() || null,
        }),
      });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.detail || "Could not create the form.");
      setStatus(`Form "${payload.name}" is ready at /public/forms/${payload.slug}/submit.`);
      setFormDraft({ name: "", slug: "", provider: "website", provider_form_id: "" });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the form.");
    } finally {
      setBusy(null);
    }
  };

  const showEmbed = async (form: CaptureForm) => {
    setBusy(form.id);
    setError(null);
    try {
      const res = await fetchWithAuth(`${API_BASE}/advertising/forms/${form.id}/embed`);
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.detail || "Could not build the embed snippet.");
      setSnippet(payload.snippet);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not build the embed snippet.");
    } finally {
      setBusy(null);
    }
  };

  const copySnippet = async () => {
    if (!snippet) return;
    try {
      await navigator.clipboard.writeText(snippet);
      setStatus("Embed snippet copied to the clipboard.");
    } catch {
      setError("Clipboard access was blocked. Select the snippet text and copy it manually.");
    }
  };

  const totals = report?.totals;

  return (
    <div style={{ maxWidth: 1240, margin: "0 auto", padding: "32px 24px" }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: "#0f172a", margin: "0 0 8px 0" }}>
          Advertising &amp; lead capture
        </h1>
        <p style={subtle}>
          Connect paid channels, capture every lead into the CRM, and see which campaigns produce
          qualified pipeline and won revenue for {organization?.name || "this organization"}.
        </p>
      </div>

      {error && (
        <div style={{ background: "#fef2f2", color: "#b91c1c", border: "1px solid #fecaca", padding: "12px 16px", borderRadius: 8, marginBottom: 16, fontSize: 14 }}>
          ⚠️ {error}
        </div>
      )}
      {status && (
        <div style={{ background: "#f0fdf4", color: "#166534", border: "1px solid #bbf7d0", padding: "12px 16px", borderRadius: 8, marginBottom: 16, fontSize: 14 }}>
          ✓ {status}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 12, marginBottom: 20 }}>
        {[
          { label: "Ad spend", value: money(totals?.spend_cents ?? 0) },
          { label: "Provider leads", value: totals?.provider_leads ?? 0 },
          { label: "CRM leads", value: totals?.crm_leads ?? 0 },
          { label: "Qualified", value: totals?.qualified_leads ?? 0 },
          { label: "Cost / lead", value: money(totals?.cost_per_lead_cents ?? null) },
          { label: "Won revenue", value: money(totals?.won_value_cents ?? 0) },
        ].map((tile) => (
          <div key={tile.label} style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 12, padding: "14px 16px" }}>
            <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.05em", color: "#64748b" }}>{tile.label}</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: "#0f172a", marginTop: 6 }}>{tile.value}</div>
          </div>
        ))}
      </div>

      <div style={panel}>
        <h2 style={{ fontSize: 16, fontWeight: 700, color: "#0f172a", margin: "0 0 6px 0" }}>Connected accounts</h2>
        <p style={{ ...subtle, marginBottom: 14 }}>
          Read-only access. GTMProspecting never changes a budget, pauses a campaign or spends money.
        </p>
        {connections.length === 0 ? (
          <p style={subtle}>No ad accounts connected yet.</p>
        ) : (
          <div style={{ display: "grid", gap: 10 }}>
            {connections.map((connection) => (
              <div key={connection.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap", border: "1px solid #e2e8f0", borderRadius: 10, padding: "12px 14px" }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: "#0f172a" }}>
                    {connection.account_name || connection.external_account_id}{" "}
                    <span style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase" }}>{connection.provider}</span>
                  </div>
                  <div style={{ fontSize: 12, color: "#64748b" }}>
                    {connection.status.replace("_", " ")} · last sync {when(connection.last_synced_at)}
                    {connection.last_error ? ` · ${connection.last_error}` : ""}
                  </div>
                </div>
                {canManage && (
                  <div style={{ display: "flex", gap: 8 }}>
                    <button
                      type="button"
                      onClick={() => syncConnection(connection)}
                      disabled={busy === connection.id || !connection.has_credentials}
                      style={{ padding: "8px 14px", borderRadius: 8, border: "none", background: connection.has_credentials ? "#4f46e5" : "#e2e8f0", color: connection.has_credentials ? "#fff" : "#64748b", fontSize: 13, fontWeight: 600, cursor: connection.has_credentials ? "pointer" : "default" }}
                    >
                      {busy === connection.id ? "Working…" : "Sync now"}
                    </button>
                    <button
                      type="button"
                      onClick={() => disconnect(connection)}
                      disabled={busy === connection.id}
                      style={{ padding: "8px 14px", borderRadius: 8, border: "1px solid #cbd5e1", background: "#fff", color: "#334155", fontSize: 13, cursor: "pointer" }}
                    >
                      Disconnect
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {canManage && (
          <form onSubmit={saveConnection} style={{ marginTop: 16, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
            <label style={{ fontSize: 12, color: "#475569", display: "grid", gap: 4 }}>
              Provider
              <select
                value={connect.provider}
                onChange={(event) => setConnect({ ...connect, provider: event.target.value })}
                style={input}
              >
                {providers.map((provider) => (
                  <option key={provider.provider} value={provider.provider}>
                    {provider.name}
                  </option>
                ))}
              </select>
            </label>
            <label style={{ fontSize: 12, color: "#475569", display: "grid", gap: 4 }}>
              Account id
              <input
                required
                value={connect.external_account_id}
                onChange={(event) => setConnect({ ...connect, external_account_id: event.target.value })}
                placeholder={connect.provider === "meta" ? "act_1234567890" : "123-456-7890"}
                style={input}
              />
            </label>
            <label style={{ fontSize: 12, color: "#475569", display: "grid", gap: 4 }}>
              Account label
              <input
                value={connect.account_name}
                onChange={(event) => setConnect({ ...connect, account_name: event.target.value })}
                placeholder="India performance"
                style={input}
              />
            </label>
            <label style={{ fontSize: 12, color: "#475569", display: "grid", gap: 4 }}>
              Access token
              <input
                type="password"
                value={connect.access_token}
                onChange={(event) => setConnect({ ...connect, access_token: event.target.value })}
                placeholder="Stored encrypted"
                style={input}
              />
            </label>
            <div style={{ display: "flex", alignItems: "flex-end" }}>
              <button
                type="submit"
                disabled={busy === "connect"}
                style={{ padding: "9px 16px", borderRadius: 8, border: "none", background: "#4f46e5", color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer" }}
              >
                Save account
              </button>
            </div>
          </form>
        )}

        {providers.length > 0 && (
          <div style={{ marginTop: 14, display: "grid", gap: 6 }}>
            {providers.map((provider) => (
              <div key={provider.provider} style={{ fontSize: 12, color: provider.app_configured ? "#047857" : "#b45309" }}>
                {provider.name}: {provider.app_configured ? "app credentials configured" : "app credentials not configured"} —{" "}
                {provider.requires.join("; ")}
              </div>
            ))}
          </div>
        )}
      </div>

      <div style={panel}>
        <h2 style={{ fontSize: 16, fontWeight: 700, color: "#0f172a", margin: "0 0 6px 0" }}>Campaign performance</h2>
        <p style={{ ...subtle, marginBottom: 12 }}>{report?.caveat || "Attribution is shown once data is synced."}</p>
        {!report || report.campaigns.length === 0 ? (
          <p style={subtle}>{loading ? "Loading campaigns…" : "No campaign data yet. Sync a connected account."}</p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={th}>Campaign</th>
                  <th style={th}>Spend</th>
                  <th style={th}>Leads</th>
                  <th style={th}>CRM leads</th>
                  <th style={th}>Qualified</th>
                  <th style={th}>Opps</th>
                  <th style={th}>Won</th>
                  <th style={th}>CPL</th>
                  <th style={th}>Cost / qualified</th>
                </tr>
              </thead>
              <tbody>
                {report.campaigns.map((campaign) => (
                  <tr key={campaign.id}>
                    <td style={td}>
                      {campaign.name}
                      <div style={{ fontSize: 11, color: "#94a3b8" }}>
                        {campaign.provider} · {campaign.external_id}
                      </div>
                    </td>
                    <td style={td}>{money(campaign.spend_cents, campaign.currency)}</td>
                    <td style={td}>{campaign.provider_leads}</td>
                    <td style={td}>{campaign.crm_leads}</td>
                    <td style={td}>{campaign.qualified_leads}</td>
                    <td style={td}>{campaign.opportunities}</td>
                    <td style={td}>{money(campaign.won_value_cents, campaign.currency)}</td>
                    <td style={td}>{money(campaign.cost_per_lead_cents, campaign.currency)}</td>
                    <td style={td}>{money(campaign.cost_per_qualified_lead_cents, campaign.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div style={panel}>
        <h2 style={{ fontSize: 16, fontWeight: 700, color: "#0f172a", margin: "0 0 6px 0" }}>Capture forms</h2>
        <p style={{ ...subtle, marginBottom: 12 }}>
          Website forms post straight into the CRM with UTM, campaign and landing-page attribution.
        </p>
        {forms.length === 0 ? (
          <p style={subtle}>No forms yet.</p>
        ) : (
          <div style={{ display: "grid", gap: 10, marginBottom: 14 }}>
            {forms.map((form) => (
              <div key={form.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap", border: "1px solid #e2e8f0", borderRadius: 10, padding: "12px 14px" }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: "#0f172a" }}>{form.name}</div>
                  <div style={{ fontSize: 12, color: "#64748b" }}>
                    {form.provider} · /{form.slug} · {form.submission_count} submission(s)
                    {form.provider_form_id ? ` · form ${form.provider_form_id}` : ""}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => showEmbed(form)}
                  disabled={busy === form.id}
                  style={{ padding: "8px 14px", borderRadius: 8, border: "1px solid #cbd5e1", background: "#fff", color: "#334155", fontSize: 13, cursor: "pointer" }}
                >
                  Embed snippet
                </button>
              </div>
            ))}
          </div>
        )}

        {snippet && (
          <div style={{ marginBottom: 14 }}>
            <textarea
              readOnly
              value={snippet}
              rows={6}
              style={{ ...input, fontFamily: "monospace", fontSize: 11 }}
            />
            <button
              type="button"
              onClick={copySnippet}
              style={{ marginTop: 8, padding: "8px 14px", borderRadius: 8, border: "none", background: "#0f172a", color: "#fff", fontSize: 13, cursor: "pointer" }}
            >
              Copy snippet
            </button>
          </div>
        )}

        {canManage && (
          <form onSubmit={createForm} style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 12 }}>
            <label style={{ fontSize: 12, color: "#475569", display: "grid", gap: 4 }}>
              Form name
              <input
                required
                value={formDraft.name}
                onChange={(event) => setFormDraft({ ...formDraft, name: event.target.value })}
                placeholder="Website demo request"
                style={input}
              />
            </label>
            <label style={{ fontSize: 12, color: "#475569", display: "grid", gap: 4 }}>
              Slug
              <input
                required
                pattern="[a-z0-9][a-z0-9-]*"
                value={formDraft.slug}
                onChange={(event) => setFormDraft({ ...formDraft, slug: event.target.value })}
                placeholder="demo-request"
                style={input}
              />
            </label>
            <label style={{ fontSize: 12, color: "#475569", display: "grid", gap: 4 }}>
              Source
              <select
                value={formDraft.provider}
                onChange={(event) => setFormDraft({ ...formDraft, provider: event.target.value })}
                style={input}
              >
                <option value="website">Website</option>
                <option value="meta">Meta lead form</option>
                <option value="google">Google lead form</option>
              </select>
            </label>
            <label style={{ fontSize: 12, color: "#475569", display: "grid", gap: 4 }}>
              Provider form id
              <input
                value={formDraft.provider_form_id}
                onChange={(event) => setFormDraft({ ...formDraft, provider_form_id: event.target.value })}
                placeholder="Required for Meta/Google"
                style={input}
              />
            </label>
            <div style={{ display: "flex", alignItems: "flex-end" }}>
              <button
                type="submit"
                disabled={busy === "form"}
                style={{ padding: "9px 16px", borderRadius: 8, border: "none", background: "#4f46e5", color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer" }}
              >
                Create form
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
