"use client";

import { useCallback, useEffect, useState } from "react";
import RecipientPicker from "./recipient-picker";
import ResearchFactPicker from "./research-fact-picker";
import UiIcon from "./ui-icon";

const API = "http://localhost:8000";
type Lead = { id: string; company_name: string; email: string | null };
type Campaign = { id: string; name: string; mode: "manual" | "automatic"; delays: number[]; status: string };
type Event = { event_type: string; event_time: string };
type Message = {
  id: string; step_number: number; subject: string; body: string; status: string;
  due_at: string | null; sent_at: string | null; approved_at: string | null;
  message_id: string; last_error: string | null; manual_reply: boolean; events: Event[];
};
type Reply = { id: string; sender: string | null; subject: string | null; body: string; classification: string | null };
type Enrollment = {
  id: string; lead_id: string; company_name: string; contact_id: string | null; contact_name: string | null;
  recipient: string; status: string; reply_blocked: boolean;
  messages: Message[]; replies: Reply[];
};
type Detail = Campaign & { sequence_approved_at: string | null; enrollments: Enrollment[] };
type Mailbox = { last_success_at: string | null; last_error: string | null };
type MailCapacity = {
  window_hours: number; configured_limit: number; attempts_counted: number;
  remaining_application_budget: number; sending_enabled: boolean; note: string;
  unsubscribe_enabled: boolean; tracking_enabled: boolean; tracking_configured: boolean; tracking_note: string;
};
type BedrockStatus = { configured: boolean; region: string | null; model_id: string | null; note: string };
type InferenceProfile = { id: string; arn: string; name: string; type: string; regions: string[] };
type ProfilePage = { profiles: InferenceProfile[]; next_token: string | null };
type SalesTask = { id: string; title: string; status: string };
type Analytics = {
  recipient_count: number; active_recipient_count: number; stopped_recipient_count: number;
  suppressed_recipient_count: number; replied_recipient_count: number;
  accepted_recipient_count: number; accepted_email_count: number;
  opened_recipient_count: number; clicked_recipient_count: number;
  reply_rate_percent: number | null; open_rate_percent: number | null; click_rate_percent: number | null;
  engagement_note: string;
};

async function request<T>(path: string, method = "GET", data?: unknown): Promise<T> {
  const response = await fetch(API + path, {
    method,
    ...(data === undefined ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : `Request failed (${response.status}).`);
  }
  return response.json() as Promise<T>;
}

function MessageEditor({ message, busy, act }: {
  message: Message; busy: boolean; act: (action: () => Promise<unknown>) => void;
}) {
  const [subject, setSubject] = useState(message.subject);
  const [body, setBody] = useState(message.body);
  const [link, setLink] = useState("");
  useEffect(() => { setSubject(message.subject); setBody(message.body); }, [message.subject, message.body]);
  const editable = ["draft", "approved", "failed", "rejected"].includes(message.status);
  return <div className="detail">
    <h4>{message.manual_reply ? "Manual response" : message.step_number === 0 ? "Initial email" : `Follow-up ${message.step_number}`}</h4>
    <p>Status: <strong>{message.status}</strong> · Due: {message.due_at ? new Date(message.due_at).toLocaleString() : "Not scheduled yet"}
      {message.sent_at && <> · SMTP accepted: {new Date(message.sent_at).toLocaleString()}</>}</p>
    {message.last_error && <p className="error">{message.last_error}</p>}
    {(message.status === "unknown" || message.status === "sending") &&
      <div><p className="error">Do not retry blindly. Check Gmail and reconcile this attempt manually.</p>
        <div className="actions">
          <button disabled={busy} onClick={() => {
            if (window.confirm("Have you verified in Gmail that this exact message was sent?")) act(() =>
              request(`/messages/${message.id}/resolve-send`, "POST", { accepted: true }));
          }}>Confirmed sent</button>
          <button disabled={busy} onClick={() => {
            if (window.confirm("Have you verified that this exact message was NOT sent? A new approval will be required.")) act(() =>
              request(`/messages/${message.id}/resolve-send`, "POST", { accepted: false }));
          }}>Confirmed not sent</button>
        </div></div>}
    <label>Subject<input value={subject} disabled={!editable} onChange={event => setSubject(event.target.value)} /></label>
    <label>Email body<textarea value={body} disabled={!editable} onChange={event => setBody(event.target.value)} /></label>
    {editable && <p>{!subject.trim() || !body.trim()
      ? "Write a subject and body here, or generate drafts using the approved facts above."
      : subject !== message.subject || body !== message.body
        ? "Unsaved changes. Save this draft before approving it."
        : message.status === "approved" ? "This exact saved email is approved. The Gmail worker still checks sending safeguards."
          : "Review the saved subject and body, then approve this exact email."}</p>}
    {editable && <div className="actions">
      <button disabled={busy || !subject.trim() || !body.trim()} onClick={() => act(() =>
        request(`/messages/${message.id}`, "PUT", { subject, body }))}>Save draft</button>
      <button disabled={busy || ["approved", "rejected"].includes(message.status) || subject !== message.subject || body !== message.body}
        onClick={() => act(() => request(`/messages/${message.id}/approve`, "POST", { subject, body }))}>Approve saved email</button>
      <button disabled={busy || message.status === "rejected"} onClick={() => act(() =>
        request(`/messages/${message.id}/reject`, "POST"))}>Reject</button>
    </div>}
    {editable && <details><summary>Optional approved click-tracking link</summary>
      <label>HTTPS URL already present in saved draft<input value={link} onChange={event => setLink(event.target.value)} /></label>
      <button disabled={busy || !link || subject !== message.subject || body !== message.body} onClick={() => act(async () => {
        await request(`/messages/${message.id}/tracking-links`, "POST", { destination: link });
        setLink("");
      })}>Add link and require reapproval</button>
    </details>}
    {message.events.length > 0 && <p>Events: {message.events.map(event => event.event_type).join(" · ")}. Opens and clicks can be generated by automated clients.</p>}
  </div>;
}

function ReplyCard({ reply, busy, act }: { reply: Reply; busy: boolean; act: (action: () => Promise<unknown>) => void }) {
  const [subject, setSubject] = useState(`Re: ${reply.subject || ""}`);
  const [body, setBody] = useState("");
  return <div className="detail">
    <p><strong>{reply.sender || "Unknown sender"}</strong> · {reply.classification || "Unclassified"}</p>
    <p>{reply.subject}</p><pre>{reply.body}</pre>
    <button disabled={busy} onClick={() => act(() => request(`/replies/${reply.id}/classify`, "POST"))}>Classify with Bedrock</button>
    <details><summary>Write a response for approval</summary>
      <label>Subject<input value={subject} onChange={event => setSubject(event.target.value)} /></label>
      <label>Body<textarea value={body} onChange={event => setBody(event.target.value)} /></label>
      <div className="actions"><button disabled={busy} onClick={() => act(async () => {
        const suggestion = await request<{ subject: string; body: string }>(`/replies/${reply.id}/suggest-response`, "POST");
        setSubject(suggestion.subject); setBody(suggestion.body);
      })}>Suggest with Bedrock</button>
      <button disabled={busy || !subject.trim() || !body.trim()} onClick={() => act(async () => {
        await request(`/replies/${reply.id}/draft-response`, "POST", { subject, body }); setBody("");
      })}>Create response draft</button></div>
    </details>
  </div>;
}

export default function OutreachWorkspace({ leadId: fixedLeadId, contactVersion = "" }: {
  leadId?: string; contactVersion?: string;
}) {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [selected, setSelected] = useState("");
  const [detail, setDetail] = useState<Detail | null>(null);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [mailbox, setMailbox] = useState<Mailbox | null>(null);
  const [capacity, setCapacity] = useState<MailCapacity | null>(null);
  const [bedrock, setBedrock] = useState<BedrockStatus | null>(null);
  const [profiles, setProfiles] = useState<InferenceProfile[]>([]);
  const [nextProfileToken, setNextProfileToken] = useState<string | null>(null);
  const [profileId, setProfileId] = useState("");
  const [profileError, setProfileError] = useState("");
  const [loadingProfiles, setLoadingProfiles] = useState(false);
  const [unmatched, setUnmatched] = useState<Reply[]>([]);
  const [tasks, setTasks] = useState<SalesTask[]>([]);
  const [name, setName] = useState("");
  const [mode, setMode] = useState("manual");
  const [delays, setDelays] = useState("3,4,5");
  const [context, setContext] = useState("");
  const [researchCompany, setResearchCompany] = useState("");
  const [researchFacts, setResearchFacts] = useState<Record<string, string[]>>({});
  const [suppression, setSuppression] = useState("");
  const [bounceRecipient, setBounceRecipient] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const [campaignData, leadData, mailboxData, capacityData, unmatchedData, taskData, analyticsData, bedrockData] = await Promise.all([
      request<Campaign[]>("/campaigns"), request<Lead[]>("/leads"),
      request<Mailbox>("/mailbox/status"), request<MailCapacity>("/mailbox/capacity"),
      request<Reply[]>("/replies/unmatched"),
      request<SalesTask[]>("/sales-tasks"),
      selected ? request<Analytics>(`/campaigns/${selected}/analytics`) : Promise.resolve(null),
      request<BedrockStatus>("/integrations/bedrock/status"),
    ]);
    setCampaigns(campaignData); setLeads(leadData); setMailbox(mailboxData); setCapacity(capacityData);
    setUnmatched(unmatchedData); setTasks(taskData);
    setAnalytics(analyticsData);
    setBedrock(bedrockData);
    if (selected) setDetail(await request<Detail>(`/campaigns/${selected}`));
  }, [selected]);

  useEffect(() => {
    refresh().catch(reason => setError(reason instanceof Error ? reason.message : "Could not load."));
    const timer = setInterval(() => refresh().catch(reason => setError(reason instanceof Error ? reason.message : "Could not refresh.")), 15000);
    return () => clearInterval(timer);
  }, [refresh]);

  function act(action: () => Promise<unknown>) {
    setBusy(true); setError(""); setNotice("");
    void action().then(() => refresh()).catch(reason => setError(reason instanceof Error ? reason.message : "Request failed."))
      .finally(() => setBusy(false));
  }

  async function loadProfiles(nextToken?: string) {
    setLoadingProfiles(true); setProfileError("");
    try {
      const result = await request<ProfilePage>("/integrations/bedrock/profiles" +
        (nextToken ? `?next_token=${encodeURIComponent(nextToken)}` : ""));
      setProfiles(current => Array.from(new Map(
        [...(nextToken ? current : []), ...result.profiles].map(profile => [profile.arn, profile]),
      ).values()));
      setNextProfileToken(result.next_token);
      if (!nextToken) setProfileId("");
      if (!result.profiles.length && !nextToken) setProfileError("AWS returned no active inference profiles in this region.");
    } catch (reason) {
      setProfileError(reason instanceof Error ? reason.message : "Could not load AWS inference profiles.");
    } finally { setLoadingProfiles(false); }
  }

  const enrollments = detail?.enrollments.filter(item => !fixedLeadId || item.lead_id === fixedLeadId) ?? [];
  const messages = enrollments.flatMap(item => item.messages);
  const campaignLeadIds = Array.from(new Set(enrollments.map(item => item.lead_id)));
  const researchLeadId = fixedLeadId || (campaignLeadIds.includes(researchCompany) ? researchCompany
    : campaignLeadIds.length === 1 ? campaignLeadIds[0] : "");
  return <div className="outreach-workspace">
    {!fixedLeadId && <header><div><p className="eyebrow">DENSO / SALES PILOT</p><h1>Follow-up management</h1>
      <p>Personal conversations. Independent threads. Every first email reviewed by you.</p></div><a className="button-link secondary" href="/"><UiIcon name="companies" size={16} /> Company workspace</a></header>}
    {error && <div role="alert" className="alert">{error}</div>}
    {notice && <div role="status" className="detail">{notice}</div>}
    <ol className="workflow-steps"><li>Create or choose a draft campaign</li><li>Select people and add recipients</li>
      <li>Write or generate drafts</li><li>Save, review and approve</li><li>Activate when ready</li></ol>
    <div className="alert">{capacity ? `Sending is ${capacity.sending_enabled ? "enabled" : "disabled"} in the server configuration.`
      : "Loading sending configuration..."} Only approved emails in active campaigns can send, after inbox sync, suppression and send-limit checks.
      {capacity?.unsubscribe_enabled && " HTTPS unsubscribe links are required."} This application has no login; keep it private.</div>
    {capacity && <p className="detail">Application sending budget: {capacity.attempts_counted} of {capacity.configured_limit} attempts in the last {capacity.window_hours} hours;
      {` ${capacity.remaining_application_budget} remaining`}. Sending is {capacity.sending_enabled ? "enabled by server configuration" : "disabled"}.
      {" "}{capacity.note}</p>}
    {capacity && <p className="detail">Unsubscribe footer: {capacity.unsubscribe_enabled ? "enabled" : "disabled by server configuration"}.
      {" "}{capacity.tracking_note}</p>}
    {mailbox && !mailbox.last_success_at && <div role="alert" className="alert">
      Sending is waiting for a complete inbox sync. {mailbox.last_error || "The Gmail inbox has not synchronized yet."}
    </div>}
    {!fixedLeadId && <div className="stats">
      <div><strong>{messages.filter(m => m.due_at && ["draft", "approved"].includes(m.status)).length}</strong><span>Scheduled in selected campaign</span></div>
      <div><strong>{messages.filter(m => m.due_at && ["draft", "approved"].includes(m.status)
        && new Date(m.due_at).toDateString() === new Date().toDateString()).length}</strong><span>Due today in selected campaign</span></div>
      <div><strong>{detail?.enrollments.filter(item => item.reply_blocked).length ?? 0}</strong><span>Recipients stopped by replies</span></div>
      <div><strong>{messages.filter(m => ["failed", "sending", "unknown"].includes(m.status)).length}</strong><span>Attempts needing attention</span></div>
    </div>}
    {!fixedLeadId && analytics && <div className="detail" aria-label="Campaign analytics">
      <h3>Campaign analytics</h3>
      <div className="stats">
        <div><strong>{analytics.recipient_count}</strong><span>Unique recipients</span></div>
        <div><strong>{analytics.accepted_recipient_count} / {analytics.accepted_email_count}</strong>
          <span>Recipients / emails with recorded acceptance</span></div>
        <div><strong>{analytics.replied_recipient_count} ({analytics.reply_rate_percent ?? "—"}%)</strong>
          <span>Recipients replied / reply rate</span></div>
        <div><strong>{analytics.opened_recipient_count} ({analytics.open_rate_percent ?? "—"}%)</strong>
          <span>Recipients with an approximate open signal</span></div>
        <div><strong>{analytics.clicked_recipient_count} ({analytics.click_rate_percent ?? "—"}%)</strong>
          <span>Recipients with an approximate click signal</span></div>
        <div><strong>{analytics.suppressed_recipient_count} / {analytics.stopped_recipient_count}</strong>
          <span>Suppressed / stopped recipients</span></div>
      </div>
      <p>{analytics.engagement_note}</p>
    </div>}
    <section>
      <h2>Create a campaign</h2>
      <div className="grid">
        <label>Name<input value={name} onChange={event => setName(event.target.value)} /></label>
        <label>Approval mode<select value={mode} onChange={event => setMode(event.target.value)}>
          <option value="manual">Approve every email</option><option value="automatic">Approve follow-up sequence</option>
        </select></label>
        <label>Days after previous send<input value={delays} onChange={event => setDelays(event.target.value)} placeholder="3,4,5" /></label>
      </div>
      <button disabled={busy || !name.trim()} onClick={() => act(async () => {
        const values = delays.trim() ? delays.split(",").map(value => Number(value.trim())) : [];
        if (values.some(value => !Number.isInteger(value) || value < 1 || value > 365) || values.length > 5)
          throw new Error("Enter up to five comma-separated whole-number delays between 1 and 365.");
        const result = await request<{ id: string }>("/campaigns", "POST", { name, mode, delays: values });
        setName(""); setSelected(result.id);
      })}>Create campaign</button>
    </section>
    <section>
      <h2>Choose a campaign</h2>
      <p>Use a draft campaign to add more people. Recipients receive separate emails, never a shared CC/BCC message.</p>
      {campaigns.length === 0 ? <p>No campaigns yet.</p> : <div className="list">
        {campaigns.map(campaign => <button key={campaign.id} className="list-item" disabled={busy} onClick={() => {
          setSelected(campaign.id); setDetail(null);
        }}><span>{campaign.name} · {campaign.mode}</span><span className="badge">{campaign.status}</span></button>)}
      </div>}
      {detail && <div>
        <h3>{detail.name} · {detail.status}</h3>
        <p>Mode: {detail.mode}; follow-up delays: {detail.delays.join(", ") || "none"} days after the previous send.</p>
        {fixedLeadId && enrollments.length !== detail.enrollments.length && <div className="alert">
          This campaign also contains {detail.enrollments.length - enrollments.length} recipients from other companies.
          Activate and pause apply to the entire campaign. <a href="/followups">Review all recipients before activating or approving the whole sequence.</a>
        </div>}
        <p>Activate only after reviewing and approving the drafts. Activation does not override disabled sending.</p>
        <div className="actions">
          <button disabled={busy} onClick={() => act(() => request(`/campaigns/${detail.id}/activate`, "POST"))}>Activate / resume campaign</button>
          <button disabled={busy} onClick={() => act(() => request(`/campaigns/${detail.id}/pause`, "POST"))}>Pause campaign</button>
          {detail.mode === "automatic" && detail.delays.length > 0 &&
            (!fixedLeadId || enrollments.length === detail.enrollments.length) && <button disabled={busy} onClick={() =>
            act(() => request(`/campaigns/${detail.id}/approve-sequence`, "POST", {
              messages: detail.enrollments.flatMap(item => item.messages)
                .filter(message => !message.manual_reply && message.step_number > 0 && ["draft", "approved", "failed"].includes(message.status))
                .map(message => ({ id: message.id, subject: message.subject, body: message.body })),
            }))}>Approve all saved follow-up drafts</button>}
        </div>
        {detail.mode === "automatic" && <p>Sequence approval: {detail.sequence_approved_at ? new Date(detail.sequence_approved_at).toLocaleString() : "not approved"}</p>}
        {detail.status === "draft" ? <RecipientPicker campaignId={detail.id} leads={leads}
          fixedLeadId={fixedLeadId} contactVersion={contactVersion}
          enrolledEmails={detail.enrollments.map(item => item.recipient)} busy={busy} act={act}
          onAdded={count => setNotice(`${count} recipients added. Each has an independent draft sequence; nothing was sent.`)} /> :
          <p>Add recipients in a new draft campaign. Existing active or paused campaigns cannot accept additional recipients.</p>}
        <div className="detail">
          <div className="section-title"><h3><UiIcon name="spark" size={18} /> AI draft generation</h3><span className="status-pill neutral">HUMAN REVIEW REQUIRED</span></div>
          <p>Bedrock model: {bedrock?.model_id || "Not configured"} · Region: {bedrock?.region || "Not configured"}</p>
          <p>{bedrock?.note || "Loading configuration..."}</p>
          <button className="secondary" disabled={busy || loadingProfiles || !bedrock?.region}
            onClick={() => void loadProfiles()}>{loadingProfiles ? "Loading AWS profiles..." : "Load AWS inference profiles"}</button>
          {nextProfileToken && <button className="secondary" disabled={busy || loadingProfiles}
            onClick={() => void loadProfiles(nextProfileToken)}>Load more profiles</button>}
          {profileError && <p role="alert" className="error">{profileError}</p>}
          {profiles.length > 0 && <label>Model / inference profile for this generation
            <select value={profileId} disabled={busy} onChange={event => setProfileId(event.target.value)}>
              <option value="">Use server-configured BEDROCK_MODEL_ID</option>
              {profiles.map(profile => <option key={profile.arn} value={profile.arn}>
                {profile.name} · {profile.type} · {profile.regions.join(", ")}
              </option>)}
            </select>
          </label>}
          {profileId && <p>Selected profile: {profiles.find(profile => profile.arn === profileId)?.name}.
            Routing regions: {profiles.find(profile => profile.arn === profileId)?.regions.join(", ")}.</p>}
          <p>Some models require an inference profile instead of a base model ID.
            Profiles may route data across regions; select only an approved profile.
            Listing a profile does not prove invocation access or Converse compatibility.
            This choice applies to draft generation here only and does not change server defaults.</p>
          {bedrock && !bedrock.configured && !profileId && <p role="alert">Set AWS_REGION and BEDROCK_MODEL_ID on the server,
            or load and explicitly select an approved inference profile when the region is configured.
            AWS credentials must also be available inside the API and worker processes.</p>}
          <label>Approved company and DENSO product facts<textarea value={context}
            placeholder="Paste approved company facts, the DENSO product or service to offer, and your call to action. A website URL alone is not research."
            onChange={event => setContext(event.target.value)} /></label>
          <p>Websites are not visited. Paste factual context rather than asking the model to browse.
            Alternatively, select saved cited research below. Only enter information approved for AWS. Each recipient is generated separately and needs review.</p>
          {!fixedLeadId && campaignLeadIds.length > 1 && <label>Company intelligence context<select value={researchLeadId}
            onChange={event => setResearchCompany(event.target.value)}><option value="">Choose a company to review its facts</option>
            {campaignLeadIds.map(id => <option key={id} value={id}>{leads.find(item => item.id === id)?.company_name || id}</option>)}</select></label>}
          {researchLeadId && <ResearchFactPicker key={researchLeadId} leadId={researchLeadId} selected={researchFacts[researchLeadId] || []}
            onChange={ids => setResearchFacts(current => ({ ...current, [researchLeadId]: ids }))} />}
        </div>
        <h3>{fixedLeadId ? "This company's recipients" : "Campaign recipients"} ({enrollments.length})</h3>
        {enrollments.length === 0 && <p>Select people above to create their drafts.</p>}
        {enrollments.map(enrollment => <details className="recipient-thread" key={enrollment.id} open={enrollments.length === 1}>
          <summary>{enrollment.contact_name || enrollment.recipient} · {enrollment.company_name} · {enrollment.status}</summary>
          <h3>{enrollment.company_name}{enrollment.contact_name ? ` · ${enrollment.contact_name}` : ""} · {enrollment.recipient}</h3>
          <p>Recipient: {enrollment.status} {enrollment.reply_blocked && "· stopped by reply — review before resuming"}</p>
          <div className="actions">
            <button disabled={busy} onClick={() => act(() => request(`/enrollments/${enrollment.id}/stop`, "POST"))}>Stop recipient</button>
            <button disabled={busy} onClick={() => act(() => request(`/enrollments/${enrollment.id}/resume`, "POST"))}>Resume after review</button>
          </div>
          <button disabled={busy || !context.trim() || !bedrock?.region || !(profileId || bedrock?.model_id)} onClick={() => {
            if (enrollment.messages.some(message => message.subject || message.body) &&
                !window.confirm("Replace this recipient's saved drafts and clear their approvals?")) return;
            act(async () => {
              await request(`/enrollments/${enrollment.id}/generate`, "POST", {
                context, inference_profile_id: profileId || null,
                research_fact_ids: researchFacts[enrollment.lead_id] || [],
              });
              setNotice(`Drafts generated for ${enrollment.recipient}. Review the subject and body below before approving.`);
            });
          }}>{busy ? "Working..." : "Generate this recipient's drafts"}</button>
          {!!researchFacts[enrollment.lead_id]?.length && <small className="selected-research-note">{researchFacts[enrollment.lead_id].length} reviewed research facts will be included for this company.</small>}
          {error && <p role="alert" className="error">{error}</p>}
          {enrollment.messages.map(message => <MessageEditor key={message.id} message={message} busy={busy} act={act} />)}
          <h4>Conversation and replies</h4>
          {enrollment.replies.length === 0 ? <p>No matched replies.</p> : enrollment.replies.map(reply =>
            <ReplyCard key={reply.id} reply={reply} busy={busy} act={act} />)}
        </details>)}
      </div>}
    </section>
    {!fixedLeadId && <section>
      <h2>Sales tasks</h2>
      {tasks.filter(task => task.status === "open").length === 0 ? <p>No open meeting tasks.</p> :
        tasks.filter(task => task.status === "open").map(task => <div className="candidate" key={task.id}>
          <span>{task.title}</span><button disabled={busy} onClick={() => act(() =>
            request(`/sales-tasks/${task.id}/complete`, "POST"))}>Mark complete</button></div>)}
    </section>}
    {!fixedLeadId && <section>
      <h2>Mailbox and suppression</h2>
      <p>Last complete inbox sync: {mailbox?.last_success_at ? new Date(mailbox.last_success_at).toLocaleString() : "not yet synchronized"}.
        {mailbox?.last_error && ` ${mailbox.last_error}`}</p>
      <label>Suppress recipient email<input value={suppression} onChange={event => setSuppression(event.target.value)} /></label>
      <button disabled={busy || !suppression} onClick={() => act(async () => {
        await request("/suppressions", "POST", { email: suppression, reason: "sales_manual" }); setSuppression("");
      })}>Suppress address</button>
      <h3>Unmatched mailbox items</h3>
      {unmatched.length === 0 ? <p>No unmatched delivery reports.</p> : unmatched.map(reply => <div className="detail" key={reply.id}>
        <p>{reply.subject} · {reply.classification}</p><pre>{reply.body}</pre>
        {reply.classification === "bounce_review" && <>
          <label>Hard-bounce recipient (if known)<input value={bounceRecipient} onChange={event => setBounceRecipient(event.target.value)} /></label>
          <div className="actions"><button disabled={busy || !bounceRecipient} onClick={() => act(async () => {
            await request(`/replies/${reply.id}/resolve`, "POST", { recipient: bounceRecipient, hard_bounce: true }); setBounceRecipient("");
          })}>Suppress and resolve</button>
            <button disabled={busy} onClick={() => act(() => request(`/replies/${reply.id}/resolve`, "POST", { hard_bounce: false }))}>Mark reviewed, not a hard bounce</button></div>
        </>}
      </div>)}
    </section>}
  </div>;
}
