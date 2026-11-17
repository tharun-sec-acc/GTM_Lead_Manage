"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import OutreachWorkspace from "../../../components/outreach-workspace";
import IntelligenceWorkspace from "../../../components/intelligence-workspace";
import UiIcon from "../../../components/ui-icon";

const API = "http://localhost:8000";
type Contact = {
  id: string; name: string | null; title: string | null; email: string | null;
  source: string; verification_status: string; is_key_decision_maker: boolean;
};
type Email = {
  id: string; campaign_name: string | null; recipient: string; step_number: number;
  subject: string; body: string; status: string; due_at: string | null; sent_at: string | null;
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

  useEffect(() => {
    loadProfile(params.id).then(setProfile).catch(reason =>
      setError(reason instanceof Error ? reason.message : "Could not load lead profile."));
  }, [params.id]);

  if (error) return <main><div role="alert" className="alert">{error}</div><a href="/">← Lead workspace</a></main>;
  if (!profile) return <main><p>Loading company profile…</p></main>;
  const { lead, overview } = profile;
  return <main>
    <header><div><p className="eyebrow">DENSO / LEAD 360</p><h1>{lead.company_name}</h1>
      <p>{lead.domain || "Domain not confirmed"} · Local pilot · no sign-in</p></div>
      <a href="/">← Lead workspace</a></header>
    <div className="actions">
      <a className="button-link" href="#research"><UiIcon name="spark" size={16} /> Research company</a>
      <a className="button-link secondary" href="#outreach"><UiIcon name="mail" size={16} /> Compose and approve emails</a>
      <a className="button-link secondary" href="#add-contact">Add people</a>
      <a className="button-link secondary" href={`/?lead=${encodeURIComponent(lead.id)}#companies`}><UiIcon name="search" size={16} /> Find people with Apollo</a>
      <a className="text-link" href="/followups">All campaigns <UiIcon name="arrow" size={15} /></a>
    </div>
    <div className="alert">This profile contains existing pilot data only. Empty or unimplemented sections are labeled; no CRM stage, meeting, research or commercial records are fabricated.</div>
    <div className="stats">
      <div><strong>{overview.contact_count}</strong><span>Contacts</span></div>
      <div><strong>{overview.email_count}</strong><span>Email records</span></div>
      <div><strong>{overview.reply_count}</strong><span>Replies</span></div>
      <div><strong>{overview.meeting_count}</strong><span>Confirmed meetings</span></div>
    </div>
    <nav className="actions" aria-label="Lead profile sections">
      {[["overview", "Overview"], ["research", "Intelligence"], ["contacts", "Contacts"], ["outreach", "Compose"],
        ["emails", "Email history"], ["meetings", "Meetings"], ["commercial", "Commercial"], ["timeline", "Timeline"]].map(([section, title]) =>
        <a key={section} href={`#${section}`}>{title}</a>)}
    </nav>
    <section id="overview"><h2>Overview</h2>
      <p><strong>Industry:</strong> {lead.industry || "Not recorded"} · <strong>Location:</strong> {lead.location || "Not recorded"}</p>
      <p><strong>Revenue:</strong> {lead.revenue || "Not recorded"} · <strong>Lead owner:</strong> {overview.owner || "Not implemented"}</p>
      <p><strong>Lifecycle stage:</strong> {overview.lifecycle_stage || "Not implemented"} · <strong>Domain:</strong> {lead.domain || "Not confirmed"}</p>
      <p><strong>Contact number:</strong> {lead.phone || "Not recorded"} · <strong>Remarks:</strong> {lead.remarks || "—"}</p>
      <p><strong>Key person information:</strong> {lead.key_person_info || "—"} · <strong>Designation:</strong> {lead.designation || "—"}</p>
      {Object.keys(lead.extra || {}).length > 0 &&
        <details><summary>Additional imported data</summary><pre>{JSON.stringify(lead.extra, null, 2)}</pre></details>}
      <p>Created date and next activity are not currently tracked as lifecycle fields.</p>
    </section>
    <section id="research" className="lead-intelligence-section">
      <IntelligenceWorkspace lead={{ id: lead.id, company_name: lead.company_name, domain: lead.domain }} />
    </section>
    <section id="contacts"><h2>People and decision-makers</h2>
      {profile.contacts.length ? profile.contacts.map(contact => <div className="detail" key={contact.id}>
        <strong>{contact.name || "Name unavailable"}</strong>{contact.is_key_decision_maker && " · Decision maker"}
        <p>{contact.title || "Title unavailable"} · {contact.email || "Business email not available"}</p>
        <small>{contact.source} · {contact.verification_status.replaceAll("_", " ")}</small>
      </div>) : <p>No active contacts. Add or search contacts from the lead workspace.</p>}
      <form id="add-contact" className="detail" onSubmit={async event => {
        event.preventDefault();
        setSavingContact(true); setContactError("");
        try {
          const response = await fetch(`${API}/leads/${encodeURIComponent(lead.id)}/contacts`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: contactName, title: contactTitle || null, email: contactEmail || null }),
          });
          if (!response.ok) {
            const body = await response.json();
            throw new Error(typeof body.detail === "string" ? body.detail : "Could not add contact.");
          }
          setContactName(""); setContactTitle(""); setContactEmail("");
          setProfile(await loadProfile(lead.id));
        } catch (reason) {
          setContactError(reason instanceof Error ? reason.message : "Could not add contact.");
        } finally { setSavingContact(false); }
      }}>
        <h3>Add a person to this company</h3>
        {contactError && <p role="alert" className="error">{contactError}</p>}
        <div className="grid">
          <label>Name<input required value={contactName} onChange={event => setContactName(event.target.value)} /></label>
          <label>Designation<input value={contactTitle} onChange={event => setContactTitle(event.target.value)} /></label>
          <label>Business email<input type="email" value={contactEmail} onChange={event => setContactEmail(event.target.value)} /></label>
        </div>
        <button disabled={savingContact || !contactName.trim()} type="submit">{savingContact ? "Adding..." : "Add person"}</button>
        <p>Repeat to add more people, then select them together below. Saving a person does not send an email.</p>
      </form>
    </section>
    <section id="outreach"><h2>Email this company's people</h2>
      <p>Create or choose a campaign, select one or more recipients, write or generate emails, then review and approve each saved draft here.
        Sending still uses the existing Gmail worker and server safeguards.</p>
      <OutreachWorkspace leadId={lead.id} contactVersion={profile.contacts.map(contact => contact.id).join(",")} />
    </section>
    <section id="emails"><h2>Email and follow-up history</h2>
      {profile.email_history.length ? profile.email_history.map(email => <details className="detail" key={email.id}>
        <summary>{email.subject || "Untitled draft"} · {email.status} · To {email.recipient}</summary>
        <p>Campaign: {email.campaign_name || "—"} · Step: {email.step_number ? `Follow-up ${email.step_number}` : "Initial"}</p>
        <p>SMTP accepted: {date(email.sent_at)} · Next scheduled: {date(email.due_at)}</p>
        <p>SMTP accepted does not mean delivered. No delivery confirmation is inferred.</p>
        <pre>{email.body}</pre>
        {email.events.map((event, index) => <p key={`${event.type}:${index}`}>{event.type} · {date(event.occurred_at)}
          {event.type === "open" || event.type === "click" ? " · approximate tracking signal" : ""}</p>)}
      </details>) : <p>No campaign email history is recorded for this company.</p>}
      <h3>Replies</h3>
      {profile.replies.length ? profile.replies.map(reply => <details className="detail" key={reply.id}>
        <summary>{reply.subject || "Customer reply"} · {reply.classification || "Unclassified"} · {date(reply.received_at)}</summary>
        <p>From: {reply.recipient || "Unknown"}</p><pre>{reply.body}</pre>
      </details>) : <p>No matched replies are recorded.</p>}
    </section>
    <section id="meetings"><h2>Meetings</h2>
      {profile.meetings.implemented ? <p>{profile.meetings.items.length} meeting records.</p> :
        <p>Meeting booking, recordings, transcripts and summaries are not implemented. Calendar availability is separate and does not create meetings.</p>}
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
