"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import UiIcon from "../../components/ui-icon";
import WorkspaceOverview from "../../components/workspace-overview";
import IntelligenceWorkspace from "../../components/intelligence-workspace";
import BulkOutreachModal from "../../components/bulk-outreach-modal";
import { getApiBase } from "../../lib/api-config";

const API = getApiBase();
const fields = [
  ["company_name", "Company name"],
  ["domain", "Company domain"],
  ["email", "Email ID"],
  ["revenue", "Revenue"],
  ["phone", "Contact number"],
  ["remarks", "Remarks"],
  ["key_person_info", "Key person contact info"],
  ["designation", "Designation"],
  ["industry", "Industry"],
  ["location", "Location"],
] as const;
type Field = typeof fields[number][0];
type Sheet = {
  name: string; headers: string[]; row_count: number; column_count: number;
  preview: Record<string, string>[];
};
type Preview = { id: string; headers: string[]; sheets: Sheet[]; row_count: number };
type Batch = {
  id: string; filename: string; status: string; error: string | null;
  counts?: Record<string, number>;
  rows?: { sheet_name: string; row_number: number; status: string; message: string | null; original: Record<string, string> }[];
};
type Lead = {
  id: string; company_name: string; domain: string | null; email: string | null;
  industry: string | null; designation: string | null; location: string | null;
  revenue: string | null; phone: string | null; remarks: string | null;
  key_person_info: string | null; extra: Record<string, string>;
};
type Candidate = {
  id: string; name: string | null; title: string | null;
  department: string | null; seniority: string | null; organization: string | null;
  organization_domain: string | null; organization_matches: boolean;
  linkedin_url: string | null; has_email: boolean | null; retrieved_at: string;
};
type Contact = {
  id: string; name: string | null; title: string | null; email: string | null;
  department: string | null; seniority: string | null; linkedin_url: string | null;
  location: string | null; is_key_decision_maker: boolean; verification_status: string;
  source: string; retrieved_at: string;
};

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(API + path, options);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : `Request failed (${response.status}).`);
  }
  return response.json() as Promise<T>;
}

function jsonOptions(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

function guessMapping(headers: string[]): Record<string, string> {
  const aliases: Record<Field, string[]> = {
    company_name: ["company name", "company"],
    domain: ["company domain", "domain"],
    email: ["email id", "email", "email address"],
    revenue: ["revenue"],
    phone: ["contact number", "phone", "phone number"],
    remarks: ["remarks", "notes"],
    key_person_info: ["key person contact info", "key person"],
    designation: ["designation", "job title", "title"],
    industry: ["industry"],
    location: ["location", "company location"],
  };
  return Object.fromEntries(fields.map(([field]) => [
    field, headers.find(header => aliases[field].includes(header.trim().toLowerCase())) ?? "",
  ]));
}

export default function Home() {
  return <Suspense fallback={<main><p>Loading company workspace...</p></main>}><CompanyWorkspace /></Suspense>;
}

function CompanyWorkspace() {
  const requestedLeadId = useSearchParams().get("lead");
  const openedLeadId = useRef("");
  const leadSelection = useRef(0);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [mapping, setMapping] = useState<Record<string, Record<string, string>>>({});
  const [selectedSheets, setSelectedSheets] = useState<string[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [showBulkModal, setShowBulkModal] = useState(false);
  const [batch, setBatch] = useState<Batch | null>(null);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [lead, setLead] = useState<Lead | null>(null);
  const [domain, setDomain] = useState("");
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [confirmedCandidates, setConfirmedCandidates] = useState<string[]>([]);
  const [searched, setSearched] = useState(false);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [manualName, setManualName] = useState("");
  const [manualTitle, setManualTitle] = useState("");
  const [manualEmail, setManualEmail] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [leadQuery, setLeadQuery] = useState("");
  const [leadFilter, setLeadFilter] = useState("all");
  const [loaded, setLoaded] = useState(false);
  const [workbench, setWorkbench] = useState<"contacts" | "research">("contacts");
  const fileInput = useRef<HTMLInputElement>(null);
  const workbenchElement = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async () => {
    const [newBatches, newLeads] = await Promise.all([
      request<Batch[]>("/batches"), request<Lead[]>("/leads"),
    ]);
    setBatches(newBatches);
    setLeads(newLeads);
    setLoaded(true);
  }, []);

  useEffect(() => {
    refresh().catch(error => setMessage(error.message));
  }, [refresh]);

  useEffect(() => {
    if (!batch?.id || batch.status !== "pending") return;
    const timer = setInterval(async () => {
      try {
        const updated = await request<Batch>(`/batches/${batch.id}`);
        setBatch(updated);
        if (updated.status !== "pending") await refresh();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Could not refresh the batch.");
      }
    }, 3000);
    return () => clearInterval(timer);
  }, [batch?.id, batch?.status, refresh]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setMessage("");
    try { await action(); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Unexpected error."); }
    finally { setBusy(false); }
  }

  function upload(file?: File) {
    if (!file) return;
    void run(async () => {
      const data = new FormData();
      data.append("file", file);
      const result = await request<Preview>("/batches", { method: "POST", body: data });
      setPreview(result);
      setMapping(Object.fromEntries(result.sheets.map(sheet => [sheet.name, guessMapping(sheet.headers)])));
      setSelectedSheets(result.sheets.filter(sheet => sheet.headers.length > 0).map(sheet => sheet.name));
      setBatch(null);
      await refresh();
    });
  }

  function selectLead(value: Lead, view: "contacts" | "research" = "contacts") {
    const selection = ++leadSelection.current;
    setLead(value);
    setWorkbench(view);
    setDomain(value.domain ?? "");
    setCandidates([]);
    setContacts([]);
    setConfirmedCandidates([]);
    setSearched(true);
    void run(async () => {
      const [savedContacts, savedCandidates] = await Promise.all([
        request<Contact[]>(`/leads/${value.id}/contacts`),
        request<Candidate[]>(`/leads/${value.id}/apollo/search-results`),
      ]);
      if (selection === leadSelection.current) {
        setContacts(savedContacts);
        setCandidates(savedCandidates);
      }
    });
  }

  useEffect(() => {
    if (!requestedLeadId || requestedLeadId === openedLeadId.current) return;
    const requestedLead = leads.find(item => item.id === requestedLeadId);
    if (requestedLead) { openedLeadId.current = requestedLeadId; selectLead(requestedLead); }
  }, [requestedLeadId, leads]);

  const visibleLeads = leads.filter(item => `${item.company_name} ${item.domain || ""} ${item.industry || ""} ${item.location || ""}`.toLowerCase().includes(leadQuery.toLowerCase()))
    .filter(item => leadFilter === "all" || (leadFilter === "missing-domain" ? !item.domain : leadFilter === "missing-email" ? !item.email : !!item.domain));
  return (
    <main className="dashboard-page">
      <WorkspaceOverview companies={leads.length} domains={leads.filter(item => !!item.domain).length} imports={batches.length} loaded={loaded} />
      {message && <div role="alert" className="alert">{message}</div>}
      <section id="import">
        <div className="section-title"><div><p className="eyebrow">01 / IMPORT</p><h2>Upload your spreadsheet</h2></div></div>
        <div className="dropzone" onDragOver={event => event.preventDefault()} onDrop={event => {
          event.preventDefault(); upload(event.dataTransfer.files[0]);
        }}>
          <span className="upload-icon"><UiIcon name="upload" size={25} /></span><strong>Drop your company workbook here</strong>
          <p>.xlsx, up to 10 MB and 5,000 data rows</p>
          <button disabled={busy} onClick={() => fileInput.current?.click()}>Choose file</button>
          <input ref={fileInput} type="file" accept=".xlsx" hidden onChange={event => {
            upload(event.target.files?.[0]); event.target.value = "";
          }} />
        </div>
        {preview && <div className="mapping">
          <h3>Map worksheets · {preview.sheets.length} sheets · {preview.row_count} rows</h3>
          <p>Select worksheets and map company name on each one. Different worksheets can use different columns. Unmapped columns are preserved.</p>
          <div className="actions">
            <button disabled={busy} onClick={() => setSelectedSheets(preview.sheets.filter(sheet => sheet.headers.length > 0).map(sheet => sheet.name))}>Select all non-empty sheets</button>
            <button disabled={busy} onClick={() => setSelectedSheets([])}>Clear selection</button>
          </div>
          {preview.sheets.map(sheet => {
            const selected = selectedSheets.includes(sheet.name);
            return <div className="detail" key={sheet.name}>
              <label><input type="checkbox" disabled={!sheet.headers.length}
                checked={selected} onChange={event => setSelectedSheets(event.target.checked ?
                  [...selectedSheets, sheet.name] : selectedSheets.filter(name => name !== sheet.name))} />
                {sheet.name} · {sheet.row_count} non-empty rows · {sheet.column_count} columns
              </label>
              {sheet.headers.length === 0 ? <p>This worksheet is empty and cannot be mapped.</p> : <>
                {selected && <div className="grid">
                  {fields.map(([key, label]) => <label key={key}>{label}{key === "company_name" && " *"}
                    <select value={mapping[sheet.name]?.[key] ?? ""} onChange={event => setMapping({
                      ...mapping, [sheet.name]: { ...mapping[sheet.name], [key]: event.target.value },
                    })}>
                      <option value="">Not mapped</option>
                      {sheet.headers.map(header => <option key={header} value={header}>{header}</option>)}
                    </select>
                  </label>)}
                </div>}
                <details><summary>Preview first {sheet.preview.length} rows</summary>
                  <div className="table-wrap"><table><thead><tr>{sheet.headers.map(h => <th key={h}>{h}</th>)}</tr></thead>
                    <tbody>{sheet.preview.map((row, i) => <tr key={i}>{sheet.headers.map(h => <td key={h}>{row[h]}</td>)}</tr>)}</tbody>
                  </table></div>
                </details>
              </>}
            </div>;
          })}
          <button disabled={busy || selectedSheets.length === 0 || selectedSheets.some(name => !mapping[name]?.company_name)} onClick={() => void run(async () => {
            const selectedMappings = Object.fromEntries(selectedSheets.map(name => [name, mapping[name]]));
            const result = await request<Batch>(`/batches/${preview.id}/start`, jsonOptions("POST", { mapping: selectedMappings }));
            setBatch(result); setPreview(null); await refresh();
          })}>Start import</button>
        </div>}
        <h3>Recent imports</h3>
        {batches.length === 0 ? <p>No imports yet.</p> : <div className="list">
          {batches.map(item => <button className="list-item" key={item.id} onClick={() => void run(async () => {
            if (item.status === "draft") {
              const result = await request<Preview>(`/batches/${item.id}/preview`);
              setPreview(result);
              setMapping(Object.fromEntries(result.sheets.map(sheet => [sheet.name, guessMapping(sheet.headers)])));
              setSelectedSheets(result.sheets.filter(sheet => sheet.headers.length > 0).map(sheet => sheet.name));
              setBatch(null);
            } else {
              setPreview(null); setBatch(await request<Batch>(`/batches/${item.id}`));
            }
          })}><span>{item.filename}</span><span className="badge">{item.status}</span></button>)}
        </div>}
        {batch && <div className="detail"><h3>Import: {batch.filename}</h3>
          <p>Status: <strong>{batch.status}</strong> {batch.status === "pending" && "(queued or processing)"}</p>
          {batch.error && <p className="error">{batch.error}</p>}
          {batch.status === "failed" && <button disabled={busy} onClick={() => void run(async () => {
            setBatch(await request<Batch>(`/batches/${batch.id}/retry`, { method: "POST" })); await refresh();
          })}>Retry import</button>}
          {batch.counts && <p>{Object.entries(batch.counts).map(([key, value]) => `${key}: ${value}`).join(" · ")}</p>}
          {batch.status === "completed" && <a className="button-link" href="#companies"><UiIcon name="search" size={16} /> Find your imported companies</a>}
          {batch.rows?.filter(row => row.status !== "imported").map(row =>
            <details key={`${row.sheet_name}:${row.row_number}`}><summary>{row.sheet_name} · Row {row.row_number}: {row.status} — {row.message}</summary>
              <pre>{JSON.stringify(row.original, null, 2)}</pre></details>)}
        </div>}
      </section>
      <section id="companies">
        <div className="section-title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "12px" }}>
          <div>
            <p className="eyebrow">02 / FIND YOUR NEXT COMPANY</p>
            <h2>Review companies</h2>
            <p>Search your imported list by company name or domain, then research the business or find its people.</p>
          </div>
          <div>
            <button
              type="button"
              className="button-link"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "8px",
                fontSize: "13px",
                padding: "8px 16px",
                cursor: "pointer",
                boxShadow: "0 2px 6px rgba(220, 38, 38, 0.18)",
              }}
              onClick={() => setShowBulkModal(true)}
            >
              <UiIcon name="mail" size={15} /> ✉️ Email All Leads / Bulk Outreach
            </button>
          </div>
        </div>
        <BulkOutreachModal
          isOpen={showBulkModal}
          onClose={() => setShowBulkModal(false)}
          onSuccess={refresh}
        />
        <div className="company-toolbar"><div className="report-search"><UiIcon name="search" size={18} /><input type="search" aria-label="Search companies" value={leadQuery}
          onChange={event => setLeadQuery(event.target.value)} placeholder="Search company, domain, industry or location..." /></div>
          <label>Company filter<select value={leadFilter} onChange={event => setLeadFilter(event.target.value)}>
            <option value="all">All companies</option><option value="with-domain">With a confirmed domain</option><option value="missing-domain">Missing domain</option><option value="missing-email">Missing imported email</option></select></label></div>
        {leads.length > 0 && <p className="result-count">{visibleLeads.length} of {leads.length} loaded companies</p>}
        {leads.length === 0 ? <p>{loaded ? "Imported companies will appear here. Upload a workbook above to get started." : "Loading imported companies..."}</p> :
          <div className="table-wrap"><table><thead><tr><th>Company</th><th>Email</th><th>Revenue</th><th>Contact</th><th /></tr></thead>
            <tbody>{visibleLeads.map(item => <tr key={item.id}><td><a className="company-name-link" href={`/leads/${encodeURIComponent(item.id)}`}><span className="company-avatar small">{item.company_name.slice(0, 2).toUpperCase()}</span><span>{item.company_name}<small>{item.domain || "Domain not confirmed"}</small></span></a></td><td>{item.email || "Not recorded"}</td>
              <td>{item.revenue || "—"}</td><td>{item.phone || "—"}</td>
              <td><div className="company-row-actions"><a className="button-link secondary" href="#company-workbench" onClick={() => selectLead(item, "research")}><UiIcon name="spark" size={14} /> Research</a>
                <button className="secondary" disabled={busy} onClick={() => {
                  selectLead(item); workbenchElement.current?.scrollIntoView({ block: "start" });
                }}>Review</button></div></td></tr>)}</tbody>
          </table></div>}
        {leads.length > 0 && visibleLeads.length === 0 && <div className="empty-state"><UiIcon name="search" size={28} /><h3>No matching companies</h3><p>Try a different search or company filter.</p></div>}
        <div id="company-workbench" ref={workbenchElement}>
        {!lead && <div className="workbench-placeholder"><UiIcon name="companies" size={24} /><div><h3>Select a company to continue</h3><p>Choose Research or Review from the table. Your imported company, domain and contacts stay connected.</p></div></div>}
        {lead && <div className="detail company-workbench">
          <h3>{lead.company_name}</h3>
          <a href={`/leads/${encodeURIComponent(lead.id)}`}>Open Lead 360 profile →</a>
          <div className="actions"><button className={workbench === "research" ? "" : "secondary"} aria-pressed={workbench === "research"} onClick={() => setWorkbench("research")}><UiIcon name="spark" size={16} /> Company research</button>
            <button className={workbench === "contacts" ? "" : "secondary"} aria-pressed={workbench === "contacts"} onClick={() => setWorkbench("contacts")}><UiIcon name="companies" size={16} /> Domain & people</button>
            <a className="button-link secondary" href={`/leads/${encodeURIComponent(lead.id)}#outreach`}><UiIcon name="mail" size={16} /> Compose outreach</a></div>
          {workbench === "research" ? <IntelligenceWorkspace key={lead.id} lead={{ id: lead.id, company_name: lead.company_name, domain: lead.domain }} /> : <>
          <p><strong>Remarks:</strong> {lead.remarks || "—"}<br /><strong>Key person:</strong> {lead.key_person_info || "—"}</p>
          <p><strong>Industry:</strong> {lead.industry || "—"} · <strong>Designation:</strong> {lead.designation || "—"} · <strong>Location:</strong> {lead.location || "—"}</p>
          {Object.keys(lead.extra).length > 0 && <details><summary>Additional imported fields</summary>
            <pre>{JSON.stringify(lead.extra, null, 2)}</pre></details>}
          <label>Confirmed company domain or website <input value={domain} placeholder="example.com or https://example.com" onChange={event => setDomain(event.target.value)} /></label>
          <p>Enter a domain or http(s) website URL; the app saves only the normalized company domain. Confirm it before searching. Apollo results can include past employers; check the person before selection.</p>
          <div className="actions"><button className="secondary" disabled={busy || !domain.trim()} onClick={() => void run(async () => {
            const updated = await request<Lead>(`/leads/${lead.id}/domain`, jsonOptions("PUT", { domain }));
            setLead(updated); setDomain(updated.domain || ""); setCandidates([]); setConfirmedCandidates([]); setSearched(false);
            await refresh();
            setMessage("Company domain saved. You can now research this company or search Apollo.");
          })}>Save domain</button><button disabled={busy || !domain} onClick={() => void run(async () => {
            const updated = await request<Lead>(`/leads/${lead.id}/domain`, jsonOptions("PUT", { domain }));
            setLead(updated); setCandidates([]); setConfirmedCandidates([]); setSearched(false);
            setCandidates(await request<Candidate[]>(`/leads/${lead.id}/apollo/search`, { method: "POST" }));
            setSearched(true);
            await refresh();
          })}>Search Apollo</button></div>
          <p className="field-help">Apollo search may show limited names and does not provide an email until enrichment. Review the current employer before enriching; enrichment may consume Apollo credits.</p>
          {searched && candidates.length === 0 && <p>Apollo returned no matching candidates.</p>}
          <div className="list">{candidates.map(person => <div className="candidate" key={person.id}>
            <span><strong>{person.name || "Name unavailable"}</strong><br />{person.title || "Title unavailable"} · {person.organization || "Company unavailable"}
              <br /><small>Org domain: {person.organization_domain || "not provided"} · {person.organization_matches ? "domain matches" : "verify current company manually"}</small>
              {person.seniority && <><br /><small>{person.seniority}{person.department ? ` · ${person.department}` : ""}</small></>}
              {person.linkedin_url && <><br /><a href={person.linkedin_url} target="_blank" rel="noreferrer">LinkedIn profile</a></>}
              {person.has_email === true && <><br /><small>Apollo indicates a business email may be available</small></>}
              {!person.organization_matches && <label className="candidate-confirmation"><input type="checkbox"
                checked={confirmedCandidates.includes(person.id)} onChange={event => setConfirmedCandidates(current =>
                  event.target.checked ? [...current, person.id] : current.filter(id => id !== person.id))} />
                <span>I checked that this person currently works at {lead.company_name}.</span></label>}</span>
            <button disabled={busy || (!person.organization_matches && !confirmedCandidates.includes(person.id))} onClick={() => {
              void run(async () => {
                await request(`/leads/${lead.id}/apollo/enrich`, jsonOptions("POST", {
                  apollo_id: person.id, organization_confirmed: !person.organization_matches,
                }));
                setContacts(await request<Contact[]>(`/leads/${lead.id}/contacts`));
                setMessage("Contact saved successfully.");
              });
            }}>Select & enrich</button>
          </div>)}</div>
          <h3>Selected contacts</h3>
          <div className="detail"><h4>Add a contact manually</h4>
            <div className="grid">
              <label>Name<input value={manualName} onChange={event => setManualName(event.target.value)} /></label>
              <label>Designation<input value={manualTitle} onChange={event => setManualTitle(event.target.value)} /></label>
              <label>Business email<input type="email" value={manualEmail} onChange={event => setManualEmail(event.target.value)} /></label>
            </div>
            <button disabled={busy || !manualName.trim()} onClick={() => void run(async () => {
              await request(`/leads/${lead.id}/contacts`, jsonOptions("POST", {
                name: manualName, title: manualTitle || null, email: manualEmail || null,
              }));
              setContacts(await request<Contact[]>(`/leads/${lead.id}/contacts`));
              setManualName(""); setManualTitle(""); setManualEmail("");
            })}>Add contact</button>
          </div>
          {contacts.length === 0 ? <p>No contacts yet. Search Apollo or add a contact manually.</p> :
            contacts.map(contact => <div className="detail" key={contact.id}>
              <strong>{contact.name || "Name unavailable"}</strong>{contact.is_key_decision_maker && " · Decision maker"}
              <p>{contact.title || "—"} · {contact.email || "Business email unavailable"}</p>
              <small>{contact.source} · {contact.verification_status} · {new Date(contact.retrieved_at).toLocaleString()}</small>
              <div className="actions">
                <button disabled={busy} onClick={() => void run(async () => {
                  const updatedEmail = window.prompt("Update business email", contact.email || "");
                  if (updatedEmail === null) return;
                  await request(`/leads/${lead.id}/contacts/${contact.id}`, jsonOptions("PUT", { email: updatedEmail.trim() || null }));
                  setContacts(await request<Contact[]>(`/leads/${lead.id}/contacts`));
                })}>Edit email</button>
                <button disabled={busy} onClick={() => void run(async () => {
                  const title = window.prompt("Update designation", contact.title || "");
                  if (title === null) return;
                  await request(`/leads/${lead.id}/contacts/${contact.id}`, jsonOptions("PUT", { title: title || null }));
                  setContacts(await request<Contact[]>(`/leads/${lead.id}/contacts`));
                })}>Edit designation</button>
                <button disabled={busy} onClick={() => void run(async () => {
                  await request(`/leads/${lead.id}/contacts/${contact.id}`, {
                    method: "DELETE",
                  });
                  setContacts(await request<Contact[]>(`/leads/${lead.id}/contacts`));
                })}>Remove association</button>
              </div>
            </div>)}
        </>}
        </div>}
        </div>
      </section>
      <footer>Local pilot. Company research is available in Company Intelligence when enabled. Product catalogue matching is not implemented.</footer>
    </main>
  );
}
