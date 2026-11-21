from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


class ZohoConnectionStatus(BaseModel):
    is_connected: bool
    connected: bool | None = None
    org_id: str | None = None
    zoho_org_id: str | None = None
    org_name: str | None = None
    zoho_org_name: str | None = None
    user_email: str | None = None
    zoho_user_email: str | None = None
    user_zuid: str | None = None
    accounts_domain: str | None = None
    api_domain: str | None = None
    crm_api_version: str = "v8"
    sync_direction: str = "bidirectional"
    last_synced_at: datetime | None = None
    last_error: str | None = None
    scopes: list[str] = Field(default_factory=list)


class ZohoAuthUrlResponse(BaseModel):
    authorization_url: str
    state: str
    accounts_domain: str


class ZohoSyncTriggerRequest(BaseModel):
    direction: Literal["outbound", "inbound", "reconcile"] = "outbound"
    module: str | None = None  # Accounts, Contacts, Leads, Deals, Tasks, Events, Notes
    entity_id: str | None = None
    force_full: bool = False


class ZohoSyncJobResponse(BaseModel):
    id: str
    job_type: str
    status: str
    records_processed: int
    records_succeeded: int
    records_failed: int
    started_at: datetime
    finished_at: datetime | None = None
    error_summary: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ZohoSyncLogResponse(BaseModel):
    id: str
    job_id: str | None = None
    entity_type: str
    entity_id: str | None = None
    zoho_module: str
    zoho_record_id: str | None = None
    action: str
    status: str
    message: str | None = None
    created_at: datetime


class ZohoFieldMappingItem(BaseModel):
    id: str
    zoho_module: str
    gtm_field: str
    zoho_field: str
    field_type: str = "string"
    sync_direction: str = "bidirectional"
    conflict_policy: str = "crm_wins"
    is_custom: bool = False
    is_active: bool = True


class ZohoFieldMappingUpdate(BaseModel):
    zoho_field: str | None = None
    sync_direction: Literal["bidirectional", "gtm_to_zoho", "zoho_to_gtm"] | None = None
    conflict_policy: Literal["crm_wins", "gtm_wins", "newest_wins"] | None = None
    is_active: bool | None = None


class ZohoConflictItem(BaseModel):
    id: str
    record_mapping_id: str | None = None
    gtm_entity_type: str
    gtm_entity_id: str
    zoho_module: str
    zoho_record_id: str
    field_name: str
    gtm_value: str | None = None
    zoho_value: str | None = None
    resolution_status: str
    created_at: datetime


class ZohoConflictResolveRequest(BaseModel):
    resolution: Literal["use_gtm", "use_zoho", "custom"]
    custom_value: str | None = None


class ZohoModuleMetadata(BaseModel):
    module_name: str
    api_name: str
    singular_label: str
    plural_label: str
    custom: bool = False


class ZohoFieldMetadata(BaseModel):
    api_name: str
    display_label: str
    data_type: str
    required: bool = False
    length: int | None = None
    pick_list_values: list[str] = Field(default_factory=list)
