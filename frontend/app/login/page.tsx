"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useAuth } from "../../lib/auth-context";

export default function LoginPage() {
  const { login, isLoading } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!email || !password) {
      setError("Please fill in both email and password.");
      return;
    }
    try {
      await login(email, password);
    } catch (err: any) {
      setError(err.message || "Failed to log in. Please check your credentials.");
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
            Welcome to Solwer GTM
          </h1>
          <p style={{ fontSize: 14, color: "var(--text-secondary, #64748b)", margin: 0 }}>
            Sign in to your sales intelligence & lead workspace
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
            gap: 8,
          }}>
            <span>⚠️</span>
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <div>
            <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "var(--text-primary, #1e293b)", marginBottom: 6 }}>
              Work Email Address
            </label>
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="name@company.com"
              style={{
                width: "100%",
                padding: "10px 14px",
                border: "1px solid var(--border-color, #cbd5e1)",
                borderRadius: 8,
                fontSize: 14,
                color: "var(--text-primary, #0f172a)",
                outline: "none",
                background: "#f8fafc",
                boxSizing: "border-box",
              }}
            />
          </div>

          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
              <label style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary, #1e293b)", margin: 0 }}>
                Password
              </label>
              <Link href="/forgot-password" style={{ fontSize: 12, color: "#6366f1", textDecoration: "none", fontWeight: 500 }}>
                Forgot password?
              </Link>
            </div>
            <div style={{ position: "relative" }}>
              <input
                type={showPassword ? "text" : "password"}
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                style={{
                  width: "100%",
                  padding: "10px 38px 10px 14px",
                  border: "1px solid var(--border-color, #cbd5e1)",
                  borderRadius: 8,
                  fontSize: 14,
                  color: "var(--text-primary, #0f172a)",
                  outline: "none",
                  background: "#f8fafc",
                  boxSizing: "border-box",
                }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                style={{
                  position: "absolute",
                  right: 10,
                  top: "50%",
                  transform: "translateY(-50%)",
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  color: "#64748b",
                  fontSize: 13,
                  padding: 4,
                }}
              >
                {showPassword ? "Hide" : "Show"}
              </button>
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
              marginTop: 4,
            }}
          >
            {isLoading ? "Signing in..." : "Sign in to Platform"}
          </button>
        </form>

        <div style={{ marginTop: 28, textAlign: "center", borderTop: "1px solid #f1f5f9", paddingTop: 20 }}>
          <p style={{ fontSize: 13, color: "#64748b", margin: 0 }}>
            Don't have an account?{" "}
            <Link href="/register" style={{ color: "#4f46e5", fontWeight: 600, textDecoration: "none" }}>
              Start your organization
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
