export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface ZohoConnectionStatus {
  is_connected: boolean;
  connected?: boolean;
  org_id?: string | null;
  zoho_org_id?: string | null;
  org_name?: string | null;
  zoho_org_name?: string | null;
  user_email?: string | null;
  zoho_user_email?: string | null;
  api_domain?: string | null;
  accounts_domain?: string | null;
  crm_api_version?: string;
  sync_direction?: string;
  last_synced_at?: string | null;
  last_error?: string | null;
  scopes?: string[];
}

export interface ZohoVerifyResult {
  success: boolean;
  is_connected: boolean;
  message: string;
  org_id?: string;
  org_name?: string;
  user_email?: string;
  api_domain?: string;
  crm_api_version?: string;
  time_zone?: string;
  trial_type?: string;
  error?: string;
}

export interface ZohoFieldMappingItem {
  id: string;
  zoho_module: string;
  gtm_entity: string;
  zoho_field: string;
  gtm_field: string;
  field_type?: string;
  sync_direction: "bidirectional" | "gtm_to_zoho" | "zoho_to_gtm" | "outbound" | "inbound";
  conflict_policy: "crm_wins" | "gtm_wins" | "newest_wins" | "zoho_wins" | "manual" | "latest_timestamp";
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ZohoSyncJobItem {
  id: string;
  job_type: string;
  status: string;
  records_processed: number;
  records_succeeded: number;
  records_failed: number;
  error_summary?: string | null;
  details?: Record<string, any>;
  started_at: string;
  finished_at?: string | null;
}

export interface ZohoSyncLogItem {
  id: string;
  job_id?: string | null;
  entity_type: string;
  entity_id?: string | null;
  zoho_module: string;
  zoho_record_id?: string | null;
  action: string;
  status: string;
  message?: string | null;
  created_at: string;
}

export interface ZohoSyncConflictItem {
  id: string;
  record_mapping_id?: string | null;
  gtm_entity_type: string;
  gtm_entity_id: string;
  zoho_module: string;
  zoho_record_id: string;
  field_name: string;
  gtm_value?: string | null;
  zoho_value?: string | null;
  resolution_status: string;
  resolved_by?: string | null;
  created_at: string;
  resolved_at?: string | null;
}

export async function fetchZohoConnection(): Promise<ZohoConnectionStatus> {
  const res = await fetch(`${API}/zoho/connection?t=${Date.now()}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch Zoho connection status");
  return res.json();
}

export async function verifyZohoConnection(): Promise<ZohoVerifyResult> {
  const res = await fetch(`${API}/zoho/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    throw new Error(err?.detail || "Failed to verify Zoho connection");
  }
  return res.json();
}

export async function fetchZohoAuthUrl(origin?: string): Promise<{ authorization_url: string; state: string }> {
  const base = origin || (typeof window !== "undefined" ? window.location.origin : "http://localhost:3000");
  const res = await fetch(`${API}/zoho/oauth/authorize?redirect_frontend=${encodeURIComponent(base + "/zoho")}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to generate Zoho OAuth authorization URL");
  return res.json();
}

export async function disconnectZoho(): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${API}/zoho/disconnect`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to disconnect Zoho CRM");
  return res.json();
}

export async function fetchZohoFieldMappings(module?: string): Promise<ZohoFieldMappingItem[]> {
  const url = module ? `${API}/zoho/mappings?module=${encodeURIComponent(module)}` : `${API}/zoho/mappings`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch field mappings");
  return res.json();
}

export async function updateZohoFieldMapping(
  id: string,
  update: Partial<Pick<ZohoFieldMappingItem, "sync_direction" | "conflict_policy" | "is_active" | "zoho_field">>
): Promise<ZohoFieldMappingItem> {
  const res = await fetch(`${API}/zoho/mappings/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(update),
  });
  if (!res.ok) throw new Error("Failed to update field mapping");
  return res.json();
}

export async function triggerZohoSync(
  direction: "outbound" | "inbound" | "reconcile",
  moduleName?: string
): Promise<{ success: boolean; job_id: string; [key: string]: any }> {
  const res = await fetch(`${API}/zoho/sync`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ direction, module: moduleName }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    throw new Error(err?.detail || "Failed to trigger sync");
  }
  return res.json();
}

export async function fetchZohoSyncJobs(): Promise<ZohoSyncJobItem[]> {
  const res = await fetch(`${API}/zoho/sync/jobs`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch sync jobs");
  return res.json();
}

export async function fetchZohoSyncLogs(limit: number = 50): Promise<ZohoSyncLogItem[]> {
  const res = await fetch(`${API}/zoho/sync/logs?limit=${limit}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch sync logs");
  return res.json();
}

export async function fetchZohoConflicts(): Promise<ZohoSyncConflictItem[]> {
  const res = await fetch(`${API}/zoho/conflicts`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch sync conflicts");
  return res.json();
}

export async function resolveZohoConflict(
  id: string,
  resolution: "use_gtm" | "use_zoho" | "custom",
  customValue?: string
): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${API}/zoho/conflicts/${id}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resolution, custom_value: customValue }),
  });
  if (!res.ok) throw new Error("Failed to resolve conflict");
  return res.json();
}
