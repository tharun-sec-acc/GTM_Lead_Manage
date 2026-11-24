"use client";

import React, { useEffect, useState } from "react";
import { useAuth } from "../../../lib/auth-context";
import { getApiBase } from "../../../lib/api-config";

const API_BASE = getApiBase();

interface Member {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: string;
  status: string;
  joined_at: string;
}

interface Invitation {
  id: string;
  email: string;
  role: string;
  status: string;
  expires_at: string;
  created_at: string;
  invite_url?: string;
}

export default function TeamSettingsPage() {
  const { organization, token, fetchWithAuth } = useAuth();
  const [members, setMembers] = useState<Member[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [loading, setLoading] = useState(true);

  // Invite modal state
  const [inviteModalOpen, setInviteModalOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("rep");
  const [inviteLoading, setInviteLoading] = useState(false);
  const [inviteResultUrl, setInviteResultUrl] = useState<string | null>(null);

  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const loadTeamData = async () => {
    try {
      const [membersRes, invitesRes] = await Promise.all([
        fetchWithAuth(`${API_BASE}/organizations/members`),
        fetchWithAuth(`${API_BASE}/organizations/invitations`),
      ]);

      if (membersRes.ok) {
        const m = await membersRes.json();
        setMembers(m);
      }
      if (invitesRes.ok) {
        const inv = await invitesRes.json();
        setInvitations(inv);
      }
    } catch {
      // quiet catch
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTeamData();
  }, [organization?.id, token]);

  const handleSendInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    setInviteLoading(true);
    setErrorMsg(null);
    try {
      const res = await fetchWithAuth(`${API_BASE}/organizations/members/invite`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: inviteEmail, role: inviteRole }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Invite failed" }));
        throw new Error(err.detail || "Failed to invite member");
      }

      const invData = await res.json();
      setInviteResultUrl(invData.invite_url || null);
      setStatusMsg(`Invitation generated for ${inviteEmail}.`);
      setInviteEmail("");
      loadTeamData();
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to invite member.");
    } finally {
      setInviteLoading(false);
    }
  };

  const handleRoleChange = async (memberId: string, newRole: string) => {
    try {
      const res = await fetchWithAuth(`${API_BASE}/organizations/members/${memberId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role: newRole }),
      });
      if (res.ok) {
        setStatusMsg("Role updated successfully.");
        loadTeamData();
      } else {
        const err = await res.json();
        setErrorMsg(err.detail || "Failed to change role.");
      }
    } catch {
      setErrorMsg("Failed to change role.");
    }
  };

  const handleRemoveMember = async (memberId: string, memberEmail: string) => {
    if (!confirm(`Are you sure you want to remove ${memberEmail} from the organization?`)) return;
    try {
      const res = await fetchWithAuth(`${API_BASE}/organizations/members/${memberId}`, {
        method: "DELETE",
      });
      if (res.ok) {
        setStatusMsg(`Removed ${memberEmail} from organization.`);
        loadTeamData();
      } else {
        const err = await res.json();
        setErrorMsg(err.detail || "Failed to remove member.");
      }
    } catch {
      setErrorMsg("Failed to remove member.");
    }
  };

  const handleRevokeInvite = async (inviteId: string) => {
    try {
      const res = await fetchWithAuth(`${API_BASE}/organizations/invitations/${inviteId}`, {
        method: "DELETE",
      });
      if (res.ok) {
        setStatusMsg("Invitation revoked.");
        loadTeamData();
      }
    } catch {
      setErrorMsg("Failed to revoke invitation.");
    }
  };

  return (
    <div style={{ maxWidth: 1000, margin: "0 auto", padding: "32px 24px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 32 }}>
        <div>
          <h1 style={{ fontSize: 26, fontWeight: 700, color: "#0f172a", margin: "0 0 8px 0" }}>
            Team & Members
          </h1>
          <p style={{ fontSize: 14, color: "#64748b", margin: 0 }}>
            Manage who has access to your organization's leads, campaigns, and intelligence.
          </p>
        </div>
        <button
          onClick={() => {
            setInviteModalOpen(true);
            setInviteResultUrl(null);
          }}
          style={{
            padding: "10px 18px",
            background: "linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)",
            color: "#ffffff",
            border: "none",
            borderRadius: 8,
            fontSize: 14,
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 2px 4px rgba(79, 70, 229, 0.2)",
          }}
        >
          + Invite Member
        </button>
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

      {/* Members Table */}
      <div style={{ background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 12, overflow: "hidden", marginBottom: 36 }}>
        <div style={{ padding: "16px 20px", borderBottom: "1px solid #e2e8f0", background: "#f8fafc" }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: "#1e293b" }}>
            Active Organization Members ({members.length})
          </h3>
        </div>
        <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid #f1f5f9", background: "#f8fafc", fontSize: 12, color: "#64748b", textTransform: "uppercase" }}>
              <th style={{ padding: "12px 20px" }}>User</th>
              <th style={{ padding: "12px 20px" }}>Role</th>
              <th style={{ padding: "12px 20px" }}>Status</th>
              <th style={{ padding: "12px 20px" }}>Joined Date</th>
              <th style={{ padding: "12px 20px", textAlign: "right" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.id} style={{ borderBottom: "1px solid #f1f5f9", fontSize: 14 }}>
                <td style={{ padding: "14px 20px" }}>
                  <div style={{ fontWeight: 600, color: "#0f172a" }}>{m.full_name}</div>
                  <div style={{ fontSize: 12, color: "#64748b" }}>{m.email}</div>
                </td>
                <td style={{ padding: "14px 20px" }}>
                  {m.role === "owner" ? (
                    <span style={{ background: "#fef3c7", color: "#92400e", padding: "3px 8px", borderRadius: 6, fontSize: 12, fontWeight: 700 }}>
                      OWNER
                    </span>
                  ) : (
                    <select
                      value={m.role}
                      onChange={(e) => handleRoleChange(m.id, e.target.value)}
                      style={{
                        padding: "4px 8px",
                        border: "1px solid #cbd5e1",
                        borderRadius: 6,
                        fontSize: 13,
                        background: "#ffffff",
                      }}
                    >
                      <option value="admin">Admin</option>
                      <option value="manager">Sales Manager</option>
                      <option value="rep">Sales Rep</option>
                      <option value="read_only">Read Only</option>
                    </select>
                  )}
                </td>
                <td style={{ padding: "14px 20px" }}>
                  <span style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                    fontSize: 13,
                    color: m.status === "active" ? "#166534" : "#94a3b8",
                  }}>
                    <span style={{ width: 8, height: 8, borderRadius: "50%", background: m.status === "active" ? "#22c55e" : "#cbd5e1" }} />
                    {m.status.toUpperCase()}
                  </span>
                </td>
                <td style={{ padding: "14px 20px", color: "#64748b", fontSize: 13 }}>
                  {new Date(m.joined_at).toLocaleDateString()}
                </td>
                <td style={{ padding: "14px 20px", textAlign: "right" }}>
                  {m.role !== "owner" && (
                    <button
                      onClick={() => handleRemoveMember(m.id, m.email)}
                      style={{
                        background: "transparent",
                        border: "1px solid #fecaca",
                        color: "#ef4444",
                        padding: "4px 10px",
                        borderRadius: 6,
                        fontSize: 12,
                        cursor: "pointer",
                      }}
                    >
                      Remove
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Invitations List */}
      {invitations.length > 0 && (
        <div style={{ background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 12, overflow: "hidden" }}>
          <div style={{ padding: "16px 20px", borderBottom: "1px solid #e2e8f0", background: "#f8fafc" }}>
            <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: "#1e293b" }}>
              Pending Invitations ({invitations.length})
            </h3>
          </div>
          <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #f1f5f9", background: "#f8fafc", fontSize: 12, color: "#64748b", textTransform: "uppercase" }}>
                <th style={{ padding: "12px 20px" }}>Email</th>
                <th style={{ padding: "12px 20px" }}>Designated Role</th>
                <th style={{ padding: "12px 20px" }}>Expires In</th>
                <th style={{ padding: "12px 20px", textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {invitations.map((inv) => (
                <tr key={inv.id} style={{ borderBottom: "1px solid #f1f5f9", fontSize: 14 }}>
                  <td style={{ padding: "12px 20px", fontWeight: 500, color: "#0f172a" }}>{inv.email}</td>
                  <td style={{ padding: "12px 20px", color: "#64748b" }}>{inv.role.toUpperCase()}</td>
                  <td style={{ padding: "12px 20px", color: "#64748b", fontSize: 13 }}>
                    {new Date(inv.expires_at).toLocaleDateString()}
                  </td>
                  <td style={{ padding: "12px 20px", textAlign: "right" }}>
                    <button
                      onClick={() => handleRevokeInvite(inv.id)}
                      style={{
                        background: "transparent",
                        border: "1px solid #e2e8f0",
                        color: "#64748b",
                        padding: "4px 10px",
                        borderRadius: 6,
                        fontSize: 12,
                        cursor: "pointer",
                      }}
                    >
                      Revoke
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Invite Modal */}
      {inviteModalOpen && (
        <div style={{
          position: "fixed",
          inset: 0,
          background: "rgba(15, 23, 42, 0.5)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          zIndex: 999,
          padding: 16,
        }}>
          <div style={{
            background: "#ffffff",
            borderRadius: 16,
            padding: "28px 24px",
            width: "100%",
            maxWidth: 440,
            boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1)",
          }}>
            <h3 style={{ margin: "0 0 6px 0", fontSize: 18, fontWeight: 700, color: "#0f172a" }}>
              Invite Team Member
            </h3>
            <p style={{ margin: "0 0 20px 0", fontSize: 13, color: "#64748b" }}>
              Send an onboarding invitation to join {organization?.name || "your organization"}.
            </p>

            {inviteResultUrl ? (
              <div>
                <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", padding: 14, borderRadius: 8, marginBottom: 16 }}>
                  <p style={{ fontSize: 13, color: "#166534", margin: "0 0 8px 0", fontWeight: 600 }}>
                    Invitation link created:
                  </p>
                  <input
                    type="text"
                    readOnly
                    value={inviteResultUrl}
                    style={{ width: "100%", padding: "8px 10px", fontSize: 12, border: "1px solid #cbd5e1", borderRadius: 6, background: "#ffffff", boxSizing: "border-box" }}
                  />
                </div>
                <button
                  onClick={() => setInviteModalOpen(false)}
                  style={{ width: "100%", padding: "10px", background: "#4f46e5", color: "#ffffff", border: "none", borderRadius: 8, fontWeight: 600, cursor: "pointer" }}
                >
                  Done
                </button>
              </div>
            ) : (
              <form onSubmit={handleSendInvite} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                <div>
                  <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#334155", marginBottom: 6 }}>
                    Colleague's Work Email
                  </label>
                  <input
                    type="email"
                    required
                    value={inviteEmail}
                    onChange={(e) => setInviteEmail(e.target.value)}
                    placeholder="teammate@company.com"
                    style={{ width: "100%", padding: "10px 12px", border: "1px solid #cbd5e1", borderRadius: 8, fontSize: 14, boxSizing: "border-box" }}
                  />
                </div>

                <div>
                  <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#334155", marginBottom: 6 }}>
                    Role Assignment
                  </label>
                  <select
                    value={inviteRole}
                    onChange={(e) => setInviteRole(e.target.value)}
                    style={{ width: "100%", padding: "10px 12px", border: "1px solid #cbd5e1", borderRadius: 8, fontSize: 14, background: "#ffffff", boxSizing: "border-box" }}
                  >
                    <option value="admin">Admin (Manage team, integrations, and leads)</option>
                    <option value="manager">Sales Manager (Lead assignment, campaigns, analytics)</option>
                    <option value="rep">Sales Rep (Assigned leads, personalized outreach)</option>
                    <option value="read_only">Read Only (View leads and reports)</option>
                  </select>
                </div>

                <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 10 }}>
                  <button
                    type="button"
                    onClick={() => setInviteModalOpen(false)}
                    style={{ padding: "9px 16px", background: "#f1f5f9", color: "#475569", border: "none", borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: "pointer" }}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={inviteLoading}
                    style={{ padding: "9px 18px", background: "#4f46e5", color: "#ffffff", border: "none", borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: "pointer" }}
                  >
                    {inviteLoading ? "Generating..." : "Generate Invite"}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
