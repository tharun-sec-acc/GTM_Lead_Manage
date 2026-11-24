"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import UiIcon from "./ui-icon";
import { getApiBase } from "../lib/api-config";

const API = getApiBase();

interface WeekdayAvailability {
  weekday: number;
  start_time: string;
  end_time: string;
  is_enabled: boolean;
}

interface BookingProfile {
  id: string;
  public_slug: string;
  public_url: string;
  display_name: string;
  description: string | null;
  company_name: string;
  meeting_title: string;
  meeting_description: string | null;
  default_provider: string;
  duration_minutes: number;
  buffer_before_minutes: number;
  buffer_after_minutes: number;
  minimum_notice_minutes: number;
  booking_horizon_days: number;
  max_meetings_per_day: number;
  timezone: string;
  is_active: boolean;
  availabilities: WeekdayAvailability[];
}

interface CalendarStatus {
  google_connected: boolean;
  microsoft_connected: boolean;
  both_connected: boolean;
  google_organizer?: string | null;
  microsoft_organizer?: string | null;
  default_provider: string;
}

interface BookingItem {
  id: string;
  profile_slug: string | null;
  customer_name: string;
  customer_email: string;
  customer_company: string | null;
  customer_phone: string | null;
  meeting_purpose: string | null;
  start_time: string;
  end_time: string;
  timezone: string;
  google_meet_uri: string | null;
  status: string;
  lead_id: string | null;
  meeting_id: string | null;
  created_at: string;
}

const WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function BookingManagement() {
  const [profiles, setProfiles] = useState<BookingProfile[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<BookingProfile | null>(null);
  const [calendarStatus, setCalendarStatus] = useState<CalendarStatus | null>(null);
  const [bookings, setBookings] = useState<BookingItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [copiedLink, setCopiedLink] = useState(false);
  const [activeTab, setActiveTab] = useState<"overview" | "bookings" | "settings">("overview");

  // Edit Settings Form State
  const [isEditing, setIsEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savingDuration, setSavingDuration] = useState(false);
  const [durationNotice, setDurationNotice] = useState("");
  const [editTitle, setEditTitle] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editDuration, setEditDuration] = useState(30);
  const [editBufferBefore, setEditBufferBefore] = useState(10);
  const [editBufferAfter, setEditBufferAfter] = useState(10);
  const [editNotice, setEditNotice] = useState(120);
  const [editHorizon, setEditHorizon] = useState(30);
  const [editMaxDaily, setEditMaxDaily] = useState(8);
  const [editTimezone, setEditTimezone] = useState("Asia/Kolkata");
  const [editSlug, setEditSlug] = useState("");
  const [editAvailabilities, setEditAvailabilities] = useState<WeekdayAvailability[]>([]);

  // Fetch initial data
  useEffect(() => {
    let isMounted = true;
    async function loadAll() {
      setLoading(true);
      setError("");
      try {
        const [profRes, calRes, bookRes] = await Promise.all([
          fetch(`${API}/api/bookings/profiles`),
          fetch(`${API}/api/bookings/calendar-connections`),
          fetch(`${API}/api/bookings`),
        ]);

        if (profRes.ok) {
          const profData: BookingProfile[] = await profRes.json();
          if (isMounted) {
            setProfiles(profData);
            if (profData.length > 0) {
              const current = profData[0];
              setSelectedProfile(current);
              populateEditForm(current);
            }
          }
        }

        if (calRes.ok) {
          const calData: CalendarStatus = await calRes.json();
          if (isMounted) setCalendarStatus(calData);
        }

        if (bookRes.ok) {
          const bookData: BookingItem[] = await bookRes.json();
          if (isMounted) setBookings(bookData);
        }
      } catch (err) {
        if (isMounted) setError("Could not load booking management data.");
      } finally {
        if (isMounted) setLoading(false);
      }
    }
    loadAll();
    return () => {
      isMounted = false;
    };
  }, []);

  function populateEditForm(p: BookingProfile) {
    setEditTitle(p.meeting_title);
    setEditDescription(p.meeting_description || "");
    setEditDuration(p.duration_minutes);
    setEditBufferBefore(p.buffer_before_minutes);
    setEditBufferAfter(p.buffer_after_minutes);
    setEditNotice(p.minimum_notice_minutes);
    setEditHorizon(p.booking_horizon_days);
    setEditMaxDaily(p.max_meetings_per_day);
    setEditTimezone(p.timezone);
    setEditSlug(p.public_slug);
    setEditAvailabilities(
      p.availabilities && p.availabilities.length > 0
        ? p.availabilities
        : Array.from({ length: 7 }, (_, i) => ({
            weekday: i,
            start_time: "09:00",
            end_time: "17:00",
            is_enabled: i < 5,
          }))
    );
  }

  const handleCopyLink = () => {
    if (!selectedProfile) return;
    const origin = typeof window !== "undefined" ? window.location.origin : "http://localhost:3000";
    const fullUrl = `${origin}/book/${selectedProfile.public_slug}`;
    navigator.clipboard.writeText(fullUrl);
    setCopiedLink(true);
    setTimeout(() => setCopiedLink(false), 2000);
  };

  const handleQuickUpdateDuration = async (minutes: number) => {
    if (!selectedProfile) return;
    setSavingDuration(true);
    try {
      const res = await fetch(`${API}/api/bookings/profiles/${selectedProfile.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ duration_minutes: minutes }),
      });
      if (res.ok) {
        const updated: BookingProfile = await res.json();
        setSelectedProfile(updated);
        setEditDuration(updated.duration_minutes);
        setProfiles((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
        setDurationNotice(`Meeting length set to ${minutes === 60 ? "1 hr" : `${minutes} mins`}`);
        setTimeout(() => setDurationNotice(""), 3500);
      }
    } catch {
      // ignore
    } finally {
      setSavingDuration(false);
    }
  };

  const handleSaveSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProfile) return;
    setSaving(true);
    setError("");

    try {
      const res = await fetch(`${API}/api/bookings/profiles/${selectedProfile.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          meeting_title: editTitle,
          meeting_description: editDescription || null,
          duration_minutes: Number(editDuration),
          buffer_before_minutes: Number(editBufferBefore),
          buffer_after_minutes: Number(editBufferAfter),
          minimum_notice_minutes: Number(editNotice),
          booking_horizon_days: Number(editHorizon),
          max_meetings_per_day: Number(editMaxDaily),
          timezone: editTimezone,
          public_slug: editSlug,
          availabilities: editAvailabilities,
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || "Failed to update profile settings.");
      }

      const updated: BookingProfile = await res.json();
      setSelectedProfile(updated);
      setProfiles((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
      setIsEditing(false);
    } catch (err: any) {
      setError(err?.message || "Error saving profile.");
    } finally {
      setSaving(false);
    }
  };

  const handleToggleActive = async () => {
    if (!selectedProfile) return;
    const action = selectedProfile.is_active ? "deactivate" : "activate";
    try {
      const res = await fetch(`${API}/api/bookings/profiles/${selectedProfile.id}/${action}`, {
        method: "POST",
      });
      if (res.ok) {
        const updated: BookingProfile = await res.json();
        setSelectedProfile(updated);
        setProfiles((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
      }
    } catch (err) {
      setError("Failed to change profile status.");
    }
  };

  function formatDateTimeLong(isoStr: string) {
    try {
      return new Date(isoStr).toLocaleString([], {
        weekday: "short",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return isoStr;
    }
  }

  const origin = typeof window !== "undefined" ? window.location.origin : "http://localhost:3000";
  const publicBookingUrl = selectedProfile ? `${origin}/book/${selectedProfile.public_slug}` : "";

  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 14, padding: 24, boxShadow: "var(--shadow-sm)" }}>
      {/* Top Banner: Public Link & Status */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 16, marginBottom: 20 }}>
        <div>
          <span style={{ fontSize: 12, fontWeight: 700, color: "var(--red)", letterSpacing: "1px", textTransform: "uppercase" }}>
            Public Booking
          </span>
          <h2 style={{ margin: "4px 0", fontSize: 20, color: "#0f172a" }}>Customer Booking System</h2>
          <p style={{ margin: 0, fontSize: 13, color: "var(--muted)", maxWidth: 640 }}>
            Share your personalized booking link with prospects. Real-time availability is verified against both Google Calendar and Microsoft Outlook before creating Google Meet calls.
          </p>
        </div>

        {/* Dual Calendar Status Badge */}
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <div
            style={{
              padding: "6px 12px",
              borderRadius: 8,
              fontSize: 12,
              fontWeight: 600,
              display: "flex",
              alignItems: "center",
              gap: 6,
              background: calendarStatus?.google_connected ? "#ecfdf5" : "#fef2f2",
              color: calendarStatus?.google_connected ? "#065f46" : "#991b1b",
              border: `1px solid ${calendarStatus?.google_connected ? "#a7f3d0" : "#fecaca"}`,
            }}
          >
            <span>{calendarStatus?.google_connected ? "✓" : "!"}</span> Google Calendar FreeBusy
          </div>
          <div
            style={{
              padding: "6px 12px",
              borderRadius: 8,
              fontSize: 12,
              fontWeight: 600,
              display: "flex",
              alignItems: "center",
              gap: 6,
              background: calendarStatus?.microsoft_connected ? "#ecfdf5" : "#fef2f2",
              color: calendarStatus?.microsoft_connected ? "#065f46" : "#991b1b",
              border: `1px solid ${calendarStatus?.microsoft_connected ? "#a7f3d0" : "#fecaca"}`,
            }}
          >
            <span>{calendarStatus?.microsoft_connected ? "✓" : "!"}</span> Outlook getSchedule
          </div>
        </div>
      </div>

      {error && (
        <div role="alert" className="alert" style={{ marginBottom: 16 }}>
          {error}
        </div>
      )}

      {/* Public Link Share Box */}
      {selectedProfile && (
        <div
          style={{
            background: "#f8fafc",
            border: "1px solid #cbd5e1",
            borderRadius: 12,
            padding: "16px 20px",
            marginBottom: 24,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: 12,
          }}
        >
          <div>
            <span style={{ fontSize: 11, fontWeight: 700, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
              Your Active Public Link
            </span>
            <div style={{ fontSize: 15, fontWeight: 600, color: "#0f172a", marginTop: 2 }}>
              {publicBookingUrl}
            </div>
            <small style={{ color: "var(--muted)" }}>
              {selectedProfile.meeting_title} · {selectedProfile.duration_minutes}m duration · {selectedProfile.timezone}
            </small>
          </div>

          <div style={{ display: "flex", gap: 8 }}>
            <button
              type="button"
              onClick={handleCopyLink}
              style={{ padding: "8px 16px", fontSize: 13, background: copiedLink ? "#059669" : "var(--red)" }}
            >
              {copiedLink ? "✓ Link Copied!" : "📋 Copy Link"}
            </button>
            <a
              href={publicBookingUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="button-link secondary"
              style={{ fontSize: 13, padding: "8px 14px" }}
            >
              Open Page ↗
            </a>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: "flex", gap: 12, borderBottom: "1px solid var(--border)", marginBottom: 20 }}>
        <button
          type="button"
          onClick={() => setActiveTab("overview")}
          style={{
            background: "none",
            border: "none",
            borderBottom: activeTab === "overview" ? "2px solid var(--red)" : "2px solid transparent",
            color: activeTab === "overview" ? "var(--red)" : "var(--muted)",
            fontWeight: 600,
            padding: "8px 12px",
            fontSize: 14,
            borderRadius: 0,
            cursor: "pointer",
            boxShadow: "none",
          }}
        >
          Overview & Config
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("bookings")}
          style={{
            background: "none",
            border: "none",
            borderBottom: activeTab === "bookings" ? "2px solid var(--red)" : "2px solid transparent",
            color: activeTab === "bookings" ? "var(--red)" : "var(--muted)",
            fontWeight: 600,
            padding: "8px 12px",
            fontSize: 14,
            borderRadius: 0,
            cursor: "pointer",
            boxShadow: "none",
          }}
        >
          Customer Bookings ({bookings.length})
        </button>
      </div>

      {/* Tab 1: Overview & Configuration */}
      {activeTab === "overview" && selectedProfile && (
        <div>
          {!isEditing ? (
            <div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 16, marginBottom: 24 }}>
                <div style={{ background: "#f8fafc", padding: 16, borderRadius: 10, border: "1px solid #e2e8f0" }}>
                  <span style={{ fontSize: 12, color: "var(--muted)", display: "block" }}>Meeting Title</span>
                  <strong>{selectedProfile.meeting_title}</strong>
                </div>
                <div style={{ background: "#f8fafc", padding: 16, borderRadius: 10, border: "1px solid #e2e8f0" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 2 }}>
                    <span style={{ fontSize: 12, color: "var(--muted)" }}>Duration &amp; Limits</span>
                    {durationNotice && <span style={{ fontSize: 11, color: "#16a34a", fontWeight: 700 }}>✓ {durationNotice}</span>}
                  </div>
                  <strong style={{ fontSize: 16 }}>{selectedProfile.duration_minutes === 60 ? "1 hour" : `${selectedProfile.duration_minutes} mins`}</strong>
                  <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
                    {[15, 30, 45, 60].map((m) => {
                      const isActive = selectedProfile.duration_minutes === m;
                      return (
                        <button
                          key={m}
                          type="button"
                          disabled={savingDuration}
                          onClick={() => handleQuickUpdateDuration(m)}
                          title={`Switch public booking slots to ${m === 60 ? "1 hour" : `${m} minutes`}`}
                          style={{
                            padding: "3px 8px",
                            borderRadius: 6,
                            fontSize: 11,
                            fontWeight: 700,
                            cursor: "pointer",
                            border: `1px solid ${isActive ? "var(--red)" : "#cbd5e1"}`,
                            background: isActive ? "var(--red)" : "#ffffff",
                            color: isActive ? "#ffffff" : "#475569",
                            transition: "all 0.15s ease",
                          }}
                        >
                          {m === 60 ? "1h" : `${m}m`}
                        </button>
                      );
                    })}
                  </div>
                  <small style={{ display: "block", color: "var(--muted)", marginTop: 6 }}>Max {selectedProfile.max_meetings_per_day} meetings/day</small>
                </div>
                <div style={{ background: "#f8fafc", padding: 16, borderRadius: 10, border: "1px solid #e2e8f0" }}>
                  <span style={{ fontSize: 12, color: "var(--muted)", display: "block" }}>Notice & Horizon</span>
                  <strong>Min {Math.round(selectedProfile.minimum_notice_minutes / 60)}h notice</strong>
                  <small style={{ display: "block", color: "var(--muted)" }}>Up to {selectedProfile.booking_horizon_days} days ahead</small>
                </div>
                <div style={{ background: "#f8fafc", padding: 16, borderRadius: 10, border: "1px solid #e2e8f0" }}>
                  <span style={{ fontSize: 12, color: "var(--muted)", display: "block" }}>Buffer Protection</span>
                  <strong>{selectedProfile.buffer_before_minutes}m before / {selectedProfile.buffer_after_minutes}m after</strong>
                  <small style={{ display: "block", color: "var(--muted)" }}>Prevents back-to-back fatigue</small>
                </div>
              </div>

              {/* Working Hours Summary */}
              <div style={{ marginBottom: 20 }}>
                <h4 style={{ margin: "0 0 10px", fontSize: 14, color: "#334155" }}>Active Working Hours</h4>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {selectedProfile.availabilities?.map((av) => (
                    <div
                      key={av.weekday}
                      style={{
                        padding: "8px 12px",
                        borderRadius: 8,
                        fontSize: 12,
                        background: av.is_enabled ? "#eff6ff" : "#f1f5f9",
                        border: `1px solid ${av.is_enabled ? "#bfdbfe" : "#cbd5e1"}`,
                        color: av.is_enabled ? "#1e40af" : "#94a3b8",
                      }}
                    >
                      <strong>{WEEKDAY_NAMES[av.weekday]}</strong>: {av.is_enabled ? `${av.start_time} - ${av.end_time}` : "Off"}
                    </div>
                  ))}
                </div>
              </div>

              <div style={{ display: "flex", gap: 10 }}>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setIsEditing(true)}
                  style={{ fontSize: 13 }}
                >
                  ⚙ Edit Working Hours & Settings
                </button>
                <button
                  type="button"
                  className="secondary"
                  onClick={handleToggleActive}
                  style={{ fontSize: 13, color: selectedProfile.is_active ? "#dc2626" : "#059669" }}
                >
                  {selectedProfile.is_active ? "Deactivate Link" : "Activate Link"}
                </button>
              </div>
            </div>
          ) : (
            /* Editing Form */
            <form onSubmit={handleSaveSettings} style={{ background: "#f8fafc", padding: 20, borderRadius: 12, border: "1px solid #cbd5e1" }}>
              <h3 style={{ margin: "0 0 16px", fontSize: 16 }}>Configure Booking Profile</h3>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 14 }}>
                <label style={{ fontSize: 13, fontWeight: 600 }}>
                  Meeting Title
                  <input
                    type="text"
                    required
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    style={{ width: "100%", padding: "6px 10px", borderRadius: 6, border: "1px solid #cbd5e1", marginTop: 4 }}
                  />
                </label>
                <label style={{ fontSize: 13, fontWeight: 600 }}>
                  Public Slug (/book/[slug])
                  <input
                    type="text"
                    required
                    value={editSlug}
                    onChange={(e) => setEditSlug(e.target.value)}
                    style={{ width: "100%", padding: "6px 10px", borderRadius: 6, border: "1px solid #cbd5e1", marginTop: 4 }}
                  />
                </label>
              </div>

              {/* Meeting Length / Duration Presets */}
              <div style={{ marginBottom: 14 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: "#334155", display: "block", marginBottom: 6 }}>
                  Meeting Length / Slot Duration: <strong style={{ color: "var(--red)" }}>{editDuration === 60 ? "1 hour (60 mins)" : `${editDuration} mins`}</strong>
                </label>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                  {[15, 30, 45, 60].map((m) => {
                    const isSel = editDuration === m;
                    return (
                      <button
                        key={m}
                        type="button"
                        onClick={() => setEditDuration(m)}
                        style={{
                          padding: "6px 14px",
                          borderRadius: 6,
                          fontSize: 12,
                          fontWeight: 700,
                          cursor: "pointer",
                          border: `1px solid ${isSel ? "var(--red)" : "#cbd5e1"}`,
                          background: isSel ? "var(--red)" : "#ffffff",
                          color: isSel ? "#ffffff" : "#334155",
                          boxShadow: isSel ? "0 2px 4px rgba(220,38,38,0.2)" : "none",
                          transition: "all 0.15s ease",
                        }}
                      >
                        {m === 60 ? "1 hour (60 mins)" : `${m} mins`}
                      </button>
                    );
                  })}
                  <div style={{ display: "flex", alignItems: "center", gap: 4, marginLeft: 6 }}>
                    <span style={{ fontSize: 11, color: "var(--muted)" }}>or custom:</span>
                    <input
                      type="number"
                      min={10}
                      max={240}
                      value={editDuration}
                      onChange={(e) => setEditDuration(Number(e.target.value))}
                      style={{ width: 68, padding: "5px 8px", borderRadius: 6, border: "1px solid #cbd5e1", fontSize: 12 }}
                    />
                    <span style={{ fontSize: 11, color: "var(--muted)" }}>mins</span>
                  </div>
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 12, marginBottom: 14 }}>
                <label style={{ fontSize: 12, fontWeight: 600 }}>
                  Buffer Before (m)
                  <input
                    type="number"
                    min={0}
                    max={60}
                    value={editBufferBefore}
                    onChange={(e) => setEditBufferBefore(Number(e.target.value))}
                    style={{ width: "100%", padding: "6px 8px", borderRadius: 6, border: "1px solid #cbd5e1", marginTop: 4 }}
                  />
                </label>
                <label style={{ fontSize: 12, fontWeight: 600 }}>
                  Buffer After (m)
                  <input
                    type="number"
                    min={0}
                    max={60}
                    value={editBufferAfter}
                    onChange={(e) => setEditBufferAfter(Number(e.target.value))}
                    style={{ width: "100%", padding: "6px 8px", borderRadius: 6, border: "1px solid #cbd5e1", marginTop: 4 }}
                  />
                </label>
                <label style={{ fontSize: 12, fontWeight: 600 }}>
                  Min Notice (mins)
                  <input
                    type="number"
                    min={0}
                    max={1440}
                    value={editNotice}
                    onChange={(e) => setEditNotice(Number(e.target.value))}
                    style={{ width: "100%", padding: "6px 8px", borderRadius: 6, border: "1px solid #cbd5e1", marginTop: 4 }}
                  />
                </label>
                <label style={{ fontSize: 12, fontWeight: 600 }}>
                  Horizon (days)
                  <input
                    type="number"
                    min={1}
                    max={90}
                    value={editHorizon}
                    onChange={(e) => setEditHorizon(Number(e.target.value))}
                    style={{ width: "100%", padding: "6px 8px", borderRadius: 6, border: "1px solid #cbd5e1", marginTop: 4 }}
                  />
                </label>
              </div>

              {/* Weekday Working Hours Editor */}
              <div style={{ marginBottom: 20 }}>
                <label style={{ fontSize: 13, fontWeight: 600, display: "block", marginBottom: 8 }}>
                  Working Hours by Day
                </label>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 10 }}>
                  {editAvailabilities.map((av, idx) => (
                    <div key={av.weekday} style={{ background: "#fff", padding: "8px 10px", borderRadius: 6, border: "1px solid #cbd5e1" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                        <span style={{ fontSize: 12, fontWeight: 700 }}>{WEEKDAY_NAMES[av.weekday]}</span>
                        <input
                          type="checkbox"
                          checked={av.is_enabled}
                          onChange={(e) => {
                            const updated = [...editAvailabilities];
                            updated[idx].is_enabled = e.target.checked;
                            setEditAvailabilities(updated);
                          }}
                        />
                      </div>
                      {av.is_enabled && (
                        <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                          <input
                            type="time"
                            value={av.start_time}
                            onChange={(e) => {
                              const updated = [...editAvailabilities];
                              updated[idx].start_time = e.target.value;
                              setEditAvailabilities(updated);
                            }}
                            style={{ fontSize: 11, padding: "2px 4px" }}
                          />
                          <span style={{ fontSize: 10 }}>to</span>
                          <input
                            type="time"
                            value={av.end_time}
                            onChange={(e) => {
                              const updated = [...editAvailabilities];
                              updated[idx].end_time = e.target.value;
                              setEditAvailabilities(updated);
                            }}
                            style={{ fontSize: 11, padding: "2px 4px" }}
                          />
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              <div style={{ display: "flex", gap: 10 }}>
                <button type="submit" disabled={saving} style={{ fontSize: 13, padding: "8px 18px" }}>
                  {saving ? "Saving…" : "Save Changes"}
                </button>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setIsEditing(false)}
                  style={{ fontSize: 13, padding: "8px 14px" }}
                >
                  Cancel
                </button>
              </div>
            </form>
          )}
        </div>
      )}

      {/* Tab 2: Customer Bookings Table */}
      {activeTab === "bookings" && (
        <div>
          {bookings.length === 0 ? (
            <div style={{ padding: "32px 16px", textAlign: "center", color: "var(--muted)", background: "#f8fafc", borderRadius: 10 }}>
              <p style={{ margin: 0, fontSize: 14 }}>No public customer bookings yet.</p>
              <small style={{ display: "block", marginTop: 4 }}>
                Share your public link ({publicBookingUrl}) with prospects to receive bookings.
              </small>
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: "2px solid #e2e8f0", textAlign: "left", color: "var(--muted)" }}>
                    <th style={{ padding: "10px 12px" }}>Customer</th>
                    <th style={{ padding: "10px 12px" }}>Company</th>
                    <th style={{ padding: "10px 12px" }}>Scheduled Time</th>
                    <th style={{ padding: "10px 12px" }}>Status</th>
                    <th style={{ padding: "10px 12px" }}>Google Meet</th>
                  </tr>
                </thead>
                <tbody>
                  {bookings.map((b) => (
                    <tr key={b.id} style={{ borderBottom: "1px solid #f1f5f9" }}>
                      <td style={{ padding: "12px 12px" }}>
                        <strong>{b.customer_name}</strong>
                        <small style={{ display: "block", color: "var(--muted)" }}>{b.customer_email}</small>
                      </td>
                      <td style={{ padding: "12px 12px" }}>{b.customer_company || "N/A"}</td>
                      <td style={{ padding: "12px 12px" }}>
                        <strong>{formatDateTimeLong(b.start_time)}</strong>
                        <small style={{ display: "block", color: "var(--muted)" }}>{b.timezone}</small>
                      </td>
                      <td style={{ padding: "12px 12px" }}>
                        <span
                          className="badge"
                          style={{
                            background: b.status === "confirmed" ? "#ecfdf5" : "#fee2e2",
                            color: b.status === "confirmed" ? "#059669" : "#dc2626",
                            border: `1px solid ${b.status === "confirmed" ? "#a7f3d0" : "#fecaca"}`,
                            textTransform: "capitalize",
                          }}
                        >
                          {b.status}
                        </span>
                      </td>
                      <td style={{ padding: "12px 12px" }}>
                        {b.google_meet_uri ? (
                          <a
                            href={b.google_meet_uri}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ color: "#059669", fontWeight: 600, display: "inline-flex", alignItems: "center", gap: 4 }}
                          >
                            <span>📹</span> Join Meet
                          </a>
                        ) : (
                          <span style={{ color: "var(--muted)" }}>—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
