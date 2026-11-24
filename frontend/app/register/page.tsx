"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useAuth } from "../../lib/auth-context";

export default function RegisterPage() {
  const { register, isLoading } = useAuth();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [orgName, setOrgName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!fullName || !email || !password) {
      setError("Please fill in all required fields.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters long.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    try {
      await register({
        full_name: fullName,
        email,
        organization_name: orgName.trim() || undefined,
        password,
      });
    } catch (err: any) {
      setError(err.message || "Failed to create account. Please try again.");
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
        maxWidth: 480,
        background: "var(--card-bg, #ffffff)",
        border: "1px solid var(--border-color, #e2e8f0)",
        borderRadius: 16,
        padding: "36px 32px",
        boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.05), 0 8px 10px -6px rgba(0, 0, 0, 0.01)",
      }}>
        <div style={{ textAlign: "center", marginBottom: 28 }}>
          <div style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            width: 48,
            height: 48,
            borderRadius: 12,
            background: "#0f172a",
            marginBottom: 16,
          }}>
            <svg width="28" height="28" viewBox="0 0 34 34" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M17 6L26.5 11.5V22.5L17 28L7.5 22.5V11.5L17 6Z" stroke="#6366f1" strokeWidth="2.5" strokeLinejoin="round" fill="rgba(99, 102, 241, 0.2)" />
              <circle cx="17" cy="17" r="3" fill="#e11d48" />
            </svg>
          </div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: "var(--text-primary, #0f172a)", margin: "0 0 6px 0" }}>
            Start with Solwer GTM
          </h1>
          <p style={{ fontSize: 14, color: "var(--text-secondary, #64748b)", margin: 0 }}>
            Create your multi-tenant sales intelligence organization
          </p>
        </div>

        {error && (
          <div style={{
            background: "#fef2f2",
            border: "1px solid #fecaca",
            color: "#b91c1c",
            padding: "10px 14px",
            borderRadius: 8,
            fontSize: 13,
            marginBottom: 20,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: 8,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span>⚠️</span>
              <span>{error}</span>
            </div>
            {error.toLowerCase().includes("already exists") && (
              <Link href="/login" style={{ color: "#4f46e5", fontWeight: 700, textDecoration: "underline", fontSize: 13 }}>
                Sign in here →
              </Link>
            )}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div>
            <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "var(--text-primary, #1e293b)", marginBottom: 6 }}>
              Full Name *
            </label>
            <input
              type="text"
              required
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="e.g. Sarah Connor"
              style={{
                width: "100%",
                padding: "10px 14px",
                border: "1px solid var(--border-color, #cbd5e1)",
                borderRadius: 8,
                fontSize: 14,
                outline: "none",
                background: "#f8fafc",
                boxSizing: "border-box",
              }}
            />
          </div>

          <div>
            <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "var(--text-primary, #1e293b)", marginBottom: 6 }}>
              Business Email Address *
            </label>
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="s.connor@cyberdyne.com"
              style={{
                width: "100%",
                padding: "10px 14px",
                border: "1px solid var(--border-color, #cbd5e1)",
                borderRadius: 8,
                fontSize: 14,
                outline: "none",
                background: "#f8fafc",
                boxSizing: "border-box",
              }}
            />
          </div>

          <div>
            <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "var(--text-primary, #1e293b)", marginBottom: 6 }}>
              Organization / Company Name
            </label>
            <input
              type="text"
              value={orgName}
              onChange={(e) => setOrgName(e.target.value)}
              placeholder="e.g. Cyberdyne Systems"
              style={{
                width: "100%",
                padding: "10px 14px",
                border: "1px solid var(--border-color, #cbd5e1)",
                borderRadius: 8,
                fontSize: 14,
                outline: "none",
                background: "#f8fafc",
                boxSizing: "border-box",
              }}
            />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "var(--text-primary, #1e293b)", marginBottom: 6 }}>
                Password *
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
                  border: "1px solid var(--border-color, #cbd5e1)",
                  borderRadius: 8,
                  fontSize: 14,
                  outline: "none",
                  background: "#f8fafc",
                  boxSizing: "border-box",
                }}
              />
            </div>
            <div>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "var(--text-primary, #1e293b)", marginBottom: 6 }}>
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
                  border: "1px solid var(--border-color, #cbd5e1)",
                  borderRadius: 8,
                  fontSize: 14,
                  outline: "none",
                  background: "#f8fafc",
                  boxSizing: "border-box",
                }}
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isLoading}
            style={{
              width: "100%",
              padding: "11px 16px",
              background: isLoading ? "#94a3b8" : "linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)",
              color: "#ffffff",
              border: "none",
              borderRadius: 8,
              fontSize: 14,
              fontWeight: 600,
              cursor: isLoading ? "not-allowed" : "pointer",
              boxShadow: "0 2px 4px rgba(79, 70, 229, 0.2)",
              transition: "all 0.2s ease",
              marginTop: 8,
            }}
          >
            {isLoading ? "Setting up workspace..." : "Create Organization & Account"}
          </button>
        </form>

        <div style={{ marginTop: 24, textAlign: "center", borderTop: "1px solid #f1f5f9", paddingTop: 18 }}>
          <p style={{ fontSize: 13, color: "#64748b", margin: 0 }}>
            Already have an account?{" "}
            <Link href="/login" style={{ color: "#4f46e5", fontWeight: 600, textDecoration: "none" }}>
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
