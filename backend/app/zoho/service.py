import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

from sqlalchemy import select, or_, and_, func
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Lead, Contact, ProductLead, ProductOpportunity, SalesTask,
    now, new_id
)

def clean_company_key(name: str) -> str:
    return name.lower().strip()


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
from app.meetings.models import Meeting, MeetingAnalysis, MeetingActionItem
from app.booking.models import Booking
from app.zoho.client import ZohoClient, ZohoAPIError
from app.zoho.crypto import encrypt_token, decrypt_token
from app.zoho.models import (
    ZohoConnection, ZohoOAuthState, ZohoFieldMapping, ZohoRecordMapping,
    ZohoSyncJob, ZohoSyncLog, ZohoSyncConflict, now as zoho_now
)
from app.zoho.schemas import (
    ZohoConnectionStatus, ZohoFieldMappingUpdate, ZohoConflictResolveRequest
)

logger = logging.getLogger(__name__)

# Standard 17-Stage GTM Journey to Zoho Deal Stages Mapping
DEFAULT_STAGE_MAPPING: Dict[str, str] = {
    "prospect": "Qualification",
    "identified": "Qualification",
    "researched": "Qualification",
    "enriched": "Qualification",
    "outreach_initiated": "Needs Analysis",
    "engaged": "Value Proposition",
    "replied": "Value Proposition",
    "meeting_requested": "Identifying Decision Makers",
    "meeting_scheduled": "Proposal/Price Quote",
    "meeting_completed": "Proposal/Price Quote",
    "discovery_completed": "Proposal/Price Quote",
    "solution_validation": "Proposal/Price Quote",
    "demo_requested": "Proposal/Price Quote",
    "demo_completed": "Negotiation/Review",
    "qualified": "Negotiation/Review",
    "pricing_discussion": "Negotiation/Review",
    "proposal": "Negotiation/Review",
    "negotiation": "Negotiation/Review",
    "won": "Closed Won",
    "closed_won": "Closed Won",
    "lost": "Closed Lost",
    "closed_lost": "Closed Lost",
    "disqualified": "Closed Lost",
    "on_hold": "On Hold",
}

DEFAULT_FIELD_MAPPINGS = [
    # Accounts
    {"zoho_module": "Accounts", "gtm_field": "company_name", "zoho_field": "Account_Name", "field_type": "string", "conflict_policy": "crm_wins"},
    {"zoho_module": "Accounts", "gtm_field": "domain", "zoho_field": "Website", "field_type": "string", "conflict_policy": "crm_wins"},
    {"zoho_module": "Accounts", "gtm_field": "phone", "zoho_field": "Phone", "field_type": "string", "conflict_policy": "crm_wins"},
    {"zoho_module": "Accounts", "gtm_field": "industry", "zoho_field": "Industry", "field_type": "string", "conflict_policy": "crm_wins"},
    {"zoho_module": "Accounts", "gtm_field": "location", "zoho_field": "Billing_City", "field_type": "string", "conflict_policy": "crm_wins"},
    {"zoho_module": "Accounts", "gtm_field": "revenue", "zoho_field": "Annual_Revenue", "field_type": "currency", "conflict_policy": "gtm_wins"},
    # Contacts
    {"zoho_module": "Contacts", "gtm_field": "name", "zoho_field": "Full_Name", "field_type": "string", "conflict_policy": "crm_wins"},
    {"zoho_module": "Contacts", "gtm_field": "email", "zoho_field": "Email", "field_type": "email", "conflict_policy": "crm_wins"},
    {"zoho_module": "Contacts", "gtm_field": "title", "zoho_field": "Title", "field_type": "string", "conflict_policy": "crm_wins"},
    {"zoho_module": "Contacts", "gtm_field": "department", "zoho_field": "Department", "field_type": "string", "conflict_policy": "crm_wins"},
    # Leads
    {"zoho_module": "Leads", "gtm_field": "name", "zoho_field": "Last_Name", "field_type": "string", "conflict_policy": "crm_wins"},
    {"zoho_module": "Leads", "gtm_field": "email", "zoho_field": "Email", "field_type": "email", "conflict_policy": "crm_wins"},
    {"zoho_module": "Leads", "gtm_field": "company_name", "zoho_field": "Company", "field_type": "string", "conflict_policy": "crm_wins"},
    # Deals
    {"zoho_module": "Deals", "gtm_field": "deal_name", "zoho_field": "Deal_Name", "field_type": "string", "conflict_policy": "crm_wins"},
    {"zoho_module": "Deals", "gtm_field": "stage", "zoho_field": "Stage", "field_type": "picklist", "conflict_policy": "crm_wins"},
    # Tasks
    {"zoho_module": "Tasks", "gtm_field": "title", "zoho_field": "Subject", "field_type": "string", "conflict_policy": "gtm_wins"},
    {"zoho_module": "Tasks", "gtm_field": "status", "zoho_field": "Status", "field_type": "string", "conflict_policy": "crm_wins"},
    # Events
    {"zoho_module": "Events", "gtm_field": "title", "zoho_field": "Event_Title", "field_type": "string", "conflict_policy": "gtm_wins"},
    {"zoho_module": "Events", "gtm_field": "start_time", "zoho_field": "Start_DateTime", "field_type": "datetime", "conflict_policy": "gtm_wins"},
    {"zoho_module": "Events", "gtm_field": "end_time", "zoho_field": "End_DateTime", "field_type": "datetime", "conflict_policy": "gtm_wins"},
    {"zoho_module": "Events", "gtm_field": "join_url", "zoho_field": "Venue", "field_type": "string", "conflict_policy": "gtm_wins"},
]


class ZohoService:
    """Core Service orchestrating Zoho CRM OAuth, discovery, sync, and business flows."""

    def __init__(self, session: Session):
        self.session = session
        self.client = ZohoClient(session)

    def is_connected(self) -> bool:
        """Checks if Zoho CRM is connected and active."""
        return bool(self.session.query(ZohoConnection).filter(ZohoConnection.is_active == True).first())

    # -------------------------------------------------------------------------
    # Phase 1: OAuth 2.0 Flow
    # -------------------------------------------------------------------------

    def generate_authorization_url(self, browser_hash: str, accounts_domain: Optional[str] = None) -> Tuple[str, str]:
        """Generates Zoho OAuth authorization URL and records state token in DB."""
        client_id = (settings.zoho_client_id or "").strip()
        if not client_id:
            raise ValueError("ZOHO_CLIENT_ID is not configured in environment.")

        accounts_domain = (accounts_domain or settings.zoho_accounts_domain or "https://accounts.zoho.in").rstrip("/")
        redirect_uri = settings.zoho_redirect_uri or "http://localhost:8000/zoho/oauth/callback"

        raw_state = f"zoho_state_{new_id()}"
        state_hash = hashlib.sha256(raw_state.encode("utf-8")).hexdigest()

        oauth_state = ZohoOAuthState(
            state_hash=state_hash,
            browser_hash=browser_hash,
            accounts_domain=accounts_domain,
            expires_at=zoho_now() + timedelta(minutes=15),
        )
        self.session.add(oauth_state)
        self.session.flush()

        scopes = [
            "ZohoCRM.modules.ALL",
            "ZohoCRM.settings.ALL",
            "ZohoCRM.users.READ",
            "ZohoCRM.org.READ",
        ]
        params = {
            "scope": ",".join(scopes),
            "client_id": client_id,
            "response_type": "code",
            "access_type": "offline",
            "prompt": "consent",
            "redirect_uri": redirect_uri,
            "state": raw_state,
        }
        auth_url = f"{accounts_domain}/oauth/v2/auth?{urlencode(params)}"
        return auth_url, raw_state

    def handle_oauth_callback(self, code: str, state: str, browser_hash: str) -> ZohoConnection:
        """Validates state, exchanges auth code for refresh & access tokens, and connects organization."""
        state_hash = hashlib.sha256(state.encode("utf-8")).hexdigest()
        state_rec = self.session.get(ZohoOAuthState, state_hash)
        if not state_rec:
            raise ValueError("Invalid or unrecognized OAuth state parameter.")
        if state_rec.consumed_at:
            raise ValueError("OAuth state has already been consumed.")
        exp = ensure_utc(state_rec.expires_at)
        if exp and exp < zoho_now():
            raise ValueError("OAuth state has expired. Please retry connection.")

        state_rec.consumed_at = zoho_now()

        accounts_domain = (state_rec.accounts_domain or settings.zoho_accounts_domain or "https://accounts.zoho.in").rstrip("/")
        token_url = f"{accounts_domain}/oauth/v2/token"

        client_id = (settings.zoho_client_id or "").strip()
        client_secret = (settings.zoho_client_secret or "").strip()
        redirect_uri = settings.zoho_redirect_uri or "http://localhost:8000/zoho/oauth/callback"

        import requests
        try:
            resp = requests.post(
                token_url,
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                timeout=25,
            )
            data = resp.json()
        except Exception as exc:
            raise RuntimeError(f"Failed to contact Zoho Accounts endpoint: {exc}") from exc

        if resp.status_code != 200 or "refresh_token" not in data:
            err = data.get("error") or data.get("message") or resp.text
            raise RuntimeError(f"Zoho token exchange rejected: {err}")

        refresh_token = data["refresh_token"]
        access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        api_domain = (data.get("api_domain") or settings.zoho_api_domain or "https://www.zohoapis.in").rstrip("/")

        # Initialize connection entity temporarily to query org details
        conn = self.session.query(ZohoConnection).first()
        if not conn:
            conn = ZohoConnection(
                org_id="pending_discovery",
                org_name="Zoho Organization",
                accounts_domain=accounts_domain,
                api_domain=api_domain,
                refresh_token_encrypted=encrypt_token(refresh_token),
                access_token_encrypted=encrypt_token(access_token),
                access_token_expires_at=zoho_now() + timedelta(seconds=expires_in),
                is_active=True,
            )
            self.session.add(conn)
        else:
            conn.accounts_domain = accounts_domain
            conn.api_domain = api_domain
            conn.refresh_token_encrypted = encrypt_token(refresh_token)
            conn.access_token_encrypted = encrypt_token(access_token)
            conn.access_token_expires_at = zoho_now() + timedelta(seconds=expires_in)
            conn.is_active = True
            conn.last_error = None

        self.session.flush()

        # Query organization metadata from Zoho CRM v8
        try:
            client = ZohoClient(self.session, connection=conn)
            org_data = client.get_organization()
            if org_data:
                conn.org_id = str(org_data.get("zgid") or org_data.get("id") or "zoho_org")
                conn.org_name = org_data.get("company_name") or "Zoho CRM Org"
                conn.user_email = org_data.get("primary_email") or org_data.get("super_admin_email")
                conn.user_zuid = str(org_data.get("zuid") or "")
        except Exception as exc:
            logger.warning("Could not immediately fetch Zoho organization profile: %s", exc)
            if conn.org_id == "pending_discovery":
                conn.org_id = f"zoho_{new_id()[:8]}"

        self.seed_default_field_mappings()
        self.session.flush()
        return conn

    def get_connection_status(self) -> ZohoConnectionStatus:
        """Returns the current connection status."""
        conn = self.session.query(ZohoConnection).filter(ZohoConnection.is_active == True).first()
        if not conn:
            return ZohoConnectionStatus(is_connected=False, connected=False)

        return ZohoConnectionStatus(
            is_connected=True,
            connected=True,
            org_id=conn.org_id,
            zoho_org_id=conn.org_id,
            org_name=conn.org_name,
            zoho_org_name=conn.org_name,
            user_email=conn.user_email,
            zoho_user_email=conn.user_email,
            user_zuid=conn.user_zuid,
            accounts_domain=conn.accounts_domain,
            api_domain=conn.api_domain,
            crm_api_version=conn.crm_api_version,
            sync_direction=conn.sync_direction,
            last_synced_at=conn.last_synced_at,
            last_error=conn.last_error,
            scopes=conn.scopes or [],
        )

    def disconnect_crm(self):
        """Disconnects and deactivates the CRM integration."""
        conn = self.session.query(ZohoConnection).first()
        if conn:
            conn.is_active = False
            conn.access_token_encrypted = None
            self.session.flush()

    def verify_connection(self) -> dict[str, Any]:
        """
        Actively calls Zoho CRM API v8 (/org) to verify live API connectivity,
        refresh tokens if necessary, and refresh stored organization metadata.
        """
        conn = self.session.query(ZohoConnection).first()
        if not conn or not conn.is_active:
            return {
                "success": False,
                "is_connected": False,
                "message": "Zoho CRM is currently not connected. Please click 'Connect Zoho CRM' to authorize.",
            }

        try:
            res = self.client.get("/org")
            org_data = {}
            if isinstance(res, dict) and "org" in res and isinstance(res["org"], list) and len(res["org"]) > 0:
                org_data = res["org"][0]
                if org_data.get("company_name"):
                    conn.org_name = org_data.get("company_name")
                if org_data.get("zgid"):
                    conn.org_id = str(org_data.get("zgid"))
                if org_data.get("primary_email"):
                    conn.user_email = org_data.get("primary_email")
                conn.updated_at = zoho_now()
                self.session.flush()

            return {
                "success": True,
                "is_connected": True,
                "message": f"Successfully verified live connection to Zoho CRM ({conn.org_name or 'Org'})!",
                "org_id": conn.org_id,
                "org_name": conn.org_name,
                "user_email": conn.user_email,
                "api_domain": conn.api_domain,
                "crm_api_version": conn.crm_api_version,
                "time_zone": org_data.get("time_zone"),
                "trial_type": org_data.get("license_details", {}).get("trial_type") if isinstance(org_data.get("license_details"), dict) else None,
            }
        except Exception as e:
            logger.error("Zoho CRM connection verification failed: %s", e)
            return {
                "success": False,
                "is_connected": True,
                "message": f"Verification failed with Zoho API error: {str(e)}",
                "error": str(e),
            }

    # -------------------------------------------------------------------------
    # Phase 3: Field Mappings & Metadata Discovery
    # -------------------------------------------------------------------------

    def seed_default_field_mappings(self):
        """Seeds default field mappings if not present in database."""
        for item in DEFAULT_FIELD_MAPPINGS:
            existing = self.session.query(ZohoFieldMapping).filter(
                ZohoFieldMapping.zoho_module == item["zoho_module"],
                ZohoFieldMapping.gtm_field == item["gtm_field"],
            ).first()
            if not existing:
                mapping = ZohoFieldMapping(
                    zoho_module=item["zoho_module"],
                    gtm_field=item["gtm_field"],
                    zoho_field=item["zoho_field"],
                    field_type=item["field_type"],
                    conflict_policy=item["conflict_policy"],
                    is_custom=False,
                    is_active=True,
                )
                self.session.add(mapping)
        self.session.commit()

    def get_field_mappings(self, module: Optional[str] = None) -> List[ZohoFieldMapping]:
        self.seed_default_field_mappings()
        q = self.session.query(ZohoFieldMapping)
        if module:
            q = q.filter(ZohoFieldMapping.zoho_module == module)
        return q.order_by(ZohoFieldMapping.zoho_module, ZohoFieldMapping.gtm_field).all()

    def update_field_mapping(self, mapping_id: str, updates: ZohoFieldMappingUpdate) -> ZohoFieldMapping:
        m = self.session.get(ZohoFieldMapping, mapping_id)
        if not m:
            raise ValueError("Field mapping not found.")
        if updates.zoho_field is not None:
            m.zoho_field = updates.zoho_field.strip()
        if updates.sync_direction is not None:
            m.sync_direction = updates.sync_direction
        if updates.conflict_policy is not None:
            m.conflict_policy = updates.conflict_policy
        if updates.is_active is not None:
            m.is_active = updates.is_active
        self.session.flush()
        return m

    # -------------------------------------------------------------------------
    # Phase 4 & 5: Record Synchronization (Outbound & Inbound)
    # -------------------------------------------------------------------------

    def sync_account_outbound(self, lead_id: str, job_id: Optional[str] = None) -> Optional[ZohoRecordMapping]:
        """
        Pushes a GTM Lead (Account) to Zoho CRM Accounts module using Upsert API.
        Matching priority: Stored mapping -> Account_Name / Website.
        """
        if not self.is_connected():
            return None
        lead = self.session.get(Lead, lead_id)
        if not lead:
            return None

        # Build account payload using field mappings
        account_name = lead.company_name.strip()
        domain = (lead.domain or "").strip()
        phone = (lead.phone or "").strip()

        payload: Dict[str, Any] = {
            "Account_Name": account_name,
            "Website": domain or None,
            "Phone": phone or None,
            "Industry": lead.industry or None,
            "Billing_City": lead.location or None,
            "Description": lead.remarks or None,
        }

        # Check existing mapping
        mapping = self.session.query(ZohoRecordMapping).filter(
            ZohoRecordMapping.gtm_entity_type == "lead",
            ZohoRecordMapping.gtm_entity_id == lead.id,
        ).first()

        if mapping and mapping.zoho_record_id:
            payload["id"] = mapping.zoho_record_id

        # Upsert with duplicate check on Website or Account_Name
        dup_fields = ["Website"] if domain else ["Account_Name"]
        res = self.client.upsert_records("Accounts", [payload], duplicate_check_fields=dup_fields)
        
        if res and isinstance(res, list) and res[0].get("status") in ("success", "duplicate_created"):
            zoho_id = res[0]["details"]["id"]
            if not mapping:
                mapping = ZohoRecordMapping(
                    gtm_entity_type="lead",
                    gtm_entity_id=lead.id,
                    zoho_module="Accounts",
                    zoho_record_id=zoho_id,
                    external_id=f"gtm_lead_{lead.id}",
                    sync_status="synced",
                    last_synced_at=zoho_now(),
                )
                self.session.add(mapping)
            else:
                mapping.zoho_record_id = zoho_id
                mapping.sync_status = "synced"
                mapping.last_synced_at = zoho_now()

            self._log_sync(
                job_id=job_id,
                entity_type="lead",
                entity_id=lead.id,
                zoho_module="Accounts",
                zoho_record_id=zoho_id,
                action="upsert",
                status="success",
                message=f"Synced Account '{account_name}' to Zoho CRM.",
            )
            self.session.flush()
            return mapping
        else:
            err = res[0].get("message") if res else "Unknown response"
            self._log_sync(
                job_id=job_id,
                entity_type="lead",
                entity_id=lead.id,
                zoho_module="Accounts",
                zoho_record_id=None,
                action="upsert",
                status="failure",
                message=f"Failed to sync Account '{account_name}': {err}",
            )
            return None

    def sync_contact_outbound(self, contact_id: str, job_id: Optional[str] = None) -> Optional[ZohoRecordMapping]:
        """
        Pushes a GTM Contact to Zoho CRM Contacts module.
        Ensures parent Account is linked.
        """
        contact = self.session.get(Contact, contact_id)
        if not contact or not contact.email:
            return None

        # Ensure parent Account is mapped
        account_id = None
        if contact.lead_id:
            acc_map = self.session.query(ZohoRecordMapping).filter(
                ZohoRecordMapping.gtm_entity_type == "lead",
                ZohoRecordMapping.gtm_entity_id == contact.lead_id,
            ).first()
            if not acc_map:
                acc_map = self.sync_account_outbound(contact.lead_id, job_id=job_id)
            if acc_map:
                account_id = acc_map.zoho_record_id

        # Split full name into First/Last
        full_name = (contact.name or contact.email.split("@")[0]).strip()
        parts = full_name.split()
        first_name = parts[0] if len(parts) > 1 else ""
        last_name = " ".join(parts[1:]) if len(parts) > 1 else parts[0]

        payload: Dict[str, Any] = {
            "First_Name": first_name or None,
            "Last_Name": last_name or "Contact",
            "Email": contact.email.strip().lower(),
            "Title": contact.title or None,
            "Department": contact.department or None,
        }
        if account_id:
            payload["Account_Name"] = {"id": account_id}

        mapping = self.session.query(ZohoRecordMapping).filter(
            ZohoRecordMapping.gtm_entity_type == "contact",
            ZohoRecordMapping.gtm_entity_id == contact.id,
        ).first()

        if mapping and mapping.zoho_record_id:
            payload["id"] = mapping.zoho_record_id

        res = self.client.upsert_records("Contacts", [payload], duplicate_check_fields=["Email"])
        if res and isinstance(res, list) and res[0].get("status") in ("success", "duplicate_created"):
            zoho_id = res[0]["details"]["id"]
            if not mapping:
                mapping = ZohoRecordMapping(
                    gtm_entity_type="contact",
                    gtm_entity_id=contact.id,
                    zoho_module="Contacts",
                    zoho_record_id=zoho_id,
                    external_id=f"gtm_contact_{contact.id}",
                    sync_status="synced",
                    last_synced_at=zoho_now(),
                )
                self.session.add(mapping)
            else:
                mapping.zoho_record_id = zoho_id
                mapping.sync_status = "synced"
                mapping.last_synced_at = zoho_now()

            self._log_sync(
                job_id=job_id,
                entity_type="contact",
                entity_id=contact.id,
                zoho_module="Contacts",
                zoho_record_id=zoho_id,
                action="upsert",
                status="success",
                message=f"Synced Contact '{contact.email}' to Zoho CRM.",
            )
            self.session.flush()
            return mapping
        else:
            err = res[0].get("message") if res else "Unknown response"
            self._log_sync(
                job_id=job_id,
                entity_type="contact",
                entity_id=contact.id,
                zoho_module="Contacts",
                zoho_record_id=None,
                action="upsert",
                status="failure",
                message=f"Failed to sync Contact '{contact.email}': {err}",
            )
            return None

    def sync_opportunity_to_deal(self, opportunity_id: str, job_id: Optional[str] = None) -> Optional[ZohoRecordMapping]:
        """
        Synchronizes a GTM ProductOpportunity to a Zoho CRM Deal, mapping the 17-stage lifecycle.
        """
        opp = self.session.get(ProductOpportunity, opportunity_id)
        if not opp:
            return None

        # Fetch product lead and lead
        prod_lead = self.session.get(ProductLead, opp.product_lead_id) if opp.product_lead_id else None
        if not prod_lead:
            return None

        lead = self.session.get(Lead, prod_lead.lead_id)
        if not lead:
            return None

        # Ensure account mapping exists
        acc_map = self.session.query(ZohoRecordMapping).filter(
            ZohoRecordMapping.gtm_entity_type == "lead",
            ZohoRecordMapping.gtm_entity_id == lead.id,
        ).first()
        if not acc_map:
            acc_map = self.sync_account_outbound(lead.id, job_id=job_id)

        # Map 17-stage lifecycle
        current_stage = (prod_lead.stage or "prospect").lower()
        zoho_stage = DEFAULT_STAGE_MAPPING.get(current_stage, "Qualification")

        deal_name = opp.opportunity_summary or f"{lead.company_name} - Solution Opportunity"
        closing_date = (zoho_now() + timedelta(days=60)).strftime("%Y-%m-%d")

        payload: Dict[str, Any] = {
            "Deal_Name": deal_name[:120],
            "Stage": zoho_stage,
            "Closing_Date": closing_date,
            "Description": opp.opportunity_summary or None,
        }
        if acc_map and acc_map.zoho_record_id:
            payload["Account_Name"] = {"id": acc_map.zoho_record_id}

        mapping = self.session.query(ZohoRecordMapping).filter(
            ZohoRecordMapping.gtm_entity_type == "product_opportunity",
            ZohoRecordMapping.gtm_entity_id == opp.id,
        ).first()

        if mapping and mapping.zoho_record_id:
            payload["id"] = mapping.zoho_record_id

        res = self.client.upsert_records("Deals", [payload], duplicate_check_fields=["Deal_Name"])
        if res and isinstance(res, list) and res[0].get("status") in ("success", "duplicate_created"):
            zoho_id = res[0]["details"]["id"]
            if not mapping:
                mapping = ZohoRecordMapping(
                    gtm_entity_type="product_opportunity",
                    gtm_entity_id=opp.id,
                    zoho_module="Deals",
                    zoho_record_id=zoho_id,
                    external_id=f"gtm_opp_{opp.id}",
                    sync_status="synced",
                    last_synced_at=zoho_now(),
                )
                self.session.add(mapping)
            else:
                mapping.zoho_record_id = zoho_id
                mapping.sync_status = "synced"
                mapping.last_synced_at = zoho_now()

            self._log_sync(
                job_id=job_id,
                entity_type="product_opportunity",
                entity_id=opp.id,
                zoho_module="Deals",
                zoho_record_id=zoho_id,
                action="upsert",
                status="success",
                message=f"Synced Deal '{deal_name}' (Stage: {zoho_stage}) to Zoho CRM.",
            )
            self.session.flush()
            return mapping
        return None

    # -------------------------------------------------------------------------
    # Phase 7: Public Booking Integration
    # -------------------------------------------------------------------------

    def sync_booking_to_zoho(self, booking_id: str, job_id: Optional[str] = None) -> Optional[ZohoRecordMapping]:
        """
        Integrates a completed customer booking into Zoho CRM:
        1. Matches / Creates Zoho Account & Contact (or Lead).
        2. Creates a Zoho Event with Google Meet conference details.
        3. Prevents duplicates on retries.
        """
        booking = self.session.get(Booking, booking_id)
        if not booking:
            return None

        # Check existing Event mapping
        existing_map = self.session.query(ZohoRecordMapping).filter(
            ZohoRecordMapping.gtm_entity_type == "booking",
            ZohoRecordMapping.gtm_entity_id == booking.id,
        ).first()
        if existing_map and existing_map.zoho_record_id:
            logger.info("Booking %s is already mapped to Zoho Event %s", booking.id, existing_map.zoho_record_id)
            return existing_map

        # Match or create Contact in GTM & Zoho
        contact_id = booking.contact_id
        if not contact_id and booking.customer_email:
            c = self.session.query(Contact).filter(Contact.email == booking.customer_email.lower().strip()).first()
            if c:
                contact_id = c.id

        zoho_contact_id = None
        if contact_id:
            cmap = self.session.query(ZohoRecordMapping).filter(
                ZohoRecordMapping.gtm_entity_type == "contact",
                ZohoRecordMapping.gtm_entity_id == contact_id,
            ).first()
            if not cmap:
                cmap = self.sync_contact_outbound(contact_id, job_id=job_id)
            if cmap:
                zoho_contact_id = cmap.zoho_record_id

        # Match or create Account
        lead_id = booking.lead_id
        zoho_account_id = None
        if lead_id:
            amap = self.session.query(ZohoRecordMapping).filter(
                ZohoRecordMapping.gtm_entity_type == "lead",
                ZohoRecordMapping.gtm_entity_id == lead_id,
            ).first()
            if not amap:
                amap = self.sync_account_outbound(lead_id, job_id=job_id)
            if amap:
                zoho_account_id = amap.zoho_record_id

        # Format ISO dates for Zoho Event
        start_dt = booking.start_time.isoformat() if booking.start_time else zoho_now().isoformat()
        end_dt = booking.end_time.isoformat() if booking.end_time else (zoho_now() + timedelta(minutes=30)).isoformat()

        # Retrieve Google Meet link from associated Meeting record
        join_url = ""
        if booking.meeting_id:
            m = self.session.get(Meeting, booking.meeting_id)
            if m and m.join_url:
                join_url = m.join_url

        event_title = f"Discovery Call: {booking.customer_name}"
        if booking.customer_company:
            event_title += f" ({booking.customer_company})"

        event_payload: Dict[str, Any] = {
            "Event_Title": event_title[:100],
            "Start_DateTime": start_dt,
            "End_DateTime": end_dt,
            "Venue": join_url or "Google Meet",
            "Description": (
                f"GTMProspecting Public Booking\n"
                f"Customer: {booking.customer_name}\n"
                f"Email: {booking.customer_email}\n"
                f"Phone: {booking.customer_phone or 'N/A'}\n"
                f"Google Meet: {join_url or 'N/A'}"
            ),
        }

        if zoho_contact_id:
            event_payload["Who_Id"] = {"id": zoho_contact_id}
        if zoho_account_id:
            event_payload["What_Id"] = {"id": zoho_account_id}

        res = self.client.create_records("Events", [event_payload])
        if res and isinstance(res, list) and res[0].get("status") == "success":
            zoho_event_id = res[0]["details"]["id"]
            mapping = ZohoRecordMapping(
                gtm_entity_type="booking",
                gtm_entity_id=booking.id,
                zoho_module="Events",
                zoho_record_id=zoho_event_id,
                external_id=f"gtm_booking_{booking.id}",
                sync_status="synced",
                last_synced_at=zoho_now(),
            )
            self.session.add(mapping)
            self._log_sync(
                job_id=job_id,
                entity_type="booking",
                entity_id=booking.id,
                zoho_module="Events",
                zoho_record_id=zoho_event_id,
                action="create",
                status="success",
                message=f"Created Zoho Event '{event_title}' with Google Meet link.",
            )
            self.session.flush()
            return mapping
        return None

    # -------------------------------------------------------------------------
    # Phase 8 & 9: AI Research & Meeting Intelligence Sync
    # -------------------------------------------------------------------------

    def sync_research_to_zoho(self, job_id: str, sync_job_id: Optional[str] = None):
        """
        Attaches AI research report findings and cited sources as a Zoho Note
        under the relevant Account record.
        """
        if not self.is_connected():
            return None

        from app.company_intelligence.models import CompanyResearchProfile, ResearchJob, ResearchReport
        job = self.session.get(ResearchJob, job_id)
        if not job or not job.company_id:
            return

        profile = self.session.get(CompanyResearchProfile, job.company_id)
        if not profile:
            return

        report = self.session.query(ResearchReport).filter(
            ResearchReport.job_id == job.id
        ).order_by(ResearchReport.version.desc()).first()

        # Find parent Zoho Account
        lead_id = profile.lead_id
        if not lead_id:
            lead = self.session.query(Lead).filter(Lead.domain == profile.domain).first()
            lead_id = lead.id if lead else None

        if not lead_id:
            return

        acc_map = self.session.query(ZohoRecordMapping).filter(
            ZohoRecordMapping.gtm_entity_type == "lead",
            ZohoRecordMapping.gtm_entity_id == lead_id,
        ).first()
        if not acc_map:
            acc_map = self.sync_account_outbound(lead_id, job_id=sync_job_id)

        if not acc_map or not acc_map.zoho_record_id:
            return

        # Prepare formatted note
        note_title = f"AI Research Profile: {profile.company_name}"
        summary_text = report.summary if report else "Autonomous research completed."
        note_body = (
            f"DENSO GTM Prospecting AI Research\n"
            f"Company: {profile.company_name} ({profile.domain})\n"
            f"Extracted Facts: {job.facts_count} | Sources Analyzed: {job.sources_count}\n\n"
            f"Executive Summary:\n{summary_text}\n\n"
            f"Research Job ID: {job.id}\n"
            f"Timestamp: {job.finished_at or zoho_now()}"
        )

        try:
            self.client.add_note(
                parent_module="Accounts",
                parent_id=acc_map.zoho_record_id,
                title=note_title,
                content=note_body,
            )
            self._log_sync(
                job_id=sync_job_id,
                entity_type="research_job",
                entity_id=job.id,
                zoho_module="Notes",
                zoho_record_id=None,
                action="create",
                status="success",
                message=f"Added AI Research Note to Zoho Account '{profile.company_name}'.",
            )
        except Exception as exc:
            logger.warning("Failed to attach research note to Zoho CRM: %s", exc)

    def sync_meeting_intelligence_to_zoho(self, meeting_id: str, sync_job_id: Optional[str] = None):
        """
        Synchronizes Meeting MoM & Executive Summary as a Zoho Note,
        and action items as Zoho Tasks.
        """
        meeting = self.session.get(Meeting, meeting_id)
        if not meeting:
            return

        # Find Account or Contact
        parent_module = "Accounts"
        parent_id = None

        if meeting.lead_id:
            acc_map = self.session.query(ZohoRecordMapping).filter(
                ZohoRecordMapping.gtm_entity_type == "lead",
                ZohoRecordMapping.gtm_entity_id == meeting.lead_id,
            ).first()
            if not acc_map:
                acc_map = self.sync_account_outbound(meeting.lead_id, job_id=sync_job_id)
            if acc_map:
                parent_id = acc_map.zoho_record_id

        if not parent_id and meeting.contact_id:
            parent_module = "Contacts"
            cmap = self.session.query(ZohoRecordMapping).filter(
                ZohoRecordMapping.gtm_entity_type == "contact",
                ZohoRecordMapping.gtm_entity_id == meeting.contact_id,
            ).first()
            if not cmap:
                cmap = self.sync_contact_outbound(meeting.contact_id, job_id=sync_job_id)
            if cmap:
                parent_id = cmap.zoho_record_id

        if not parent_id:
            return

        # 1. Sync MoM Note
        analysis: Optional[MeetingAnalysis] = meeting.analysis
        if analysis:
            note_title = f"Meeting MoM: {meeting.title}"
            mom_content = (
                f"Executive Summary:\n{analysis.executive_summary or 'N/A'}\n\n"
                f"Customer Requirements:\n" + "\n".join([f"- {r}" for r in (analysis.customer_requirements or [])]) + "\n\n"
                f"Operational Pain Points:\n" + "\n".join([f"- {p}" for p in (analysis.customer_pain_points or [])]) + "\n\n"
                f"Agreed Decisions:\n" + "\n".join([f"- {d}" for d in (getattr(analysis, "decisions", None) or getattr(analysis, "agreed_decisions", None) or [])]) + "\n\n"
                f"Recommended Sales Stage: {analysis.recommended_sales_stage or 'Discovery Completed'}\n"
                f"Source: GTMProspecting Amazon Bedrock Meeting Intelligence"
            )
            try:
                self.client.add_note(
                    parent_module=parent_module,
                    parent_id=parent_id,
                    title=note_title,
                    content=mom_content,
                )
            except Exception as e:
                logger.warning("Could not add MoM note to Zoho: %s", e)

        # 2. Sync Action Items as Tasks
        for item in meeting.action_items:
            task_payload = {
                "Subject": f"Action Item: {item.title}",
                "Status": "Completed" if item.status == "completed" else "Not Started",
                "Priority": (item.priority or "Medium").capitalize(),
                "Description": f"Generated from meeting: {meeting.title}",
            }
            if item.due_date:
                task_payload["Due_Date"] = item.due_date.strftime("%Y-%m-%d")
            if parent_module == "Accounts":
                task_payload["What_Id"] = {"id": parent_id}
            else:
                task_payload["Who_Id"] = {"id": parent_id}

            try:
                self.client.create_records("Tasks", [task_payload])
            except Exception as e:
                logger.warning("Could not create Zoho Task for action item: %s", e)

    # -------------------------------------------------------------------------
    # Batch Outbound / Inbound Orchestration
    # -------------------------------------------------------------------------

    def run_outbound_sync(self) -> ZohoSyncJob:
        """Pushes pending Leads, Contacts, and Opportunities to Zoho CRM."""
        job = ZohoSyncJob(job_type="outbound_sync", status="running", started_at=zoho_now())
        self.session.add(job)
        self.session.flush()

        succeeded = 0
        failed = 0

        # Sync top 20 unsynced Leads
        leads = self.session.query(Lead).order_by(Lead.created_at.desc()).limit(20).all()
        for l in leads:
            try:
                res = self.sync_account_outbound(l.id, job_id=job.id)
                if res:
                    succeeded += 1
                else:
                    failed += 1
            except Exception as exc:
                failed += 1
                logger.warning("Error syncing lead %s: %s", l.id, exc)

        # Sync top 20 unsynced Contacts
        contacts = self.session.query(Contact).filter(Contact.email.isnot(None)).order_by(Contact.updated_at.desc()).limit(20).all()
        for c in contacts:
            try:
                res = self.sync_contact_outbound(c.id, job_id=job.id)
                if res:
                    succeeded += 1
                else:
                    failed += 1
            except Exception as exc:
                failed += 1
                logger.warning("Error syncing contact %s: %s", c.id, exc)

        job.status = "completed" if failed == 0 else "partial"
        job.records_processed = succeeded + failed
        job.records_succeeded = succeeded
        job.records_failed = failed
        job.finished_at = zoho_now()

        conn = self.session.query(ZohoConnection).first()
        if conn:
            conn.last_synced_at = zoho_now()

        self.session.flush()
        return job

    def run_inbound_sync(self) -> ZohoSyncJob:
        """Pulls recently updated Accounts and Contacts from Zoho CRM."""
        job = ZohoSyncJob(job_type="inbound_sync", status="running", started_at=zoho_now())
        self.session.add(job)
        self.session.flush()

        succeeded = 0
        failed = 0
        errors: list[str] = []

        # 1. Pull Accounts from Zoho CRM
        try:
            records, _ = self.client.get_records("Accounts", page=1, per_page=100)
            for acc in records:
                try:
                    with self.session.begin_nested():
                        name = acc.get("Account_Name")
                        website = acc.get("Website")
                        zid = str(acc.get("id"))
                        if not name or not zid:
                            continue

                        lead = None
                        map_rec = self.session.query(ZohoRecordMapping).filter(
                            ZohoRecordMapping.zoho_module == "Accounts",
                            ZohoRecordMapping.zoho_record_id == zid,
                        ).first()
                        if map_rec:
                            lead = self.session.get(Lead, map_rec.gtm_entity_id)

                        if not lead and website:
                            lead = self.session.query(Lead).filter(Lead.domain == website).first()

                        if not lead and name:
                            lead = self.session.query(Lead).filter(func.lower(Lead.company_name) == name.lower().strip()).first()

                        if lead:
                            if acc.get("Phone") and not lead.phone:
                                lead.phone = acc["Phone"]
                            if acc.get("Industry") and not lead.industry:
                                lead.industry = acc["Industry"]
                        else:
                            comp_key = clean_company_key(name)
                            lead = Lead(
                                id=new_id(),
                                company_name=name,
                                company_key=comp_key,
                                domain=website,
                                phone=acc.get("Phone"),
                                industry=acc.get("Industry"),
                                extra={"source": "zoho_crm_inbound"},
                            )
                            self.session.add(lead)
                            self.session.flush()

                        existing_lead_map = self.session.query(ZohoRecordMapping).filter(
                            ZohoRecordMapping.gtm_entity_type == "lead",
                            ZohoRecordMapping.gtm_entity_id == lead.id,
                        ).first()

                        if not existing_lead_map and not map_rec:
                            self.session.add(ZohoRecordMapping(
                                gtm_entity_type="lead",
                                gtm_entity_id=lead.id,
                                zoho_module="Accounts",
                                zoho_record_id=zid,
                                external_id=f"gtm_lead_{lead.id}",
                                sync_status="synced",
                                last_synced_at=zoho_now(),
                            ))
                        elif existing_lead_map:
                            existing_lead_map.last_synced_at = zoho_now()

                        self._log_sync(
                            job_id=job.id,
                            entity_type="lead",
                            entity_id=lead.id,
                            zoho_module="Accounts",
                            zoho_record_id=zid,
                            action="pull",
                            status="success",
                            message=f"Inbound sync for account '{name}' (Zoho ID: {zid})",
                        )
                        succeeded += 1
                except Exception as inner_exc:
                    failed += 1
                    errors.append(f"Account {acc.get('id')}: {inner_exc}")
        except Exception as exc:
            failed += 1
            errors.append(f"Accounts module fetch failed: {exc}")
            logger.error("Zoho Accounts inbound sync error: %s", exc)

        # 2. Pull Contacts from Zoho CRM
        try:
            contact_records, _ = self.client.get_records("Contacts", page=1, per_page=100)
            for c in contact_records:
                try:
                    with self.session.begin_nested():
                        zid = str(c.get("id"))
                        if not zid:
                            continue

                        first_name = c.get("First_Name") or ""
                        last_name = c.get("Last_Name") or ""
                        full_name = f"{first_name} {last_name}".strip() or last_name or first_name or "Unknown Contact"
                        email = (c.get("Email") or "").strip() or None
                        phone = (c.get("Phone") or "").strip() or None
                        title = c.get("Title")
                        department = c.get("Department")

                        acc_obj = c.get("Account_Name") or {}
                        acc_id = str(acc_obj.get("id")) if isinstance(acc_obj, dict) and acc_obj.get("id") else None
                        acc_name = acc_obj.get("name") if isinstance(acc_obj, dict) else (acc_obj if isinstance(acc_obj, str) else None)

                        # Resolve parent Lead
                        lead = None
                        if acc_id:
                            acc_map = self.session.query(ZohoRecordMapping).filter(
                                ZohoRecordMapping.zoho_module == "Accounts",
                                ZohoRecordMapping.zoho_record_id == acc_id,
                            ).first()
                            if acc_map:
                                lead = self.session.get(Lead, acc_map.gtm_entity_id)

                        if not lead and acc_name:
                            lead = self.session.query(Lead).filter(func.lower(Lead.company_name) == acc_name.lower().strip()).first()

                        if not lead and email and "@" in email:
                            email_domain = email.split("@")[-1].lower()
                            if email_domain not in ("gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com"):
                                lead = self.session.query(Lead).filter(Lead.domain == email_domain).first()

                        # If still no lead, create an inbound lead for this contact's company
                        if not lead:
                            company_title = acc_name or (f"{email.split('@')[-1].split('.')[0].title()} Logistics" if email and "@" in email else f"{full_name} Organization")
                            comp_key = clean_company_key(company_title)
                            lead = Lead(
                                id=new_id(),
                                company_name=company_title,
                                company_key=comp_key,
                                phone=phone,
                                extra={"source": "zoho_crm_inbound"},
                            )
                            self.session.add(lead)
                            self.session.flush()

                            if acc_id:
                                existing_lead_map = self.session.query(ZohoRecordMapping).filter(
                                    ZohoRecordMapping.gtm_entity_type == "lead",
                                    ZohoRecordMapping.gtm_entity_id == lead.id,
                                ).first()
                                if not existing_lead_map:
                                    self.session.add(ZohoRecordMapping(
                                        gtm_entity_type="lead",
                                        gtm_entity_id=lead.id,
                                        zoho_module="Accounts",
                                        zoho_record_id=acc_id,
                                        external_id=f"gtm_lead_{lead.id}",
                                        sync_status="synced",
                                        last_synced_at=zoho_now(),
                                    ))

                        # Resolve Contact in GTM
                        contact_map = self.session.query(ZohoRecordMapping).filter(
                            ZohoRecordMapping.zoho_module == "Contacts",
                            ZohoRecordMapping.zoho_record_id == zid,
                        ).first()

                        contact = None
                        if contact_map:
                            contact = self.session.get(Contact, contact_map.gtm_entity_id)

                        if not contact and email:
                            contact = self.session.query(Contact).filter(
                                Contact.lead_id == lead.id,
                                Contact.email == email,
                            ).first()

                        if contact:
                            contact.name = full_name
                            if email:
                                contact.email = email
                            if title:
                                contact.title = title
                            if department:
                                contact.department = department
                            if email and contact.verification_status != "verified":
                                contact.verification_status = "verified"
                            contact.updated_at = now()
                        else:
                            contact = Contact(
                                id=new_id(),
                                lead_id=lead.id,
                                name=full_name,
                                email=email,
                                title=title,
                                department=department,
                                apollo_id=f"zoho_{zid}",
                                source="Zoho CRM",
                                verification_status="verified" if email else "unverified",
                                is_active=True,
                            )
                            self.session.add(contact)
                            self.session.flush()

                        existing_contact_map = self.session.query(ZohoRecordMapping).filter(
                            ZohoRecordMapping.gtm_entity_type == "contact",
                            ZohoRecordMapping.gtm_entity_id == contact.id,
                        ).first()

                        if not existing_contact_map and not contact_map:
                            self.session.add(ZohoRecordMapping(
                                gtm_entity_type="contact",
                                gtm_entity_id=contact.id,
                                zoho_module="Contacts",
                                zoho_record_id=zid,
                                external_id=f"gtm_contact_{contact.id}",
                                sync_status="synced",
                                last_synced_at=zoho_now(),
                            ))
                        elif existing_contact_map:
                            existing_contact_map.last_synced_at = zoho_now()

                        self._log_sync(
                            job_id=job.id,
                            entity_type="contact",
                            entity_id=contact.id,
                            zoho_module="Contacts",
                            zoho_record_id=zid,
                            action="pull",
                            status="success",
                            message=f"Synced contact '{full_name}' ({email or 'no email'}) to lead '{lead.company_name}'",
                        )
                        succeeded += 1
                except Exception as inner_exc:
                    failed += 1
                    errors.append(f"Contact {c.get('id')}: {inner_exc}")
        except Exception as exc:
            failed += 1
            errors.append(f"Contacts module fetch failed: {exc}")
            logger.error("Zoho Contacts inbound sync error: %s", exc)

        job.records_processed = succeeded + failed
        job.records_succeeded = succeeded
        job.records_failed = failed
        job.status = "completed" if failed == 0 else ("partial" if succeeded > 0 else "failed")
        job.error_summary = "; ".join(errors[:5]) if errors else None
        job.finished_at = zoho_now()

        conn = self.session.query(ZohoConnection).first()
        if conn:
            conn.last_synced_at = zoho_now()

        self.session.flush()
        return job

    def run_reconcile_sync(self) -> ZohoSyncJob:
        """Executes full bidirectional reconciliation: inbound pull followed by outbound push."""
        inbound_job = self.run_inbound_sync()
        outbound_job = self.run_outbound_sync()

        # Consolidate into a unified reconcile record
        reconcile_job = ZohoSyncJob(
            job_type="reconcile",
            status="completed" if (inbound_job.status == "completed" and outbound_job.status == "completed") else "partial",
            records_processed=inbound_job.records_processed + outbound_job.records_processed,
            records_succeeded=inbound_job.records_succeeded + outbound_job.records_succeeded,
            records_failed=inbound_job.records_failed + outbound_job.records_failed,
            started_at=inbound_job.started_at,
            finished_at=zoho_now(),
            details={
                "inbound_job_id": inbound_job.id,
                "inbound_succeeded": inbound_job.records_succeeded,
                "outbound_job_id": outbound_job.id,
                "outbound_succeeded": outbound_job.records_succeeded,
            },
            error_summary=inbound_job.error_summary or outbound_job.error_summary,
        )
        self.session.add(reconcile_job)
        self.session.flush()
        return reconcile_job

    def _log_sync(
        self,
        job_id: Optional[str],
        entity_type: str,
        entity_id: Optional[str],
        zoho_module: str,
        zoho_record_id: Optional[str],
        action: str,
        status: str,
        message: Optional[str],
    ):
        log = ZohoSyncLog(
            job_id=job_id,
            entity_type=entity_type,
            entity_id=entity_id,
            zoho_module=zoho_module,
            zoho_record_id=zoho_record_id,
            action=action,
            status=status,
            message=message,
        )
        self.session.add(log)
