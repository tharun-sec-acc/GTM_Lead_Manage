"use client";

import React, { Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { getApiBase } from "../../lib/api-config";

const API_BASE = getApiBase();

function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const token = searchParams.get("token") || "";

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!token) {
      setError("Reset token is missing or invalid.");
      return;
    }
    if (newPassword.length < 8) {
      setError("Password must be at least 8 characters long.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setIsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/auth/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: newPassword }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Failed to reset password." }));
        throw new Error(err.detail || "Reset token has expired or is invalid.");
      }
      setSuccess(true);
      setTimeout(() => {
        router.push("/login");
      }, 2500);
    } catch (err: any) {
      setError(err.message || "Failed to reset password.");
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
            Set New Password
          </h1>
          <p style={{ fontSize: 13, color: "#64748b", margin: 0 }}>
            Enter your new secure password below
          </p>
        </div>

        {error && (
          <div style={{ background: "#fef2f2", color: "#b91c1c", padding: "10px 14px", borderRadius: 8, fontSize: 13, marginBottom: 16 }}>
            {error}
          </div>
        )}

        {success ? (
          <div style={{ textAlign: "center", padding: "16px 0" }}>
            <div style={{ fontSize: 40, marginBottom: 12 }}>✅</div>
            <h3 style={{ fontSize: 16, fontWeight: 700, color: "#166534", margin: "0 0 6px 0" }}>Password Updated!</h3>
            <p style={{ fontSize: 13, color: "#475569" }}>
              Your password has been reset successfully. Redirecting you to login...
            </p>
            <div style={{ marginTop: 16 }}>
              <Link href="/login" style={{ fontSize: 13, color: "#4f46e5", fontWeight: 600 }}>
                Click here to sign in now
              </Link>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#1e293b", marginBottom: 6 }}>
                New Password
              </label>
              <input
                type="password"
                required
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
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
                Confirm New Password
              </label>
              <input
                type="password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Repeat new password"
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
              {isLoading ? "Updating..." : "Update Password"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<div style={{ textAlign: "center", padding: 60, color: "#64748b" }}>Loading reset form...</div>}>
      <ResetPasswordForm />
    </Suspense>
  );
}
