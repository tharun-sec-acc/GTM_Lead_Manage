export const API = "http://localhost:8000";

export async function intelligenceRequest<T>(path: string, method = "GET", data?: unknown): Promise<T> {
  const response = await fetch(API + path, {
    method, cache: "no-store",
    ...(data === undefined ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }),
  });
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail = body && typeof body === "object" && "detail" in body ? body.detail : null;
    throw new Error(typeof detail === "string" ? detail : `Request failed (${response.status}). Check the submitted fields and integration configuration.`);
  }
  return response.json() as Promise<T>;
}

export type ResearchStatus = { enabled: boolean; search_provider: string; search_configured: boolean; model_configured: boolean; note: string };
export type JobSummary = {
  id: string; company_id: string; company_name: string; domain: string; lead_id: string | null;
  status: string; progress: number; created_at: string; updated_at: string; report_id: string | null;
};
export type AgentRun = {
  id: string; agent: string; status: string; progress: number; error: string | null;
  retry_count: number; started_at: string | null; finished_at: string | null;
};
export type ResearchJob = JobSummary & {
  stage: string; error: string | null; sources_count: number; pages_processed: number;
  facts_count: number; agents: AgentRun[];
};
export type Citation = {
  source_id: string; url: string; title: string; excerpt: string; page_number: number | null;
  retrieved_at: string; published_at: string | null; reliability: string;
};
export type ResearchFact = {
  id: string; category: string; field_name: string; value: string; unit: string | null;
  currency: string | null; reporting_period: string | null; entity_scope: string | null;
  verification_status: string; confidence: number | null; citations: Citation[];
};
export type ResearchSource = {
  id: string; url: string; title: string; domain: string; publisher: string | null;
  published_at: string | null; retrieved_at: string; content_hash: string; category: string;
  reliability: string; retrieval_method: string; excerpt: string;
};
export type ResearchReport = {
  id: string; company_id: string; job_id: string; version: number; created_at: string; summary: string;
  sections: { category: string; title: string; status: string; fact_ids: string[]; text: string }[];
  limitations: string[];
};
export type Page<T> = { items: T[]; total: number };
export type InferenceProfile = { id: string; arn: string; name: string; type: string; regions: string[] };

export function label(value: string) {
  return value.replaceAll("_", " ").replace(/^\w/, letter => letter.toUpperCase());
}

export function statusTone(status: string) {
  if (["completed", "succeeded", "verified", "active"].includes(status)) return "positive";
  if (["failed", "conflicting", "error"].includes(status)) return "danger";
  if (["running", "processing", "queued", "pending", "reported", "partially_verified", "partial"].includes(status)) return "attention";
  return "neutral";
}

export function displayDate(value: string | null | undefined) {
  if (!value) return "Not available";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Invalid date" : date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}
