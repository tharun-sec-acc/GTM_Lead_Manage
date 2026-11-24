import { getApiBase } from "./api-config";

export const API = getApiBase();

export interface ProviderStatus {
  provider: "teams" | "google_meet";
  connected: boolean;
  organizer_email: string | null;
  scopes: string[];
  capabilities: {
    instant_meeting?: boolean;
    scheduled_meeting?: boolean;
    calendar_invitations?: boolean;
    recording_retrieval?: boolean;
    transcript_retrieval?: boolean;
    availability_lookup?: boolean;
  };
}

export interface MeetingSummary {
  id: string;
  provider: "teams" | "google_meet";
  external_meeting_id: string | null;
  organizer_email: string | null;
  lead_id: string | null;
  company_name: string | null;
  contact_id: string | null;
  contact_name: string | null;
  product_id: string | null;
  product_name: string | null;
  title: string;
  description: string | null;
  meeting_type: "instant" | "scheduled";
  join_url: string;
  scheduled_start: string | null;
  scheduled_end: string | null;
  timezone: string;
  status: "scheduled" | "in_progress" | "completed" | "cancelled";
  has_recording: boolean;
  has_transcript: boolean;
  has_analysis: boolean;
  action_items_count: number;
  created_at: string;
}

export interface MeetingParticipant {
  id: string;
  email: string;
  display_name: string | null;
  participant_role: string;
  join_time: string | null;
  leave_time: string | null;
}

export interface MeetingRecording {
  id: string;
  filename: string;
  mime_type: string;
  duration_seconds: number | null;
  download_url: string | null;
  processing_status: string;
}

export interface MeetingTranscriptEntry {
  id: string;
  speaker_name: string;
  text: string;
  start_timestamp: string | null;
  end_timestamp: string | null;
}

export interface MeetingTranscript {
  id: string;
  language: string;
  source: string;
  processing_status: string;
  entries: MeetingTranscriptEntry[];
}

export interface MeetingActionItem {
  id: string;
  meeting_id: string;
  lead_id: string | null;
  title: string;
  description: string | null;
  owner: string | null;
  due_date: string | null;
  priority: "low" | "medium" | "high";
  status: "open" | "in_progress" | "completed" | "cancelled";
  source_timestamp: string | null;
  created_at: string;
}

export interface MeetingAnalysis {
  id: string;
  analysis_version: string;
  executive_summary: string;
  customer_requirements: string[];
  customer_pain_points: string[];
  technical_requirements: string[];
  objections: string[];
  buying_signals: string[];
  decisions: string[];
  next_steps: string[];
  meeting_minutes: string;
  followup_draft_subject: string | null;
  followup_draft_body: string | null;
  recommended_sales_stage: string | null;
  recommended_next_action: string | null;
  analysis_status: string;
  confidence: number;
  created_at: string;
}

export interface MeetingDetail extends MeetingSummary {
  actual_start: string | null;
  actual_end: string | null;
  provider_metadata: Record<string, any>;
  participants: MeetingParticipant[];
  recordings: MeetingRecording[];
  transcripts: MeetingTranscript[];
  analysis: MeetingAnalysis | null;
  action_items: MeetingActionItem[];
  updated_at: string;
}

export interface MeetingCreateInput {
  provider: "teams" | "google_meet";
  meeting_type: "instant" | "scheduled";
  title: string;
  description?: string;
  lead_id?: string;
  contact_id?: string;
  product_id?: string;
  scheduled_start?: string;
  scheduled_end?: string;
  timezone?: string;
  participant_emails?: string[];
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(API + path, { cache: "no-store", ...options });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : `Request failed (${res.status}).`);
  }
  return res.json() as Promise<T>;
}

export async function fetchProviderStatuses(): Promise<ProviderStatus[]> {
  return request<ProviderStatus[]>("/meetings/providers/status");
}

export async function fetchMeetings(params?: {
  provider?: string;
  status?: string;
  lead_id?: string;
  product_id?: string;
  search?: string;
}): Promise<MeetingSummary[]> {
  const query = new URLSearchParams();
  if (params?.provider) query.set("provider", params.provider);
  if (params?.status) query.set("status", params.status);
  if (params?.lead_id) query.set("lead_id", params.lead_id);
  if (params?.product_id) query.set("product_id", params.product_id);
  if (params?.search) query.set("search", params.search);
  const qStr = query.toString();
  return request<MeetingSummary[]>(`/meetings${qStr ? `?${qStr}` : ""}`);
}

export async function fetchMeetingDetail(meetingId: string): Promise<MeetingDetail> {
  return request<MeetingDetail>(`/meetings/${meetingId}`);
}

export async function createMeeting(input: MeetingCreateInput): Promise<MeetingDetail> {
  return request<MeetingDetail>("/meetings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export async function syncMeetingArtifacts(meetingId: string): Promise<{ sync_result: any; meeting: MeetingDetail }> {
  return request<{ sync_result: any; meeting: MeetingDetail }>(`/meetings/${meetingId}/sync-artifacts`, {
    method: "POST",
  });
}

export async function sendMeetingInvites(meetingId: string): Promise<{ success: boolean; message: string; attendee_count?: number }> {
  return request<{ success: boolean; message: string; attendee_count?: number }>(`/meetings/${meetingId}/send-invites`, {
    method: "POST",
  });
}

export async function addManualTranscript(meetingId: string, raw_text: string): Promise<MeetingDetail> {
  return request<MeetingDetail>(`/meetings/${meetingId}/transcript`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ raw_text }),
  });
}

export async function rescheduleMeeting(
  meetingId: string,
  payload: { new_start: string; new_end: string; timezone?: string; note?: string }
): Promise<MeetingDetail> {
  return request<MeetingDetail>(`/meetings/${meetingId}/reschedule`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function cancelMeeting(
  meetingId: string,
  reason?: string
): Promise<MeetingDetail> {
  return request<MeetingDetail>(`/meetings/${meetingId}/cancel`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });
}

export async function analyzeMeeting(meetingId: string): Promise<MeetingDetail> {
  return request<MeetingDetail>(`/meetings/${meetingId}/analyze`, {
    method: "POST",
  });
}

export async function addMeetingActionItem(
  meetingId: string,
  item: { title: string; description?: string; owner?: string; due_date?: string; priority?: string }
): Promise<MeetingActionItem> {
  return request<MeetingActionItem>(`/meetings/${meetingId}/action-items`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(item),
  });
}

export async function updateMeetingActionItem(
  itemId: string,
  update: { status?: string; priority?: string; title?: string }
): Promise<MeetingActionItem> {
  return request<MeetingActionItem>(`/meetings/action-items/${itemId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(update),
  });
}

export async function sendFollowupDraft(
  meetingId: string,
  payload: { recipient: string; subject: string; body: string }
): Promise<{ status: string; recipient: string; message_id: string }> {
  return request<{ status: string; recipient: string; message_id: string }>(`/meetings/${meetingId}/send-followup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
