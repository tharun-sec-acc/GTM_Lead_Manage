"use client";

import React, { useState } from "react";
import Link from "next/link";
import { getApiBase } from "../../lib/api-config";

const API_BASE = getApiBase();

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [resetToken, setResetToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/auth/forgot-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await res.json();
      setSubmitted(true);
      if (data.reset_token) {
        setResetToken(data.reset_token);
      }
    } catch {
      setError("Failed to request password reset. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

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
        maxWidth: 440,
        background: "var(--card-bg, #ffffff)",
        border: "1px solid var(--border-color, #e2e8f0)",
        borderRadius: 16,
        padding: "36px 32px",
        boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.05)",
      }}>
        <div style={{ textAlign: "center", marginBottom: 24 }}>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: "#0f172a", margin: "0 0 6px 0" }}>
            Reset Your Password
          </h1>
          <p style={{ fontSize: 13, color: "#64748b", margin: 0 }}>
            Enter your work email address and we'll send you recovery instructions.
          </p>
        </div>

        {error && (
          <div style={{ background: "#fef2f2", color: "#b91c1c", padding: "10px 14px", borderRadius: 8, fontSize: 13, marginBottom: 16 }}>
            {error}
          </div>
        )}

        {submitted ? (
          <div style={{ textAlign: "center", padding: "12px 0" }}>
            <div style={{ fontSize: 40, marginBottom: 12 }}>✉️</div>
            <p style={{ fontSize: 14, color: "#334155", lineHeight: 1.5 }}>
              If an account with <strong>{email}</strong> exists, instructions have been generated.
            </p>
            {resetToken && (
              <div style={{ marginTop: 16, padding: 12, background: "#f0fdf4", borderRadius: 8, border: "1px solid #bbf7d0" }}>
                <p style={{ fontSize: 12, color: "#166534", margin: "0 0 6px 0", fontWeight: 600 }}>Development Mode Link:</p>
                <Link
                  href={`/reset-password?token=${resetToken}`}
                  style={{ fontSize: 13, color: "#15803d", wordBreak: "break-all", fontWeight: 500 }}
                >
                  Click here to complete password reset
                </Link>
              </div>
            )}
            <div style={{ marginTop: 24 }}>
              <Link href="/login" style={{ fontSize: 13, color: "#4f46e5", fontWeight: 600, textDecoration: "none" }}>
                ← Return to Sign in
              </Link>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#1e293b", marginBottom: 6 }}>
                Email Address
              </label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@company.com"
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
              disabled={isLoading}
              style={{
                width: "100%",
                padding: "11px 16px",
                background: isLoading ? "#94a3b8" : "#4f46e5",
                color: "#ffffff",
                border: "none",
                borderRadius: 8,
                fontSize: 14,
                fontWeight: 600,
                cursor: isLoading ? "not-allowed" : "pointer",
              }}
            >
              {isLoading ? "Sending..." : "Send Reset Instructions"}
            </button>
            <div style={{ textAlign: "center", marginTop: 8 }}>
              <Link href="/login" style={{ fontSize: 13, color: "#64748b", textDecoration: "none" }}>
                Cancel and return to login
              </Link>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
