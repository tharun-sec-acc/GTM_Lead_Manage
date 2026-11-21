import hashlib
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.zoho.models import ZohoConnection, ZohoSyncJob, ZohoSyncLog, ZohoSyncConflict, ZohoRecordMapping
from app.zoho.schemas import (
    ZohoConnectionStatus, ZohoAuthUrlResponse, ZohoSyncTriggerRequest,
    ZohoSyncJobResponse, ZohoSyncLogResponse, ZohoFieldMappingItem,
    ZohoFieldMappingUpdate, ZohoConflictItem, ZohoConflictResolveRequest
)
from app.zoho.service import ZohoService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/zoho", tags=["zoho"])


def _get_browser_hash(request: Request) -> str:
    ua = request.headers.get("user-agent", "")
    ip = request.client.host if request.client else ""
    return hashlib.sha256(f"{ua}:{ip}".encode("utf-8")).hexdigest()


@router.get("/oauth/authorize", response_model=ZohoAuthUrlResponse)
def get_zoho_auth_url(
    accounts_domain: Optional[str] = Query(default=None),
    request: Request = None,
    session: Session = Depends(get_db),
):
    """Generates a secure authorization URL for Zoho CRM OAuth 2.0."""
    service = ZohoService(session)
    browser_hash = _get_browser_hash(request)
    try:
        auth_url, state = service.generate_authorization_url(browser_hash, accounts_domain=accounts_domain)
        session.commit()
        return ZohoAuthUrlResponse(
            authorization_url=auth_url,
            state=state,
            accounts_domain=accounts_domain or "https://accounts.zoho.in",
        )
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/oauth/callback")
def zoho_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    request: Request = None,
    session: Session = Depends(get_db),
):
    """Handles OAuth 2.0 callback, exchanges auth code for tokens, and connects organization."""
    service = ZohoService(session)
    browser_hash = _get_browser_hash(request)
    try:
        conn = service.handle_oauth_callback(code, state, browser_hash)
        session.commit()
        # Redirect to frontend Zoho settings page
        return RedirectResponse(url="http://localhost:3000/zoho?connected=true")
    except Exception as exc:
        session.rollback()
        logger.error("Zoho OAuth callback failed: %s", exc)
        return RedirectResponse(url=f"http://localhost:3000/zoho?error={str(exc)}")


@router.get("/connection", response_model=ZohoConnectionStatus)
def get_connection(response: Response, session: Session = Depends(get_db)):
    """Retrieves current Zoho CRM connection status and organization details."""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    service = ZohoService(session)
    return service.get_connection_status()


@router.post("/disconnect")
def disconnect_crm(session: Session = Depends(get_db)):
    """Disconnects and deactivates Zoho CRM integration."""
    service = ZohoService(session)
    service.disconnect_crm()
    session.commit()
    return {"message": "Zoho CRM disconnected successfully."}


@router.post("/verify")
def verify_connection(session: Session = Depends(get_db)):
    """Actively verifies live connection to Zoho CRM API v8 and returns org metadata."""
    service = ZohoService(session)
    result = service.verify_connection()
    session.commit()
    return result


@router.get("/modules")
def get_modules(session: Session = Depends(get_db)):
    """Discovers active CRM modules from Zoho API."""
    service = ZohoService(session)
    try:
        return service.client.get_modules()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch Zoho modules: {exc}") from exc


@router.get("/modules/{module}/fields")
def get_module_fields(module: str, session: Session = Depends(get_db)):
    """Discovers fields and picklist values for a given Zoho module."""
    service = ZohoService(session)
    try:
        return service.client.get_module_fields(module)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch module fields: {exc}") from exc


@router.get("/mappings", response_model=List[ZohoFieldMappingItem])
def get_field_mappings(module: Optional[str] = Query(default=None), session: Session = Depends(get_db)):
    """Returns configured field mappings for modules."""
    service = ZohoService(session)
    mappings = service.get_field_mappings(module=module)
    session.commit()
    return [
        ZohoFieldMappingItem(
            id=m.id,
            zoho_module=m.zoho_module,
            gtm_field=m.gtm_field,
            zoho_field=m.zoho_field,
            field_type=m.field_type,
            sync_direction=m.sync_direction,
            conflict_policy=m.conflict_policy,
            is_custom=m.is_custom,
            is_active=m.is_active,
        )
        for m in mappings
    ]


@router.patch("/mappings/{mapping_id}", response_model=ZohoFieldMappingItem)
def update_field_mapping(
    mapping_id: str,
    updates: ZohoFieldMappingUpdate,
    session: Session = Depends(get_db),
):
    """Updates field mapping rules or conflict policies."""
    service = ZohoService(session)
    try:
        m = service.update_field_mapping(mapping_id, updates)
        session.commit()
        return ZohoFieldMappingItem(
            id=m.id,
            zoho_module=m.zoho_module,
            gtm_field=m.gtm_field,
            zoho_field=m.zoho_field,
            field_type=m.field_type,
            sync_direction=m.sync_direction,
            conflict_policy=m.conflict_policy,
            is_custom=m.is_custom,
            is_active=m.is_active,
        )
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sync", response_model=ZohoSyncJobResponse)
def trigger_sync(
    data: ZohoSyncTriggerRequest,
    session: Session = Depends(get_db),
):
    """Triggers on-demand synchronization (outbound, inbound, or reconcile)."""
    service = ZohoService(session)
    try:
        if data.direction == "inbound":
            job = service.run_inbound_sync()
        elif data.direction == "reconcile":
            job = service.run_reconcile_sync()
        else:
            job = service.run_outbound_sync()

        session.commit()
        return ZohoSyncJobResponse(
            id=job.id,
            job_type=job.job_type,
            status=job.status,
            records_processed=job.records_processed,
            records_succeeded=job.records_succeeded,
            records_failed=job.records_failed,
            started_at=job.started_at,
            finished_at=job.finished_at,
            error_summary=job.error_summary,
            details=job.details or {},
        )
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Sync execution failed: {exc}") from exc


@router.get("/sync/jobs", response_model=List[ZohoSyncJobResponse])
def get_sync_jobs(limit: int = Query(default=20, le=100), session: Session = Depends(get_db)):
    """Returns recent synchronization job records."""
    jobs = session.query(ZohoSyncJob).order_by(ZohoSyncJob.started_at.desc()).limit(limit).all()
    return [
        ZohoSyncJobResponse(
            id=j.id,
            job_type=j.job_type,
            status=j.status,
            records_processed=j.records_processed,
            records_succeeded=j.records_succeeded,
            records_failed=j.records_failed,
            started_at=j.started_at,
            finished_at=j.finished_at,
            error_summary=j.error_summary,
            details=j.details or {},
        )
        for j in jobs
    ]


@router.get("/sync/logs", response_model=List[ZohoSyncLogResponse])
def get_sync_logs(limit: int = Query(default=50, le=200), session: Session = Depends(get_db)):
    """Returns detailed synchronization audit logs."""
    logs = session.query(ZohoSyncLog).order_by(ZohoSyncLog.created_at.desc()).limit(limit).all()
    return [
        ZohoSyncLogResponse(
            id=l.id,
            job_id=l.job_id,
            entity_type=l.entity_type,
            entity_id=l.entity_id,
            zoho_module=l.zoho_module,
            zoho_record_id=l.zoho_record_id,
            action=l.action,
            status=l.status,
            message=l.message,
            created_at=l.created_at,
        )
        for l in logs
    ]


@router.get("/conflicts", response_model=List[ZohoConflictItem])
def get_conflicts(session: Session = Depends(get_db)):
    """Returns unresolved synchronization conflicts."""
    conflicts = session.query(ZohoSyncConflict).filter(
        ZohoSyncConflict.resolution_status == "unresolved"
    ).order_by(ZohoSyncConflict.created_at.desc()).all()
    return [
        ZohoConflictItem(
            id=c.id,
            record_mapping_id=c.record_mapping_id,
            gtm_entity_type=c.gtm_entity_type,
            gtm_entity_id=c.gtm_entity_id,
            zoho_module=c.zoho_module,
            zoho_record_id=c.zoho_record_id,
            field_name=c.field_name,
            gtm_value=c.gtm_value,
            zoho_value=c.zoho_value,
            resolution_status=c.resolution_status,
            created_at=c.created_at,
        )
        for c in conflicts
    ]


@router.post("/conflicts/{conflict_id}/resolve")
def resolve_conflict(
    conflict_id: str,
    data: ZohoConflictResolveRequest,
    session: Session = Depends(get_db),
):
    """Resolves an existing conflict record."""
    c = session.get(ZohoSyncConflict, conflict_id)
    if not c:
        raise HTTPException(status_code=404, detail="Conflict record not found.")

    c.resolution_status = f"resolved_{data.resolution}"
    c.resolved_by = "user_manual"
    c.resolved_at = ZohoService(session).session.query(ZohoConnection).first().updated_at
    session.commit()
    return {"message": "Conflict resolved successfully."}


@router.post("/sync/leads/{lead_id}")
def sync_specific_lead(lead_id: str, session: Session = Depends(get_db)):
    """Instantly syncs a specific lead as a Zoho Account."""
    service = ZohoService(session)
    res = service.sync_account_outbound(lead_id)
    if not res:
        raise HTTPException(status_code=400, detail="Failed to sync lead to Zoho CRM.")
    session.commit()
    return {"message": "Lead synced successfully to Zoho CRM.", "zoho_record_id": res.zoho_record_id}


@router.post("/sync/contacts/{contact_id}")
def sync_specific_contact(contact_id: str, session: Session = Depends(get_db)):
    """Instantly syncs a specific contact to Zoho Contacts."""
    service = ZohoService(session)
    res = service.sync_contact_outbound(contact_id)
    if not res:
        raise HTTPException(status_code=400, detail="Failed to sync contact to Zoho CRM.")
    session.commit()
    return {"message": "Contact synced successfully to Zoho CRM.", "zoho_record_id": res.zoho_record_id}
