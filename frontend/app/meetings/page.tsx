"use client";

import Link from "next/link";
import { useState } from "react";
import UnifiedMeetingsView from "../../components/unified-meetings-view";
import BookingManagement from "../../components/booking-management";

const API = "http://localhost:8000";

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

export default function MeetingsPage() {
  const [showAvailabilityTool, setShowAvailabilityTool] = useState(false);
  const [start, setStart] = useState(() => {
    const first = new Date(Date.now() + 5 * 60000);
    return localInput(first);
  });
  const [end, setEnd] = useState(() => {
    const first = new Date(Date.now() + 5 * 60000);
    return localInput(new Date(first.getTime() + 24 * 60 * 60000));
  });
  const [availability, setAvailability] = useState<Availability | null>(null);
  const [availError, setAvailError] = useState("");
  const [availBusy, setAvailBusy] = useState(false);

  async function checkAvailability() {
    setAvailBusy(true);
    setAvailError("");
    setAvailability(null);
    try {
      const from = new Date(start);
      const to = new Date(end);
      if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime())) {
        throw new Error("Enter valid start and end times.");
      }
      setAvailability(
        await request<Availability>("/microsoft/availability", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ start: from.toISOString(), end: to.toISOString() }),
        })
      );
    } catch (reason) {
      setAvailError(reason instanceof Error ? reason.message : "Could not retrieve Microsoft availability.");
    } finally {
      setAvailBusy(false);
    }
  }

  return (
    <main>
      <header style={{ marginBottom: 20 }}>
        <div>
          <p className="eyebrow">DENSO GTM / VIDEO INTELLIGENCE</p>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <Link href="/" style={{ fontSize: 13, color: "var(--muted)" }}>
              ← Return to Dashboard
            </Link>
          </div>
        </div>
        <div className="actions">
          <button
            type="button"
            className="secondary"
            onClick={() => setShowAvailabilityTool(!showAvailabilityTool)}
            style={{ fontSize: 13 }}
          >
            {showAvailabilityTool ? "Hide Calendar Free/Busy Tool" : "🔍 Check Outlook Free/Busy"}
          </button>
        </div>
      </header>

      {/* Preserved Calendar Free/Busy Inspector */}
      {showAvailabilityTool && (
        <section style={{ marginBottom: 24, border: "1px solid var(--border)", background: "#fff", borderRadius: 10, padding: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h3 style={{ margin: 0 }}>Outlook Free/Busy Availability Inspector</h3>
            <span style={{ fontSize: 12, color: "var(--muted)" }}>Delegated Read-Only</span>
          </div>
          <p style={{ fontSize: 13, color: "var(--muted)", margin: "4px 0 16px" }}>
            Lookup organizer free/busy calendar windows from Microsoft Graph without modifying schedules.
          </p>
          {availError && <div role="alert" className="alert" style={{ marginBottom: 12 }}>{availError}</div>}
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
            <label style={{ fontSize: 12, fontWeight: 600 }}>
              From
              <input
                type="datetime-local"
                value={start}
                onChange={(e) => setStart(e.target.value)}
                style={{ display: "block", marginTop: 4, padding: "6px 10px", borderRadius: 6, border: "1px solid var(--border)" }}
              />
            </label>
            <label style={{ fontSize: 12, fontWeight: 600 }}>
              To
              <input
                type="datetime-local"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
                style={{ display: "block", marginTop: 4, padding: "6px 10px", borderRadius: 6, border: "1px solid var(--border)" }}
              />
            </label>
            <button
              disabled={availBusy || !start || !end}
              onClick={checkAvailability}
              style={{ padding: "8px 16px", fontSize: 13 }}
            >
              {availBusy ? "Checking…" : "Query Graph Schedule"}
            </button>
          </div>

          {availability && (
            <div style={{ marginTop: 16, background: "#f8fafc", padding: 14, borderRadius: 8, border: "1px solid #e2e8f0" }}>
              <p style={{ margin: 0, fontSize: 13, fontWeight: 600 }}>
                Timezone: {availability.timezone} · Slot Duration: {availability.duration_minutes}m
              </p>
              {availability.slots.length === 0 ? (
                <p style={{ margin: "8px 0 0", fontSize: 12, color: "var(--muted)" }}>No free slots found in this window.</p>
              ) : (
                <ul style={{ margin: "8px 0 0 16px", padding: 0, fontSize: 12 }}>
                  {availability.slots.map((s) => (
                    <li key={s.start}>
                      {new Date(s.start).toLocaleString()} – {new Date(s.end).toLocaleTimeString()}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </section>
      )}

      {/* Customer Public Booking Management */}
      <section style={{ marginBottom: 28 }}>
        <BookingManagement />
      </section>

      {/* Unified Meeting Management Component */}
      <UnifiedMeetingsView />
    </main>
  );
}
