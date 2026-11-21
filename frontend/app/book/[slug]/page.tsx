"use client";

import React, { useEffect, useState, use } from "react";
import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface PublicProfile {
  public_slug: string;
  display_name: string;
  description: string | null;
  company_name: string;
  meeting_title: string;
  meeting_description: string | null;
  duration_minutes: number;
  timezone: string;
  booking_horizon_days: number;
  minimum_notice_minutes: number;
}

interface SlotItem {
  start: string;
  end: string;
  utc_start: string;
  utc_end: string;
}

interface ConfirmedBooking {
  id: string;
  customer_name: string;
  customer_email: string;
  customer_company: string | null;
  meeting_title: string;
  start_time: string;
  end_time: string;
  timezone: string;
  google_meet_uri: string | null;
  status: string;
  management_token?: string;
  reschedule_url?: string;
  cancellation_url?: string;
}

const COMMON_TIMEZONES = [
  "Asia/Kolkata",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "Europe/London",
  "Europe/Berlin",
  "Europe/Paris",
  "Asia/Dubai",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Australia/Sydney",
  "UTC",
];

export default function PublicBookingPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);

  // Profile State
  const [profile, setProfile] = useState<PublicProfile | null>(null);
  const [loadingProfile, setLoadingProfile] = useState(true);
  const [profileError, setProfileError] = useState("");

  // Timezone & Date
  const [timezone, setTimezone] = useState("Asia/Kolkata");
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [selectedDuration, setSelectedDuration] = useState<number>(30);

  // Slots State
  const [slots, setSlots] = useState<SlotItem[]>([]);
  const [loadingSlots, setLoadingSlots] = useState(false);
  const [slotsError, setSlotsError] = useState("");
  const [selectedSlot, setSelectedSlot] = useState<SlotItem | null>(null);

  // Reservation State
  const [reservationToken, setReservationToken] = useState<string | null>(null);
  const [reservationExpiresAt, setReservationExpiresAt] = useState<Date | null>(null);
  const [secondsRemaining, setSecondsRemaining] = useState<number>(0);
  const [reserving, setReserving] = useState(false);
  const [reserveError, setReserveError] = useState("");

  // Customer Form State
  const [customerName, setCustomerName] = useState("");
  const [customerEmail, setCustomerEmail] = useState("");
  const [customerCompany, setCustomerCompany] = useState("");
  const [customerPhone, setCustomerPhone] = useState("");
  const [meetingPurpose, setMeetingPurpose] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [confirmError, setConfirmError] = useState("");

  // Confirmed Booking State
  const [confirmedBooking, setConfirmedBooking] = useState<ConfirmedBooking | null>(null);
  const [copiedLink, setCopiedLink] = useState(false);

  // Detect browser timezone on mount
  useEffect(() => {
    try {
      const detected = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (detected) setTimezone(detected);
    } catch {
      // fallback
    }
  }, []);

  // Fetch Public Profile
  useEffect(() => {
    let isMounted = true;
    async function load() {
      setLoadingProfile(true);
      setProfileError("");
      try {
        const res = await fetch(`${API_BASE}/api/public/book/${slug}`);
        if (!res.ok) {
          const body = await res.json().catch(() => null);
          throw new Error(body?.detail || `Booking page not found (${res.status})`);
        }
        const data = await res.json();
        if (isMounted) {
          setProfile(data);
          if (data.duration_minutes) {
            setSelectedDuration(data.duration_minutes);
          }
          // Set initial date to tomorrow or today
          const now = new Date();
          now.setDate(now.getDate() + 1);
          const initialDateStr = now.toISOString().split("T")[0];
          setSelectedDate(initialDateStr);
        }
      } catch (err) {
        if (isMounted) {
          setProfileError(err instanceof Error ? err.message : "Failed to load booking page.");
        }
      } finally {
        if (isMounted) setLoadingProfile(false);
      }
    }
    load();
    return () => {
      isMounted = false;
    };
  }, [slug]);

  // Fetch Available Slots when selectedDate or timezone changes
  useEffect(() => {
    if (!profile || !selectedDate) return;

    let isMounted = true;
    async function fetchSlots() {
      setLoadingSlots(true);
      setSlotsError("");
      setSelectedSlot(null);
      setReservationToken(null);
      setReservationExpiresAt(null);
      setReserveError("");

      try {
        // Query window: 3 days around selectedDate
        const start = `${selectedDate}T00:00:00`;
        const end = `${selectedDate}T23:59:59`;

        const url = `${API_BASE}/api/public/book/${slug}/availability?start=${encodeURIComponent(
          start
        )}&end=${encodeURIComponent(end)}&timezone=${encodeURIComponent(timezone)}&duration_minutes=${selectedDuration}`;

        const res = await fetch(url);
        if (!res.ok) {
          const body = await res.json().catch(() => null);
          throw new Error(body?.detail || `Could not fetch available slots (${res.status})`);
        }
        const data = await res.json();
        if (isMounted) {
          setSlots(data.slots || []);
        }
      } catch (err) {
        if (isMounted) {
          setSlotsError(err instanceof Error ? err.message : "Failed to fetch availability.");
          setSlots([]);
        }
      } finally {
        if (isMounted) setLoadingSlots(false);
      }
    }

    fetchSlots();
    return () => {
      isMounted = false;
    };
  }, [profile, selectedDate, timezone, selectedDuration, slug]);

  // Reservation hold countdown timer
  useEffect(() => {
    if (!reservationExpiresAt) {
      setSecondsRemaining(0);
      return;
    }

    const interval = setInterval(() => {
      const now = new Date().getTime();
      const expires = reservationExpiresAt.getTime();
      const diff = Math.max(0, Math.floor((expires - now) / 1000));
      setSecondsRemaining(diff);

      if (diff <= 0) {
        clearInterval(interval);
        setReservationToken(null);
        setReserveError("Your reservation hold has expired. Please select a slot again.");
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [reservationExpiresAt]);

  // Handle slot selection and temporary hold
  async function handleSelectSlot(slot: SlotItem) {
    setSelectedSlot(slot);
    setReserving(true);
    setReserveError("");
    setReservationToken(null);
    setReservationExpiresAt(null);

    try {
      const res = await fetch(`${API_BASE}/api/public/book/${slug}/reserve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          start_time: slot.utc_start,
          end_time: slot.utc_end,
          timezone: timezone,
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || "This slot is no longer available. Please pick another.");
      }

      const data = await res.json();
      setReservationToken(data.reservation_token);
      setReservationExpiresAt(new Date(data.expires_at));
    } catch (err) {
      setReserveError(err instanceof Error ? err.message : "Failed to reserve slot.");
      setSelectedSlot(null);
    } finally {
      setReserving(false);
    }
  }

  // Handle final booking confirmation
  async function handleConfirmBooking(e: React.FormEvent) {
    e.preventDefault();
    if (!reservationToken) {
      setConfirmError("Reservation hold expired. Please re-select your slot.");
      return;
    }

    setConfirming(true);
    setConfirmError("");

    try {
      const res = await fetch(`${API_BASE}/api/public/book/${slug}/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reservation_token: reservationToken,
          customer_name: customerName,
          customer_email: customerEmail,
          customer_company: customerCompany || null,
          customer_phone: customerPhone || null,
          meeting_purpose: meetingPurpose || null,
          timezone: timezone,
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || "Could not confirm booking. Please try again.");
      }

      const bookingData: ConfirmedBooking = await res.json();
      setConfirmedBooking(bookingData);
    } catch (err) {
      setConfirmError(err instanceof Error ? err.message : "Confirmation failed.");
    } finally {
      setConfirming(false);
    }
  }

  function formatTime(isoStr: string) {
    try {
      const d = new Date(isoStr);
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch {
      return isoStr;
    }
  }

  function formatDateTimeLong(isoStr: string) {
    try {
      const d = new Date(isoStr);
      return d.toLocaleString([], {
        weekday: "short",
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return isoStr;
    }
  }

  // Loading state
  if (loadingProfile) {
    return (
      <div style={{ maxWidth: 840, margin: "60px auto", padding: 24, textAlign: "center" }}>
        <p style={{ color: "var(--muted)" }}>Loading booking schedule…</p>
      </div>
    );
  }

  // Profile error / not found state
  if (profileError || !profile) {
    return (
      <div style={{ maxWidth: 640, margin: "60px auto", padding: 32, background: "#fff", borderRadius: 12, border: "1px solid var(--border)", textAlign: "center" }}>
        <h2 style={{ color: "var(--red)", marginTop: 0 }}>Booking Page Unavailable</h2>
        <p style={{ color: "var(--muted)" }}>{profileError || "This booking link does not exist or has been deactivated."}</p>
        <Link href="/" className="button-link secondary" style={{ marginTop: 16 }}>
          Return to DENSO Prospecting
        </Link>
      </div>
    );
  }

  // Success Confirmation Screen
  if (confirmedBooking) {
    return (
      <div style={{ maxWidth: 680, margin: "40px auto", padding: 36, background: "#fff", borderRadius: 16, border: "1px solid #cbd5e1", boxShadow: "0 10px 25px -5px rgba(0,0,0,0.05)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
          <div style={{ width: 44, height: 44, borderRadius: "50%", background: "#ecfdf5", border: "2px solid #10b981", display: "flex", alignItems: "center", justifyContent: "center", color: "#059669", fontSize: 22, fontWeight: "bold" }}>
            ✓
          </div>
          <div>
            <span style={{ fontSize: 12, fontWeight: 700, color: "var(--red)", letterSpacing: "1px", textTransform: "uppercase" }}>
              {profile.company_name} · Confirmed
            </span>
            <h1 style={{ margin: "2px 0 0", fontSize: 24, color: "#0f172a" }}>Meeting Confirmed</h1>
          </div>
        </div>

        <p style={{ color: "#475569", fontSize: 15, margin: "0 0 24px" }}>
          We have scheduled your appointment and dispatched a calendar invitation with the Google Meet link to{" "}
          <strong>{confirmedBooking.customer_email}</strong>.
        </p>

        <div style={{ background: "#f8fafc", borderRadius: 12, padding: 20, border: "1px solid #e2e8f0", marginBottom: 24 }}>
          <h3 style={{ margin: "0 0 12px", fontSize: 17, color: "#1e293b" }}>{confirmedBooking.meeting_title}</h3>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, fontSize: 14 }}>
            <div>
              <span style={{ fontSize: 12, color: "var(--muted)", display: "block" }}>Date & Time</span>
              <strong>{formatDateTimeLong(confirmedBooking.start_time)}</strong>
              <small style={{ display: "block", color: "var(--muted)" }}>Timezone: {confirmedBooking.timezone}</small>
            </div>
            <div>
              <span style={{ fontSize: 12, color: "var(--muted)", display: "block" }}>Participant</span>
              <strong>{confirmedBooking.customer_name}</strong>
              <small style={{ display: "block", color: "var(--muted)" }}>{confirmedBooking.customer_company || "N/A"}</small>
            </div>
          </div>

          {confirmedBooking.google_meet_uri && (
            <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid #e2e8f0" }}>
              <span style={{ fontSize: 12, color: "var(--muted)", display: "block", marginBottom: 6 }}>
                Video Conference
              </span>
              <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                <a
                  href={confirmedBooking.google_meet_uri}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="button-link"
                  style={{ background: "#059669", color: "#fff", display: "inline-flex", alignItems: "center", gap: 8 }}
                >
                  <span>📹</span> Join Google Meet
                </a>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => {
                    if (confirmedBooking.google_meet_uri) {
                      navigator.clipboard.writeText(confirmedBooking.google_meet_uri);
                      setCopiedLink(true);
                      setTimeout(() => setCopiedLink(false), 2000);
                    }
                  }}
                  style={{ fontSize: 13 }}
                >
                  {copiedLink ? "✓ Copied" : "Copy Meet Link"}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Self-service management links */}
        {confirmedBooking.management_token && (
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: 16, borderTop: "1px solid #f1f5f9" }}>
            <span style={{ fontSize: 13, color: "var(--muted)" }}>Need to make changes?</span>
            <div style={{ display: "flex", gap: 12 }}>
              <Link
                href={`/book/manage/${confirmedBooking.management_token}`}
                className="button-link secondary"
                style={{ fontSize: 13, padding: "6px 14px" }}
              >
                Reschedule or Cancel
              </Link>
            </div>
          </div>
        )}
      </div>
    );
  }

  // Interactive Booking View (Profile + Calendar + Slot Selection + Form)
  return (
    <div style={{ maxWidth: 1000, margin: "32px auto", padding: "0 20px" }}>
      {/* Brand Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div>
          <span style={{ fontSize: 12, fontWeight: 700, color: "var(--red)", letterSpacing: "1.5px", textTransform: "uppercase" }}>
            {profile.company_name} Solutions
          </span>
          <h1 style={{ margin: "2px 0 0", fontSize: 26, color: "#0f172a" }}>{profile.meeting_title}</h1>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span className="badge" style={{ background: "#f1f5f9", color: "#334155", border: "1px solid #cbd5e1" }}>
            ⏱ {selectedDuration === 60 ? "1 hour" : `${selectedDuration} mins`}
          </span>
          <span className="badge" style={{ background: "#ecfdf5", color: "#059669", border: "1px solid #a7f3d0" }}>
            Google Meet
          </span>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "360px 1fr", gap: 24, alignItems: "start" }}>
        {/* Left Column: Profile Card & Date Picker */}
        <div style={{ background: "#fff", borderRadius: 14, border: "1px solid var(--border)", padding: 24, boxShadow: "var(--shadow-sm)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
            <div style={{ width: 44, height: 44, borderRadius: "50%", background: "#fee2e2", color: "var(--red)", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: "bold", fontSize: 18 }}>
              D
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: 16 }}>{profile.display_name}</h3>
              <small style={{ color: "var(--muted)" }}>Industrial Solutions Team</small>
            </div>
          </div>

          {profile.description && (
            <p style={{ fontSize: 13, color: "#475569", margin: "0 0 20px", lineHeight: 1.5 }}>
              {profile.description}
            </p>
          )}

          <hr style={{ border: 0, borderTop: "1px solid #f1f5f9", margin: "16px 0" }} />

          {/* Date Picker */}
          <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#334155", marginBottom: 6 }}>
            Select Date
            <input
              type="date"
              value={selectedDate}
              min={new Date().toISOString().split("T")[0]}
              onChange={(e) => setSelectedDate(e.target.value)}
              style={{
                width: "100%",
                padding: "8px 12px",
                borderRadius: 8,
                border: "1px solid #cbd5e1",
                marginTop: 4,
                fontSize: 14,
              }}
            />
          </label>

          {/* Timezone Selector */}
          <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#334155", marginTop: 14 }}>
            Timezone
            <select
              value={timezone}
              onChange={(e) => setTimezone(e.target.value)}
              style={{
                width: "100%",
                padding: "8px 12px",
                borderRadius: 8,
                border: "1px solid #cbd5e1",
                marginTop: 4,
                fontSize: 13,
                background: "#fff",
              }}
            >
              {COMMON_TIMEZONES.map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </select>
          </label>
        </div>

        {/* Right Column: Time Slots & Reservation / Booking Form */}
        <div style={{ background: "#fff", borderRadius: 14, border: "1px solid var(--border)", padding: 24, boxShadow: "var(--shadow-sm)" }}>
          {/* Step 1: Slot Selection (if no active reservation) */}
          {!reservationToken ? (
            <div>
              {/* Meeting Length Selector */}
              <div style={{ marginBottom: 16, padding: "12px 14px", background: "#f8fafc", borderRadius: 10, border: "1px solid #e2e8f0" }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: "#475569", textTransform: "uppercase", letterSpacing: "0.5px", display: "block", marginBottom: 8 }}>
                  Meeting Length:
                </span>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {[15, 30, 45, 60].map((mins) => {
                    const isSelected = selectedDuration === mins;
                    return (
                      <button
                        key={mins}
                        type="button"
                        onClick={() => {
                          setSelectedDuration(mins);
                          setSelectedSlot(null);
                        }}
                        style={{
                          padding: "6px 14px",
                          borderRadius: 20,
                          fontSize: 12,
                          fontWeight: 700,
                          border: isSelected ? "2px solid var(--red)" : "1px solid #cbd5e1",
                          background: isSelected ? "#fee2e2" : "#ffffff",
                          color: isSelected ? "var(--red)" : "#334155",
                          cursor: "pointer",
                          transition: "all 0.15s ease",
                        }}
                      >
                        ⏱ {mins === 60 ? "1 hour" : `${mins} mins`}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
                <h3 style={{ margin: 0, fontSize: 17, color: "#1e293b" }}>
                  Available Times for {selectedDate ? new Date(selectedDate).toLocaleDateString([], { month: "short", day: "numeric", weekday: "short" }) : "Selected Date"}
                </h3>
                <span style={{ fontSize: 12, color: "var(--muted)" }}>
                  Aggregated Google & Outlook Free/Busy
                </span>
              </div>

              {loadingSlots && <p style={{ color: "var(--muted)", fontSize: 14 }}>Checking live calendar availability…</p>}

              {slotsError && (
                <div role="alert" className="alert" style={{ marginBottom: 16 }}>
                  {slotsError}
                </div>
              )}

              {reserveError && (
                <div role="alert" className="alert" style={{ marginBottom: 16 }}>
                  {reserveError}
                </div>
              )}

              {!loadingSlots && !slotsError && slots.length === 0 && (
                <div style={{ padding: "32px 16px", textAlign: "center", color: "var(--muted)", background: "#f8fafc", borderRadius: 10 }}>
                  <p style={{ margin: 0, fontSize: 14 }}>No free slots available on this date.</p>
                  <small style={{ display: "block", marginTop: 4 }}>Try selecting another date on the left.</small>
                </div>
              )}

              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))", gap: 10 }}>
                {slots.map((slot) => {
                  const isSelected = selectedSlot?.utc_start === slot.utc_start;
                  return (
                    <button
                      key={slot.utc_start}
                      type="button"
                      disabled={reserving}
                      onClick={() => handleSelectSlot(slot)}
                      style={{
                        padding: "10px 12px",
                        fontSize: 13,
                        fontWeight: 600,
                        borderRadius: 8,
                        border: isSelected ? "2px solid var(--red)" : "1px solid #cbd5e1",
                        background: isSelected ? "var(--red-subtle)" : "#ffffff",
                        color: isSelected ? "var(--red)" : "#1e293b",
                        cursor: "pointer",
                        display: "flex",
                        justifyContent: "center",
                        alignItems: "center",
                        transition: "all 0.15s ease",
                      }}
                    >
                      {formatTime(slot.start)}
                    </button>
                  );
                })}
              </div>

              {reserving && (
                <p style={{ fontSize: 13, color: "var(--muted)", marginTop: 12 }}>
                  Holding slot for 10 minutes…
                </p>
              )}
            </div>
          ) : (
            /* Step 2: Customer Contact Form with Active Reservation Hold */
            <div>
              {/* Hold Banner with Countdown */}
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  background: "#eff6ff",
                  border: "1px solid #bfdbfe",
                  borderRadius: 10,
                  padding: "10px 16px",
                  marginBottom: 20,
                }}
              >
                <div>
                  <span style={{ fontSize: 13, fontWeight: 600, color: "#1e40af" }}>
                    Slot reserved for you: {selectedSlot ? `${formatTime(selectedSlot.start)} – ${formatTime(selectedSlot.end)}` : ""}
                  </span>
                  <small style={{ display: "block", color: "#3b82f6" }}>
                    Complete form to finalize booking
                  </small>
                </div>
                <div style={{ textAlign: "right" }}>
                  <span style={{ fontSize: 12, color: "#1e40af", fontWeight: 700 }}>
                    Hold expires in:
                  </span>
                  <div style={{ fontSize: 16, fontWeight: "bold", color: secondsRemaining < 120 ? "#dc2626" : "#2563eb" }}>
                    {Math.floor(secondsRemaining / 60)}:{(secondsRemaining % 60).toString().padStart(2, "0")}
                  </div>
                </div>
              </div>

              {confirmError && (
                <div role="alert" className="alert" style={{ marginBottom: 16 }}>
                  {confirmError}
                </div>
              )}

              <form onSubmit={handleConfirmBooking}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 14 }}>
                  <label style={{ fontSize: 13, fontWeight: 600, color: "#334155" }}>
                    Full Name *
                    <input
                      type="text"
                      required
                      value={customerName}
                      onChange={(e) => setCustomerName(e.target.value)}
                      placeholder="e.g. Arun Kumar"
                      style={{
                        width: "100%",
                        padding: "8px 12px",
                        borderRadius: 8,
                        border: "1px solid #cbd5e1",
                        marginTop: 4,
                        fontSize: 14,
                      }}
                    />
                  </label>
                  <label style={{ fontSize: 13, fontWeight: 600, color: "#334155" }}>
                    Email Address *
                    <input
                      type="email"
                      required
                      value={customerEmail}
                      onChange={(e) => setCustomerEmail(e.target.value)}
                      placeholder="name@company.com"
                      style={{
                        width: "100%",
                        padding: "8px 12px",
                        borderRadius: 8,
                        border: "1px solid #cbd5e1",
                        marginTop: 4,
                        fontSize: 14,
                      }}
                    />
                  </label>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 14 }}>
                  <label style={{ fontSize: 13, fontWeight: 600, color: "#334155" }}>
                    Company Name
                    <input
                      type="text"
                      value={customerCompany}
                      onChange={(e) => setCustomerCompany(e.target.value)}
                      placeholder="e.g. VRL Logistics"
                      style={{
                        width: "100%",
                        padding: "8px 12px",
                        borderRadius: 8,
                        border: "1px solid #cbd5e1",
                        marginTop: 4,
                        fontSize: 14,
                      }}
                    />
                  </label>
                  <label style={{ fontSize: 13, fontWeight: 600, color: "#334155" }}>
                    Phone Number
                    <input
                      type="tel"
                      value={customerPhone}
                      onChange={(e) => setCustomerPhone(e.target.value)}
                      placeholder="+91 9876543210"
                      style={{
                        width: "100%",
                        padding: "8px 12px",
                        borderRadius: 8,
                        border: "1px solid #cbd5e1",
                        marginTop: 4,
                        fontSize: 14,
                      }}
                    />
                  </label>
                </div>

                <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#334155", marginBottom: 20 }}>
                  What would you like to discuss? (Optional)
                  <textarea
                    rows={3}
                    value={meetingPurpose}
                    onChange={(e) => setMeetingPurpose(e.target.value)}
                    placeholder="Briefly describe your objectives or questions regarding DENSO solutions."
                    style={{
                      width: "100%",
                      padding: "8px 12px",
                      borderRadius: 8,
                      border: "1px solid #cbd5e1",
                      marginTop: 4,
                      fontSize: 14,
                      fontFamily: "inherit",
                    }}
                  />
                </label>

                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => {
                      setReservationToken(null);
                      setReservationExpiresAt(null);
                    }}
                    style={{ fontSize: 13 }}
                  >
                    ← Choose Different Time
                  </button>
                  <button
                    type="submit"
                    disabled={confirming || !customerName || !customerEmail}
                    style={{ fontSize: 14, padding: "10px 24px" }}
                  >
                    {confirming ? "Confirming Booking…" : "Confirm Booking"}
                  </button>
                </div>
              </form>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
