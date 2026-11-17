"use client";

import { useEffect, useState } from "react";

type Lead = { id: string; company_name: string; email: string | null };
type Contact = { id: string; name: string | null; title: string | null; email: string | null };

export default function RecipientPicker({ campaignId, leads, fixedLeadId, contactVersion, enrolledEmails, busy, act, onAdded }: {
  campaignId: string; leads: Lead[]; fixedLeadId?: string; contactVersion: string;
  enrolledEmails: string[]; busy: boolean;
  act: (action: () => Promise<unknown>) => void; onAdded: (count: number) => void;
}) {
  const [selectedLeadId, setSelectedLeadId] = useState("");
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [selectedContacts, setSelectedContacts] = useState<string[]>([]);
  const [manual, setManual] = useState("");
  const [includeImported, setIncludeImported] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const leadId = fixedLeadId || selectedLeadId;
  const lead = leads.find(item => item.id === leadId);
  const enrolled = new Set(enrolledEmails.map(email => email.toLowerCase()));

  useEffect(() => {
    let active = true;
    setContacts([]); setSelectedContacts([]); setManual(""); setIncludeImported(false); setError("");
    if (!leadId) return;
    setLoading(true);
    fetch(`http://localhost:8000/leads/${encodeURIComponent(leadId)}/contacts`, { cache: "no-store" })
      .then(async response => {
        if (!response.ok) throw new Error("Could not load saved contacts. Select the company again to retry.");
        return response.json() as Promise<Contact[]>;
      }).then(items => { if (active) setContacts(items); })
      .catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "Could not load contacts."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [leadId, contactVersion]);

  const selected = contacts.filter(contact => selectedContacts.includes(contact.id) && contact.email);
  const manualEmails = manual.split(/[\s,;]+/).filter(Boolean);
  const recipients = [
    ...selected.map(contact => ({ lead_id: leadId, contact_id: contact.id, recipient: contact.email! })),
    ...(includeImported && lead?.email ? [{ lead_id: leadId, contact_id: null, recipient: lead.email }] : []),
    ...manualEmails.map(email => ({ lead_id: leadId, contact_id: null, recipient: email })),
  ];
  const unique = new Map(recipients.map(item => [item.recipient.trim().toLowerCase(), item]));
  const duplicateCount = recipients.length - unique.size;

  return <div className="detail">
    <h3>Add multiple recipients</h3>
    {!fixedLeadId && <label>Company<select value={selectedLeadId} onChange={event => setSelectedLeadId(event.target.value)}>
      <option value="">Choose a company</option>
      {leads.map(item => <option key={item.id} value={item.id}>{item.company_name}</option>)}
    </select></label>}
    {leadId && <>
      {error && <p role="alert" className="error">{error}</p>}
      {loading ? <p>Loading contacts...</p> : <fieldset disabled={busy}>
        <legend>Choose saved people</legend>
        {contacts.length === 0 && <p>No saved contacts yet. Add people in the company's Lead 360 profile, or enter addresses below.</p>}
        {contacts.map(contact => <label className="recipient-option" key={contact.id}>
          <input type="checkbox" checked={selectedContacts.includes(contact.id)}
            disabled={!contact.email || enrolled.has(contact.email.toLowerCase())}
            onChange={event => setSelectedContacts(current => event.target.checked
              ? [...current, contact.id] : current.filter(id => id !== contact.id))} />
          <span>{contact.name || "Unnamed contact"}{contact.title ? ` · ${contact.title}` : ""}
            <small>{contact.email || "Add an email to this contact first"}
              {contact.email && enrolled.has(contact.email.toLowerCase()) && " · Already in campaign"}</small></span>
        </label>)}
        {lead?.email && <label className="recipient-option">
          <input type="checkbox" checked={includeImported} disabled={enrolled.has(lead.email.toLowerCase())}
            onChange={event => setIncludeImported(event.target.checked)} />
          <span>Imported company email<small>{lead.email}</small></span>
        </label>}
      </fieldset>}
      <label>Additional email addresses<textarea value={manual} onChange={event => setManual(event.target.value)}
        placeholder={"person1@example.com\nperson2@example.com\nSeparate addresses with a comma, semicolon or new line."} /></label>
      <p>{unique.size} recipients selected. Up to 100 per addition. Each gets an independent email thread.</p>
      {duplicateCount > 0 && <p role="alert">The same address is selected more than once. Remove duplicates before adding.</p>}
      <button disabled={busy || loading || unique.size === 0 || unique.size > 100 || duplicateCount > 0}
        onClick={() => act(async () => {
          const response = await fetch(`http://localhost:8000/campaigns/${encodeURIComponent(campaignId)}/enrollments/bulk`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ recipients: Array.from(unique.values()) }),
          });
          const body = await response.json();
          if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Could not add recipients.");
          setSelectedContacts([]); setManual(""); setIncludeImported(false);
          onAdded(body.added);
        })}>Add {unique.size || ""} recipients</button>
      <p>Nothing is sent when people are added. Invalid, suppressed, or already enrolled addresses reject the whole addition.</p>
    </>}
  </div>;
}
