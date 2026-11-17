import { API } from "./products";

export type TemplateType =
  | "initial" | "followup" | "product_intro" | "meeting_request" | "post_meeting" | "custom";

export interface EmailTemplate {
  id: string;
  product_id: string | null;
  parent_template_id: string | null;
  name: string;
  type: TemplateType;
  subject_template: string;
  body_template: string;
  variables: string[];
  is_active: boolean;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface TemplateVersion {
  id: string;
  version: number;
  subject_template: string;
  body_template: string;
  variables: string[];
  created_at: string;
}

export interface TemplatePreview {
  subject: string;
  body: string;
}

export const TEMPLATE_VARIABLES = [
  "company_name", "company_domain", "company_industry",
  "contact_first_name", "contact_last_name", "contact_title",
  "contact_department", "contact_seniority",
  "product_name", "product_value_proposition",
  "reviewed_research_facts", "product_opportunity_summary",
  "sender_name", "sender_signature",
] as const;

export const TEMPLATE_TYPES: TemplateType[] = [
  "initial", "followup", "product_intro", "meeting_request", "post_meeting", "custom",
];

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(API + path, { cache: "no-store", ...options });
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    if (body && typeof body === "object" && "unknown_variables" in body) {
      const unknown = (body as { unknown_variables?: string[] }).unknown_variables ?? [];
      throw new Error(`Unknown template variables: ${unknown.join(", ")}.`);
    }
    const detail = body && typeof body === "object" && "detail" in body ? body.detail : null;
    throw new Error(typeof detail === "string" ? detail : `Request failed (${response.status}).`);
  }
  return response.json() as Promise<T>;
}

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

/** productId "global" lists templates with no product owner. */
export async function fetchTemplates(productId?: string | null): Promise<EmailTemplate[]> {
  const qs = productId ? `?product_id=${encodeURIComponent(productId)}` : "";
  return request<EmailTemplate[]>(`/templates${qs}`);
}

export async function fetchTemplateVersions(templateId: string): Promise<TemplateVersion[]> {
  return request<TemplateVersion[]>(`/templates/${templateId}/versions`);
}

export async function createTemplate(data: {
  product_id?: string | null;
  parent_template_id?: string | null;
  name: string;
  type: TemplateType;
  subject_template: string;
  body_template: string;
}): Promise<EmailTemplate> {
  return request<EmailTemplate>("/templates", json("POST", data));
}

export async function updateTemplate(
  templateId: string,
  data: { name?: string; type?: TemplateType; subject_template?: string; body_template?: string },
): Promise<EmailTemplate> {
  return request<EmailTemplate>(`/templates/${templateId}`, json("PUT", data));
}

export async function previewTemplate(
  templateId: string,
  overrides?: { subject_template?: string; body_template?: string },
): Promise<TemplatePreview> {
  return request<TemplatePreview>(`/templates/${templateId}/preview`, json("POST", overrides ?? {}));
}
