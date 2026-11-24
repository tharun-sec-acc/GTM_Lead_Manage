"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { getApiBase } from "../../../lib/api-config";

const API_BASE = getApiBase();

export default function AcceptInvitationPage() {
  const params = useParams();
  const router = useRouter();
  const token = (params?.token as string) || "";

  const [loading, setLoading] = useState(true);
  const [inviteData, setInviteData] = useState<{ email: string; role: string; organization_name: string } | null>(null);
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!token) return;
    const checkInvite = async () => {
      try {
        const res = await fetch(`${API_BASE}/public/invitations/${token}`);
        if (!res.ok) {
          throw new Error("This invitation link has expired or is invalid.");
        }
        const data = await res.json();
        setInviteData(data);
      } catch (err: any) {
        setError(err.message || "Failed to load invitation.");
      } finally {
        setLoading(false);
      }
    };
    checkInvite();
  }, [token]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!fullName || !password) {
      setError("Please fill in your name and choose a password.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/public/invitations/accept`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token,
          full_name: fullName,
          password,
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Failed to accept invitation." }));
        throw new Error(err.detail || "Failed to accept invitation.");
      }

      router.push("/login?accepted=true");
    } catch (err: any) {
      setError(err.message || "Failed to accept invitation.");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: "100px 20px" }}>
        <p style={{ color: "#64748b" }}>Verifying your invitation...</p>
      </div>
    );
  }

  return (
    <div style={{
      minHeight: "85vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: "24px 16px",
    }}>
      <div style={{
        width: "100%",
        maxWidth: 460,
        background: "var(--card-bg, #ffffff)",
        border: "1px solid var(--border-color, #e2e8f0)",
        borderRadius: 16,
        padding: "36px 32px",
        boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.05)",
      }}>
        <div style={{ textAlign: "center", marginBottom: 24 }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>🤝</div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: "#0f172a", margin: "0 0 6px 0" }}>
            Join {inviteData?.organization_name || "Team"}
          </h1>
          <p style={{ fontSize: 13, color: "#64748b", margin: 0 }}>
            You've been invited as a <strong>{inviteData?.role.toUpperCase()}</strong> to join the sales intelligence workspace.
          </p>
        </div>

        {error && (
          <div style={{ background: "#fef2f2", color: "#b91c1c", padding: "10px 14px", borderRadius: 8, fontSize: 13, marginBottom: 16 }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div>
            <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#1e293b", marginBottom: 6 }}>
              Email Address
            </label>
            <input
              type="email"
              disabled
              value={inviteData?.email || ""}
              style={{
                width: "100%",
                padding: "10px 14px",
                border: "1px solid #e2e8f0",
                borderRadius: 8,
                fontSize: 14,
                color: "#64748b",
                background: "#f1f5f9",
                boxSizing: "border-box",
              }}
            />
          </div>

          <div>
            <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#1e293b", marginBottom: 6 }}>
              Your Full Name *
            </label>
            <input
              type="text"
              required
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="e.g. Alex Mercer"
              style={{
                width: "100%",
                padding: "10px 14px",
                border: "1px solid #cbd5e1",
                borderRadius: 8,
                fontSize: 14,
                outline: "none",
                background: "#f8fafc",
                boxSizing: "border-box",
              }}
            />
          </div>

          <div>
            <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#1e293b", marginBottom: 6 }}>
              Create Password *
            </label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Min 8 characters"
              style={{
                width: "100%",
                padding: "10px 14px",
                border: "1px solid #cbd5e1",
                borderRadius: 8,
                fontSize: 14,
                outline: "none",
                background: "#f8fafc",
                boxSizing: "border-box",
              }}
            />
          </div>

          <div>
            <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#1e293b", marginBottom: 6 }}>
              Confirm Password *
            </label>
            <input
              type="password"
              required
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Repeat password"
              style={{
                width: "100%",
                padding: "10px 14px",
                border: "1px solid #cbd5e1",
                borderRadius: 8,
                fontSize: 14,
                outline: "none",
                background: "#f8fafc",
                boxSizing: "border-box",
              }}
            />
          </div>

          <button
            type="submit"
            disabled={submitting}
            style={{
              width: "100%",
              padding: "11px 16px",
              background: submitting ? "#94a3b8" : "#4f46e5",
              color: "#ffffff",
              border: "none",
              borderRadius: 8,
              fontSize: 14,
              fontWeight: 600,
              cursor: submitting ? "not-allowed" : "pointer",
            }}
          >
            {submitting ? "Joining..." : "Accept Invitation & Activate Account"}
          </button>
        </form>
      </div>
    </div>
  );
}
