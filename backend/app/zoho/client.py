import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import requests
from sqlalchemy.orm import Session

from app.config import settings
from app.zoho.crypto import decrypt_token, encrypt_token
from app.zoho.models import ZohoConnection, now

logger = logging.getLogger(__name__)


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class ZohoAPIError(Exception):
    """Normalized Zoho CRM API Error."""
    def __init__(self, message: str, status_code: int = 500, code: Optional[str] = None, details: Optional[Dict] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details or {}

    def __str__(self):
        code_str = f" [{self.code}]" if self.code else ""
        return f"ZohoAPIError({self.status_code}{code_str}): {self.message}"


class ZohoRateLimitError(ZohoAPIError):
    """Raised when Zoho rate limit / concurrency limit is hit."""
    pass


class ZohoClient:
    """
    Robust Zoho CRM REST API Client (API v8).
    Handles proactive OAuth token refresh, regional routing, rate limits, exponential backoff,
    pagination, and batch upserts.
    """

    DEFAULT_MODULE_FIELDS = {
        "Accounts": "id,Account_Name,Website,Phone,Industry,Annual_Revenue,Employees,Modified_Time",
        "Contacts": "id,First_Name,Last_Name,Email,Phone,Title,Department,Account_Name,Modified_Time",
        "Leads": "id,First_Name,Last_Name,Company,Email,Phone,Designation,Industry,Modified_Time",
        "Deals": "id,Deal_Name,Amount,Stage,Closing_Date,Account_Name,Contact_Name,Modified_Time",
        "Tasks": "id,Subject,Due_Date,Status,Priority,What_Id,Who_Id,Modified_Time",
        "Events": "id,Event_Title,Start_DateTime,End_DateTime,What_Id,Who_Id,Modified_Time",
    }

    def __init__(self, session: Session, connection: Optional[ZohoConnection] = None):
        self.session = session
        self._connection = connection

    def get_connection(self) -> ZohoConnection:
        if self._connection:
            return self._connection
        conn = self.session.query(ZohoConnection).filter(ZohoConnection.is_active == True).first()
        if not conn:
            raise ZohoAPIError("Zoho CRM is not connected or active.", status_code=401, code="NOT_CONNECTED")
        self._connection = conn
        return conn

    def get_access_token(self) -> str:
        """
        Retrieves a valid access token. If missing or expiring within 5 minutes,
        proactively refreshes the token using the stored encrypted refresh token.
        """
        conn = self.get_connection()
        current_time = now()
        expires_at = ensure_utc(conn.access_token_expires_at)

        # Check if current access token is valid and not expiring in next 300 seconds
        if (
            conn.access_token_encrypted
            and expires_at
            and expires_at > (current_time + timedelta(seconds=300))
        ):
            return decrypt_token(conn.access_token_encrypted)

        # Refresh access token
        return self.refresh_access_token()

    def refresh_access_token(self) -> str:
        """Exchanges refresh token with Zoho Accounts server for a new access token."""
        conn = self.get_connection()
        refresh_token = decrypt_token(conn.refresh_token_encrypted)
        if not refresh_token:
            raise ZohoAPIError("No refresh token available to refresh Zoho CRM session.", status_code=401, code="NO_REFRESH_TOKEN")

        accounts_domain = (conn.accounts_domain or settings.zoho_accounts_domain or "https://accounts.zoho.in").rstrip("/")
        token_url = f"{accounts_domain}/oauth/v2/token"
        
        client_id = (settings.zoho_client_id or "").strip()
        client_secret = (settings.zoho_client_secret or "").strip()

        params = {
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
        }

        logger.info("Refreshing Zoho access token via %s", accounts_domain)
        try:
            resp = requests.post(token_url, data=params, timeout=20)
            data = resp.json()
        except Exception as exc:
            logger.error("Network failure contacting Zoho Accounts token endpoint: %s", exc)
            raise ZohoAPIError(f"Failed to refresh Zoho token: {exc}", status_code=502) from exc

        if resp.status_code != 200 or "access_token" not in data:
            err_msg = data.get("error") or data.get("message") or resp.text
            logger.error("Zoho token refresh failed with code %s: %s", resp.status_code, err_msg)
            conn.last_error = f"Token refresh failed: {err_msg}"
            self.session.flush()
            raise ZohoAPIError(f"Token refresh rejected: {err_msg}", status_code=resp.status_code, code="REFRESH_FAILED", details=data)

        access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        expires_at = now() + timedelta(seconds=expires_in)

        # Update connection
        conn.access_token_encrypted = encrypt_token(access_token)
        conn.access_token_expires_at = expires_at
        if "api_domain" in data and data["api_domain"]:
            conn.api_domain = data["api_domain"].rstrip("/")
        conn.last_error = None
        self.session.flush()

        logger.info("Zoho access token refreshed successfully. Expires at %s", expires_at.isoformat())
        return access_token

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Any] = None,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """
        Executes an authenticated HTTP request to Zoho CRM API v8 with exponential backoff on 429 rate limit.
        """
        conn = self.get_connection()
        api_domain = (conn.api_domain or settings.zoho_api_domain or "https://www.zohoapis.in").rstrip("/")
        version = (conn.crm_api_version or settings.zoho_crm_api_version or "v8").lstrip("/")
        
        # Normalize path
        path_clean = path.lstrip("/")
        if not path_clean.startswith("crm/"):
            url = f"{api_domain}/crm/{version}/{path_clean}"
        else:
            url = f"{api_domain}/{path_clean}"

        attempt = 0
        backoff_delay = 1.0

        while attempt < max_retries:
            attempt += 1
            access_token = self.get_access_token()
            headers = {
                "Authorization": f"Zoho-oauthtoken {access_token}",
                "Content-Type": "application/json",
            }

            try:
                resp = requests.request(
                    method=method.upper(),
                    url=url,
                    params=params,
                    json=json_data,
                    headers=headers,
                    timeout=30,
                )
            except requests.RequestException as exc:
                if attempt >= max_retries:
                    raise ZohoAPIError(f"HTTP connection failed: {exc}", status_code=503) from exc
                time.sleep(backoff_delay)
                backoff_delay *= 2
                continue

            # Check for Rate Limit (HTTP 429)
            if resp.status_code == 429:
                logger.warning("Zoho CRM rate limit hit (429) on attempt %d/%d for %s", attempt, max_retries, url)
                if attempt >= max_retries:
                    raise ZohoRateLimitError("Zoho CRM API rate limit exceeded.", status_code=429, code="RATE_LIMIT_EXCEEDED")
                time.sleep(backoff_delay)
                backoff_delay *= 2
                continue

            # Check for expired token (HTTP 401)
            if resp.status_code == 401:
                logger.info("Received 401 from Zoho, forcing token refresh...")
                try:
                    self.refresh_access_token()
                except Exception:
                    pass
                if attempt < max_retries:
                    continue

            # Handle 204 No Content
            if resp.status_code == 204:
                return {"data": [], "info": {"more_records": False}}

            try:
                result = resp.json()
            except Exception:
                result = {"raw": resp.text}

            # Check for error status codes
            if resp.status_code >= 400:
                err_code = "API_ERROR"
                err_msg = f"Zoho API returned HTTP {resp.status_code}"
                if isinstance(result, dict):
                    err_code = result.get("code") or result.get("status") or err_code
                    err_msg = result.get("message") or result.get("details", {}).get("error") or err_msg
                raise ZohoAPIError(err_msg, status_code=resp.status_code, code=err_code, details=result if isinstance(result, dict) else {})

            return result if isinstance(result, dict) else {"data": result}

        raise ZohoAPIError("Max retries exceeded for Zoho request.", status_code=500)

    # Standard API Methods
    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request("GET", path, params=params)

    def post(self, path: str, json_data: Any, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request("POST", path, params=params, json_data=json_data)

    def put(self, path: str, json_data: Any, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request("PUT", path, params=params, json_data=json_data)

    def delete(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request("DELETE", path, params=params)

    # High-level Module Operations
    def get_organization(self) -> Dict[str, Any]:
        """Fetches current authenticated Zoho organization details."""
        res = self.get("org")
        orgs = res.get("org") or []
        if isinstance(orgs, list) and orgs:
            return orgs[0]
        return {}

    def get_modules(self) -> List[Dict[str, Any]]:
        """Discovers active CRM modules."""
        res = self.get("settings/modules")
        return res.get("modules") or []

    def get_module_fields(self, module_api_name: str) -> List[Dict[str, Any]]:
        """Discovers fields and picklists for a module."""
        res = self.get(f"settings/fields?module={module_api_name}")
        return res.get("fields") or []

    def get_records(
        self,
        module: str,
        page: int = 1,
        per_page: int = 50,
        sort_by: Optional[str] = None,
        sort_order: str = "desc",
        modified_since: Optional[datetime] = None,
        fields: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Retrieves paginated records from a Zoho module.
        Returns (records_list, pagination_info).
        """
        params: Dict[str, Any] = {"page": page, "per_page": per_page}
        if sort_by:
            params["sort_by"] = sort_by
            params["sort_order"] = sort_order

        # Zoho CRM API v8 mandates the 'fields' parameter on GET /{module}
        if fields:
            params["fields"] = fields
        elif module in self.DEFAULT_MODULE_FIELDS:
            params["fields"] = self.DEFAULT_MODULE_FIELDS[module]
        elif modified_since:
            params["fields"] = "id,Modified_Time"

        res = self.get(module, params=params)
        records = res.get("data") or []
        info = res.get("info") or {}
        return records, info

    def get_record_by_id(self, module: str, record_id: str) -> Optional[Dict[str, Any]]:
        """Fetches a single record by ID."""
        try:
            res = self.get(f"{module}/{record_id}")
            data = res.get("data") or []
            return data[0] if data else None
        except ZohoAPIError as e:
            if e.status_code == 404 or e.code == "INVALID_DATA":
                return None
            raise

    def search_records(self, module: str, criteria: str) -> List[Dict[str, Any]]:
        """
        Searches records using Zoho search criteria.
        E.g. criteria="((Email:equals:john@example.com))"
        """
        params = {"criteria": criteria}
        try:
            res = self.get(f"{module}/search", params=params)
            return res.get("data") or []
        except ZohoAPIError as e:
            if e.status_code == 204 or e.code == "NO_CONTENT":
                return []
            raise

    def upsert_records(
        self,
        module: str,
        records: List[Dict[str, Any]],
        duplicate_check_fields: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Upserts records into Zoho CRM via `POST /{module}/upsert`.
        Uses duplicate_check_fields (e.g. ['Email'] or ['Account_Name']) to prevent duplicates.
        """
        if not records:
            return []
        payload: Dict[str, Any] = {"data": records}
        if duplicate_check_fields:
            payload["duplicate_check_fields"] = duplicate_check_fields

        res = self.post(f"{module}/upsert", json_data=payload)
        return res.get("data") or []

    def create_records(self, module: str, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Inserts records into a module."""
        if not records:
            return []
        res = self.post(module, json_data={"data": records})
        return res.get("data") or []

    def update_records(self, module: str, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Updates existing records in a module."""
        if not records:
            return []
        res = self.put(module, json_data={"data": records})
        return res.get("data") or []

    def add_note(self, parent_module: str, parent_id: str, title: str, content: str) -> Dict[str, Any]:
        """Creates a Note attached to a parent Zoho record (Account, Contact, Lead, or Deal)."""
        note_data = {
            "Note_Title": title,
            "Note_Content": content,
            "Parent_Id": parent_id,
            "$se_module": parent_module,
        }
        res = self.post("Notes", json_data={"data": [note_data]})
        created = res.get("data") or []
        return created[0] if created else {}
