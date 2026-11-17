"use client";

import { useEffect, useState } from "react";

const API = "http://localhost:8000";
type Status = { connected: boolean; organizer_email: string | null; scopes: string[] };
type Availability = {
  timezone: string;
  duration_minutes: number;
  slots: { start: string; end: string }[];
};

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(API + path, { cache: "no-store", ...options });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : `Request failed (${response.status}).`);
  }
  return response.json() as Promise<T>;
}

function localInput(date: Date) {
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

export default function Meetings() {
  const [status, setStatus] = useState<Status | null>(null);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [availability, setAvailability] = useState<Availability | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const first = new Date(Date.now() + 5 * 60000);
    setStart(localInput(first));
    setEnd(localInput(new Date(first.getTime() + 24 * 60 * 60000)));
    request<Status>("/microsoft/oauth/status").then(setStatus).catch(reason =>
      setError(reason instanceof Error ? reason.message : "Could not load Microsoft status."));
  }, []);

  async function disconnect() {
    if (!window.confirm("Remove the locally stored Microsoft organizer connection?")) return;
    setBusy(true); setError("");
    try {
      await request("/microsoft/oauth/disconnect", { method: "POST" });
      setStatus({ connected: false, organizer_email: null, scopes: [] });
      setAvailability(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not remove the local connection.");
    } finally { setBusy(false); }
  }

  async function checkAvailability() {
    setBusy(true); setError(""); setAvailability(null);
    try {
      const from = new Date(start);
      const to = new Date(end);
      if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime())) {
        throw new Error("Enter valid start and end times.");
      }
      setAvailability(await request<Availability>("/microsoft/availability", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ start: from.toISOString(), end: to.toISOString() }),
      }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not retrieve Microsoft availability.");
    } finally { setBusy(false); }
  }

  return <main>
    <header><div><p className="eyebrow">DENSO / SALES PILOT</p><h1>Outlook calendar availability</h1>
      <p>Local testing only. This screen does not book meetings or send invitations.</p></div>
      <a href="/">← Lead workspace</a></header>
    <div className="alert">This pilot has no app login. Do not expose it or use production customer data.</div>
    {error && <div role="alert" className="alert">{error}</div>}
    <section>
      <h2>Organizer connection</h2>
      {status === null ? <p>Loading connection status…</p> : status.connected ?
        <><p>Connected: {status.organizer_email}</p>
          <p>Availability uses delegated, read-only calendar access. Disconnect removes local tokens; it does not revoke tenant consent.</p>
          <button disabled={busy} onClick={disconnect}>Remove local connection</button></> :
        <><p>No organizer connected.</p><a href={`${API}/microsoft/oauth/start`}>Connect Microsoft organizer</a></>}
    </section>
    {status?.connected && <section>
      <h2>Check availability</h2>
      <p>Enter a future range using your computer&apos;s timezone. Results show the configured organizer timezone.</p>
      <label>From<input type="datetime-local" value={start} onChange={event => setStart(event.target.value)} /></label>
      <label>To<input type="datetime-local" value={end} onChange={event => setEnd(event.target.value)} /></label>
      <button disabled={busy || !start || !end} onClick={checkAvailability}>Check Outlook calendar</button>
      {availability && <div>
        <p>Timezone: {availability.timezone} · Duration: {availability.duration_minutes} minutes</p>
        {availability.slots.length === 0 ? <p>No available slots in this range.</p> :
          <ul>{availability.slots.map(slot => <li key={slot.start}>{slot.start} – {slot.end}</li>)}</ul>}
        <p>Availability may change; a future booking implementation must recheck it.</p>
      </div>}
    </section>}
  </main>;
}
