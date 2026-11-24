"use client";

import React, { useEffect, useState } from "react";
import { useAuth } from "../../lib/auth-context";
import { getApiBase } from "../../lib/api-config";

const API_BASE = getApiBase();

interface Stage {
  id: string;
  name: string;
  position: number;
  probability: number;
  is_won: boolean;
  is_lost: boolean;
}

interface Pipeline {
  id: string;
  name: string;
  is_default: boolean;
  stages: Stage[];
}

interface Opportunity {
  id: string;
  name: string;
  stage_id: string;
  stage_name: string | null;
  lead_id: string;
  company_name: string | null;
  amount_cents: number;
  amount: number;
  currency: string;
  expected_close_date: string | null;
  status: string;
  owner_id: string | null;
  source: string | null;
}

interface CrmLead {
  id: string;
  company_name: string;
  domain: string | null;
  score: number;
  qualification_status: string;
  lifecycle_stage: string;
  owner_id: string | null;
}

interface PipelineMetrics {
  pipeline_id: string;
  pipeline_name: string;
  open_count: number;
  open_value_cents: number;
  weighted_forecast_cents: number;
  won_count: number;
  won_value_cents: number;
  lost_count: number;
  lost_value_cents: number;
  win_rate: number;
  average_cycle_days: number | null;
}

interface Task {
  id: string;
  title: string;
  status: string;
  priority: string;
  due_at: string | null;
  lead_id: string | null;
}

interface Summary {
  leads: { total: number; qualified: number; unqualified: number; customers: number };
  opportunities: {
    open_count: number;
    open_value_cents: number;
    weighted_forecast_cents: number;
    won_count: number;
    won_value_cents: number;
    lost_count: number;
    lost_value_cents: number;
    win_rate: number;
    average_cycle_days: number | null;
  };
  tasks: { open: number; overdue: number; completed: number };
  activities_last_30_days: number;
  needs_attention: { kind: string; label: string; entity_id: string; lead_id: string | null }[];
}

function money(cents: number, currency = "INR"): string {
  const value = cents / 100;
  return new Intl.NumberFormat(currency === "INR" ? "en-IN" : "en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(value);
}

function shortDate(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

const tile: React.CSSProperties = {
  background: "#ffffff",
  border: "1px solid #e2e8f0",
  borderRadius: 12,
  padding: "16px 18px",
};

export default function CrmPage() {
  const { fetchWithAuth, organization } = useAuth();
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [pipelineId, setPipelineId] = useState<string>("");
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [metrics, setMetrics] = useState<PipelineMetrics | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [leads, setLeads] = useState<CrmLead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    lead_id: "",
    name: "",
    amount: "",
    expected_close_date: "",
    source: "",
  });
  const [newTask, setNewTask] = useState("");

  const role = organization?.role || "";
  const canWrite = role !== "read_only";

  const loadPipelines = async () => {
    const res = await fetchWithAuth(`${API_BASE}/crm/pipelines`);
    if (!res.ok) return;
    const data: Pipeline[] = await res.json();
    setPipelines(data);
    if (!pipelineId && data.length) {
      const preferred = data.find((item) => item.is_default) || data[0];
      setPipelineId(preferred.id);
    }
  };

  const loadBoard = async (id: string) => {
    if (!id) return;
    const [oppsRes, summaryRes, metricsRes, tasksRes, leadsRes] = await Promise.all([
      fetchWithAuth(`${API_BASE}/crm/opportunities?pipeline_id=${id}&limit=300`),
      fetchWithAuth(`${API_BASE}/crm/summary`),
      fetchWithAuth(`${API_BASE}/crm/pipeline-summary?pipeline_id=${id}`),
      fetchWithAuth(`${API_BASE}/crm/tasks?status=open&limit=25`),
      fetchWithAuth(`${API_BASE}/crm/leads?limit=200`),
    ]);
    if (oppsRes.ok) setOpportunities(await oppsRes.json());
    if (summaryRes.ok) setSummary(await summaryRes.json());
    if (metricsRes.ok) setMetrics(await metricsRes.json());
    if (tasksRes.ok) setTasks(await tasksRes.json());
    if (leadsRes.ok) setLeads(await leadsRes.json());
    setLoading(false);
  };

  useEffect(() => {
    loadPipelines();
  }, [organization?.id]);

  useEffect(() => {
    if (pipelineId) loadBoard(pipelineId);
  }, [pipelineId, organization?.id]);

  const act = async (url: string, init: RequestInit, successMessage: string) => {
    setError(null);
    setStatus(null);
    try {
      const res = await fetchWithAuth(url, init);
      if (!res.ok) {
        const payload = await res.json().catch(() => ({ detail: "Request failed." }));
        throw new Error(typeof payload.detail === "string" ? payload.detail : "Request failed.");
      }
      setStatus(successMessage);
      await loadBoard(pipelineId);
      return true;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Request failed.");
      return false;
    }
  };

  const createOpportunity = async (event: React.FormEvent) => {
    event.preventDefault();
    const amountCents = Math.round(Number(form.amount || "0") * 100);
    const created = await act(
      `${API_BASE}/crm/opportunities`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lead_id: form.lead_id,
          name: form.name,
          amount_cents: Number.isFinite(amountCents) ? amountCents : 0,
          pipeline_id: pipelineId || undefined,
          expected_close_date: form.expected_close_date || undefined,
          source: form.source || undefined,
        }),
      },
      "Opportunity created."
    );
    if (created) {
      setForm({ lead_id: "", name: "", amount: "", expected_close_date: "", source: "" });
      setShowForm(false);
    }
  };

  const moveStage = async (opportunity: Opportunity, stageId: string) => {
    const stageName = stages.find((stage) => stage.id === stageId)?.name || "the new stage";
    await act(
      `${API_BASE}/crm/opportunities/${opportunity.id}/stage`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stage_id: stageId }),
      },
      `Moved to ${stageName}.`
    );
  };

  const closeDeal = async (opportunity: Opportunity, won: boolean) => {
    const reason = won ? undefined : window.prompt("Why was this deal lost?") || "";
    if (!won && !(reason ?? "").trim()) {
      setError("A lost reason is required.");
      return;
    }
    await act(
      `${API_BASE}/crm/opportunities/${opportunity.id}/close`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: won ? "won" : "lost", lost_reason: reason }),
      },
      won ? "Deal marked won." : "Deal marked lost."
    );
  };

  const completeTask = async (task: Task) => {
    await act(`${API_BASE}/crm/tasks/${task.id}/complete`, { method: "POST" }, "Task completed.");
  };

  const addTask = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!newTask.trim()) return;
    const created = await act(
      `${API_BASE}/crm/tasks`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: newTask.trim() }),
      },
      "Task added."
    );
    if (created) setNewTask("");
  };

  const pipeline = pipelines.find((item) => item.id === pipelineId);
  const stages = pipeline?.stages || [];

  return (
    <div style={{ maxWidth: 1240, margin: "0 auto", padding: "32px 24px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 26, fontWeight: 700, color: "#0f172a", margin: "0 0 8px 0" }}>Sales pipeline</h1>
          <p style={{ fontSize: 14, color: "#64748b", margin: 0 }}>
            Opportunities, ownership, activities and forecast for {organization?.name || "this organization"}.
          </p>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <select
            value={pipelineId}
            onChange={(event) => setPipelineId(event.target.value)}
            style={{ padding: "9px 12px", borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 13, background: "#fff" }}
          >
            {pipelines.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
          <button
            onClick={() => setShowForm((open) => !open)}
            disabled={!canWrite}
            style={{
              padding: "10px 18px",
              background: canWrite ? "linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)" : "#e2e8f0",
              color: canWrite ? "#fff" : "#64748b",
              border: "none",
              borderRadius: 8,
              fontSize: 14,
              fontWeight: 600,
              cursor: canWrite ? "pointer" : "default",
            }}
          >
            + New opportunity
          </button>
        </div>
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

      {showForm && (
        <form
          onSubmit={createOpportunity}
          style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 12, padding: 20, marginBottom: 20, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 12 }}
        >
          <label style={{ fontSize: 12, color: "#475569", display: "grid", gap: 4 }}>
            Company
            <select
              required
              value={form.lead_id}
              onChange={(event) => setForm({ ...form, lead_id: event.target.value })}
              style={{ padding: "8px 10px", borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 13 }}
            >
              <option value="">Select a company…</option>
              {leads.map((lead) => (
                <option key={lead.id} value={lead.id}>
                  {lead.company_name} (score {lead.score})
                </option>
              ))}
            </select>
          </label>
          <label style={{ fontSize: 12, color: "#475569", display: "grid", gap: 4 }}>
            Opportunity name
            <input
              required
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              placeholder="Annual licence renewal"
              style={{ padding: "8px 10px", borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 13 }}
            />
          </label>
          <label style={{ fontSize: 12, color: "#475569", display: "grid", gap: 4 }}>
            Amount (₹)
            <input
              type="number"
              min="0"
              step="1"
              value={form.amount}
              onChange={(event) => setForm({ ...form, amount: event.target.value })}
              placeholder="250000"
              style={{ padding: "8px 10px", borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 13 }}
            />
          </label>
          <label style={{ fontSize: 12, color: "#475569", display: "grid", gap: 4 }}>
            Expected close
            <input
              type="date"
              value={form.expected_close_date}
              onChange={(event) => setForm({ ...form, expected_close_date: event.target.value })}
              style={{ padding: "8px 10px", borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 13 }}
            />
          </label>
          <label style={{ fontSize: 12, color: "#475569", display: "grid", gap: 4 }}>
            Source
            <input
              value={form.source}
              onChange={(event) => setForm({ ...form, source: event.target.value })}
              placeholder="Referral, website, ads…"
              style={{ padding: "8px 10px", borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 13 }}
            />
          </label>
          <div style={{ display: "flex", alignItems: "flex-end", gap: 8 }}>
            <button type="submit" style={{ padding: "9px 16px", borderRadius: 8, border: "none", background: "#4f46e5", color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
              Create
            </button>
            <button type="button" onClick={() => setShowForm(false)} style={{ padding: "9px 16px", borderRadius: 8, border: "1px solid #cbd5e1", background: "#fff", color: "#334155", fontSize: 13, cursor: "pointer" }}>
              Cancel
            </button>
          </div>
        </form>
      )}

      {summary && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 12, marginBottom: 24 }}>
          <div style={tile}>
            <div style={{ fontSize: 12, color: "#64748b", marginBottom: 6 }}>Open pipeline</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: "#0f172a" }}>
              {money((metrics || summary.opportunities).open_value_cents)}
            </div>
            <div style={{ fontSize: 12, color: "#94a3b8" }}>
              {(metrics || summary.opportunities).open_count} open deal(s) · {pipeline?.name}
            </div>
          </div>
          <div style={tile}>
            <div style={{ fontSize: 12, color: "#64748b", marginBottom: 6 }}>Weighted forecast</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: "#0f172a" }}>
              {money((metrics || summary.opportunities).weighted_forecast_cents)}
            </div>
            <div style={{ fontSize: 12, color: "#94a3b8" }}>stage probability applied</div>
          </div>
          <div style={tile}>
            <div style={{ fontSize: 12, color: "#64748b", marginBottom: 6 }}>Won</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: "#047857" }}>
              {money((metrics || summary.opportunities).won_value_cents)}
            </div>
            <div style={{ fontSize: 12, color: "#94a3b8" }}>
              {(metrics || summary.opportunities).won_count} won · {(metrics || summary.opportunities).lost_count} lost · {Math.round((metrics || summary.opportunities).win_rate * 100)}% win rate
            </div>
          </div>
          <div style={tile}>
            <div style={{ fontSize: 12, color: "#64748b", marginBottom: 6 }}>Leads</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: "#0f172a" }}>{summary.leads.total}</div>
            <div style={{ fontSize: 12, color: "#94a3b8" }}>
              {summary.leads.qualified} qualified · {summary.leads.customers} customers
            </div>
          </div>
          <div style={tile}>
            <div style={{ fontSize: 12, color: "#64748b", marginBottom: 6 }}>Cycle time</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: "#0f172a" }}>
              {(metrics || summary.opportunities).average_cycle_days ?? "—"}
              {(metrics || summary.opportunities).average_cycle_days !== null ? "d" : ""}
            </div>
            <div style={{ fontSize: 12, color: "#94a3b8" }}>average days to won</div>
          </div>
          <div style={tile}>
            <div style={{ fontSize: 12, color: "#64748b", marginBottom: 6 }}>Tasks open</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: summary.tasks.overdue ? "#b91c1c" : "#0f172a" }}>{summary.tasks.open}</div>
            <div style={{ fontSize: 12, color: "#94a3b8" }}>{summary.tasks.overdue} overdue</div>
          </div>
        </div>
      )}

      {loading && <p style={{ color: "#64748b", fontSize: 14 }}>Loading pipeline…</p>}

      {!loading && stages.length > 0 && (
        <div style={{ display: "grid", gridAutoFlow: "column", gridAutoColumns: "minmax(230px, 1fr)", gap: 14, overflowX: "auto", paddingBottom: 8, marginBottom: 28 }}>
          {stages.map((stage) => {
            const items = opportunities.filter((opportunity) => opportunity.stage_id === stage.id);
            const value = items.reduce((total, opportunity) => total + opportunity.amount_cents, 0);
            return (
              <div key={stage.id} style={{ background: stage.is_won ? "#f0fdf4" : stage.is_lost ? "#fef2f2" : "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 12, padding: 12, minHeight: 120 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: "#334155" }}>{stage.name}</div>
                  <div style={{ fontSize: 11, color: "#94a3b8" }}>{stage.probability}%</div>
                </div>
                <div style={{ fontSize: 11, color: "#64748b", marginBottom: 10 }}>
                  {items.length} deal(s) · {money(value)}
                </div>
                <div style={{ display: "grid", gap: 10 }}>
                  {items.map((opportunity) => (
                    <div key={opportunity.id} style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, padding: 12 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: "#0f172a", marginBottom: 2 }}>{opportunity.name}</div>
                      <div style={{ fontSize: 12, color: "#64748b", marginBottom: 6 }}>
                        {opportunity.company_name || "Unknown company"} · {money(opportunity.amount_cents, opportunity.currency)}
                      </div>
                      <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 8 }}>
                        Close {shortDate(opportunity.expected_close_date)}
                        {opportunity.source ? ` · ${opportunity.source}` : ""}
                      </div>
                      {canWrite && opportunity.status === "open" && (
                        <div style={{ display: "grid", gap: 6 }}>
                          <select
                            value={opportunity.stage_id}
                            onChange={(event) => moveStage(opportunity, event.target.value)}
                            style={{ padding: "6px 8px", borderRadius: 6, border: "1px solid #cbd5e1", fontSize: 12 }}
                          >
                            {stages.map((option) => (
                              <option key={option.id} value={option.id}>
                                {option.name}
                              </option>
                            ))}
                          </select>
                          <div style={{ display: "flex", gap: 6 }}>
                            <button onClick={() => closeDeal(opportunity, true)} style={{ flex: 1, padding: "5px 8px", borderRadius: 6, border: "1px solid #a7f3d0", background: "#ecfdf5", color: "#047857", fontSize: 11, fontWeight: 600, cursor: "pointer" }}>
                              Won
                            </button>
                            <button onClick={() => closeDeal(opportunity, false)} style={{ flex: 1, padding: "5px 8px", borderRadius: 6, border: "1px solid #fecaca", background: "#fef2f2", color: "#b91c1c", fontSize: 11, fontWeight: 600, cursor: "pointer" }}>
                              Lost
                            </button>
                          </div>
                        </div>
                      )}
                      {opportunity.status !== "open" && (
                        <div style={{ fontSize: 11, fontWeight: 700, color: opportunity.status === "won" ? "#047857" : "#b91c1c", textTransform: "uppercase" }}>
                          {opportunity.status}
                        </div>
                      )}
                    </div>
                  ))}
                  {!items.length && <div style={{ fontSize: 12, color: "#cbd5e1" }}>No deals</div>}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 16 }}>
        <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 12, padding: 20 }}>
          <h2 style={{ margin: "0 0 12px 0", fontSize: 15, fontWeight: 700, color: "#1e293b" }}>Open tasks</h2>
          <form onSubmit={addTask} style={{ display: "flex", gap: 8, marginBottom: 12 }}>
            <input
              value={newTask}
              onChange={(event) => setNewTask(event.target.value)}
              placeholder="Add a follow-up task"
              disabled={!canWrite}
              style={{ flex: 1, padding: "8px 10px", borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 13 }}
            />
            <button type="submit" disabled={!canWrite} style={{ padding: "8px 14px", borderRadius: 8, border: "none", background: canWrite ? "#4f46e5" : "#e2e8f0", color: canWrite ? "#fff" : "#64748b", fontSize: 13, fontWeight: 600, cursor: canWrite ? "pointer" : "default" }}>
              Add
            </button>
          </form>
          <div style={{ display: "grid", gap: 8 }}>
            {tasks.map((task) => (
              <div key={task.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, borderBottom: "1px solid #f1f5f9", paddingBottom: 8 }}>
                <div>
                  <div style={{ fontSize: 13, color: "#0f172a", fontWeight: 600 }}>{task.title}</div>
                  <div style={{ fontSize: 11, color: "#94a3b8" }}>
                    {task.priority} priority · due {shortDate(task.due_at)}
                  </div>
                </div>
                {canWrite && (
                  <button onClick={() => completeTask(task)} style={{ padding: "5px 10px", borderRadius: 6, border: "1px solid #cbd5e1", background: "#fff", fontSize: 11, cursor: "pointer" }}>
                    Done
                  </button>
                )}
              </div>
            ))}
            {!tasks.length && <div style={{ fontSize: 12, color: "#94a3b8" }}>No open tasks.</div>}
          </div>
        </div>

        <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 12, padding: 20 }}>
          <h2 style={{ margin: "0 0 12px 0", fontSize: 15, fontWeight: 700, color: "#1e293b" }}>Needs attention</h2>
          <div style={{ display: "grid", gap: 8 }}>
            {(summary?.needs_attention || []).map((item) => (
              <div key={`${item.kind}-${item.entity_id}`} style={{ fontSize: 13, color: "#334155", display: "flex", justifyContent: "space-between", gap: 8 }}>
                <span>{item.label}</span>
                <span style={{ fontSize: 11, color: item.kind === "overdue_task" ? "#b91c1c" : "#4338ca", textTransform: "uppercase", fontWeight: 700 }}>
                  {item.kind === "overdue_task" ? "overdue" : "qualify → open deal"}
                </span>
              </div>
            ))}
            {(!summary || summary.needs_attention.length === 0) && (
              <div style={{ fontSize: 12, color: "#94a3b8" }}>Nothing overdue and no qualified lead is without an opportunity.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
