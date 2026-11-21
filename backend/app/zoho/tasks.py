import logging
from app.database import SessionLocal
from app.zoho.service import ZohoService
from app.zoho.client import ZohoClient

logger = logging.getLogger(__name__)


def zoho_outbound_sync_task():
    """Celery background job for outbound synchronization to Zoho CRM."""
    logger.info("Executing periodic Zoho CRM outbound synchronization...")
    try:
        with SessionLocal.begin() as session:
            service = ZohoService(session)
            conn = service.get_connection_status()
            if not conn.is_connected:
                logger.info("Zoho CRM is not connected. Skipping outbound sync.")
                return {"status": "skipped", "reason": "not_connected"}

            job = service.run_outbound_sync()
            logger.info("Zoho outbound sync completed. Succeeded: %d, Failed: %d", job.records_succeeded, job.records_failed)
            return {
                "status": "completed",
                "processed": job.records_processed,
                "succeeded": job.records_succeeded,
                "failed": job.records_failed,
            }
    except Exception as exc:
        logger.exception("Zoho outbound sync task failed: %s", exc)
        return {"status": "failed", "error": str(exc)}


def zoho_inbound_sync_task():
    """Celery background job for inbound synchronization from Zoho CRM."""
    logger.info("Executing periodic Zoho CRM inbound synchronization...")
    try:
        with SessionLocal.begin() as session:
            service = ZohoService(session)
            conn = service.get_connection_status()
            if not conn.is_connected:
                logger.info("Zoho CRM is not connected. Skipping inbound sync.")
                return {"status": "skipped", "reason": "not_connected"}

            job = service.run_inbound_sync()
            logger.info("Zoho inbound sync completed. Succeeded: %d, Failed: %d", job.records_succeeded, job.records_failed)
            return {
                "status": "completed",
                "processed": job.records_processed,
                "succeeded": job.records_succeeded,
                "failed": job.records_failed,
            }
    except Exception as exc:
        logger.exception("Zoho inbound sync task failed: %s", exc)
        return {"status": "failed", "error": str(exc)}


def zoho_token_refresh_task():
    """Proactive token refresh task to guarantee valid access tokens."""
    try:
        with SessionLocal.begin() as session:
            client = ZohoClient(session)
            conn = session.query(client.get_connection().__class__).filter_by(is_active=True).first()
            if conn:
                client.refresh_access_token()
                logger.info("Proactively refreshed Zoho CRM access token.")
    except Exception as exc:
        logger.warning("Zoho proactive token refresh check: %s", exc)
