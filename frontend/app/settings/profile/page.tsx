"use client";

import React, { useState } from "react";
import { useAuth } from "../../../lib/auth-context";
import { getApiBase } from "../../../lib/api-config";

const API_BASE = getApiBase();

export default function UserProfileSettingsPage() {
  const { user, refreshUser, fetchWithAuth } = useAuth();
  const [fullName, setFullName] = useState(user?.full_name || "");
  const [savingProfile, setSavingProfile] = useState(false);

  // Password change state
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [savingPassword, setSavingPassword] = useState(false);

  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleUpdateProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingProfile(true);
    setStatusMsg(null);
    setErrorMsg(null);
    try {
      const res = await fetchWithAuth(`${API_BASE}/auth/profile`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ full_name: fullName }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Update failed" }));
        throw new Error(err.detail || "Failed to update profile");
      }
      setStatusMsg("Profile updated successfully.");
      await refreshUser();
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to update profile.");
    } finally {
      setSavingProfile(false);
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatusMsg(null);
    setErrorMsg(null);
    if (newPassword.length < 8) {
      setErrorMsg("New password must be at least 8 characters long.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setErrorMsg("New passwords do not match.");
      return;
    }

    setSavingPassword(true);
    try {
      const res = await fetchWithAuth(`${API_BASE}/auth/change-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Password change failed" }));
        throw new Error(err.detail || "Failed to change password");
      }
      setStatusMsg("Password updated successfully.");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to change password.");
    } finally {
      setSavingPassword(false);
    }
  };

  return (
    <div style={{ maxWidth: 800, margin: "0 auto", padding: "32px 24px" }}>
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ fontSize: 26, fontWeight: 700, color: "#0f172a", margin: "0 0 8px 0" }}>
          User Profile
        </h1>
        <p style={{ fontSize: 14, color: "#64748b", margin: 0 }}>
          Manage your personal account credentials and security settings.
        </p>
      </div>

      {statusMsg && (
        <div style={{ background: "#f0fdf4", color: "#166534", border: "1px solid #bbf7d0", padding: "12px 16px", borderRadius: 8, marginBottom: 20, fontSize: 14 }}>
          ✓ {statusMsg}
        </div>
      )}
      {errorMsg && (
        <div style={{ background: "#fef2f2", color: "#b91c1c", border: "1px solid #fecaca", padding: "12px 16px", borderRadius: 8, marginBottom: 20, fontSize: 14 }}>
          ⚠️ {errorMsg}
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
        {/* Profile Card */}
        <div style={{ background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 12, padding: 24 }}>
          <h2 style={{ fontSize: 18, fontWeight: 600, color: "#1e293b", margin: "0 0 18px 0" }}>
            Personal Information
          </h2>
          <form onSubmit={handleUpdateProfile} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#334155", marginBottom: 6 }}>
                Full Name
              </label>
              <input
                type="text"
                required
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                style={{ width: "100%", padding: "10px 14px", border: "1px solid #cbd5e1", borderRadius: 8, fontSize: 14, boxSizing: "border-box" }}
              />
            </div>

            <div>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#334155", marginBottom: 6 }}>
                Email Address
              </label>
              <input
                type="email"
                disabled
                value={user?.email || ""}
                style={{ width: "100%", padding: "10px 14px", border: "1px solid #e2e8f0", borderRadius: 8, fontSize: 14, color: "#64748b", background: "#f8fafc", boxSizing: "border-box" }}
              />
              <span style={{ fontSize: 12, color: "#94a3b8", marginTop: 4, display: "block" }}>
                Primary sign-in identity.
              </span>
            </div>

            <button
              type="submit"
              disabled={savingProfile}
              style={{
                alignSelf: "flex-start",
                padding: "9px 18px",
                background: "#4f46e5",
                color: "#ffffff",
                border: "none",
                borderRadius: 8,
                fontSize: 13,
                fontWeight: 600,
                cursor: savingProfile ? "not-allowed" : "pointer",
                marginTop: 4,
              }}
            >
              {savingProfile ? "Saving..." : "Save Profile"}
            </button>
          </form>
        </div>

        {/* Change Password Card */}
        <div style={{ background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 12, padding: 24 }}>
          <h2 style={{ fontSize: 18, fontWeight: 600, color: "#1e293b", margin: "0 0 18px 0" }}>
            Change Password
          </h2>
          <form onSubmit={handleChangePassword} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#334155", marginBottom: 6 }}>
                Current Password
              </label>
              <input
                type="password"
                required
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                placeholder="••••••••••••"
                style={{ width: "100%", padding: "10px 14px", border: "1px solid #cbd5e1", borderRadius: 8, fontSize: 14, boxSizing: "border-box" }}
              />
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
              <div>
                <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#334155", marginBottom: 6 }}>
                  New Password
                </label>
                <input
                  type="password"
                  required
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Min 8 characters"
                  style={{ width: "100%", padding: "10px 14px", border: "1px solid #cbd5e1", borderRadius: 8, fontSize: 14, boxSizing: "border-box" }}
                />
              </div>
              <div>
                <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#334155", marginBottom: 6 }}>
                  Confirm New Password
                </label>
                <input
                  type="password"
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Repeat new password"
                  style={{ width: "100%", padding: "10px 14px", border: "1px solid #cbd5e1", borderRadius: 8, fontSize: 14, boxSizing: "border-box" }}
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={savingPassword}
              style={{
                alignSelf: "flex-start",
                padding: "9px 18px",
                background: "#0f172a",
                color: "#ffffff",
                border: "none",
                borderRadius: 8,
                fontSize: 13,
                fontWeight: 600,
                cursor: savingPassword ? "not-allowed" : "pointer",
                marginTop: 4,
              }}
            >
              {savingPassword ? "Updating Password..." : "Update Password"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
