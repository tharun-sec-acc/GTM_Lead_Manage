"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  API,
  type ProviderStatus,
  type MeetingSummary,
  type MeetingDetail,
  type MeetingActionItem,
  fetchProviderStatuses,
  fetchMeetings,
  fetchMeetingDetail,
  createMeeting,
  syncMeetingArtifacts,
  analyzeMeeting,
  addMeetingActionItem,
  updateMeetingActionItem,
  sendFollowupDraft,
  sendMeetingInvites,
  addManualTranscript,
  rescheduleMeeting,
  cancelMeeting,
} from "../lib/meetings";
import UiIcon from "./ui-icon";

interface LeadOption {
  id: string;
  company_name: string;
  email: string | null;
  domain: string | null;
}

interface ContactOption {
  id: string;
  lead_id: string;
  name: string | null;
  title: string | null;
  email: string | null;
  company_name?: string;
  lead_email?: string | null;
  is_key_decision_maker?: boolean;
}

interface Props {
  productId?: string;
  leadId?: string;
  title?: string;
  description?: string;
}

export default function UnifiedMeetingsView({
  productId,
  leadId,
  title = "Meetings & Video Intelligence",
  description = "Schedule, host, and analyze meetings across Microsoft Teams and Google Meet with Bedrock AI intelligence.",
}: Props) {
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [meetings, setMeetings] = useState<MeetingSummary[]>([]);
  const [selectedMeetingId, setSelectedMeetingId] = useState<string | null>(null);
  const [meetingDetail, setMeetingDetail] = useState<MeetingDetail | null>(null);

  const [providerFilter, setProviderFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");

  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

  // Create Modal State
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createProvider, setCreateProvider] = useState<"teams" | "google_meet">("teams");
  const [createType, setCreateType] = useState<"scheduled" | "instant">("scheduled");
  const [createTitle, setCreateTitle] = useState("DENSO Solutions Discovery Call");
  const [createDescription, setCreateDescription] = useState("");
  const [createStart, setCreateStart] = useState("");
  const [createEnd, setCreateEnd] = useState("");
  const [createDuration, setCreateDuration] = useState<number>(30);
  const [createEmails, setCreateEmails] = useState("");
  const [createdJoinUrl, setCreatedJoinUrl] = useState<string | null>(null);

  // Clipboard Feedback State
  const [copiedMoM, setCopiedMoM] = useState(false);
  const [copiedLink, setCopiedLink] = useState(false);
  const [copiedEmailDraft, setCopiedEmailDraft] = useState(false);

  // Lead Contacts & Participant Picker State
  const [leadsList, setLeadsList] = useState<LeadOption[]>([]);
  const [contactsList, setContactsList] = useState<ContactOption[]>([]);
  const [selectedLeadFilter, setSelectedLeadFilter] = useState<string>(leadId || "");
  const [contactSearchQuery, setContactSearchQuery] = useState("");
  const [loadingContacts, setLoadingContacts] = useState(false);

  // Follow-up Email Draft State
  const [followupRecipient, setFollowupRecipient] = useState("");
  const [followupSubject, setFollowupSubject] = useState("");
  const [followupBody, setFollowupBody] = useState("");
  const [sendingFollowup, setSendingFollowup] = useState(false);

  // New Action Item Input
  const [newActionTitle, setNewActionTitle] = useState("");
  const [newActionOwner, setNewActionOwner] = useState("Sales Rep");

  // Manual Notes / Transcript State
  const [showPasteNotes, setShowPasteNotes] = useState(false);
  const [pastedNotesText, setPastedNotesText] = useState("");
  const [savingNotes, setSavingNotes] = useState(false);

  // Reschedule & Cancel State
  const [showRescheduleModal, setShowRescheduleModal] = useState(false);
  const [rescheduleStart, setRescheduleStart] = useState("");
  const [rescheduleEnd, setRescheduleEnd] = useState("");
  const [rescheduleDuration, setRescheduleDuration] = useState<number>(30);
  const [rescheduleNote, setRescheduleNote] = useState("");
  const [rescheduling, setRescheduling] = useState(false);

  const [showCancelModal, setShowCancelModal] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const [cancelling, setCancelling] = useState(false);

  // Load Initial Data
  const loadData = async () => {
    try {
      setLoading(true);
      setError("");
      const [pStats, mList] = await Promise.all([
        fetchProviderStatuses().catch(() => []),
        fetchMeetings({
          product_id: productId,
          lead_id: leadId,
          provider: providerFilter !== "all" ? providerFilter : undefined,
          status: statusFilter !== "all" ? statusFilter : undefined,
          search: searchQuery || undefined,
        }).catch(() => []),
      ]);
      setProviders(pStats);
      setMeetings(mList);
    } catch (err: any) {
      setError(err?.message || "Failed to load meetings.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [providerFilter, statusFilter, productId, leadId]);

  // Load Meeting Details
  useEffect(() => {
    if (!selectedMeetingId) {
      setMeetingDetail(null);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    fetchMeetingDetail(selectedMeetingId)
      .then((detail) => {
        if (!cancelled) {
          setMeetingDetail(detail);
          if (detail.analysis) {
            setFollowupSubject(detail.analysis.followup_draft_subject || `Follow-up: ${detail.title}`);
            setFollowupBody(detail.analysis.followup_draft_body || "");
          } else {
            // Automatically trigger AI meeting analysis in background so sales reps never have to click
            analyzeMeeting(selectedMeetingId)
              .then((analyzed) => {
                if (!cancelled) {
                  setMeetingDetail(analyzed);
                  if (analyzed.analysis) {
                    setFollowupSubject(analyzed.analysis.followup_draft_subject || `Follow-up: ${analyzed.title}`);
                    setFollowupBody(analyzed.analysis.followup_draft_body || "");
                  }
                  loadData();
                }
              })
              .catch(() => {});
          }
          if (detail.participants && detail.participants.length > 0) {
            const prospect = detail.participants.find((p) => p.participant_role !== "organizer");
            setFollowupRecipient(prospect ? prospect.email : detail.participants[0].email);
          }
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message || "Failed to load meeting details.");
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedMeetingId]);

  const loadContactsAndLeads = async () => {
    setLoadingContacts(true);
    try {
      const leadsPromise = !leadId
        ? fetch(`${API}/leads`).then((r) => (r.ok ? r.json() : [])).catch(() => [])
        : Promise.resolve([]);

      const contactsUrl = leadId
        ? `${API}/contacts?lead_id=${encodeURIComponent(leadId)}`
        : productId
        ? `${API}/contacts?product_id=${encodeURIComponent(productId)}`
        : `${API}/contacts`;

      const contactsPromise = fetch(contactsUrl).then((r) => (r.ok ? r.json() : [])).catch(() => []);

      const [leadsData, contactsData] = await Promise.all([leadsPromise, contactsPromise]);
      setLeadsList(leadsData);
      setContactsList(contactsData);
    } catch {
      // Non-fatal, fallback to manual typing
    } finally {
      setLoadingContacts(false);
    }
  };

  const parsedEmails = useMemo(() => {
    return Array.from(
      new Set(
        createEmails
          .split(/[\s,;]+/)
          .map((e) => e.trim())
          .filter(Boolean)
      )
    );
  }, [createEmails]);

  const toggleContactEmail = (email: string) => {
    const cleanEmail = email.trim();
    if (!cleanEmail) return;
    const lower = cleanEmail.toLowerCase();
    const current = createEmails
      .split(/[\s,;]+/)
      .map((e) => e.trim())
      .filter(Boolean);

    let next: string[];
    if (current.some((e) => e.toLowerCase() === lower)) {
      next = current.filter((e) => e.toLowerCase() !== lower);
    } else {
      next = [...current, cleanEmail];
    }
    setCreateEmails(next.join(", "));
  };

  const removeEmail = (email: string) => {
    const lower = email.trim().toLowerCase();
    const current = createEmails
      .split(/[\s,;]+/)
      .map((e) => e.trim())
      .filter(Boolean);
    const next = current.filter((e) => e.toLowerCase() !== lower);
    setCreateEmails(next.join(", "));
  };

  const filteredContacts = useMemo(() => {
    return contactsList.filter((c) => {
      if (selectedLeadFilter && selectedLeadFilter !== "" && c.lead_id !== selectedLeadFilter) {
        return false;
      }
      if (!contactSearchQuery.trim()) return true;
      const q = contactSearchQuery.trim().toLowerCase();
      const nameMatch = (c.name || "").toLowerCase().includes(q);
      const emailMatch = (c.email || "").toLowerCase().includes(q);
      const titleMatch = (c.title || "").toLowerCase().includes(q);
      const compMatch = (c.company_name || "").toLowerCase().includes(q);
      return nameMatch || emailMatch || titleMatch || compMatch;
    });
  }, [contactsList, selectedLeadFilter, contactSearchQuery]);

  const selectedLead = useMemo(() => {
    return leadsList.find((l) => l.id === selectedLeadFilter);
  }, [leadsList, selectedLeadFilter]);

  // Duration & End-Time Calculator Helpers
  const calculateEndTime = (startStr: string, minutes: number): string => {
    if (!startStr) return "";
    const startDate = new Date(startStr);
    if (isNaN(startDate.getTime())) return "";
    const endDate = new Date(startDate.getTime() + minutes * 60000);
    const offset = endDate.getTimezoneOffset() * 60000;
    return new Date(endDate.getTime() - offset).toISOString().slice(0, 16);
  };

  const handleSelectCreateDuration = (minutes: number) => {
    setCreateDuration(minutes);
    if (createStart) {
      setCreateEnd(calculateEndTime(createStart, minutes));
    }
  };

  const handleCreateStartChange = (val: string) => {
    setCreateStart(val);
    if (val && createDuration > 0) {
      setCreateEnd(calculateEndTime(val, createDuration));
    }
  };

  const handleCreateEndChange = (val: string) => {
    setCreateEnd(val);
    if (createStart && val) {
      const diff = Math.round((new Date(val).getTime() - new Date(createStart).getTime()) / 60000);
      if (diff > 0) {
        setCreateDuration(diff);
      }
    }
  };

  const handleSelectRescheduleDuration = (minutes: number) => {
    setRescheduleDuration(minutes);
    if (rescheduleStart) {
      setRescheduleEnd(calculateEndTime(rescheduleStart, minutes));
    }
  };

  const handleRescheduleStartChange = (val: string) => {
    setRescheduleStart(val);
    if (val && rescheduleDuration > 0) {
      setRescheduleEnd(calculateEndTime(val, rescheduleDuration));
    }
  };

  const handleRescheduleEndChange = (val: string) => {
    setRescheduleEnd(val);
    if (rescheduleStart && val) {
      const diff = Math.round((new Date(val).getTime() - new Date(rescheduleStart).getTime()) / 60000);
      if (diff > 0) {
        setRescheduleDuration(diff);
      }
    }
  };

  const copyToClipboard = (text: string, type: "mom" | "link" | "email") => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    if (type === "mom") {
      setCopiedMoM(true);
      setTimeout(() => setCopiedMoM(false), 2500);
    } else if (type === "link") {
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 2500);
    } else if (type === "email") {
      setCopiedEmailDraft(true);
      setTimeout(() => setCopiedEmailDraft(false), 2500);
    }
  };

  // Default datetimes for modal
  const openModal = () => {
    const dur = createDuration || 30;
    const start = new Date(Date.now() + 15 * 60000);
    const end = new Date(start.getTime() + dur * 60000);
    const offset = start.getTimezoneOffset() * 60000;
    setCreateStart(new Date(start.getTime() - offset).toISOString().slice(0, 16));
    setCreateEnd(new Date(end.getTime() - offset).toISOString().slice(0, 16));
    setCreatedJoinUrl(null);
    setSelectedLeadFilter(leadId || "");
    setContactSearchQuery("");
    setShowCreateModal(true);
    void loadContactsAndLeads();
  };

  // Submit Meeting Creation
  const handleCreateMeeting = async (e: React.FormEvent) => {
    e.preventDefault();
    setActionLoading(true);
    setError("");
    try {
      const emails = Array.from(
        new Set(
          createEmails
            .split(/[\s,;]+/)
            .map((s) => s.trim())
            .filter(Boolean)
        )
      );

      const effectiveLeadId = leadId || (selectedLeadFilter && selectedLeadFilter !== "" ? selectedLeadFilter : undefined);

      const res = await createMeeting({
        provider: createProvider,
        meeting_type: createType,
        title: createTitle,
        description: createDescription || undefined,
        lead_id: effectiveLeadId,
        product_id: productId,
        scheduled_start: createType === "scheduled" && createStart ? new Date(createStart).toISOString() : undefined,
        scheduled_end: createType === "scheduled" && createEnd ? new Date(createEnd).toISOString() : undefined,
        participant_emails: emails,
      });

      setCreatedJoinUrl(res.join_url);
      setSuccessMsg(`Meeting "${res.title}" created successfully!`);
      loadData();
      setSelectedMeetingId(res.id);
    } catch (err: any) {
      setError(err?.message || "Failed to create meeting.");
    } finally {
      setActionLoading(false);
    }
  };

  // Sync Artifacts
  const handleSyncArtifacts = async (mid: string) => {
    setActionLoading(true);
    setError("");
    try {
      const res = await syncMeetingArtifacts(mid);
      setMeetingDetail(res.meeting);
      setSuccessMsg("Artifacts checked and synced from provider.");
      loadData();
    } catch (err: any) {
      setError(err?.message || "Artifact sync failed.");
    } finally {
      setActionLoading(false);
    }
  };

  // Resend / Send Invites
  const handleSendInvites = async (mid: string) => {
    setActionLoading(true);
    setError("");
    try {
      const res = await sendMeetingInvites(mid);
      setSuccessMsg(res.message || "Meeting invitation emails dispatched successfully!");
    } catch (err: any) {
      setError(err?.message || "Failed to send meeting invitations.");
    } finally {
      setActionLoading(false);
    }
  };

  // Save Manual Notes and Run AI Intelligence
  const handleSaveNotes = async () => {
    if (!selectedMeetingId || !pastedNotesText.trim()) return;
    setSavingNotes(true);
    setError("");
    try {
      const updated = await addManualTranscript(selectedMeetingId, pastedNotesText.trim());
      setMeetingDetail(updated);
      setShowPasteNotes(false);
      setPastedNotesText("");
      setSuccessMsg("Meeting notes saved. Running AI intelligence...");
      await handleAnalyzeMeeting(selectedMeetingId);
    } catch (err: any) {
      setError(err?.message || "Failed to save transcript.");
    } finally {
      setSavingNotes(false);
    }
  };

  // Handle Reschedule / Postpone
  const handleRescheduleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedMeetingId || !rescheduleStart) return;
    setRescheduling(true);
    setError("");
    try {
      const startIso = new Date(rescheduleStart).toISOString();
      const endIso = rescheduleEnd
        ? new Date(rescheduleEnd).toISOString()
        : new Date(new Date(rescheduleStart).getTime() + 30 * 60000).toISOString();
      const updated = await rescheduleMeeting(selectedMeetingId, {
        new_start: startIso,
        new_end: endIso,
        note: rescheduleNote || undefined,
      });
      setMeetingDetail(updated);
      setShowRescheduleModal(false);
      setSuccessMsg("Meeting rescheduled successfully! Updated invitation emails sent to all attendees.");
      loadData();
    } catch (err: any) {
      setError(err?.message || "Failed to reschedule meeting.");
    } finally {
      setRescheduling(false);
    }
  };

  // Handle Cancel Meeting
  const handleCancelSubmit = async () => {
    if (!selectedMeetingId) return;
    setCancelling(true);
    setError("");
    try {
      const updated = await cancelMeeting(selectedMeetingId, cancelReason || undefined);
      setMeetingDetail(updated);
      setShowCancelModal(false);
      setSuccessMsg("Meeting cancelled. Cancellation notices sent to all participants.");
      loadData();
    } catch (err: any) {
      setError(err?.message || "Failed to cancel meeting.");
    } finally {
      setCancelling(false);
    }
  };

  // Trigger Bedrock Analysis
  const handleAnalyzeMeeting = async (mid: string) => {
    setActionLoading(true);
    setError("");
    try {
      const res = await analyzeMeeting(mid);
      setMeetingDetail(res);
      if (res.analysis) {
        setFollowupSubject(res.analysis.followup_draft_subject || `Follow-up: ${res.title}`);
        setFollowupBody(res.analysis.followup_draft_body || "");
      }
      setSuccessMsg("AI meeting analysis complete!");
      loadData();
    } catch (err: any) {
      setError(err?.message || "Meeting analysis failed.");
    } finally {
      setActionLoading(false);
    }
  };

  // Toggle Action Item Status
  const handleToggleActionItem = async (item: MeetingActionItem) => {
    const nextStatus = item.status === "completed" ? "open" : "completed";
    try {
      await updateMeetingActionItem(item.id, { status: nextStatus });
      if (meetingDetail) {
        setMeetingDetail({
          ...meetingDetail,
          action_items: meetingDetail.action_items.map((i) =>
            i.id === item.id ? { ...i, status: nextStatus } : i
          ),
        });
      }
    } catch (err: any) {
      setError(err?.message || "Failed to update action item.");
    }
  };

  // Add Action Item
  const handleAddActionItem = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedMeetingId || !newActionTitle.trim()) return;
    try {
      const added = await addMeetingActionItem(selectedMeetingId, {
        title: newActionTitle.trim(),
        owner: newActionOwner,
        priority: "medium",
      });
      if (meetingDetail) {
        setMeetingDetail({
          ...meetingDetail,
          action_items: [...meetingDetail.action_items, added],
        });
      }
      setNewActionTitle("");
    } catch (err: any) {
      setError(err?.message || "Failed to add action item.");
    }
  };

  // Send Follow-up Email
  const handleSendFollowup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedMeetingId || !followupRecipient || !followupSubject || !followupBody) return;
    setSendingFollowup(true);
    setError("");
    try {
      await sendFollowupDraft(selectedMeetingId, {
        recipient: followupRecipient,
        subject: followupSubject,
        body: followupBody,
      });
      setSuccessMsg(`Follow-up email dispatched successfully to ${followupRecipient}!`);
    } catch (err: any) {
      setError(err?.message || "Failed to send follow-up.");
    } finally {
      setSendingFollowup(false);
    }
  };

  return (
    <div className="meetings-workspace" style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {/* Header */}
      <div className="page-heading" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 16 }}>
        <div>
          <p className="eyebrow">UNIFIED MEETINGS</p>
          <h1 style={{ margin: "4px 0" }}>{title}</h1>
          <p style={{ margin: 0, color: "var(--muted)", maxWidth: 700 }}>{description}</p>
        </div>
        <div style={{ display: "flex", gap: 12 }}>
          <button onClick={openModal} style={{ background: "var(--red)", color: "#fff", display: "inline-flex", alignItems: "center", gap: 8, padding: "10px 18px", borderRadius: 8, border: "none", cursor: "pointer", fontWeight: 600 }}>
            <UiIcon name="calendar" size={16} /> + Schedule / Instant Meeting
          </button>
        </div>
      </div>

      {/* Notifications */}
      {error && (
        <div style={{ background: "#fef2f2", color: "#991b1b", border: "1px solid #fecaca", padding: "12px 16px", borderRadius: 8 }}>
          {error}
        </div>
      )}
      {successMsg && (
        <div style={{ background: "#ecfdf5", color: "#065f46", border: "1px solid #a7f3d0", padding: "12px 16px", borderRadius: 8 }}>
          {successMsg}
        </div>
      )}

      {/* Provider Connectivity Banner */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 16 }}>
        {providers.map((p) => {
          const isTeams = p.provider === "teams";
          const brandColor = isTeams ? "#4f46e5" : "#059669";
          const titleName = isTeams ? "Microsoft Teams" : "Google Meet";
          const connectUrl = isTeams ? `${API}/microsoft/oauth/start` : `${API}/google/oauth/start`;

          return (
            <div
              key={p.provider}
              style={{
                background: "var(--surface)",
                border: "1px solid var(--border)",
                borderRadius: 12,
                padding: "18px 20px",
                display: "flex",
                flexDirection: "column",
                gap: 12,
                boxShadow: "var(--shadow-sm)",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <div
                    style={{
                      width: 32,
                      height: 32,
                      borderRadius: 8,
                      background: isTeams ? "#ede9fe" : "#d1fae5",
                      color: brandColor,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontWeight: 700,
                      fontSize: 14,
                    }}
                  >
                    {isTeams ? "MS" : "GM"}
                  </div>
                  <div>
                    <h3 style={{ margin: 0, fontSize: 16 }}>{titleName}</h3>
                    <span style={{ fontSize: 12, color: "var(--muted)" }}>
                      {p.connected ? `Connected: ${p.organizer_email || "Active"}` : "Not Connected"}
                    </span>
                  </div>
                </div>
                <span
                  style={{
                    padding: "3px 8px",
                    borderRadius: 12,
                    fontSize: 11,
                    fontWeight: 600,
                    background: p.connected ? "#ecfdf5" : "#f1f5f9",
                    color: p.connected ? "#065f46" : "#64748b",
                    border: `1px solid ${p.connected ? "#a7f3d0" : "#cbd5e1"}`,
                  }}
                >
                  {p.connected ? "● Connected" : "Disconnected"}
                </span>
              </div>

              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, fontSize: 11 }}>
                <span style={{ background: "#f8fafc", padding: "2px 6px", borderRadius: 4, color: "#475569" }}>
                  Instant: {p.capabilities?.instant_meeting ? "✓" : "✗"}
                </span>
                <span style={{ background: "#f8fafc", padding: "2px 6px", borderRadius: 4, color: "#475569" }}>
                  Calendar: {p.capabilities?.scheduled_meeting ? "✓" : "✗"}
                </span>
                <span style={{ background: "#f8fafc", padding: "2px 6px", borderRadius: 4, color: "#475569" }}>
                  Recordings: {p.capabilities?.recording_retrieval ? "✓" : "✗"}
                </span>
                <span style={{ background: "#f8fafc", padding: "2px 6px", borderRadius: 4, color: "#475569" }}>
                  Transcripts: {p.capabilities?.transcript_retrieval ? "✓" : "✗"}
                </span>
              </div>

              {!p.connected && (
                <a
                  href={connectUrl}
                  style={{
                    display: "inline-block",
                    textAlign: "center",
                    padding: "6px 12px",
                    borderRadius: 6,
                    fontSize: 12,
                    fontWeight: 600,
                    background: brandColor,
                    color: "#fff",
                    textDecoration: "none",
                    marginTop: 4,
                  }}
                >
                  Connect {titleName}
                </a>
              )}
            </div>
          );
        })}
      </div>

      {/* Filter and Search Bar */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: 12,
          background: "var(--surface)",
          padding: "12px 16px",
          borderRadius: 8,
          border: "1px solid var(--border)",
        }}
      >
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
          <div style={{ display: "flex", gap: 4 }}>
            {["all", "teams", "google_meet"].map((prov) => (
              <button
                key={prov}
                onClick={() => setProviderFilter(prov)}
                style={{
                  padding: "6px 12px",
                  fontSize: 13,
                  borderRadius: 6,
                  border: "1px solid",
                  borderColor: providerFilter === prov ? "var(--red)" : "var(--border)",
                  background: providerFilter === prov ? "var(--red)" : "#fff",
                  color: providerFilter === prov ? "#fff" : "var(--primary-text)",
                  cursor: "pointer",
                  fontWeight: 500,
                }}
              >
                {prov === "all" ? "All Providers" : prov === "teams" ? "Teams" : "Google Meet"}
              </button>
            ))}
          </div>

          <div style={{ height: 20, width: 1, background: "var(--border)" }} />

          <div style={{ display: "flex", gap: 4 }}>
            {["all", "scheduled", "in_progress", "completed"].map((st) => (
              <button
                key={st}
                onClick={() => setStatusFilter(st)}
                style={{
                  padding: "6px 12px",
                  fontSize: 13,
                  borderRadius: 6,
                  border: "1px solid",
                  borderColor: statusFilter === st ? "var(--primary-text)" : "var(--border)",
                  background: statusFilter === st ? "var(--primary-text)" : "#fff",
                  color: statusFilter === st ? "#fff" : "var(--primary-text)",
                  cursor: "pointer",
                  fontWeight: 500,
                }}
              >
                {st === "all" ? "All Status" : st.replace("_", " ")}
              </button>
            ))}
          </div>
        </div>

        <input
          type="text"
          placeholder="Search meetings by title, company..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && loadData()}
          style={{
            padding: "8px 14px",
            fontSize: 13,
            borderRadius: 6,
            border: "1px solid var(--border)",
            minWidth: 260,
          }}
        />
      </div>

      {/* Optional Lead Executive Briefing Banner if embedded in Lead 360 */}
      {leadId && meetings.some((m) => m.has_analysis) && (
        <div
          style={{
            background: "linear-gradient(135deg, #fef2f2 0%, #fff1f2 100%)",
            border: "1px solid #fecaca",
            borderRadius: 12,
            padding: "16px 20px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: 12,
          }}
        >
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
              <span style={{ fontSize: 11, background: "var(--red)", color: "#fff", padding: "2px 8px", borderRadius: 12, fontWeight: 700, textTransform: "uppercase" }}>
                Lead Intelligence
              </span>
              <span style={{ fontSize: 13, fontWeight: 700, color: "#991b1b" }}>
                Executive Meeting Minutes &amp; Takeaways Ready
              </span>
            </div>
            <p style={{ margin: 0, fontSize: 13, color: "#475569" }}>
              Click any analyzed discussion below to expand the full MoM, customer requirements, pain points, and action items.
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              const firstAnalyzed = meetings.find((m) => m.has_analysis);
              if (firstAnalyzed) setSelectedMeetingId(firstAnalyzed.id);
            }}
            style={{
              background: "var(--red)",
              color: "#fff",
              border: "none",
              padding: "8px 16px",
              borderRadius: 6,
              fontSize: 12,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            📋 Open Latest MoM
          </button>
        </div>
      )}

      {/* Full-Width Meetings List with Inline Expandable MoM Under Each Meet */}
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {loading ? (
          <div style={{ padding: 40, textAlign: "center", color: "var(--muted)", background: "var(--surface)", borderRadius: 12, border: "1px solid var(--border)" }}>
            Loading meetings…
          </div>
        ) : meetings.length === 0 ? (
          <div style={{ padding: 48, textAlign: "center", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12 }}>
            <UiIcon name="calendar" size={32} />
            <h3 style={{ margin: "12px 0 4px" }}>No meetings found</h3>
            <p style={{ color: "var(--muted)", margin: 0 }}>Schedule an outreach meeting or create an instant link above.</p>
          </div>
        ) : (
          meetings.map((m) => {
            const isSelected = selectedMeetingId === m.id;
            const isTeams = m.provider === "teams";
            const durationMinutes = m.scheduled_start && m.scheduled_end
              ? Math.max(1, Math.round((new Date(m.scheduled_end).getTime() - new Date(m.scheduled_start).getTime()) / 60000))
              : null;

            return (
              <div
                key={m.id}
                style={{
                  background: "#ffffff",
                  border: `1px solid ${isSelected ? "var(--red)" : "var(--border)"}`,
                  borderLeft: isSelected ? "4px solid var(--red)" : "1px solid var(--border)",
                  borderRadius: 10,
                  boxShadow: isSelected ? "0 8px 20px -4px rgba(210, 15, 50, 0.12)" : "var(--shadow-sm)",
                  transition: "all 0.15s ease",
                  overflow: "hidden",
                }}
              >
                {/* Meeting Card Header Row (Click to toggle MoM inline under this meet) */}
                <div
                  onClick={() => setSelectedMeetingId(isSelected ? null : m.id)}
                  style={{
                    padding: 16,
                    cursor: "pointer",
                    background: isSelected ? "rgba(210, 15, 50, 0.02)" : "#ffffff",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8, flexWrap: "wrap" }}>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4, flexWrap: "wrap" }}>
                        <span
                          style={{
                            padding: "2px 8px",
                            borderRadius: 4,
                            fontSize: 11,
                            fontWeight: 700,
                            background: isTeams ? "#ede9fe" : "#d1fae5",
                            color: isTeams ? "#4f46e5" : "#059669",
                          }}
                        >
                          {isTeams ? "Teams" : "Google Meet"}
                        </span>
                        <span style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", fontWeight: 600 }}>
                          {m.meeting_type}
                        </span>
                        {durationMinutes && (
                          <span style={{ fontSize: 11, background: "#f1f5f9", padding: "1px 6px", borderRadius: 4, color: "#334155", fontWeight: 600 }}>
                            ⏱ {durationMinutes >= 60 ? (durationMinutes % 60 === 0 ? `${durationMinutes / 60}h` : `${Math.floor(durationMinutes / 60)}h ${durationMinutes % 60}m`) : `${durationMinutes}m`}
                          </span>
                        )}
                        {m.company_name && (
                          <span style={{ fontSize: 12, fontWeight: 700, color: "#1e293b" }}>
                            {m.company_name}
                          </span>
                        )}
                      </div>
                      <h4 style={{ margin: "2px 0 6px", fontSize: 16, color: "#0f172a", fontWeight: 600 }}>{m.title}</h4>
                      <p style={{ margin: 0, fontSize: 12, color: "var(--muted)" }}>
                        {m.scheduled_start
                          ? new Date(m.scheduled_start).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })
                          : `Created ${new Date(m.created_at).toLocaleDateString()}`}
                      </p>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <span
                        style={{
                          padding: "4px 10px",
                          borderRadius: 12,
                          fontSize: 11,
                          fontWeight: 700,
                          background: m.status === "completed" ? "#ecfdf5" : m.status === "in_progress" ? "#eff6ff" : m.status === "cancelled" ? "#fee2e2" : "#fffbeb",
                          color: m.status === "completed" ? "#065f46" : m.status === "in_progress" ? "#1e40af" : m.status === "cancelled" ? "#991b1b" : "#92400e",
                          border: `1px solid ${m.status === "completed" ? "#a7f3d0" : m.status === "in_progress" ? "#bfdbfe" : m.status === "cancelled" ? "#fecaca" : "#fde68a"}`,
                          textTransform: "capitalize",
                        }}
                      >
                        {m.status.replace("_", " ")}
                      </span>

                      {/* Expand / Collapse Pill */}
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 4,
                          padding: "4px 10px",
                          borderRadius: 6,
                          fontSize: 12,
                          fontWeight: 600,
                          background: isSelected ? "var(--red)" : "#f1f5f9",
                          color: isSelected ? "#ffffff" : "#475569",
                          border: `1px solid ${isSelected ? "var(--red)" : "#cbd5e1"}`,
                          transition: "all 0.15s ease",
                        }}
                      >
                        {isSelected ? "▲ Fold MoM" : "▼ MoM & Details"}
                      </span>
                    </div>
                  </div>

                  {/* Artifact Indicators Bar */}
                  <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12, marginTop: 12, paddingTop: 10, borderTop: "1px solid #f1f5f9", fontSize: 12 }}>
                    <span style={{ color: m.has_recording ? "#059669" : "#94a3b8", display: "inline-flex", alignItems: "center", gap: 4 }}>
                      🎥 {m.has_recording ? "Recording available" : "No recording"}
                    </span>
                    <span style={{ color: m.has_transcript ? "#4f46e5" : "#94a3b8", display: "inline-flex", alignItems: "center", gap: 4 }}>
                      📝 {m.has_transcript ? "Transcript synced" : "No transcript"}
                    </span>
                    <span style={{ color: m.has_analysis ? "var(--red)" : "#94a3b8", fontWeight: m.has_analysis ? 700 : 400, display: "inline-flex", alignItems: "center", gap: 4 }}>
                      📋 {m.has_analysis ? "MoM & Takeaways Ready" : "MoM Pending"}
                    </span>
                    {m.action_items_count > 0 && (
                      <span style={{ color: "#0284c7", fontWeight: 600, display: "inline-flex", alignItems: "center", gap: 4 }}>
                        ✅ {m.action_items_count} Action {m.action_items_count === 1 ? "Item" : "Items"}
                      </span>
                    )}
                    <span style={{ marginLeft: "auto", color: isSelected ? "var(--red)" : "var(--muted)", fontWeight: 500, fontSize: 11 }}>
                      {isSelected ? "Click to fold ↑" : "Click to view MoM & key discussion points ↓"}
                    </span>
                  </div>
                </div>

                {/* INLINE EXPANDED MOM & MEETING INTELLIGENCE PANEL */}
                {isSelected && (
                  <div
                    style={{
                      borderTop: "1px solid var(--border)",
                      padding: "20px 22px 24px",
                      background: "#f8fafc",
                      display: "flex",
                      flexDirection: "column",
                      gap: 20,
                    }}
                  >
                    {detailLoading || !meetingDetail || meetingDetail.id !== m.id ? (
                      <div style={{ padding: "36px 0", textAlign: "center", color: "var(--muted)" }}>
                        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>Loading MoM &amp; meeting details…</div>
                        <div style={{ fontSize: 12 }}>Retrieving Amazon Bedrock intelligence, transcripts, and action items</div>
                      </div>
                    ) : (
                      <>
                        {/* Control Bar: Join, Sync, Run AI MoM, Reschedule, Cancel, Fold */}
                        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 10, paddingBottom: 14, borderBottom: "1px solid #e2e8f0" }}>
                          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
                            {meetingDetail.join_url && (
                              <a
                                href={meetingDetail.join_url}
                                target="_blank"
                                rel="noreferrer"
                                style={{
                                  background: "#059669",
                                  color: "#fff",
                                  padding: "7px 14px",
                                  borderRadius: 6,
                                  fontSize: 13,
                                  fontWeight: 600,
                                  textDecoration: "none",
                                  display: "inline-flex",
                                  alignItems: "center",
                                  gap: 6,
                                }}
                              >
                                <UiIcon name="external" size={14} /> Join Meeting
                              </a>
                            )}
                            {meetingDetail.join_url && (
                              <button
                                type="button"
                                onClick={() => copyToClipboard(meetingDetail.join_url, "link")}
                                style={{
                                  background: "#fff",
                                  border: "1px solid var(--border)",
                                  color: "#334155",
                                  padding: "7px 12px",
                                  borderRadius: 6,
                                  fontSize: 12,
                                  fontWeight: 600,
                                  cursor: "pointer",
                                }}
                              >
                                {copiedLink ? "✓ Link Copied!" : "📋 Copy Link"}
                              </button>
                            )}
                            <button
                              type="button"
                              disabled={actionLoading}
                              onClick={() => handleSendInvites(meetingDetail.id)}
                              style={{
                                background: "#fff",
                                border: "1px solid var(--border)",
                                color: "#0284c7",
                                padding: "7px 12px",
                                borderRadius: 6,
                                fontSize: 12,
                                fontWeight: 600,
                                cursor: "pointer",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: 5,
                              }}
                            >
                              <UiIcon name="mail" size={14} /> Send / Resend Invites
                            </button>
                            <button
                              type="button"
                              disabled={actionLoading}
                              onClick={() => handleSyncArtifacts(meetingDetail.id)}
                              style={{
                                background: "#fff",
                                border: "1px solid var(--border)",
                                color: "#4f46e5",
                                padding: "7px 12px",
                                borderRadius: 6,
                                fontSize: 12,
                                fontWeight: 600,
                                cursor: "pointer",
                              }}
                            >
                              🔄 Sync Artifacts
                            </button>
                            <button
                              type="button"
                              disabled={actionLoading}
                              onClick={() => handleAnalyzeMeeting(meetingDetail.id)}
                              style={{
                                background: "#fff",
                                border: "1px solid #cbd5e1",
                                color: "#334155",
                                padding: "7px 12px",
                                borderRadius: 6,
                                fontSize: 12,
                                fontWeight: 600,
                                cursor: "pointer",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: 6,
                              }}
                              title="Re-run Bedrock AI analysis to refresh highlights and MoM"
                            >
                              🔄 {actionLoading ? "Analyzing…" : "Refresh AI MoM"}
                            </button>
                          </div>

                          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                            {meetingDetail.status !== "cancelled" && (
                              <>
                                <button
                                  type="button"
                                  onClick={() => {
                                    const startStr = meetingDetail.scheduled_start
                                      ? new Date(meetingDetail.scheduled_start).toISOString().slice(0, 16)
                                      : new Date().toISOString().slice(0, 16);
                                    setRescheduleStart(startStr);
                                    const dur = (meetingDetail.scheduled_start && meetingDetail.scheduled_end)
                                      ? Math.round((new Date(meetingDetail.scheduled_end).getTime() - new Date(meetingDetail.scheduled_start).getTime()) / 60000)
                                      : 30;
                                    setRescheduleDuration(dur > 0 ? dur : 30);
                                    setRescheduleEnd(
                                      meetingDetail.scheduled_end
                                        ? new Date(meetingDetail.scheduled_end).toISOString().slice(0, 16)
                                        : calculateEndTime(startStr, dur > 0 ? dur : 30)
                                    );
                                    setShowRescheduleModal(true);
                                  }}
                                  style={{
                                    background: "#fff",
                                    border: "1px solid #cbd5e1",
                                    color: "#b45309",
                                    padding: "7px 12px",
                                    borderRadius: 6,
                                    fontSize: 12,
                                    fontWeight: 600,
                                    cursor: "pointer",
                                    display: "inline-flex",
                                    alignItems: "center",
                                    gap: 5,
                                  }}
                                >
                                  <UiIcon name="calendar" size={13} /> Reschedule
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setShowCancelModal(true)}
                                  style={{
                                    background: "#fff",
                                    border: "1px solid #fecaca",
                                    color: "#dc2626",
                                    padding: "7px 12px",
                                    borderRadius: 6,
                                    fontSize: 12,
                                    fontWeight: 600,
                                    cursor: "pointer",
                                  }}
                                >
                                  ✕ Cancel
                                </button>
                              </>
                            )}
                            <button
                              type="button"
                              onClick={() => setSelectedMeetingId(null)}
                              style={{
                                background: "#ffffff",
                                border: "1px solid var(--border)",
                                color: "var(--muted)",
                                padding: "6px 12px",
                                borderRadius: 6,
                                fontSize: 12,
                                cursor: "pointer",
                                fontWeight: 600,
                              }}
                            >
                              ▲ Fold
                            </button>
                          </div>
                        </div>

                        {/* Attendees List */}
                        {meetingDetail.participants && meetingDetail.participants.length > 0 && (
                          <div>
                            <span style={{ fontSize: 11, fontWeight: 700, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.5px", display: "block", marginBottom: 6 }}>
                              Meeting Attendees ({meetingDetail.participants.length})
                            </span>
                            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                              {meetingDetail.participants.map((p) => (
                                <div
                                  key={p.id}
                                  style={{
                                    background: "#ffffff",
                                    border: "1px solid #e2e8f0",
                                    borderRadius: 6,
                                    padding: "4px 10px",
                                    fontSize: 12,
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 6,
                                  }}
                                >
                                  <span style={{ fontWeight: 600, color: "#1e293b" }}>{p.display_name || p.email}</span>
                                  <span style={{ fontSize: 10, background: p.participant_role === "organizer" ? "#e0e7ff" : "#f1f5f9", color: p.participant_role === "organizer" ? "#4338ca" : "#64748b", padding: "1px 5px", borderRadius: 4, textTransform: "capitalize" }}>
                                    {p.participant_role}
                                  </span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Minutes of Meeting (MoM) & Executive Summary */}
                        {meetingDetail.analysis ? (
                          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                            {/* MoM Official Record Box */}
                            <div
                              style={{
                                background: "#ffffff",
                                border: "1px solid #cbd5e1",
                                borderRadius: 10,
                                padding: 20,
                                boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
                              }}
                            >
                              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                  <span style={{ fontSize: 15, fontWeight: 700, color: "#0f172a" }}>
                                    📋 Minutes of Meeting (MoM)
                                  </span>
                                  <span style={{ fontSize: 11, background: "#ede9fe", color: "#6b21a8", padding: "2px 8px", borderRadius: 12, fontWeight: 600 }}>
                                    Amazon Bedrock AI Analysis ({Math.round((meetingDetail.analysis.confidence || 0.9) * 100)}% confidence)
                                  </span>
                                </div>
                                <button
                                  type="button"
                                  onClick={() => copyToClipboard(meetingDetail.analysis?.meeting_minutes || "", "mom")}
                                  style={{
                                    padding: "6px 14px",
                                    fontSize: 12,
                                    fontWeight: 600,
                                    borderRadius: 6,
                                    border: "1px solid #cbd5e1",
                                    background: copiedMoM ? "#ecfdf5" : "#ffffff",
                                    color: copiedMoM ? "#065f46" : "#334155",
                                    cursor: "pointer",
                                    display: "inline-flex",
                                    alignItems: "center",
                                    gap: 6,
                                  }}
                                >
                                  {copiedMoM ? "✓ MoM Copied to Clipboard!" : "📋 Copy MoM"}
                                </button>
                              </div>

                              {/* Executive Summary Callout */}
                              {meetingDetail.analysis.executive_summary && (
                                <div style={{ background: "#f8fafc", borderLeft: "4px solid var(--red)", padding: "12px 16px", borderRadius: "0 8px 8px 0", marginBottom: 16 }}>
                                  <div style={{ fontSize: 12, fontWeight: 700, color: "var(--red)", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: 4 }}>
                                    Executive Summary
                                  </div>
                                  <p style={{ margin: 0, fontSize: 13, color: "#1e293b", lineHeight: 1.6 }}>
                                    {meetingDetail.analysis.executive_summary}
                                  </p>
                                </div>
                              )}

                              {/* Formatted MoM Body */}
                              {meetingDetail.analysis.meeting_minutes ? (
                                <div>
                                  <div style={{ fontSize: 12, fontWeight: 600, color: "#64748b", marginBottom: 6 }}>
                                    Official Record &amp; Minutes:
                                  </div>
                                  <div
                                    style={{
                                      maxHeight: 340,
                                      overflowY: "auto",
                                      background: "#fbfcfd",
                                      border: "1px solid #e2e8f0",
                                      borderRadius: 8,
                                      padding: 16,
                                      fontSize: 13,
                                      lineHeight: 1.65,
                                      whiteSpace: "pre-wrap",
                                      color: "#1e293b",
                                      fontFamily: "ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
                                    }}
                                  >
                                    {meetingDetail.analysis.meeting_minutes}
                                  </div>
                                </div>
                              ) : null}
                            </div>

                            {/* Important Discussion Points: Requirements, Pain Points, Decisions */}
                            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 14 }}>
                              {/* Requirements & Key Points */}
                              <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 8, padding: 16 }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
                                  <span style={{ fontSize: 13, fontWeight: 700, color: "#166534" }}>
                                    🎯 Customer Requirements &amp; Scope
                                  </span>
                                  <span style={{ fontSize: 11, background: "#dcfce7", color: "#15803d", padding: "1px 6px", borderRadius: 10, fontWeight: 700 }}>
                                    {meetingDetail.analysis.customer_requirements.length}
                                  </span>
                                </div>
                                {meetingDetail.analysis.customer_requirements.length > 0 ? (
                                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: "#14532d", lineHeight: 1.6 }}>
                                    {meetingDetail.analysis.customer_requirements.map((req, i) => (
                                      <li key={i} style={{ marginBottom: 4 }}>{req}</li>
                                    ))}
                                  </ul>
                                ) : (
                                  <p style={{ margin: 0, fontSize: 12, color: "#166534", opacity: 0.8 }}>No specific technical requirements identified in discussion.</p>
                                )}
                              </div>

                              {/* Customer Pain Points */}
                              <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, padding: 16 }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
                                  <span style={{ fontSize: 13, fontWeight: 700, color: "#991b1b" }}>
                                    ⚠️ Customer Pain Points &amp; Bottlenecks
                                  </span>
                                  <span style={{ fontSize: 11, background: "#fee2e2", color: "#b91c1c", padding: "1px 6px", borderRadius: 10, fontWeight: 700 }}>
                                    {meetingDetail.analysis.customer_pain_points.length}
                                  </span>
                                </div>
                                {meetingDetail.analysis.customer_pain_points.length > 0 ? (
                                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: "#7f1d1d", lineHeight: 1.6 }}>
                                    {meetingDetail.analysis.customer_pain_points.map((p, i) => (
                                      <li key={i} style={{ marginBottom: 4 }}>{p}</li>
                                    ))}
                                  </ul>
                                ) : (
                                  <p style={{ margin: 0, fontSize: 12, color: "#991b1b", opacity: 0.8 }}>No major operational bottlenecks or pain points reported.</p>
                                )}
                              </div>

                              {/* Agreed Decisions & Next Steps */}
                              <div style={{ background: "#eff6ff", border: "1px solid #bfdbfe", borderRadius: 8, padding: 16 }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
                                  <span style={{ fontSize: 13, fontWeight: 700, color: "#1e40af" }}>
                                    🤝 Agreed Decisions &amp; Next Steps
                                  </span>
                                  <span style={{ fontSize: 11, background: "#dbeafe", color: "#1d4ed8", padding: "1px 6px", borderRadius: 10, fontWeight: 700 }}>
                                    {(meetingDetail.analysis.decisions?.length || 0) + (meetingDetail.analysis.next_steps?.length || 0)}
                                  </span>
                                </div>
                                {((meetingDetail.analysis.decisions?.length || 0) + (meetingDetail.analysis.next_steps?.length || 0)) > 0 ? (
                                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: "#1e3a8a", lineHeight: 1.6 }}>
                                    {meetingDetail.analysis.decisions?.map((d, i) => (
                                      <li key={`dec-${i}`} style={{ marginBottom: 4 }}><strong>Decision:</strong> {d}</li>
                                    ))}
                                    {meetingDetail.analysis.next_steps?.map((n, i) => (
                                      <li key={`next-${i}`} style={{ marginBottom: 4 }}><strong>Next Step:</strong> {n}</li>
                                    ))}
                                  </ul>
                                ) : (
                                  <p style={{ margin: 0, fontSize: 12, color: "#1e40af", opacity: 0.8 }}>Follow-up milestone scheduling pending.</p>
                                )}
                              </div>
                            </div>

                            {/* Recommended Sales Stage & Next Action */}
                            {(meetingDetail.analysis.recommended_sales_stage || meetingDetail.analysis.recommended_next_action) && (
                              <div style={{ display: "flex", flexWrap: "wrap", gap: 16, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, padding: "12px 18px", alignItems: "center" }}>
                                {meetingDetail.analysis.recommended_sales_stage && (
                                  <div>
                                    <span style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", fontWeight: 700 }}>
                                      Recommended Stage:
                                    </span>
                                    <span style={{ marginLeft: 6, fontSize: 12, fontWeight: 700, color: "var(--red)" }}>
                                      {meetingDetail.analysis.recommended_sales_stage}
                                    </span>
                                  </div>
                                )}
                                {meetingDetail.analysis.recommended_next_action && (
                                  <div style={{ borderLeft: "1px solid #e2e8f0", paddingLeft: 16 }}>
                                    <span style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", fontWeight: 700 }}>
                                      Next Recommended Action:
                                    </span>
                                    <span style={{ marginLeft: 6, fontSize: 12, fontWeight: 600, color: "#0f172a" }}>
                                      {meetingDetail.analysis.recommended_next_action}
                                    </span>
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        ) : (
                          /* Automatic analysis loading banner */
                          <div
                            style={{
                              background: "#ffffff",
                              border: "1px dashed #cbd5e1",
                              borderRadius: 10,
                              padding: "36px 20px",
                              textAlign: "center",
                            }}
                          >
                            <div style={{ fontSize: 32, marginBottom: 10 }}>🧠</div>
                            <h4 style={{ margin: "0 0 6px", fontSize: 16, color: "#0f172a", fontWeight: 700 }}>
                              Automatically Analyzing Meeting Intelligence &amp; Generating MoM…
                            </h4>
                            <p style={{ margin: "0 auto 12px", fontSize: 13, color: "var(--muted)", maxWidth: 520 }}>
                              Amazon Bedrock is synthesizing discussion points into customer requirements, operational pain points, agreed decisions, and next steps. Highlights appear automatically.
                            </p>
                            <div style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--red)", fontWeight: 600 }}>
                              <span>⚡ Auto-synthesizing insights in background…</span>
                            </div>
                          </div>
                        )}

                        {/* Action Items Checklist */}
                        <div style={{ background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 8, padding: 16 }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                            <span style={{ fontSize: 14, fontWeight: 700, color: "#0f172a" }}>
                              ✅ Action Items &amp; Responsibilities ({meetingDetail.action_items.length})
                            </span>
                          </div>
                          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                            {meetingDetail.action_items.map((item) => (
                              <div
                                key={item.id}
                                onClick={() => handleToggleActionItem(item)}
                                style={{
                                  display: "flex",
                                  alignItems: "center",
                                  justifyContent: "space-between",
                                  padding: "8px 12px",
                                  borderRadius: 6,
                                  background: item.status === "completed" ? "#f8fafc" : "#ffffff",
                                  border: `1px solid ${item.status === "completed" ? "#e2e8f0" : "#cbd5e1"}`,
                                  cursor: "pointer",
                                  transition: "all 0.15s ease",
                                }}
                              >
                                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                                  <input
                                    type="checkbox"
                                    checked={item.status === "completed"}
                                    readOnly
                                    style={{ cursor: "pointer" }}
                                  />
                                  <span
                                    style={{
                                      fontSize: 13,
                                      textDecoration: item.status === "completed" ? "line-through" : "none",
                                      color: item.status === "completed" ? "#94a3b8" : "#0f172a",
                                      fontWeight: item.status === "completed" ? 400 : 500,
                                    }}
                                  >
                                    {item.title}
                                  </span>
                                </div>
                                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                  {item.due_date && (
                                    <span style={{ fontSize: 11, color: "var(--muted)" }}>
                                      Due {new Date(item.due_date).toLocaleDateString()}
                                    </span>
                                  )}
                                  <span style={{ fontSize: 11, background: "#f1f5f9", color: "#475569", padding: "2px 8px", borderRadius: 12, fontWeight: 600 }}>
                                    {item.owner || "Sales Rep"}
                                  </span>
                                </div>
                              </div>
                            ))}

                            {/* Inline Add Action Item */}
                            <form onSubmit={handleAddActionItem} style={{ display: "flex", gap: 8, marginTop: 6 }}>
                              <input
                                type="text"
                                placeholder="Add a new agreed action item..."
                                value={newActionTitle}
                                onChange={(e) => setNewActionTitle(e.target.value)}
                                style={{ flex: 1, padding: "8px 12px", fontSize: 12, borderRadius: 6, border: "1px solid var(--border)" }}
                              />
                              <button
                                type="submit"
                                disabled={!newActionTitle.trim()}
                                style={{ background: "#334155", color: "#fff", border: "none", padding: "8px 16px", borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                              >
                                + Add Item
                              </button>
                            </form>
                          </div>
                        </div>

                        {/* Approved Follow-up Email Outreach */}
                        <div style={{ background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 8, padding: 16 }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                            <span style={{ fontSize: 14, fontWeight: 700, color: "#0f172a" }}>
                              ✉️ Approved Follow-up Email Outreach
                            </span>
                            {followupBody && (
                              <button
                                type="button"
                                onClick={() => copyToClipboard(`Subject: ${followupSubject}

${followupBody}`, "email")}
                                style={{
                                  background: "none",
                                  border: "1px solid var(--border)",
                                  borderRadius: 4,
                                  padding: "3px 8px",
                                  fontSize: 11,
                                  cursor: "pointer",
                                  color: copiedEmailDraft ? "#059669" : "#475569",
                                  fontWeight: 600,
                                }}
                              >
                                {copiedEmailDraft ? "✓ Copied Draft!" : "📋 Copy Draft"}
                              </button>
                            )}
                          </div>
                          <form onSubmit={handleSendFollowup} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                            <div>
                              <label style={{ fontSize: 11, fontWeight: 600, color: "var(--muted)" }}>Recipient Email</label>
                              <input
                                type="email"
                                required
                                value={followupRecipient}
                                onChange={(e) => setFollowupRecipient(e.target.value)}
                                style={{ width: "100%", padding: "6px 10px", fontSize: 12, borderRadius: 6, border: "1px solid var(--border)", marginTop: 2 }}
                              />
                            </div>
                            <div>
                              <label style={{ fontSize: 11, fontWeight: 600, color: "var(--muted)" }}>Subject</label>
                              <input
                                type="text"
                                required
                                value={followupSubject}
                                onChange={(e) => setFollowupSubject(e.target.value)}
                                style={{ width: "100%", padding: "6px 10px", fontSize: 12, borderRadius: 6, border: "1px solid var(--border)", marginTop: 2 }}
                              />
                            </div>
                            <div>
                              <label style={{ fontSize: 11, fontWeight: 600, color: "var(--muted)" }}>Body</label>
                              <textarea
                                rows={4}
                                required
                                value={followupBody}
                                onChange={(e) => setFollowupBody(e.target.value)}
                                style={{ width: "100%", padding: "8px 10px", fontSize: 12, borderRadius: 6, border: "1px solid var(--border)", marginTop: 2, fontFamily: "inherit" }}
                              />
                            </div>
                            <div style={{ display: "flex", justifyContent: "flex-end" }}>
                              <button
                                type="submit"
                                disabled={sendingFollowup || !followupRecipient || !followupSubject || !followupBody}
                                style={{
                                  background: "var(--red)",
                                  color: "#fff",
                                  border: "none",
                                  padding: "8px 18px",
                                  borderRadius: 6,
                                  fontSize: 12,
                                  fontWeight: 600,
                                  cursor: "pointer",
                                }}
                              >
                                {sendingFollowup ? "Sending Follow-up…" : "Send Follow-up Email"}
                              </button>
                            </div>
                          </form>
                        </div>

                        {/* Transcripts & Call Notes */}
                        <div style={{ background: "#ffffff", border: "1px solid #e2e8f0", borderRadius: 8, padding: 16 }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                            <span style={{ fontSize: 14, fontWeight: 700, color: "#0f172a" }}>
                              📝 Dialog, Transcripts &amp; Raw Notes
                            </span>
                            <button
                              type="button"
                              onClick={() => setShowPasteNotes(!showPasteNotes)}
                              style={{
                                background: "none",
                                border: "1px dashed #cbd5e1",
                                borderRadius: 4,
                                padding: "4px 10px",
                                fontSize: 12,
                                color: "#475569",
                                cursor: "pointer",
                                fontWeight: 600,
                              }}
                            >
                              {showPasteNotes ? "Cancel" : "✏️ Paste Call Notes / MoM"}
                            </button>
                          </div>

                          {showPasteNotes && (
                            <div style={{ background: "#f8fafc", border: "1px solid #cbd5e1", borderRadius: 8, padding: 12, marginBottom: 12 }}>
                              <p style={{ margin: "0 0 6px", fontSize: 12, color: "#64748b" }}>
                                Paste meeting transcript or notes from this call to generate / refresh the AI MoM and key takeaways:
                              </p>
                              <textarea
                                rows={5}
                                value={pastedNotesText}
                                onChange={(e) => setPastedNotesText(e.target.value)}
                                placeholder={"Sales Rep: Welcome everyone. What are your main logistics pain points?\nProspect: We are facing warehouse bottlenecks at our Pune plant and need better TMS visibility."}
                                style={{
                                  width: "100%",
                                  padding: 8,
                                  borderRadius: 6,
                                  border: "1px solid #cbd5e1",
                                  fontSize: 12,
                                  fontFamily: "monospace",
                                  resize: "vertical",
                                }}
                              />
                              <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 8 }}>
                                <button
                                  type="button"
                                  disabled={savingNotes || !pastedNotesText.trim()}
                                  onClick={handleSaveNotes}
                                  style={{
                                    background: "var(--red)",
                                    color: "#fff",
                                    border: "none",
                                    borderRadius: 6,
                                    padding: "6px 14px",
                                    fontSize: 12,
                                    fontWeight: 600,
                                    cursor: "pointer",
                                  }}
                                >
                                  {savingNotes ? "Saving & Analyzing..." : "✨ Save Notes & Run AI Intelligence"}
                                </button>
                              </div>
                            </div>
                          )}

                          {meetingDetail.transcripts.length === 0 || meetingDetail.transcripts.every((t) => t.entries.length === 0) ? (
                            <div style={{ background: "#f8fafc", padding: 12, borderRadius: 6, fontSize: 12, color: "var(--muted)" }}>
                              No raw transcript entries stored yet. Use &quot;Sync Artifacts&quot; to fetch automatically from {meetingDetail.provider === "teams" ? "Teams" : "Google Meet"}, or click &quot;✏️ Paste Call Notes / MoM&quot; above.
                            </div>
                          ) : (
                            <div style={{ maxHeight: 200, overflowY: "auto", display: "flex", flexDirection: "column", gap: 6, border: "1px solid #e2e8f0", borderRadius: 6, padding: 10 }}>
                              {meetingDetail.transcripts.flatMap((t) => t.entries).map((e) => (
                                <div key={e.id} style={{ fontSize: 12 }}>
                                  <span style={{ fontWeight: 600, color: "#0f172a" }}>{e.speaker_name}</span>{" "}
                                  <span style={{ fontSize: 10, color: "#94a3b8" }}>{e.start_timestamp || ""}</span>
                                  <p style={{ margin: "2px 0 0", color: "#334155" }}>{e.text}</p>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Create Meeting Modal */}
      {showCreateModal && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(15, 23, 42, 0.6)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 100,
            padding: 20,
          }}
        >
          <div
            style={{
              background: "#fff",
              borderRadius: 12,
              padding: 24,
              maxWidth: 620,
              width: "100%",
              maxHeight: "92vh",
              overflowY: "auto",
              boxShadow: "var(--shadow-lg)",
              display: "flex",
              flexDirection: "column",
              gap: 16,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h2 style={{ margin: 0, fontSize: 20 }}>Schedule / Instant Meeting</h2>
              <button onClick={() => setShowCreateModal(false)} style={{ background: "none", border: "none", fontSize: 18, cursor: "pointer" }}>
                ✕
              </button>
            </div>

            {createdJoinUrl ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 14, textAlign: "center", padding: "16px 0" }}>
                <div style={{ fontSize: 36 }}>🎉</div>
                <h3 style={{ margin: 0 }}>Meeting is Ready!</h3>
                <p style={{ margin: 0, color: "var(--muted)", fontSize: 14 }}>
                  Share this join link with participants:
                </p>
                <div style={{ background: "#f8fafc", padding: 12, borderRadius: 8, border: "1px solid var(--border)", wordBreak: "break-all", fontSize: 13, fontFamily: "monospace" }}>
                  {createdJoinUrl}
                </div>
                <div style={{ display: "flex", gap: 10, justifyContent: "center" }}>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(createdJoinUrl);
                      setSuccessMsg("Copied to clipboard!");
                    }}
                    style={{ background: "#059669", color: "#fff", border: "none", padding: "8px 16px", borderRadius: 6, fontWeight: 600, cursor: "pointer" }}
                  >
                    Copy Link
                  </button>
                  <a
                    href={createdJoinUrl}
                    target="_blank"
                    rel="noreferrer"
                    style={{ background: "var(--red)", color: "#fff", padding: "8px 16px", borderRadius: 6, fontWeight: 600, textDecoration: "none" }}
                  >
                    Open Meeting Now
                  </a>
                </div>
                <button
                  onClick={() => setShowCreateModal(false)}
                  style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", marginTop: 8 }}
                >
                  Close
                </button>
              </div>
            ) : (
              <form onSubmit={handleCreateMeeting} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                {/* Provider Selector */}
                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, color: "var(--muted)" }}>Meeting Provider</label>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 4 }}>
                    <button
                      type="button"
                      onClick={() => setCreateProvider("teams")}
                      style={{
                        padding: 10,
                        borderRadius: 8,
                        border: `2px solid ${createProvider === "teams" ? "#4f46e5" : "var(--border)"}`,
                        background: createProvider === "teams" ? "#ede9fe" : "#fff",
                        color: createProvider === "teams" ? "#4f46e5" : "var(--primary-text)",
                        fontWeight: 600,
                        cursor: "pointer",
                      }}
                    >
                      Microsoft Teams
                    </button>
                    <button
                      type="button"
                      onClick={() => setCreateProvider("google_meet")}
                      style={{
                        padding: 10,
                        borderRadius: 8,
                        border: `2px solid ${createProvider === "google_meet" ? "#059669" : "var(--border)"}`,
                        background: createProvider === "google_meet" ? "#d1fae5" : "#fff",
                        color: createProvider === "google_meet" ? "#059669" : "var(--primary-text)",
                        fontWeight: 600,
                        cursor: "pointer",
                      }}
                    >
                      Google Meet
                    </button>
                  </div>
                </div>

                {/* Meeting Type Selector */}
                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, color: "var(--muted)" }}>Meeting Type</label>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 4 }}>
                    <button
                      type="button"
                      onClick={() => setCreateType("scheduled")}
                      style={{
                        padding: 8,
                        borderRadius: 6,
                        border: `1px solid ${createType === "scheduled" ? "var(--red)" : "var(--border)"}`,
                        background: createType === "scheduled" ? "var(--red-subtle)" : "#fff",
                        color: createType === "scheduled" ? "var(--red)" : "var(--primary-text)",
                        fontWeight: 600,
                        cursor: "pointer",
                      }}
                    >
                      📅 Scheduled Calendar
                    </button>
                    <button
                      type="button"
                      onClick={() => setCreateType("instant")}
                      style={{
                        padding: 8,
                        borderRadius: 6,
                        border: `1px solid ${createType === "instant" ? "var(--red)" : "var(--border)"}`,
                        background: createType === "instant" ? "var(--red-subtle)" : "#fff",
                        color: createType === "instant" ? "var(--red)" : "var(--primary-text)",
                        fontWeight: 600,
                        cursor: "pointer",
                      }}
                    >
                      ⚡ Instant Meeting
                    </button>
                  </div>
                </div>

                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, color: "var(--muted)" }}>Meeting Title</label>
                  <input
                    type="text"
                    required
                    value={createTitle}
                    onChange={(e) => setCreateTitle(e.target.value)}
                    style={{ width: "100%", padding: "8px 12px", borderRadius: 6, border: "1px solid var(--border)", marginTop: 4 }}
                  />
                </div>

                {createType === "scheduled" && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    {/* Meeting Duration Selection */}
                    <div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                        <label style={{ fontSize: 12, fontWeight: 600, color: "var(--muted)" }}>
                          Meeting Length / Duration
                        </label>
                        <span style={{ fontSize: 12, fontWeight: 700, color: "var(--red)" }}>
                          {createDuration >= 60 ? (createDuration % 60 === 0 ? `${createDuration / 60} hour${createDuration > 60 ? "s" : ""}` : `${Math.floor(createDuration / 60)}h ${createDuration % 60}m`) : `${createDuration} mins`}
                        </span>
                      </div>
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                        {[
                          { label: "15 mins", val: 15 },
                          { label: "30 mins", val: 30 },
                          { label: "45 mins", val: 45 },
                          { label: "1 hour", val: 60 },
                          { label: "1.5 hours", val: 90 },
                        ].map((item) => {
                          const isActive = createDuration === item.val;
                          return (
                            <button
                              key={item.val}
                              type="button"
                              onClick={() => handleSelectCreateDuration(item.val)}
                              style={{
                                padding: "6px 14px",
                                borderRadius: 6,
                                fontSize: 12,
                                fontWeight: 600,
                                border: `1px solid ${isActive ? "var(--red)" : "var(--border)"}`,
                                background: isActive ? "var(--red)" : "#ffffff",
                                color: isActive ? "#ffffff" : "var(--primary-text)",
                                cursor: "pointer",
                                transition: "all 0.15s ease",
                              }}
                            >
                              {item.label}
                            </button>
                          );
                        })}
                      </div>
                    </div>

                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                      <div>
                        <label style={{ fontSize: 12, fontWeight: 600, color: "var(--muted)" }}>Start Time</label>
                        <input
                          type="datetime-local"
                          required
                          value={createStart}
                          onChange={(e) => handleCreateStartChange(e.target.value)}
                          style={{ width: "100%", padding: "8px 12px", borderRadius: 6, border: "1px solid var(--border)", marginTop: 4 }}
                        />
                      </div>
                      <div>
                        <label style={{ fontSize: 12, fontWeight: 600, color: "var(--muted)" }}>End Time</label>
                        <input
                          type="datetime-local"
                          required
                          value={createEnd}
                          onChange={(e) => handleCreateEndChange(e.target.value)}
                          style={{ width: "100%", padding: "8px 12px", borderRadius: 6, border: "1px solid var(--border)", marginTop: 4 }}
                        />
                      </div>
                    </div>
                  </div>
                )}

                {/* Participant Selection & Comma-Separated Input */}
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
                    <label style={{ fontSize: 12, fontWeight: 600, color: "var(--muted)" }}>
                      Participant Attendees &amp; Emails
                    </label>
                    {parsedEmails.length > 0 && (
                      <span style={{ fontSize: 11, color: "var(--muted)" }}>
                        {parsedEmails.length} {parsedEmails.length === 1 ? "participant" : "participants"} selected ·{" "}
                        <button
                          type="button"
                          onClick={() => setCreateEmails("")}
                          style={{ background: "none", border: "none", color: "var(--red)", fontSize: 11, cursor: "pointer", padding: 0 }}
                        >
                          Clear all
                        </button>
                      </span>
                    )}
                  </div>

                  {/* Selected Participant Chips */}
                  {parsedEmails.length > 0 && (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, margin: "6px 0 10px", padding: 8, background: "#f8fafc", borderRadius: 8, border: "1px solid var(--border)" }}>
                      {parsedEmails.map((email) => {
                        const matchedContact = contactsList.find((c) => c.email && c.email.toLowerCase() === email.toLowerCase());
                        return (
                          <span
                            key={email}
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: 6,
                              background: "#e0f2fe",
                              color: "#0369a1",
                              fontSize: 12,
                              fontWeight: 500,
                              padding: "3px 8px",
                              borderRadius: 16,
                              border: "1px solid #bae6fd",
                            }}
                          >
                            {matchedContact ? (
                              <span><strong>{matchedContact.name || "Contact"}</strong> <small style={{ opacity: 0.8 }}>({email})</small></span>
                            ) : (
                              <span>{email}</span>
                            )}
                            <button
                              type="button"
                              onClick={() => removeEmail(email)}
                              style={{
                                background: "none",
                                border: "none",
                                color: "#0284c7",
                                cursor: "pointer",
                                padding: 0,
                                fontSize: 12,
                                lineHeight: 1,
                                display: "flex",
                                alignItems: "center",
                              }}
                              aria-label={`Remove ${email}`}
                            >
                              ✕
                            </button>
                          </span>
                        );
                      })}
                    </div>
                  )}

                  {/* Select from Lead Contacts Panel */}
                  <div
                    style={{
                      border: "1px solid var(--border)",
                      borderRadius: 8,
                      padding: 12,
                      background: "#ffffff",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8, gap: 8, flexWrap: "wrap" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 600 }}>
                        <span>👥 Select from Lead Contacts</span>
                      </div>
                      {!leadId && leadsList.length > 0 && (
                        <select
                          value={selectedLeadFilter}
                          onChange={(e) => setSelectedLeadFilter(e.target.value)}
                          style={{
                            fontSize: 12,
                            padding: "4px 8px",
                            borderRadius: 6,
                            border: "1px solid var(--border)",
                            maxWidth: 220,
                            background: "#f8fafc",
                          }}
                        >
                          <option value="">All Companies ({leadsList.length})</option>
                          {leadsList.map((l) => (
                            <option key={l.id} value={l.id}>
                              {l.company_name}
                            </option>
                          ))}
                        </select>
                      )}
                    </div>

                    {/* Search contacts input */}
                    <div style={{ position: "relative", marginBottom: 8 }}>
                      <input
                        type="text"
                        placeholder="Search contacts by name, email, designation..."
                        value={contactSearchQuery}
                        onChange={(e) => setContactSearchQuery(e.target.value)}
                        style={{
                          width: "100%",
                          padding: "6px 10px 6px 28px",
                          borderRadius: 6,
                          border: "1px solid var(--border)",
                          fontSize: 12,
                          background: "#f8fafc",
                        }}
                      />
                      <span style={{ position: "absolute", left: 8, top: "50%", transform: "translateY(-50%)", fontSize: 12, opacity: 0.5 }}>
                        🔍
                      </span>
                      {contactSearchQuery && (
                        <button
                          type="button"
                          onClick={() => setContactSearchQuery("")}
                          style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", fontSize: 12, cursor: "pointer", color: "var(--muted)" }}
                        >
                          ✕
                        </button>
                      )}
                    </div>

                    {/* Quick add primary lead email if available */}
                    {selectedLead && selectedLead.email && (
                      <div style={{ marginBottom: 8 }}>
                        <button
                          type="button"
                          onClick={() => toggleContactEmail(selectedLead.email!)}
                          style={{
                            fontSize: 11,
                            padding: "3px 8px",
                            borderRadius: 12,
                            border: `1px solid ${parsedEmails.includes(selectedLead.email.toLowerCase()) ? "#059669" : "var(--border)"}`,
                            background: parsedEmails.includes(selectedLead.email.toLowerCase()) ? "#d1fae5" : "#f1f5f9",
                            color: parsedEmails.includes(selectedLead.email.toLowerCase()) ? "#065f46" : "#334155",
                            cursor: "pointer",
                            fontWeight: 500,
                          }}
                        >
                          {parsedEmails.includes(selectedLead.email.toLowerCase()) ? "✓ " : "+ "}
                          Add Company Primary Email: {selectedLead.email}
                        </button>
                      </div>
                    )}

                    {/* Contacts list */}
                    <div
                      style={{
                        maxHeight: 140,
                        overflowY: "auto",
                        display: "flex",
                        flexDirection: "column",
                        gap: 4,
                        paddingRight: 4,
                      }}
                    >
                      {loadingContacts ? (
                        <div style={{ padding: 12, textAlign: "center", fontSize: 12, color: "var(--muted)" }}>
                          Loading contacts…
                        </div>
                      ) : filteredContacts.length === 0 ? (
                        <div style={{ padding: "12px 8px", textAlign: "center", fontSize: 12, color: "var(--muted)" }}>
                          {contactsList.length === 0
                            ? "No saved contacts found. You can type participant email(s) below."
                            : "No contacts match your search."}
                        </div>
                      ) : (
                        filteredContacts.map((c) => {
                          const hasEmail = Boolean(c.email && c.email.trim());
                          const isSelected = hasEmail && parsedEmails.includes(c.email!.trim().toLowerCase());
                          return (
                            <label
                              key={c.id}
                              onClick={(e) => {
                                if (!hasEmail) return;
                                e.preventDefault();
                                toggleContactEmail(c.email!);
                              }}
                              style={{
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "space-between",
                                padding: "6px 10px",
                                borderRadius: 6,
                                border: `1px solid ${isSelected ? "#93c5fd" : "#f1f5f9"}`,
                                background: isSelected ? "#eff6ff" : hasEmail ? "#fafafa" : "#f8fafc",
                                cursor: hasEmail ? "pointer" : "default",
                                opacity: hasEmail ? 1 : 0.6,
                                transition: "all 0.15s ease",
                              }}
                            >
                              <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
                                <input
                                  type="checkbox"
                                  checked={isSelected}
                                  disabled={!hasEmail}
                                  onChange={() => {}}
                                  style={{ cursor: hasEmail ? "pointer" : "default" }}
                                />
                                <div style={{ minWidth: 0, textOverflow: "ellipsis", overflow: "hidden", whiteSpace: "nowrap" }}>
                                  <span style={{ fontSize: 12, fontWeight: 600, color: isSelected ? "#1d4ed8" : "inherit" }}>
                                    {c.name || "Unnamed Contact"}
                                  </span>
                                  {c.title && (
                                    <span style={{ fontSize: 11, color: "var(--muted)", marginLeft: 6 }}>
                                      · {c.title}
                                    </span>
                                  )}
                                  {c.company_name && !selectedLeadFilter && (
                                    <span
                                      style={{
                                        fontSize: 10,
                                        background: "#e2e8f0",
                                        color: "#475569",
                                        padding: "1px 6px",
                                        borderRadius: 4,
                                        marginLeft: 6,
                                      }}
                                    >
                                      {c.company_name}
                                    </span>
                                  )}
                                </div>
                              </div>
                              <div style={{ fontSize: 11, color: hasEmail ? (isSelected ? "#1d4ed8" : "var(--muted)") : "#ef4444", flexShrink: 0, marginLeft: 8 }}>
                                {hasEmail ? c.email : "No email"}
                              </div>
                            </label>
                          );
                        })
                      )}
                    </div>
                  </div>

                  {/* Manual Comma-Separated Input */}
                  <div style={{ marginTop: 10 }}>
                    <label style={{ fontSize: 12, fontWeight: 600, color: "var(--muted)", display: "block", marginBottom: 4 }}>
                      Or type / edit participant emails (comma-separated):
                    </label>
                    <input
                      type="text"
                      placeholder="prospect@company.com, colleague@example.com"
                      value={createEmails}
                      onChange={(e) => setCreateEmails(e.target.value)}
                      style={{
                        width: "100%",
                        padding: "8px 12px",
                        borderRadius: 6,
                        border: "1px solid var(--border)",
                        fontSize: 13,
                      }}
                    />
                    <span style={{ fontSize: 11, color: "var(--muted)", marginTop: 4, display: "block" }}>
                      Type single or multiple comma-separated emails. Contacts selected above automatically sync here.
                    </span>
                  </div>
                </div>

                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, color: "var(--muted)" }}>Description / Agenda</label>
                  <textarea
                    rows={2}
                    value={createDescription}
                    onChange={(e) => setCreateDescription(e.target.value)}
                    style={{ width: "100%", padding: "8px 12px", borderRadius: 6, border: "1px solid var(--border)", marginTop: 4 }}
                  />
                </div>

                <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 8 }}>
                  <button
                    type="button"
                    onClick={() => setShowCreateModal(false)}
                    style={{ background: "#f1f5f9", color: "#475569", border: "1px solid var(--border)", padding: "10px 16px", borderRadius: 6, fontWeight: 600, cursor: "pointer" }}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={actionLoading}
                    style={{ background: "var(--red)", color: "#fff", border: "none", padding: "10px 18px", borderRadius: 6, fontWeight: 600, cursor: "pointer" }}
                  >
                    {actionLoading ? "Creating Meeting…" : createType === "instant" ? "Start Instant Meeting" : "Schedule Meeting"}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {/* Reschedule / Postpone Modal */}
      {showRescheduleModal && meetingDetail && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.6)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
          <div style={{ background: "#fff", borderRadius: 12, padding: 24, maxWidth: 480, width: "100%", boxShadow: "0 20px 25px -5px rgba(0,0,0,0.1)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <h3 style={{ margin: 0, fontSize: 18 }}>Postpone / Reschedule Meeting</h3>
              <button onClick={() => setShowRescheduleModal(false)} style={{ background: "none", border: "none", fontSize: 18, cursor: "pointer", color: "var(--muted)" }}>✕</button>
            </div>
            <p style={{ margin: "0 0 16px", fontSize: 13, color: "var(--muted)" }}>
              Select a new date and time. Updated calendar invitations with the Google Meet / Teams link will automatically be emailed to all participants.
            </p>
            <form onSubmit={handleRescheduleSubmit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {/* Reschedule Duration Preset Selector */}
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                  <label style={{ fontSize: 12, fontWeight: 600, color: "var(--muted)" }}>
                    Meeting Length / Duration
                  </label>
                  <span style={{ fontSize: 12, fontWeight: 700, color: "#0284c7" }}>
                    {rescheduleDuration >= 60 ? (rescheduleDuration % 60 === 0 ? `${rescheduleDuration / 60} hour${rescheduleDuration > 60 ? "s" : ""}` : `${Math.floor(rescheduleDuration / 60)}h ${rescheduleDuration % 60}m`) : `${rescheduleDuration} mins`}
                  </span>
                </div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  {[
                    { label: "15 mins", val: 15 },
                    { label: "30 mins", val: 30 },
                    { label: "45 mins", val: 45 },
                    { label: "1 hour", val: 60 },
                    { label: "1.5 hours", val: 90 },
                  ].map((item) => {
                    const isActive = rescheduleDuration === item.val;
                    return (
                      <button
                        key={item.val}
                        type="button"
                        onClick={() => handleSelectRescheduleDuration(item.val)}
                        style={{
                          padding: "6px 12px",
                          borderRadius: 6,
                          fontSize: 12,
                          fontWeight: 600,
                          border: `1px solid ${isActive ? "#0284c7" : "var(--border)"}`,
                          background: isActive ? "#0284c7" : "#ffffff",
                          color: isActive ? "#ffffff" : "var(--primary-text)",
                          cursor: "pointer",
                          transition: "all 0.15s ease",
                        }}
                      >
                        {item.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, color: "var(--muted)" }}>New Start Time *</label>
                  <input
                    type="datetime-local"
                    required
                    value={rescheduleStart}
                    onChange={(e) => handleRescheduleStartChange(e.target.value)}
                    style={{ width: "100%", padding: "8px 12px", borderRadius: 6, border: "1px solid var(--border)", marginTop: 4 }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, color: "var(--muted)" }}>New End Time</label>
                  <input
                    type="datetime-local"
                    value={rescheduleEnd}
                    onChange={(e) => handleRescheduleEndChange(e.target.value)}
                    style={{ width: "100%", padding: "8px 12px", borderRadius: 6, border: "1px solid var(--border)", marginTop: 4 }}
                  />
                </div>
              </div>
              <div>
                <label style={{ fontSize: 12, fontWeight: 600, color: "var(--muted)" }}>Reason / Note for Attendees (Optional)</label>
                <input
                  type="text"
                  placeholder="e.g. Moved to tomorrow per client request"
                  value={rescheduleNote}
                  onChange={(e) => setRescheduleNote(e.target.value)}
                  style={{ width: "100%", padding: "8px 12px", borderRadius: 6, border: "1px solid var(--border)", marginTop: 4 }}
                />
              </div>
              <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 8 }}>
                <button
                  type="button"
                  onClick={() => setShowRescheduleModal(false)}
                  style={{ background: "#f1f5f9", color: "#475569", border: "1px solid var(--border)", padding: "10px 16px", borderRadius: 6, fontWeight: 600, cursor: "pointer" }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={rescheduling || !rescheduleStart}
                  style={{ background: "#0284c7", color: "#fff", border: "none", padding: "10px 18px", borderRadius: 6, fontWeight: 600, cursor: "pointer" }}
                >
                  {rescheduling ? "Updating Calendar…" : "Confirm Reschedule & Send Updates"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Cancel Confirmation Modal */}
      {showCancelModal && meetingDetail && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.6)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
          <div style={{ background: "#fff", borderRadius: 12, padding: 24, maxWidth: 440, width: "100%", boxShadow: "0 20px 25px -5px rgba(0,0,0,0.1)" }}>
            <h3 style={{ margin: "0 0 10px", fontSize: 18, color: "#dc2626" }}>Cancel Meeting</h3>
            <p style={{ margin: "0 0 14px", fontSize: 13, color: "var(--muted)" }}>
              Are you sure you want to cancel <strong>&quot;{meetingDetail.title}&quot;</strong>? This will remove the event from Google/Outlook calendars and send cancellation notices to all participants.
            </p>
            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: "var(--muted)" }}>Cancellation Reason (Optional)</label>
              <input
                type="text"
                placeholder="e.g. Prospect requested cancellation"
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                style={{ width: "100%", padding: "8px 12px", borderRadius: 6, border: "1px solid var(--border)", marginTop: 4 }}
              />
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
              <button
                type="button"
                onClick={() => setShowCancelModal(false)}
                style={{ background: "#f1f5f9", color: "#475569", border: "1px solid var(--border)", padding: "10px 16px", borderRadius: 6, fontWeight: 600, cursor: "pointer" }}
              >
                Keep Meeting
              </button>
              <button
                type="button"
                disabled={cancelling}
                onClick={handleCancelSubmit}
                style={{ background: "#dc2626", color: "#fff", border: "none", padding: "10px 18px", borderRadius: 6, fontWeight: 600, cursor: "pointer" }}
              >
                {cancelling ? "Cancelling…" : "Yes, Cancel Meeting"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
