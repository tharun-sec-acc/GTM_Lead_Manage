"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import DirectOutreachPanel from "../../../components/direct-outreach-panel";
import IntelligenceWorkspace from "../../../components/intelligence-workspace";
import UnifiedMeetingsView from "../../../components/unified-meetings-view";
import UiIcon from "../../../components/ui-icon";
import { fetchOpportunities, type OpportunitySignalItem } from "../../../lib/market-intelligence";

const API = "http://localhost:8000";
type Contact = {
  id: string; name: string | null; title: string | null; email: string | null;
  source: string; verification_status: string; is_key_decision_maker: boolean;
};
type Email = {
  id: string; campaign_name: string | null; recipient: string; step_number: number;
  subject: string; body: string; status: string; due_at: string | null; sent_at: string | null;
  attachments?: { id: string; filename: string; size_bytes: number }[];
  events: { type: string; occurred_at: string; detail: string | null }[];
};
type Reply = {
  id: string; recipient: string | null; subject: string | null; body: string;
  classification: string | null; received_at: string;
};
type Activity = { type: string; occurred_at: string; summary: string; details: Record<string, unknown> };
type Profile = {
  lead: {
    id: string; company_name: string; domain: string | null; industry: string | null;
    location: string | null; designation: string | null; revenue: string | null;
    email: string | null; phone: string | null; remarks: string | null;
    key_person_info: string | null; extra: Record<string, string>;
  };
  overview: { contact_count: number; email_count: number; reply_count: number; meeting_count: number; lifecycle_stage: string | null; owner: string | null };
  contacts: Contact[];
  email_history: Email[];
  replies: Reply[];
  meetings: { implemented: boolean; items: unknown[] };
  company_research: { implemented: boolean; items: unknown[] };
  commercial_lifecycle: { implemented: boolean; items: unknown[] };
  timeline: Activity[];
  timeline_limit: number;
};

async function loadProfile(leadId: string): Promise<Profile> {
  const response = await fetch(`${API}/leads/${encodeURIComponent(leadId)}/profile?limit=200`, { cache: "no-store" });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : `Request failed (${response.status}).`);
  }
  return response.json() as Promise<Profile>;
}

function date(value: string | null) {
  return value ? new Date(value).toLocaleString() : "—";
}

export default function LeadProfilePage() {
  const params = useParams<{ id: string }>();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState("");
  const [contactName, setContactName] = useState("");
  const [contactTitle, setContactTitle] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactError, setContactError] = useState("");
  const [savingContact, setSavingContact] = useState(false);
  const [domainInput, setDomainInput] = useState("");
  const [savingDomain, setSavingDomain] = useState(false);
  const [domainNotice, setDomainNotice] = useState("");
  const [marketSignals, setMarketSignals] = useState<OpportunitySignalItem[]>([]);

  const reloadProfile = () => {
    loadProfile(params.id).then(setProfile).catch(() => {});
  };

  useEffect(() => {
    if (!params.id) return;
    fetchOpportunities("all", "all", "all", undefined, params.id)
      .then((res) => {
        if (res.length > 0) {
          setMarketSignals(res);
        } else if (profile?.lead?.company_name) {
          fetchOpportunities("all", "all", "all", profile.lead.company_name)
            .then(setMarketSignals)
            .catch(() => {});
        }
      })
      .catch(() => {});
  }, [params.id, profile?.lead?.company_name]);

  useEffect(() => {
    let mounted = true;
    loadProfile(params.id)
      .then(p => {
        if (mounted) {
          setProfile(p);
          if (p?.lead?.domain) setDomainInput(p.lead.domain);
        }
      })
      .catch(reason => {
        if (mounted) setError(reason instanceof Error ? reason.message : "Could not load lead profile.");
      });
    const interval = setInterval(() => {
      loadProfile(params.id).then(p => {
        if (mounted) {
          setProfile(p);
          if (!domainInput && p?.lead?.domain) setDomainInput(p.lead.domain);
        }
      }).catch(() => {});
    }, 5000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [params.id]);

  const handleSaveDomain = async () => {
    if (!domainInput.trim()) return;
    setSavingDomain(true);
    setDomainNotice("");
    try {
      const res = await fetch(`http://localhost:8000/leads/${encodeURIComponent(params.id)}/domain`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domain: domainInput.trim() }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || "Could not save domain.");
      }
      setDomainNotice("Domain saved successfully!");
      reloadProfile();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed to save domain.");
    } finally {
      setSavingDomain(false);
    }
  };

  if (error) return <main><div role="alert" className="alert">{error}</div><a href="/">← Lead workspace</a></main>;
  if (!profile) return <main><p>Loading company profile…</p></main>;
  const { lead, overview } = profile;
  return <main>
    <header><div><p className="eyebrow">SOLWER GTM / LEAD 360</p><h1>{lead.company_name}</h1>
      <p>{lead.domain || "Domain not confirmed"} · Local pilot · no sign-in</p></div>
      <a href="/">← Lead workspace</a></header>
    <div className="actions">
      <a className="button-link" href="#research"><UiIcon name="spark" size={16} /> Research company</a>
      <a className="button-link secondary" href="#contacts"><UiIcon name="mail" size={16} /> Compose and send emails</a>
      <a className="button-link secondary" href="#contacts">Select people</a>
      <a className="button-link secondary" href={`/?lead=${encodeURIComponent(lead.id)}#companies`}><UiIcon name="search" size={16} /> Find people with Apollo</a>
      <button
        type="button"
        className="button-link secondary"
        onClick={async () => {
          try {
            const res = await fetch(`http://localhost:8000/zoho/sync/leads/${encodeURIComponent(lead.id)}`, { method: "POST" });
            const data = await res.json();
            if (res.ok) alert(`Synced to Zoho CRM! Account ID: ${data.zoho_account_id || "Updated"}`);
            else alert(data?.detail || "Sync to Zoho failed (check if Zoho CRM is connected).");
          } catch {
            alert("Error communicating with Zoho CRM sync endpoint.");
          }
        }}
        title="Sync this company & its contacts to Zoho CRM"
      >
        <UiIcon name="link" size={16} /> Sync to Zoho CRM
      </button>
      <a className="text-link" href="/zoho">Zoho CRM Settings <UiIcon name="arrow" size={15} /></a>
      <a className="text-link" href="/followups">Mailbox &amp; tracking <UiIcon name="arrow" size={15} /></a>
    </div>
    <div className="alert">This profile contains existing pilot data only. Empty or unimplemented sections are labeled; no CRM stage, meeting, research or commercial records are fabricated.</div>
    <div className="stats">
      <a href="#contacts" className="stat-card" title="Click to view & select contacts">
        <strong>{overview.contact_count}</strong>
        <span>Contacts</span>
        <small>Click to view &amp; select</small>
      </a>
      <a href="#emails" className="stat-card" title="Click to view email history">
        <strong>{overview.email_count}</strong>
        <span>Email records</span>
        <small>Click to view sent emails</small>
      </a>
      <a href="#replies-section" className="stat-card" title="Click to view inbound replies">
        <strong>{overview.reply_count}</strong>
        <span>Replies</span>
        <small>Click to view replies</small>
      </a>
      <a href="#meetings" className="stat-card" title="Click to view meetings">
        <strong>{overview.meeting_count}</strong>
        <span>Confirmed meetings</span>
        <small>Click to view meetings</small>
      </a>
    </div>
    <nav className="actions" aria-label="Lead profile sections">
      {[["overview", "Overview"], ["research", "Intelligence"], ["signals", "Market Signals"], ["contacts", "Contacts & Direct Outreach"],
        ["emails", "Email history"], ["meetings", "Meetings"], ["commercial", "Commercial"], ["timeline", "Timeline"]].map(([section, title]) =>
        <a key={section} href={`#${section}`}>{title}</a>)}
    </nav>
    <section id="overview"><h2>Overview</h2>
      <div style={{ margin: "16px 0", padding: "16px", background: "#f8fafc", borderRadius: "8px", border: "1px solid #e2e8f0", maxWidth: "600px" }}>
        <label style={{ display: "block", fontWeight: 600, color: "#0f172a", marginBottom: "6px", fontSize: "14px" }}>
          Company Domain &amp; Official Website
        </label>
        <div style={{ display: "flex", gap: "8px" }}>
          <input
            value={domainInput}
            onChange={e => setDomainInput(e.target.value)}
            placeholder="e.g. tatamotors.com or vrlgroup.in"
            style={{ flex: 1, padding: "8px 12px" }}
          />
          <button
            type="button"
            className="secondary"
            disabled={savingDomain || !domainInput.trim()}
            onClick={handleSaveDomain}
          >
            {savingDomain ? "Saving..." : "Save domain"}
          </button>
        </div>
        {domainNotice && <small style={{ color: "#059669", display: "block", marginTop: "6px", fontWeight: 600 }}>✓ {domainNotice}</small>}
        <small style={{ color: "#64748b", display: "block", marginTop: "6px" }}>
          Confirming the company domain enables autonomous background multi-agent research and public source verification.
        </small>
      </div>
      <p><strong>Industry:</strong> {lead.industry || "Not recorded"} · <strong>Location:</strong> {lead.location || "Not recorded"}</p>
      <p><strong>Revenue:</strong> {lead.revenue || "Not recorded"} · <strong>Lead owner:</strong> {overview.owner || "Not implemented"}</p>
      <p><strong>Lifecycle stage:</strong> {overview.lifecycle_stage || "Not implemented"} · <strong>Domain:</strong> {lead.domain || "Not confirmed"}</p>
      <p><strong>Contact number:</strong> {lead.phone || "Not recorded"} · <strong>Remarks:</strong> {lead.remarks || "—"}</p>
      <p><strong>Key person information:</strong> {lead.key_person_info || "—"} · <strong>Designation:</strong> {lead.designation || "—"} director</p>
      {Object.keys(lead.extra || {}).length > 0 &&
        <details><summary>Additional imported data</summary><pre>{JSON.stringify(lead.extra, null, 2)}</pre></details>}
      {overview.meeting_count > 0 && (
        <div style={{ margin: "16px 0", padding: "16px 20px", background: "#f0fdf4", borderRadius: "10px", border: "1px solid #bbf7d0", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
              <span style={{ fontSize: 16 }}>📋</span>
              <strong style={{ fontSize: 14, color: "#166534" }}>Meeting Minutes (MoM) &amp; Intelligence Ready</strong>
              <span style={{ fontSize: 11, background: "#dcfce7", color: "#15803d", padding: "2px 8px", borderRadius: 10, fontWeight: 700 }}>
                {overview.meeting_count} {overview.meeting_count === 1 ? "Meeting" : "Meetings"}
              </span>
            </div>
            <p style={{ margin: 0, fontSize: 13, color: "#14532d" }}>
              AI MoM, executive summary, customer requirements, pain points, and action items are automatically generated for {lead.company_name}.
            </p>
          </div>
          <a
            href="#meetings"
            style={{
              padding: "8px 16px",
              background: "#16a34a",
              color: "#ffffff",
              borderRadius: "6px",
              fontSize: "13px",
              fontWeight: 600,
              textDecoration: "none",
              whiteSpace: "nowrap",
            }}
          >
            View Meeting MoM ↓
          </a>
        </div>
      )}
      <p>Created date and next activity are not currently tracked as lifecycle fields.</p>
    </section>
    <section id="research" className="lead-intelligence-section">
      <IntelligenceWorkspace lead={{ id: lead.id, company_name: lead.company_name, domain: lead.domain }} />
    </section>
    <section id="contacts">
      <div id="outreach" />
      <h2>Contacts &amp; Direct Outreach</h2>
      <p style={{ color: "#64748b", marginTop: "-4px", marginBottom: "16px" }}>
        Select decision-makers below to send personalized 1-on-1 emails. Attach collaterals, review drafts, and send directly from your connected mailbox.
      </p>
      <DirectOutreachPanel
        leadId={lead.id}
        companyName={lead.company_name}
        contactVersion={profile.contacts.map(c => c.id).join(",")}
        onActivity={reloadProfile}
      />
    </section>
    <section id="emails"><h2>Email and follow-up history</h2>
      {profile.email_history.length ? profile.email_history.map(email => <details className="detail" key={email.id}>
        <summary style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
          <div>
            <strong>{email.subject || "Untitled email"}</strong> · To <span style={{ color: "#0284c7" }}>{email.recipient}</span>
          </div>
          <span className={`status-pill ${email.status === "sent" ? "positive" : "neutral"}`}>
            {email.status.toUpperCase()}
          </span>
        </summary>
        <p><strong>Recipient:</strong> {email.recipient} · <strong>Status:</strong> {email.status}</p>
        <p><strong>SMTP accepted:</strong> {date(email.sent_at)} {email.due_at ? `· Next scheduled: ${date(email.due_at)}` : ""}</p>
        {email.attachments && email.attachments.length > 0 && (
          <div style={{ margin: "10px 0", padding: "10px 14px", background: "#f8fafc", borderRadius: "6px", border: "1px solid #e2e8f0" }}>
            <span style={{ fontSize: "12px", fontWeight: 600, color: "#475569" }}>📎 Collateral attached ({email.attachments.length}):</span>
            <div style={{ display: "flex", gap: "8px", marginTop: "6px", flexWrap: "wrap" }}>
              {email.attachments.map(att => (
                <span key={att.id} style={{ display: "inline-flex", alignItems: "center", gap: "6px", background: "#ffffff", border: "1px solid #cbd5e1", borderRadius: "4px", padding: "4px 8px", fontSize: "12px", color: "#0f172a" }}>
                  📄 {att.filename} ({Math.round(att.size_bytes / 1024)} KB)
                </span>
              ))}
            </div>
          </div>
        )}
        <pre>{email.body}</pre>
        {email.events.map((event, index) => <p key={`${event.type}:${index}`}>{event.type} · {date(event.occurred_at)}
          {event.type === "open" || event.type === "click" ? " · approximate tracking signal" : ""}</p>)}
      </details>) : <p>No email history is recorded for this company.</p>}
      <h3 id="replies-section">Inbound Replies</h3>
      {profile.replies.length ? profile.replies.map(reply => <details className="detail" key={reply.id}>
        <summary>{reply.subject || "Customer reply"} · {reply.classification || "Unclassified"} · {date(reply.received_at)}</summary>
        <p>From: {reply.recipient || "Unknown"}</p><pre>{reply.body}</pre>
      </details>) : <p>No matched replies are recorded.</p>}
    </section>
    <section id="signals" style={{ padding: "16px 0" }}>
      <div style={{ background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: "10px", padding: "20px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px", flexWrap: "wrap", gap: 12 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
              <span style={{ fontSize: 18 }}>📡</span>
              <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "#0f172a" }}>Autonomous Market Intelligence &amp; Opportunity Signals</h2>
            </div>
            <p style={{ margin: 0, fontSize: 13, color: "var(--muted)" }}>
              Continuous Playwright web monitoring detects plant expansions, fleet acquisitions, tenders, and business developments for {profile.lead.company_name}.
            </p>
          </div>
          <a
            href={`/market-intelligence`}
            style={{
              padding: "8px 16px",
              background: "var(--red)",
              color: "#ffffff",
              borderRadius: "6px",
              fontSize: 13,
              fontWeight: 600,
              textDecoration: "none",
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            Open Market Intelligence Radar <UiIcon name="arrow" size={14} />
          </a>
        </div>

        {marketSignals.length > 0 ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 14 }}>
            {marketSignals.map((sig) => (
              <div
                key={sig.id}
                style={{
                  background: sig.priority_level === "high" ? "#fffbfb" : "#f8fafc",
                  border: sig.priority_level === "high" ? "1.5px solid #fca5a5" : "1px solid #e2e8f0",
                  borderRadius: 8,
                  padding: "14px 16px",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 8, marginBottom: 6 }}>
                  <div>
                    <span style={{ fontSize: 11, fontWeight: 700, color: "var(--red)", textTransform: "uppercase" }}>
                      Matched Solwer Solution:
                    </span>
                    <strong style={{ fontSize: 15, color: "#0f172a", marginLeft: 6 }}>{sig.product_name}</strong>
                  </div>
                  <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    <span style={{ fontSize: 11, fontWeight: 700, background: sig.priority_level === "high" ? "#fee2e2" : "#fef3c7", color: sig.priority_level === "high" ? "var(--red)" : "#d97706", padding: "2px 8px", borderRadius: 6 }}>
                      {sig.priority_level.toUpperCase()}
                    </span>
                    <span style={{ fontSize: 12, fontWeight: 800, background: "#f0fdf4", color: "#166534", padding: "2px 8px", borderRadius: 6 }}>
                      Readiness: {sig.sales_readiness_score}/100
                    </span>
                  </div>
                </div>

                <div style={{ fontSize: 13, color: "#0f172a", fontWeight: 600, marginBottom: 4 }}>
                  📰 {sig.article_headline || sig.event_title}
                </div>

                <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 6, padding: "8px 12px", marginTop: 6 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#166534", textTransform: "uppercase" }}>
                    💡 Where Solwer Helps:
                  </div>
                  <div style={{ fontSize: 12, color: "#1e3a8a", marginTop: 2, fontWeight: 500 }}>
                    &quot;{sig.suggested_next_action}&quot;
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div style={{ padding: "14px 16px", background: "#f8fafc", borderRadius: 8, border: "1px solid #e2e8f0", marginTop: 12, fontSize: 13, color: "#64748b" }}>
            No active market signals recorded yet for {profile.lead.company_name}. Crawlers monitor 62 Indian websites to automatically detect upcoming announcements, tenders, and expansions.
          </div>
        )}
      </div>
    </section>
    <section id="meetings" style={{ padding: "16px 0" }}>
      <UnifiedMeetingsView
        leadId={profile.lead.id}
        title={`${profile.lead.company_name} — Meetings & Intelligence`}
        description={`Scheduled discussions, instant video meetings, recordings, transcripts, and AI analysis for ${profile.lead.company_name}.`}
      />
    </section>
    <section id="commercial"><h2>Proposals, contracts and customer lifecycle</h2>
      {profile.commercial_lifecycle.implemented ? <p>{profile.commercial_lifecycle.items.length} records.</p> :
        <p>Proposals, negotiations, contracts, approvals, handover, implementation and customer-success tracking are not implemented.</p>}
    </section>
    <section id="timeline"><h2>Activity timeline</h2>
      {profile.timeline.length ? profile.timeline.map((activity, index) => <div className="detail" key={`${activity.type}:${index}`}>
        <strong>{activity.summary}</strong><p>{activity.type} · {date(activity.occurred_at)}</p>
        {Object.keys(activity.details).length > 0 && <small>{JSON.stringify(activity.details)}</small>}
      </div>) : <p>No activity history is recorded.</p>}
      {profile.timeline.length >= profile.timeline_limit && <p>Showing the most recent {profile.timeline_limit} events.</p>}
    </section>
  </main>;
}
