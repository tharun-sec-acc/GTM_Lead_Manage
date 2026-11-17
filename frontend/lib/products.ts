export const API = "http://localhost:8000";

export interface Product {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  short_description: string | null;
  logo_url: string | null;
  primary_color: string | null;
  status: "active" | "archived";
  product_context: string | null;
  value_proposition: string | null;
  target_industries: string[];
  created_at: string;
  updated_at: string;
}

export interface ProductLead {
  id: string;
  product_id: string;
  lead_id: string;
  stage: string;
  priority: string;
  status: string;
  owner_id: string | null;
  sales_notes: string | null;
  associated_at: string;
  updated_at: string;
  company_name?: string;
  domain?: string | null;
  email?: string | null;
  industry?: string | null;
  location?: string | null;
  designation?: string | null;
  revenue?: string | null;
  phone?: string | null;
  active_contact_count?: number;
}

export interface LeadSummary {
  id: string;
  company_name: string;
  domain: string | null;
  email: string | null;
  industry: string | null;
  location: string | null;
  designation: string | null;
  revenue: string | null;
  phone: string | null;
}

export interface ProductContact {
  id: string;
  lead_id: string;
  company_name: string;
  name: string | null;
  title: string | null;
  email: string | null;
  department: string | null;
  seniority: string | null;
  location: string | null;
  linkedin_url: string | null;
  is_key_decision_maker: boolean;
  verification_status: string;
  source: string;
  retrieved_at: string;
}

export interface ProductCampaign {
  id: string;
  name: string;
  mode: "manual" | "automatic";
  delays: number[];
  status: string;
  sequence_approved_at: string | null;
  product_id: string;
}

export interface ProductBatch {
  id: string;
  filename: string;
  status: string;
  error: string | null;
  product_id: string | null;
}

export interface ProductResearchJob {
  id: string;
  company_id: string;
  lead_id: string | null;
  status: string;
  stage: string;
  depth: string;
  progress: number;
  facts_count: number;
  sources_count: number;
  error: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface ProductSalesTask {
  id: string;
  reply_id: string;
  title: string;
  status: string;
  created_at: string;
  completed_at: string | null;
  lead_id: string;
  company_name: string;
  sender: string | null;
  subject: string | null;
  classification: string | null;
}

export interface ProductOverview {
  product_id: string;
  associated_companies: number;
  active_contacts: number;
  campaigns_count: number;
  messages_by_status: Record<string, number>;
  replies_count: number;
  meeting_tasks_open: number;
  contacted_companies: number;
  contacted_company_percent: number | null;
  research_jobs: number;
  research_jobs_completed: number;
  research_jobs_active: number;
  research_jobs_failed: number;
  pipeline: Record<string, number>;
  date_range: { start: string | null; end: string | null };
  metrics_note: string;
}

export interface GlobalOverview {
  unique_companies: number;
  product_associations: number;
  product_associated_companies: number;
  unique_contacts: number;
  product_associated_contacts: number;
  total_campaigns: number;
  total_messages: number;
  total_replies: number;
  products_count: number;
  per_product: Array<{
    product_id: string;
    product_name: string;
    slug: string;
    status: string;
    associated_companies: number;
    active_contacts: number;
    campaigns_count: number;
  }>;
  date_range: { start: string | null; end: string | null };
  metrics_note: string;
}

async function apiRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(API + path, { cache: "no-store", ...options });
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail = body && typeof body === "object" && "detail" in body ? body.detail : null;
    throw new Error(typeof detail === "string" ? detail : `Request failed (${response.status}).`);
  }
  return response.json() as Promise<T>;
}

export async function fetchProducts(status?: string): Promise<Product[]> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  return apiRequest<Product[]>(`/products${qs}`);
}

export async function fetchProduct(productId: string): Promise<Product> {
  return apiRequest<Product>(`/products/${productId}`);
}

export async function fetchProductBySlug(slug: string, products: Product[]): Promise<Product | undefined> {
  return products.find((p) => p.slug === slug);
}

export async function fetchProductOverview(productId: string, startDate?: string, endDate?: string): Promise<ProductOverview> {
  const params = new URLSearchParams();
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  const qs = params.toString() ? `?${params.toString()}` : "";
  return apiRequest<ProductOverview>(`/products/${productId}/overview${qs}`);
}

export async function fetchGlobalOverview(startDate?: string, endDate?: string): Promise<GlobalOverview> {
  const params = new URLSearchParams();
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  const qs = params.toString() ? `?${params.toString()}` : "";
  return apiRequest<GlobalOverview>(`/overview${qs}`);
}

export async function fetchLeads(): Promise<LeadSummary[]> {
  return apiRequest<LeadSummary[]>("/leads");
}

export async function fetchProductLeads(productId: string): Promise<ProductLead[]> {
  return apiRequest<ProductLead[]>(`/products/${productId}/leads`);
}

export async function associateProductLead(
  productId: string,
  leadId: string,
  patch: Partial<Pick<ProductLead, "stage" | "priority" | "sales_notes">> = {},
): Promise<ProductLead> {
  return apiRequest<ProductLead>(`/products/${productId}/leads`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lead_id: leadId, ...patch }),
  });
}

export async function updateProductLead(
  productId: string,
  leadId: string,
  patch: Partial<Pick<ProductLead, "stage" | "priority" | "status" | "sales_notes">>,
): Promise<ProductLead> {
  return apiRequest<ProductLead>(`/products/${productId}/leads/${leadId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
}

export async function removeProductLead(productId: string, leadId: string): Promise<void> {
  await fetch(`${API}/products/${productId}/leads/${leadId}`, { method: "DELETE" });
}

export async function fetchProductContacts(productId: string): Promise<ProductContact[]> {
  return apiRequest<ProductContact[]>(`/products/${productId}/contacts`);
}

export async function fetchProductCampaigns(productId: string): Promise<ProductCampaign[]> {
  return apiRequest<ProductCampaign[]>(`/products/${productId}/campaigns`);
}

export async function createProductCampaign(
  productId: string,
  data: { name: string; mode: "manual" | "automatic"; delays: number[] },
): Promise<ProductCampaign> {
  return apiRequest<ProductCampaign>(`/products/${productId}/campaigns`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function fetchProductBatches(productId: string): Promise<ProductBatch[]> {
  return apiRequest<ProductBatch[]>(`/products/${productId}/batches`);
}

export async function fetchProductResearch(productId: string): Promise<ProductResearchJob[]> {
  return apiRequest<ProductResearchJob[]>(`/products/${productId}/research`);
}

export async function fetchProductSalesTasks(productId: string): Promise<ProductSalesTask[]> {
  return apiRequest<ProductSalesTask[]>(`/products/${productId}/sales-tasks`);
}

export async function createProduct(data: Partial<Product>): Promise<Product> {
  return apiRequest<Product>("/products", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function updateProductStatus(productId: string, status: "active" | "archived"): Promise<Product> {
  return apiRequest<Product>(`/products/${productId}/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
}