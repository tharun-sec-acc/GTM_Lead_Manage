"use client";

import React, { useEffect, useState, use } from "react";
import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface BookingDetails {
  id: string;
  customer_name: string;
  customer_email: string;
  customer_company: string | null;
  meeting_title: string;
  meeting_description: string | null;
  start_time: string;
  end_time: string;
  timezone: string;
  google_meet_uri: string | null;
  status: string;
  created_at: string;
  management_token?: string;
}

interface SlotItem {
  start: string;
  end: string;
  utc_start: string;
  utc_end: string;
}

export default function BookingManagePage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = use(params);

  const [booking, setBooking] = useState<BookingDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [activeTab, setActiveTab] = useState<"view" | "reschedule" | "cancel">("view");

  // Reschedule state
  const [rescheduleDate, setRescheduleDate] = useState("");
  const [rescheduleSlots, setRescheduleSlots] = useState<SlotItem[]>([]);
  const [loadingReschedSlots, setLoadingReschedSlots] = useState(false);
  const [selectedNewSlot, setSelectedNewSlot] = useState<SlotItem | null>(null);
  const [rescheduleReason, setRescheduleReason] = useState("");
  const [rescheduling, setRescheduling] = useState(false);
  const [rescheduleError, setRescheduleError] = useState("");
  const [rescheduleSuccess, setRescheduleSuccess] = useState(false);

  // Cancel state
  const [cancelReason, setCancelReason] = useState("");
  const [cancelling, setCancelling] = useState(false);
  const [cancelError, setCancelError] = useState("");

  // Load Booking Details
  useEffect(() => {
    let isMounted = true;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const res = await fetch(`${API_BASE}/api/public/bookings/${token}`);
        if (!res.ok) {
          const body = await res.json().catch(() => null);
          throw new Error(body?.detail || "Booking not found or link has expired.");
        }
        const data = await res.json();
        if (isMounted) {
          setBooking(data);
          const nextDay = new Date();
          nextDay.setDate(nextDay.getDate() + 1);
          setRescheduleDate(nextDay.toISOString().split("T")[0]);
        }
      } catch (err) {
        if (isMounted) setError(err instanceof Error ? err.message : "Failed to load booking.");
      } finally {
        if (isMounted) setLoading(false);
      }
    }
    load();
    return () => {
      isMounted = false;
    };
  }, [token]);

  // Load slots for rescheduling
  useEffect(() => {
    if (activeTab !== "reschedule" || !rescheduleDate || !booking) return;

    let isMounted = true;
    async function loadSlots() {
      setLoadingReschedSlots(true);
      setRescheduleError("");
      try {
        const start = `${rescheduleDate}T00:00:00`;
        const end = `${rescheduleDate}T23:59:59`;
        // Use default slug or profile slug
        const slug = "denso-discovery";
        const url = `${API_BASE}/api/public/book/${slug}/availability?start=${encodeURIComponent(
          start
        )}&end=${encodeURIComponent(end)}&timezone=${encodeURIComponent(booking?.timezone || "UTC")}`;

        const res = await fetch(url);
        if (!res.ok) {
          throw new Error("Could not fetch available slots for rescheduling.");
        }
        const data = await res.json();
        if (isMounted) {
          setRescheduleSlots(data.slots || []);
        }
      } catch (err) {
        if (isMounted) {
          setRescheduleError(err instanceof Error ? err.message : "Failed to load slots.");
        }
      } finally {
        if (isMounted) setLoadingReschedSlots(false);
      }
    }
    loadSlots();
    return () => {
      isMounted = false;
    };
  }, [activeTab, rescheduleDate, booking]);

  async function handleReschedule(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedNewSlot) {
      setRescheduleError("Please select a new time slot.");
      return;
    }

    setRescheduling(true);
    setRescheduleError("");

    try {
      const res = await fetch(`${API_BASE}/api/public/bookings/${token}/reschedule`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          new_start_time: selectedNewSlot.utc_start,
          new_end_time: selectedNewSlot.utc_end,
          timezone: booking?.timezone || "UTC",
          reason: rescheduleReason || null,
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || "Could not reschedule booking.");
      }

      const updated = await res.json();
      setBooking(updated);
      setRescheduleSuccess(true);
      setActiveTab("view");
    } catch (err) {
      setRescheduleError(err instanceof Error ? err.message : "Reschedule failed.");
    } finally {
      setRescheduling(false);
    }
  }

  async function handleCancel(e: React.FormEvent) {
    e.preventDefault();
    setCancelling(true);
    setCancelError("");

    try {
      const res = await fetch(`${API_BASE}/api/public/bookings/${token}/cancel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reason: cancelReason || null,
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || "Could not cancel booking.");
      }

      const updated = await res.json();
      setBooking(updated);
      setActiveTab("view");
    } catch (err) {
      setCancelError(err instanceof Error ? err.message : "Cancellation failed.");
    } finally {
      setCancelling(false);
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

  function formatTime(isoStr: string) {
    try {
      const d = new Date(isoStr);
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch {
      return isoStr;
    }
  }

  if (loading) {
    return (
      <div style={{ maxWidth: 640, margin: "60px auto", textAlign: "center", color: "var(--muted)" }}>
        Loading appointment details…
      </div>
    );
  }

  if (error || !booking) {
    return (
      <div style={{ maxWidth: 600, margin: "60px auto", padding: 32, background: "#fff", borderRadius: 12, border: "1px solid var(--border)", textAlign: "center" }}>
        <h2 style={{ color: "var(--red)", marginTop: 0 }}>Appointment Not Found</h2>
        <p style={{ color: "var(--muted)" }}>{error || "The appointment link is invalid or has expired."}</p>
        <Link href="/" className="button-link secondary" style={{ marginTop: 14 }}>
          Return to DENSO Prospecting
        </Link>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 720, margin: "40px auto", padding: "0 20px" }}>
      {/* Brand Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div>
          <span style={{ fontSize: 12, fontWeight: 700, color: "var(--red)", letterSpacing: "1.5px", textTransform: "uppercase" }}>
            DENSO Solutions
          </span>
          <h1 style={{ margin: "2px 0 0", fontSize: 24, color: "#0f172a" }}>Manage Appointment</h1>
        </div>
        <div>
          <span
            className="badge"
            style={{
              background: booking.status === "confirmed" ? "#ecfdf5" : "#fee2e2",
              color: booking.status === "confirmed" ? "#059669" : "#dc2626",
              border: `1px solid ${booking.status === "confirmed" ? "#a7f3d0" : "#fecaca"}`,
              textTransform: "capitalize",
            }}
          >
            ● {booking.status}
          </span>
        </div>
      </div>

      {rescheduleSuccess && (
        <div style={{ background: "#ecfdf5", border: "1px solid #10b981", color: "#065f46", padding: "12px 16px", borderRadius: 8, marginBottom: 20 }}>
          ✓ Your appointment has been successfully rescheduled to the new time.
        </div>
      )}

      {/* Appointment Overview Card */}
      <div style={{ background: "#fff", borderRadius: 14, border: "1px solid var(--border)", padding: 24, marginBottom: 24, boxShadow: "var(--shadow-sm)" }}>
        <h2 style={{ margin: "0 0 16px", fontSize: 18, color: "#1e293b" }}>{booking.meeting_title}</h2>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, fontSize: 14, marginBottom: 20 }}>
          <div>
            <span style={{ fontSize: 12, color: "var(--muted)", display: "block" }}>Scheduled Time</span>
            <strong style={{ fontSize: 15, color: booking.status === "cancelled" ? "var(--muted)" : "#0f172a" }}>
              {formatDateTimeLong(booking.start_time)}
            </strong>
            <small style={{ display: "block", color: "var(--muted)" }}>Timezone: {booking.timezone}</small>
          </div>
          <div>
            <span style={{ fontSize: 12, color: "var(--muted)", display: "block" }}>Participant</span>
            <strong>{booking.customer_name}</strong>
            <small style={{ display: "block", color: "var(--muted)" }}>{booking.customer_email}</small>
          </div>
        </div>

        {booking.status === "confirmed" && booking.google_meet_uri && (
          <div style={{ paddingTop: 16, borderTop: "1px solid #f1f5f9", display: "flex", alignItems: "center", gap: 12 }}>
            <a
              href={booking.google_meet_uri}
              target="_blank"
              rel="noopener noreferrer"
              className="button-link"
              style={{ background: "#059669", color: "#fff", display: "inline-flex", alignItems: "center", gap: 6 }}
            >
              <span>📹</span> Join Google Meet
            </a>
            <small style={{ color: "var(--muted)" }}>Google Calendar event updated automatically</small>
          </div>
        )}
      </div>

      {/* Action Options (only if confirmed) */}
      {booking.status === "confirmed" && (
        <div>
          {activeTab === "view" && (
            <div style={{ display: "flex", gap: 12 }}>
              <button
                type="button"
                className="secondary"
                onClick={() => setActiveTab("reschedule")}
                style={{ flex: 1, padding: "12px 18px", fontSize: 14 }}
              >
                🗓 Reschedule Appointment
              </button>
              <button
                type="button"
                className="secondary"
                onClick={() => setActiveTab("cancel")}
                style={{ flex: 1, padding: "12px 18px", fontSize: 14, color: "#dc2626", borderColor: "#fecaca" }}
              >
                ✕ Cancel Appointment
              </button>
            </div>
          )}

          {/* Reschedule Panel */}
          {activeTab === "reschedule" && (
            <div style={{ background: "#fff", borderRadius: 14, border: "1px solid var(--border)", padding: 24, boxShadow: "var(--shadow-sm)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                <h3 style={{ margin: 0, fontSize: 17 }}>Choose New Time Slot</h3>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setActiveTab("view")}
                  style={{ fontSize: 12, padding: "4px 10px" }}
                >
                  Cancel
                </button>
              </div>

              {rescheduleError && (
                <div role="alert" className="alert" style={{ marginBottom: 14 }}>
                  {rescheduleError}
                </div>
              )}

              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#334155", marginBottom: 12 }}>
                New Date
                <input
                  type="date"
                  value={rescheduleDate}
                  min={new Date().toISOString().split("T")[0]}
                  onChange={(e) => setRescheduleDate(e.target.value)}
                  style={{ display: "block", width: "100%", padding: "8px 12px", borderRadius: 8, border: "1px solid #cbd5e1", marginTop: 4 }}
                />
              </label>

              {loadingReschedSlots && <p style={{ fontSize: 13, color: "var(--muted)" }}>Loading available slots…</p>}

              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))", gap: 8, marginBottom: 16 }}>
                {rescheduleSlots.map((slot) => {
                  const isSel = selectedNewSlot?.utc_start === slot.utc_start;
                  return (
                    <button
                      key={slot.utc_start}
                      type="button"
                      onClick={() => setSelectedNewSlot(slot)}
                      style={{
                        padding: "8px 10px",
                        fontSize: 13,
                        fontWeight: 600,
                        borderRadius: 6,
                        border: isSel ? "2px solid var(--red)" : "1px solid #cbd5e1",
                        background: isSel ? "var(--red-subtle)" : "#ffffff",
                        color: isSel ? "var(--red)" : "#1e293b",
                      }}
                    >
                      {formatTime(slot.start)}
                    </button>
                  );
                })}
              </div>

              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#334155", marginBottom: 16 }}>
                Reason for Rescheduling (Optional)
                <input
                  type="text"
                  value={rescheduleReason}
                  onChange={(e) => setRescheduleReason(e.target.value)}
                  placeholder="e.g. Schedule conflict"
                  style={{ display: "block", width: "100%", padding: "8px 12px", borderRadius: 8, border: "1px solid #cbd5e1", marginTop: 4 }}
                />
              </label>

              <button
                type="button"
                disabled={!selectedNewSlot || rescheduling}
                onClick={handleReschedule}
                style={{ width: "100%", padding: "10px 18px", fontSize: 14 }}
              >
                {rescheduling ? "Updating Calendar…" : "Confirm Reschedule"}
              </button>
            </div>
          )}

          {/* Cancel Panel */}
          {activeTab === "cancel" && (
            <div style={{ background: "#fff", borderRadius: 14, border: "1px solid #fecaca", padding: 24, boxShadow: "var(--shadow-sm)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                <h3 style={{ margin: 0, fontSize: 17, color: "#dc2626" }}>Cancel This Appointment?</h3>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setActiveTab("view")}
                  style={{ fontSize: 12, padding: "4px 10px" }}
                >
                  Back
                </button>
              </div>

              <p style={{ fontSize: 14, color: "#475569", margin: "0 0 16px" }}>
                Cancelling will remove this meeting from both Google Calendar and Microsoft Outlook, and free up the time slot.
              </p>

              {cancelError && (
                <div role="alert" className="alert" style={{ marginBottom: 14 }}>
                  {cancelError}
                </div>
              )}

              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#334155", marginBottom: 16 }}>
                Reason for Cancellation (Optional)
                <input
                  type="text"
                  value={cancelReason}
                  onChange={(e) => setCancelReason(e.target.value)}
                  placeholder="e.g. No longer needed"
                  style={{ display: "block", width: "100%", padding: "8px 12px", borderRadius: 8, border: "1px solid #cbd5e1", marginTop: 4 }}
                />
              </label>

              <button
                type="button"
                disabled={cancelling}
                onClick={handleCancel}
                style={{ width: "100%", padding: "10px 18px", fontSize: 14, background: "#dc2626" }}
              >
                {cancelling ? "Cancelling…" : "Yes, Cancel Appointment"}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
