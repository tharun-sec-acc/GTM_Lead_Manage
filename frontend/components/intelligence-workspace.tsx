"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { displayDate, intelligenceRequest as request, label, statusTone, type InferenceProfile, type JobSummary, type Page,
  type ResearchFact, type ResearchJob, type ResearchReport, type ResearchSource, type ResearchStatus } from "../lib/intelligence";
import IntelligenceReport from "./intelligence-report";
import UiIcon from "./ui-icon";

type LeadContext = { id: string; company_name: string; domain: string | null };
const terminal = new Set(["completed", "partial", "failed", "canceled", "cancelled"]);
const agentDescriptions: Record<string, string> = {
  company: "Identity, business model, products and locations",
  news: "Dated announcements and relevant developments",
  financial: "Reported financials, periods and entity scope",
  funding: "Disclosed investments, rounds and acquisitions",
  leadership: "Public leadership and appointment evidence",
  competitors: "Supported market and competitor relationships",
  signals: "Observed developments, separate from opportunities",
  verification: "Evidence support, duplicates and conflicts",
  synthesis: "Consolidated findings without new factual claims",
};

export default function IntelligenceWorkspace({ lead, initialJobId }: { lead?: LeadContext; initialJobId?: string }) {
  const [status, setStatus] = useState<ResearchStatus | null>(null);
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [selectedId, setSelectedId] = useState(initialJobId || "");
  const [job, setJob] = useState<ResearchJob | null>(null);
  const [company, setCompany] = useState(lead?.company_name || "");
  const [website, setWebsite] = useState(lead?.domain || "");
  const [country, setCountry] = useState("");
  const [registrationId, setRegistrationId] = useState("");
  const [depth, setDepth] = useState("quick");
  const [consent, setConsent] = useState(false);
  const [profileId, setProfileId] = useState("");
  const [profiles, setProfiles] = useState<InferenceProfile[]>([]);
  const [profileNext, setProfileNext] = useState<string | null>(null);
  const [profileError, setProfileError] = useState("");
  const [profilesLoading, setProfilesLoading] = useState(false);
  const [forceRefresh, setForceRefresh] = useState(false);
  const [showForm, setShowForm] = useState(!initialJobId);
  const [facts, setFacts] = useState<ResearchFact[]>([]);
  const [sources, setSources] = useState<ResearchSource[]>([]);
  const [factsTotal, setFactsTotal] = useState(0);
  const [sourcesTotal, setSourcesTotal] = useState(0);
  const [report, setReport] = useState<ResearchReport | null>(null);
  const [error, setError] = useState("");
  const [jobError, setJobError] = useState("");
  const [reportError, setReportError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const refreshVersion = useRef(0);
  const [pollVersion, setPollVersion] = useState(0);

  const loadWorkspace = useCallback(async () => {
    const [configuration, history] = await Promise.all([
      request<ResearchStatus>("/intelligence/status"),
      request<Page<JobSummary>>(`/intelligence/research?limit=20${lead ? `&lead_id=${encodeURIComponent(lead.id)}` : ""}`),
    ]);
    setStatus(configuration); setJobs(history.items);
    return history.items;
  }, [lead?.id]);

  useEffect(() => {
    let active = true;
    setError("");
    void loadWorkspace().then(items => {
      if (active && lead && !initialJobId && items.length) { setSelectedId(items[0].id); setShowForm(false); }
    }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "Could not load intelligence."); });
    return () => { active = false; };
  }, [loadWorkspace, initialJobId, lead?.id]);

  useEffect(() => {
    if (!selectedId) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    setJob(null); setJobError(""); setFacts([]); setSources([]); setReport(null);
    setFactsTotal(0); setSourcesTotal(0);
    async function poll() {
      try {
        const detail = await request<ResearchJob>(`/intelligence/research/${encodeURIComponent(selectedId)}`);
        if (!active) return;
        setJob(detail); setJobError("");
        setJobs(current => current.map(item => item.id === detail.id ? { ...item, status: detail.status,
          progress: detail.progress, report_id: detail.report_id, updated_at: detail.updated_at } : item));
        if (!terminal.has(detail.status)) timer = setTimeout(() => void poll(), 4000);
      } catch (reason) {
        if (active) {
          setJobError(reason instanceof Error ? reason.message : "Could not refresh research progress.");
          timer = setTimeout(() => void poll(), 10000);
        }
      }
    }
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [selectedId, pollVersion]);

  useEffect(() => {
    if (!job) return;
    let active = true;
    const version = ++refreshVersion.current;
    setReportError("");
    void Promise.all([
      request<Page<ResearchFact>>(`/intelligence/companies/${job.company_id}/facts?job_id=${job.id}&limit=100&offset=0`),
      request<Page<ResearchSource>>(`/intelligence/companies/${job.company_id}/sources?job_id=${job.id}&limit=100&offset=0`),
      job.report_id ? request<ResearchReport>(`/intelligence/reports/${job.report_id}`) : Promise.resolve(null),
    ]).then(([foundFacts, foundSources, foundReport]) => {
      if (!active || version !== refreshVersion.current) return;
      setFacts(foundFacts.items); setSources(foundSources.items);
      setFactsTotal(foundFacts.total); setSourcesTotal(foundSources.total); setReport(foundReport);
    }).catch(reason => { if (active) setReportError(reason instanceof Error ? reason.message : "Could not load findings."); });
    return () => { active = false; };
  }, [job?.company_id, job?.sources_count, job?.facts_count, job?.report_id, job?.status]);

  async function loadProfiles(nextToken?: string) {
    setProfilesLoading(true); setProfileError("");
    try {
      const result = await request<{ profiles: InferenceProfile[]; next_token: string | null }>(
        `/integrations/bedrock/profiles${nextToken ? `?next_token=${encodeURIComponent(nextToken)}` : ""}`);
      setProfiles(current => Array.from(new Map([...(nextToken ? current : []), ...result.profiles].map(profile => [profile.arn, profile])).values()));
      setProfileNext(result.next_token);
      if (!nextToken) setProfileId("");
      if (!result.profiles.length && !nextToken) setProfileError("No active inference profiles were returned in the configured region.");
    } catch (reason) { setProfileError(reason instanceof Error ? reason.message : "Could not load AWS profiles."); }
    finally { setProfilesLoading(false); }
  }

  async function startResearch(overrideForceRefresh?: boolean) {
    const shouldForce = overrideForceRefresh !== undefined ? overrideForceRefresh : forceRefresh;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await request<{ job_id: string; company_id: string; reused: boolean }>("/intelligence/research", "POST", {
        company_name: company, website, country: country || null, registration_id: registrationId || null,
        lead_id: lead?.id || null, depth, inference_profile_id: profileId || null, force_refresh: shouldForce,
      });
      setSelectedId(result.job_id); setPollVersion(value => value + 1); setShowForm(false);
      setNotice(result.reused ? "Reopened existing research. No duplicate job was created." : "Research queued. Progress below comes from persisted worker activity.");
      await loadWorkspace();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not start research."); }
    finally { setBusy(false); }
  }

  async function jobAction(action: "retry" | "cancel") {
    if (!job) return;
    setBusy(true); setJobError("");
    try {
      await request(`/intelligence/research/${job.id}/${action}`, "POST");
      setPollVersion(value => value + 1); await loadWorkspace();
      setNotice(action === "retry" ? "Retry requested. Completed agent findings are preserved." : "Cancellation requested. In-flight work may finish its current bounded operation.");
    } catch (reason) { setJobError(reason instanceof Error ? reason.message : `Could not ${action} research.`); }
    finally { setBusy(false); }
  }

  async function loadMore(kind: "facts" | "sources") {
    if (!job) return;
    const version = refreshVersion.current;
    setLoadingMore(true); setReportError("");
    try {
      if (kind === "facts") {
        const page = await request<Page<ResearchFact>>(`/intelligence/companies/${job.company_id}/facts?job_id=${job.id}&limit=100&offset=${facts.length}`);
        if (version === refreshVersion.current) { setFacts(current => [...current, ...page.items]); setFactsTotal(page.total); }
      } else {
        const page = await request<Page<ResearchSource>>(`/intelligence/companies/${job.company_id}/sources?job_id=${job.id}&limit=100&offset=${sources.length}`);
        if (version === refreshVersion.current) { setSources(current => [...current, ...page.items]); setSourcesTotal(page.total); }
      }
    } catch (reason) { setReportError(reason instanceof Error ? reason.message : "Could not load more records."); }
    finally { setLoadingMore(false); }
  }

  const progress = Math.max(0, Math.min(100, job?.progress || 0));
  return <div className={`intelligence-workspace${lead ? " embedded-intelligence" : ""}`}>
    <div className={lead ? "section-title" : "page-heading intelligence-heading"}>
      <div><p className="eyebrow">EVIDENCE-FIRST RESEARCH</p>
        {lead ? <h2>Company intelligence</h2> : <h1>Know the company.<br /><span>See the opportunity.</span></h1>}
        <p>{lead ? "Research this company without leaving its profile. Existing contacts and approvals stay unchanged."
          : "From scattered sources to a clear, cited company profile. Research first. Reach out with confidence."}</p></div>
      <div className="actions"><button className="secondary" disabled={busy} onClick={() => {
        setShowForm(true); setConsent(false); setForceRefresh(false);
      }}><UiIcon name="spark" size={16} /> New research</button>
        <button className="icon-button secondary" aria-label="Refresh research history" disabled={busy} onClick={() => {
          setError(""); void loadWorkspace().catch(reason => setError(reason instanceof Error ? reason.message : "Could not refresh history."));
          if (selectedId) setPollVersion(value => value + 1);
        }}><UiIcon name="refresh" size={18} /></button></div>
    </div>
    {error && <div className="alert" role="alert">{error}</div>}
    {notice && <div className="notice" role="status"><UiIcon name="check" size={17} />{notice}</div>}
    {status && !status.enabled && <div className="alert" role="status"><strong>Research is not enabled on the server.</strong> {status.note} Existing reports remain available.</div>}
    <div className="intelligence-layout">
      <div>{showForm && <section className="research-request">
        <div className="section-title"><div><span className="feature-label"><UiIcon name="search" size={16} /> START A DISCOVERY</span><h2>Which company are you researching?</h2></div></div>
        <form onSubmit={event => { event.preventDefault(); void startResearch(); }}>
          <div className="grid research-inputs"><label>Company name <span aria-hidden="true">*</span><input required value={company} onChange={event => setCompany(event.target.value)} placeholder="e.g. Example Manufacturing" disabled={!!lead} /></label>
            <label>Official website or domain <span aria-hidden="true">*</span><input required value={website} onChange={event => setWebsite(event.target.value)} placeholder="example.com" /></label></div>
          <p className="field-help">Confirm the official company website. Private networks, credentials, restricted pages and unsupported URLs are not permitted.</p>
          <details className="optional-fields"><summary>Country & legal-entity details <span>Optional</span></summary><div className="grid research-inputs">
            <label>Country<input value={country} onChange={event => setCountry(event.target.value)} placeholder="e.g. India" /></label>
            <label>Registration identifier<input value={registrationId} onChange={event => setRegistrationId(event.target.value)} placeholder="Public company registration identifier" /></label></div></details>
          <fieldset className="research-depth"><legend>Choose research depth</legend>
            <label className={depth === "quick" ? "selected" : ""}><input type="radio" name={`research-depth-${lead?.id || "standalone"}`} value="quick" checked={depth === "quick"} onChange={() => setDepth("quick")} />
              <span><strong>Quick discovery</strong><small>Company overview, news, leadership and business signals.</small></span><UiIcon name="clock" size={18} /></label>
            <label className={depth === "comprehensive" ? "selected" : ""}><input type="radio" name={`research-depth-${lead?.id || "standalone"}`} value="comprehensive" checked={depth === "comprehensive"} onChange={() => setDepth("comprehensive")} />
              <span><strong>Comprehensive research</strong><small>Add financial, funding and competitor research where evidence is available.</small></span><UiIcon name="spark" size={18} /></label>
          </fieldset>
          <div className="model-configuration"><div><strong>Approved Bedrock model</strong><p>Use your server default or explicitly select an approved inference profile. Profiles may route data across regions.</p></div>
            <button type="button" className="secondary" disabled={profilesLoading || busy} onClick={() => void loadProfiles()}>{profilesLoading ? "Loading profiles..." : "Load AWS profiles"}</button>
            {profiles.length > 0 && <label>Research inference profile<select value={profileId} onChange={event => setProfileId(event.target.value)}><option value="">Use configured server model</option>{profiles.map(profile =>
              <option key={profile.arn} value={profile.arn}>{profile.name} · {profile.regions.join(", ")}</option>)}</select></label>}
            {profileNext && <button type="button" className="secondary" disabled={profilesLoading} onClick={() => void loadProfiles(profileNext)}>Load more profiles</button>}
            {profileError && <p role="alert" className="error">{profileError}</p>}
          </div>
          <label className="consent-option"><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} />
            <span>I confirm this public-company research and its processing through the selected AWS model are approved. Research may incur provider charges.</span></label>
          <label className="consent-option"><input type="checkbox" checked={forceRefresh} onChange={event => setForceRefresh(event.target.checked)} />
            <span>Force fresh crawl &amp; extraction (bypass 24-hour cache)</span></label>
          <div className="request-footer"><small>{status?.search_configured ? `Search provider: ${status.search_provider}` : "Without a configured search provider, discovery is limited to the supplied website and its accessible sources."}</small>
            <button type="submit" disabled={busy || !status?.enabled || !consent || !company.trim() || !website.trim()}><UiIcon name="spark" size={17} />{busy ? "Starting research..." : "Start research"} <UiIcon name="arrow" size={16} /></button></div>
        </form>
      </section>}
      {!showForm && !job && !jobError && selectedId && <section className="empty-state"><span className="loading-ring" /><h2>Loading persisted research...</h2></section>}
      {jobError && <div role="alert" className="alert">{jobError}</div>}
      {job && <section className="research-progress">
        <div className="section-title"><div><p className="eyebrow">RESEARCH WORKSPACE</p><h2>{job.company_name}</h2><p>{job.domain} · Started {displayDate(job.created_at)}</p></div><span className={`status-pill ${statusTone(job.status)}`}>{label(job.status)}</span></div>
        <div className="progress-heading"><strong>{label(job.stage)}</strong><span>{progress}%</span></div>
        <progress value={progress} max={100} aria-label="Overall research progress">{progress}%</progress>
        <div className="research-counts"><div><UiIcon name="link" size={17} /><strong>{job.sources_count}</strong><span>Sources</span></div>
          <div><UiIcon name="file" size={17} /><strong>{job.pages_processed}</strong><span>Pages processed</span></div><div><UiIcon name="check" size={17} /><strong>{job.facts_count}</strong><span>Extracted findings</span></div></div>
        {job.error && <div className="alert" role="alert">{job.error}</div>}
        <div className="agent-list">{job.agents.map(agent => <div key={agent.id} className={`agent-row ${statusTone(agent.status)}`}>
          <span className="agent-icon">{agent.status === "completed" ? <UiIcon name="check" size={17} /> : <UiIcon name={agent.agent === "verification" ? "link" : "spark"} size={17} />}</span>
          <div><strong>{label(agent.agent)} {agent.agent.endsWith("agent") ? "" : "agent"}</strong><small>{agentDescriptions[agent.agent] || "Persisted research task"}
            {agent.retry_count > 0 && <> · {agent.retry_count} {agent.retry_count === 1 ? "retry" : "retries"}</>}</small>{agent.error && <p className="error">{agent.error}</p>}</div>
          <span className={`status-pill ${statusTone(agent.status)}`}>{label(agent.status)}</span>
        </div>)}</div>
        <div className="actions">
          {lead && factsTotal > 0 && <a className="button-link" href={`/leads/${encodeURIComponent(lead.id)}#outreach`}><UiIcon name="mail" size={16} /> Choose facts for outreach</a>}
          {lead && <Link className="button-link secondary" href={`/?lead=${encodeURIComponent(lead.id)}#companies`}><UiIcon name="companies" size={16} /> Find decision-makers</Link>}
          {["failed", "partial"].includes(job.status) && <button className="secondary" disabled={busy} onClick={() => void jobAction("retry")}><UiIcon name="refresh" size={16} /> Retry failed work</button>}
          {terminal.has(job.status) && (
            <button
              className="secondary"
              disabled={busy}
              onClick={() => {
                setCompany(job.company_name);
                setWebsite(job.domain);
                void startResearch(true);
              }}
            >
              <UiIcon name="spark" size={16} /> Re-run fresh research
            </button>
          )}
          {!terminal.has(job.status) && <button className="secondary" disabled={busy} onClick={() => void jobAction("cancel")}>Cancel research</button>}
          {terminal.has(job.status) && (
            <button
              className="secondary"
              disabled={busy}
              onClick={() => {
                setShowForm(true);
                setConsent(true);
                setForceRefresh(true);
                setCompany(job.company_name);
                setWebsite(job.domain);
              }}
            >
              Review & refresh research
            </button>
          )}
          <Link className="text-link" href={`/intelligence/jobs/${job.id}`}>Open research workspace <UiIcon name="external" size={14} /></Link>
        </div>
        {showForm && terminal.has(job.status) && <p className="field-help">To bypass fresh cached research, review the form and explicitly refresh below.</p>}
        {showForm && terminal.has(job.status) && <button className="secondary" disabled={busy || !consent || !status?.enabled} onClick={() => void startResearch(true)}>Refresh with new source collection</button>}
        <p className="field-help">Progress is persisted by background workers. Missing information and failed tasks are not filled with simulated data.</p>
      </section>}
      </div>
      {!lead && <aside className="research-sidebar">
        <section><div className="section-title"><h2>Recent research</h2><span className="count-badge">{jobs.length}</span></div>
          {jobs.length ? <div className="research-history">{jobs.map(item => <button key={item.id} className={`history-item${selectedId === item.id ? " selected" : ""}`} onClick={() => {
            setSelectedId(item.id); setShowForm(false); setNotice("");
          }}><span className="company-avatar">{item.company_name.slice(0, 2).toUpperCase()}</span><span><strong>{item.company_name}</strong><small>{item.domain}</small><span className={`status-pill ${statusTone(item.status)}`}>{label(item.status)}</span></span></button>)}</div>
            : <div className="empty-state small"><UiIcon name="clock" size={26} /><h3>{status ? "No research yet" : error ? "History unavailable" : "Loading history..."}</h3>
              <p>{status ? "Your recent research will appear here." : "Research history is shown only after a successful API response."}</p></div>}
        </section>
        <div className="research-principles"><span className="icon-tile"><UiIcon name="link" /></span><h3>Every useful insight starts with a source.</h3>
          <p>Open the evidence behind each finding. Review dates, financial periods and company identity before using it.</p><ul><li>No fabricated financials</li><li>Original source citations</li><li>Missing information stays visible</li><li>You approve all outreach</li></ul></div>
      </aside>}
    </div>
    {lead && jobs.length > 1 && <label className="research-history-select">Earlier research for this company<select value={selectedId} onChange={event => { setSelectedId(event.target.value); setShowForm(false); }}>
      {jobs.map(item => <option key={item.id} value={item.id}>{displayDate(item.created_at)} · {label(item.status)} · {item.id.slice(0, 8)}</option>)}</select></label>}
    {reportError && <div className="alert" role="alert">{reportError}</div>}
    {job && <IntelligenceReport facts={facts} sources={sources} report={report} factsTotal={factsTotal} sourcesTotal={sourcesTotal}
      loadingMore={loadingMore} onMoreFacts={() => void loadMore("facts")} onMoreSources={() => void loadMore("sources")} />}
  </div>;
}
