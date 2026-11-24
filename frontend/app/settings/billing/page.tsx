"use client";

import React, { useEffect, useState } from "react";
import { useAuth } from "../../../lib/auth-context";
import { getApiBase } from "../../../lib/api-config";

const API_BASE = getApiBase();

interface Plan {
  id: string;
  code: string;
  name: string;
  description: string | null;
  price_cents: number | null;
  currency: string;
  billing_interval: string;
  trial_days: number;
  limits: Record<string, number | null>;
  features: string[];
}

interface SubscriptionState {
  subscription: {
    id: string;
    status: string;
    plan_code: string;
    plan_name: string;
    seats: number | null;
    trial_ends_at: string | null;
    current_period_start: string;
    current_period_end: string;
    cancel_at_period_end: boolean;
    canceled_at: string | null;
    price_cents: number | null;
    currency: string;
    billing_interval: string;
  };
  plan: Plan;
  features: string[];
  limits: Record<string, number | null>;
  usage: Record<string, number>;
  remaining: Record<string, number | null>;
  active: boolean;
}

const METRIC_LABELS: Record<string, string> = {
  seats: "Team seats",
  leads: "Companies / leads",
  email_sends_monthly: "Emails sent this month",
  ai_research_runs_monthly: "AI research runs this month",
  enrichment_credits_monthly: "Contact enrichment credits",
  active_campaigns: "Active campaigns",
  email_accounts: "Connected email accounts",
  integrations: "Integrations",
};

function formatPrice(priceCents: number | null, currency: string, interval: string): string {
  if (priceCents === null) return "Custom pricing";
  if (priceCents === 0) return "Free";
  const amount = (priceCents / 100).toLocaleString(currency === "INR" ? "en-IN" : "en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
  const suffix = interval === "year" ? "/year" : interval === "month" ? "/month" : "";
  return `${currency === "INR" ? "₹" : currency + " "}${amount}${suffix}`;
}

function formatDate(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

const statusStyles: Record<string, React.CSSProperties> = {
  active: { background: "#ecfdf5", color: "#047857", border: "1px solid #a7f3d0" },
  trialing: { background: "#eef2ff", color: "#4338ca", border: "1px solid #c7d2fe" },
  past_due: { background: "#fff7ed", color: "#c2410c", border: "1px solid #fed7aa" },
  canceled: { background: "#fef2f2", color: "#b91c1c", border: "1px solid #fecaca" },
};

export default function BillingSettingsPage() {
  const { organization, token, fetchWithAuth } = useAuth();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [state, setState] = useState<SubscriptionState | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyPlan, setBusyPlan] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const role = organization?.role || "";
  const canManage = role === "owner" || role === "admin" || role === "super_admin";

  const load = async () => {
    try {
      const [plansRes, stateRes] = await Promise.all([
        fetchWithAuth(`${API_BASE}/billing/plans`),
        fetchWithAuth(`${API_BASE}/billing/subscription`),
      ]);
      if (plansRes.ok) setPlans(await plansRes.json());
      if (stateRes.ok) setState(await stateRes.json());
    } catch {
      // quiet catch for offline/local runs
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [organization?.id, token]);

  const changePlan = async (planCode: string) => {
    setBusyPlan(planCode);
    setErrorMsg(null);
    setStatusMsg(null);
    try {
      const res = await fetchWithAuth(`${API_BASE}/billing/subscription/change`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan_code: planCode }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Plan change failed." }));
        throw new Error(err.detail || "Plan change failed.");
      }
      const next = await res.json();
      setState(next);
      setStatusMsg(`Organization moved to the ${next.plan?.name ?? planCode} plan.`);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Plan change failed.");
    } finally {
      setBusyPlan(null);
    }
  };

  const mutateSubscription = async (action: "cancel" | "resume") => {
    setErrorMsg(null);
    setStatusMsg(null);
    try {
      const res = await fetchWithAuth(`${API_BASE}/billing/subscription/${action}`, {
        method: "POST",
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Request failed." }));
        throw new Error(err.detail || "Request failed.");
      }
      setState(await res.json());
      setStatusMsg(action === "cancel" ? "Subscription will end after the current period." : "Subscription resumed.");
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Request failed.");
    }
  };

  const usageEntries = state ? Object.keys(state.limits) : [];

  return (
    <div style={{ maxWidth: 1120, margin: "0 auto", padding: "32px 24px" }}>
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: "#0f172a", margin: "0 0 8px 0" }}>
          Billing &amp; Plan
        </h1>
        <p style={{ fontSize: 14, color: "#64748b", margin: 0 }}>
          Subscription, plan entitlements and metered usage for {organization?.name || "this organization"}.
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

      {loading && <p style={{ color: "#64748b", fontSize: 14 }}>Loading subscription…</p>}

      {!loading && state && (
        <>
          <div style={{ background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 12, padding: 24, marginBottom: 24 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
                  <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: "#0f172a" }}>
                    {state.plan.name}
                  </h2>
                  <span style={{ ...(statusStyles[state.subscription.status] || statusStyles.active), padding: "3px 10px", borderRadius: 999, fontSize: 12, fontWeight: 600 }}>
                    {state.subscription.status}
                  </span>
                  {state.subscription.cancel_at_period_end && (
                    <span style={{ background: "#fff7ed", color: "#c2410c", border: "1px solid #fed7aa", padding: "3px 10px", borderRadius: 999, fontSize: 12, fontWeight: 600 }}>
                      ends {formatDate(state.subscription.current_period_end)}
                    </span>
                  )}
                </div>
                <p style={{ margin: 0, fontSize: 13, color: "#64748b" }}>
                  {formatPrice(state.plan.price_cents, state.plan.currency, state.plan.billing_interval)}
                  {state.subscription.trial_ends_at && state.subscription.status === "trialing"
                    ? ` · trial ends ${formatDate(state.subscription.trial_ends_at)}`
                    : ""}
                  {` · current period ${formatDate(state.subscription.current_period_start)} – ${formatDate(state.subscription.current_period_end)}`}
                </p>
              </div>
              {canManage && (
                <div style={{ display: "flex", gap: 10 }}>
                  {state.subscription.cancel_at_period_end ? (
                    <button onClick={() => mutateSubscription("resume")} style={{ padding: "9px 16px", borderRadius: 8, border: "1px solid #cbd5e1", background: "#ffffff", color: "#0f172a", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
                      Resume subscription
                    </button>
                  ) : (
                    <button onClick={() => mutateSubscription("cancel")} style={{ padding: "9px 16px", borderRadius: 8, border: "1px solid #fecaca", background: "#fef2f2", color: "#b91c1c", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
                      Cancel at period end
                    </button>
                  )}
                </div>
              )}
            </div>

            {state.subscription.status === "trialing" && (
              <p style={{ margin: "14px 0 0 0", fontSize: 13, color: "#475569" }}>
                Add a payment method with your provider before the trial ends to keep sending and researching.
              </p>
            )}
          </div>

          <div style={{ background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 12, padding: 24, marginBottom: 28 }}>
            <h3 style={{ margin: "0 0 18px 0", fontSize: 16, fontWeight: 600, color: "#1e293b" }}>
              Usage this period
            </h3>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 18 }}>
              {usageEntries.map((metric) => {
                const limit = state.limits[metric];
                const used = state.usage[metric] ?? 0;
                const pct = limit === null || limit === 0 ? 0 : Math.min(100, Math.round((used / limit) * 100));
                return (
                  <div key={metric}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 6 }}>
                      <span style={{ color: "#334155", fontWeight: 600 }}>{METRIC_LABELS[metric] || metric}</span>
                      <span style={{ color: "#64748b" }}>
                        {used}{limit === null ? " / unlimited" : ` / ${limit}`}
                      </span>
                    </div>
                    <div style={{ height: 6, borderRadius: 999, background: "#e2e8f0", overflow: "hidden" }}>
                      <div style={{ width: `${limit === null ? Math.min(100, used > 0 ? 8 : 0) : pct}%`, height: "100%", background: pct >= 90 ? "#dc2626" : "#4f46e5" }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}

      {!loading && plans.length > 0 && (
        <>
          <h3 style={{ margin: "0 0 16px 0", fontSize: 16, fontWeight: 600, color: "#1e293b" }}>Available plans</h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 16 }}>
            {plans.map((plan) => {
              const isCurrent = state?.plan.code === plan.code;
              return (
                <div
                  key={plan.id}
                  style={{
                    background: "#ffffff",
                    border: isCurrent ? "2px solid #4f46e5" : "1px solid #e2e8f0",
                    borderRadius: 12,
                    padding: 20,
                    display: "flex",
                    flexDirection: "column",
                    gap: 10,
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <h4 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: "#0f172a" }}>{plan.name}</h4>
                    {isCurrent && <span style={{ fontSize: 11, fontWeight: 700, color: "#4338ca", textTransform: "uppercase" }}>Current</span>}
                  </div>
                  <div style={{ fontSize: 18, fontWeight: 700, color: "#0f172a" }}>
                    {formatPrice(plan.price_cents, plan.currency, plan.billing_interval)}
                  </div>
                  <p style={{ margin: 0, fontSize: 13, color: "#64748b", minHeight: 38 }}>{plan.description}</p>
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: "#475569", display: "grid", gap: 4 }}>
                    <li>{plan.limits.seats === null ? "Unlimited seats" : `${plan.limits.seats} seats`}</li>
                    <li>{plan.limits.leads === null ? "Unlimited companies" : `${plan.limits.leads.toLocaleString()} companies`}</li>
                    <li>{plan.limits.email_sends_monthly === null ? "Unlimited monthly emails" : `${plan.limits.email_sends_monthly.toLocaleString()} emails / month`}</li>
                  </ul>
                  <button
                    onClick={() => changePlan(plan.code)}
                    disabled={!canManage || isCurrent || busyPlan !== null}
                    style={{
                      marginTop: "auto",
                      padding: "9px 16px",
                      borderRadius: 8,
                      border: "none",
                      background: isCurrent ? "#e2e8f0" : "linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)",
                      color: isCurrent ? "#64748b" : "#ffffff",
                      fontSize: 13,
                      fontWeight: 600,
                      cursor: !canManage || isCurrent || busyPlan !== null ? "default" : "pointer",
                    }}
                  >
                    {isCurrent ? "Active plan" : busyPlan === plan.code ? "Switching…" : canManage ? `Switch to ${plan.name}` : "Admin access required"}
                  </button>
                </div>
              );
            })}
          </div>
          <p style={{ marginTop: 18, fontSize: 12, color: "#94a3b8" }}>
            Plan changes take effect immediately. Payment-provider checkout is not connected yet, so switching plans
            records the entitlement change without taking payment.
          </p>
        </>
      )}
    </div>
  );
}
