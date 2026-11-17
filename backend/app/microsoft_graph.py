import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
import msal
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calendar_utils import available_slots, utc
from app.config import settings
from app.database import get_db
from app.models import MicrosoftOAuthCredential, MicrosoftOAuthState, now

router = APIRouter(prefix="/microsoft")
GRAPH_SCOPES = ["User.Read", "Calendars.ReadBasic"]
CALENDAR_SCOPE = "Calendars.ReadBasic"
CALLBACK_URI = "http://localhost:8000/microsoft/oauth/callback"
GRAPH_HOST = "graph.microsoft.com"
COOKIE = "microsoft_oauth_browser"


class AvailabilityRequest(BaseModel):
    start: AwareDatetime
    end: AwareDatetime


class GraphRequestError(RuntimeError):
    pass


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def cipher() -> Fernet:
    try:
        return Fernet(settings.microsoft_token_encryption_key.encode("ascii"))
    except (ValueError, UnicodeError) as exc:
        raise RuntimeError("MICROSOFT_TOKEN_ENCRYPTION_KEY must be a valid Fernet key.") from exc


def validate_config():
    required = (
        settings.microsoft_tenant_id,
        settings.microsoft_client_id,
        settings.microsoft_client_secret,
        settings.microsoft_organizer_email,
    )
    if not all(required):
        raise RuntimeError("Microsoft tenant, client, and organizer settings are required.")
    if settings.microsoft_redirect_uri != CALLBACK_URI:
        raise RuntimeError(f"MICROSOFT_REDIRECT_URI must be {CALLBACK_URI}.")
    try:
        UUID(settings.microsoft_tenant_id)
    except ValueError as exc:
        raise RuntimeError("MICROSOFT_TENANT_ID must be the Entra directory (tenant) ID.") from exc
    graph_url = urlsplit(settings.microsoft_graph_base_url)
    if (graph_url.scheme != "https" or graph_url.netloc != GRAPH_HOST
        or graph_url.path.rstrip("/") != "/v1.0" or graph_url.username or graph_url.password
        or graph_url.query or graph_url.fragment):
        raise RuntimeError("MICROSOFT_GRAPH_BASE_URL must be https://graph.microsoft.com/v1.0.")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", settings.microsoft_organizer_email.strip()):
        raise RuntimeError("MICROSOFT_ORGANIZER_EMAIL must be a valid work or school email address.")
    cipher()


def client(cache=None):
    validate_config()
    return msal.ConfidentialClientApplication(
        settings.microsoft_client_id,
        client_credential=settings.microsoft_client_secret,
        authority=f"https://login.microsoftonline.com/{settings.microsoft_tenant_id}",
        token_cache=cache,
    )


def graph_request(access_token: str, method: str, path: str, *, payload=None, headers=None):
    request_headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    request_headers.update(headers or {})
    url = f"{settings.microsoft_graph_base_url.rstrip('/')}/{path.lstrip('/')}"
    try:
        with httpx.Client(timeout=20, follow_redirects=False) as http:
            response = http.request(method, url, json=payload, headers=request_headers)
    except httpx.HTTPError as exc:
        raise GraphRequestError("Microsoft Graph could not be reached.") from exc
    if response.status_code == 401:
        raise GraphRequestError("Microsoft authorization expired or was rejected; reconnect the organizer.")
    if response.status_code == 403:
        raise GraphRequestError(
            "Microsoft Graph denied access. Verify delegated permission consent and organizer mailbox access."
        )
    if response.status_code == 429:
        raise GraphRequestError("Microsoft Graph throttled the request; retry later.")
    if response.is_error:
        raise GraphRequestError(f"Microsoft Graph request failed (HTTP {response.status_code}).")
    try:
        return response.json()
    except ValueError as exc:
        raise GraphRequestError("Microsoft Graph returned an invalid response.") from exc


def _account_email(profile: dict) -> str | None:
    addresses = {
        value.strip().casefold()
        for value in (profile.get("mail"), profile.get("userPrincipalName"))
        if isinstance(value, str) and value.strip()
    }
    configured = settings.microsoft_organizer_email.strip().casefold()
    return configured if configured in addresses else None


def _auth_error(result: dict) -> str:
    error = str(result.get("error", "")).casefold()
    suberror = str(result.get("suberror", "")).casefold()
    if error in {"consent_required", "unauthorized_client"} or suberror == "consent_required":
        return "Microsoft Graph permission consent is required; ask the tenant administrator if user consent is restricted."
    if error in {"interaction_required", "invalid_grant"}:
        return "Microsoft authorization is expired or incomplete; start the connection again."
    return "Microsoft sign-in failed. Check the tenant, client registration, redirect URI, and requested permissions."


def start_oauth(session: Session):
    validate_config()
    flow = client(msal.SerializableTokenCache()).initiate_auth_code_flow(
        scopes=GRAPH_SCOPES,
        redirect_uri=settings.microsoft_redirect_uri,
    )
    if "error" in flow or not flow.get("auth_uri") or not flow.get("state"):
        raise RuntimeError("Microsoft authorization could not be initialized.")
    state = flow["state"]
    browser = secrets.token_urlsafe(32)
    record = MicrosoftOAuthState(
        state_hash=digest(state),
        browser_hash=digest(browser),
        auth_flow_encrypted=cipher().encrypt(json.dumps(flow).encode("utf-8")),
        expires_at=now() + timedelta(minutes=10),
    )
    session.add(record)
    session.commit()
    response = RedirectResponse(flow["auth_uri"], status_code=302, headers={"Cache-Control": "no-store"})
    response.set_cookie(COOKIE, browser, max_age=600, httponly=True, samesite="lax",
                        secure=False, path="/microsoft/oauth")
    return response


def _load_auth_flow(record: MicrosoftOAuthState) -> dict:
    try:
        value = cipher().decrypt(record.auth_flow_encrypted).decode("utf-8")
        flow = json.loads(value)
    except (InvalidToken, UnicodeError, ValueError, TypeError) as exc:
        raise HTTPException(503, "Microsoft OAuth state cannot be decrypted; check the encryption key.") from exc
    if not isinstance(flow, dict):
        raise HTTPException(503, "Microsoft OAuth state is invalid; start the connection again.")
    return flow


def oauth_callback(request: Request, session: Session):
    state = request.query_params.get("state", "")
    browser = request.cookies.get(COOKIE, "")
    if not state or not browser:
        raise HTTPException(400, "Microsoft OAuth state or browser cookie is missing.")
    record = session.scalar(select(MicrosoftOAuthState).where(
        MicrosoftOAuthState.state_hash == digest(state)
    ).with_for_update())
    if (not record or record.consumed_at is not None or utc(record.expires_at) <= now()
        or not hmac.compare_digest(record.browser_hash, digest(browser))):
        raise HTTPException(400, "Microsoft OAuth state is invalid, expired, or already used.")

    validate_config()
    flow = _load_auth_flow(record)
    if flow.get("state") != state:
        raise HTTPException(400, "Microsoft OAuth state did not match.")
    record.consumed_at = now()
    session.commit()
    if request.query_params.get("error"):
        raise HTTPException(400, "Microsoft authorization was denied.")

    cache = msal.SerializableTokenCache()
    application = client(cache)
    try:
        result = application.acquire_token_by_auth_code_flow(flow, dict(request.query_params))
    except ValueError as exc:
        raise HTTPException(400, "Microsoft OAuth response failed state validation; start again.") from exc
    if not isinstance(result, dict) or not result.get("access_token"):
        raise HTTPException(403, _auth_error(result if isinstance(result, dict) else {}))

    claims = result.get("id_token_claims")
    if not isinstance(claims, dict):
        raise HTTPException(403, "Microsoft did not return a verified signed-in identity.")
    try:
        actual_tenant = UUID(str(claims.get("tid", "")))
        expected_tenant = UUID(settings.microsoft_tenant_id)
    except ValueError as exc:
        raise HTTPException(403, "The signed-in Microsoft identity has no valid tenant ID.") from exc
    if actual_tenant != expected_tenant or not claims.get("oid"):
        raise HTTPException(403, "Sign in with an account from the configured Microsoft Entra tenant.")

    try:
        profile = graph_request(
            result["access_token"], "GET", "/me",
        )
    except GraphRequestError as exc:
        raise HTTPException(502, str(exc)) from exc
    organizer_email = _account_email(profile if isinstance(profile, dict) else {})
    if not organizer_email:
        raise HTTPException(403, "The signed-in account does not match MICROSOFT_ORGANIZER_EMAIL.")

    scopes = result.get("scope", [])
    scopes = scopes.split() if isinstance(scopes, str) else scopes
    if not isinstance(scopes, list) or not any(
        isinstance(scope, str) and scope.casefold() == CALENDAR_SCOPE.casefold() for scope in scopes
    ):
        raise HTTPException(403, "Calendars.ReadBasic consent was not granted; reconnect after permission approval.")

    try:
        serialized_cache = cache.serialize().encode("utf-8")
    except (ValueError, TypeError) as exc:
        raise HTTPException(502, "Microsoft token cache could not be saved.") from exc
    encrypted_cache = cipher().encrypt(serialized_cache)
    credential = session.get(MicrosoftOAuthCredential, "organizer")
    if credential is None:
        credential = MicrosoftOAuthCredential(
            id="organizer",
            tenant_id=str(expected_tenant),
            organizer_email=organizer_email,
            token_cache_encrypted=encrypted_cache,
            scopes=scopes,
        )
        session.add(credential)
    else:
        credential.tenant_id = str(expected_tenant)
        credential.organizer_email = organizer_email
        credential.token_cache_encrypted = encrypted_cache
        credential.scopes = scopes
        credential.updated_at = now()
    session.commit()
    response = RedirectResponse("http://localhost:3000/meetings?microsoft=connected", status_code=303,
                                headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
    response.delete_cookie(COOKIE, path="/microsoft/oauth")
    return response


def access_token(session: Session) -> str:
    validate_config()
    credential = session.scalar(select(MicrosoftOAuthCredential).where(
        MicrosoftOAuthCredential.id == "organizer"
    ).with_for_update())
    if credential is None:
        raise RuntimeError("Connect the configured Microsoft organizer account first.")
    if (credential.tenant_id != str(UUID(settings.microsoft_tenant_id))
        or credential.organizer_email.casefold() != settings.microsoft_organizer_email.strip().casefold()):
        raise RuntimeError("Microsoft organizer configuration changed; reconnect the account.")

    cache = msal.SerializableTokenCache()
    try:
        serialized_cache = cipher().decrypt(credential.token_cache_encrypted).decode("utf-8")
        cache.deserialize(serialized_cache)
    except (InvalidToken, UnicodeError, ValueError, TypeError) as exc:
        raise RuntimeError("Microsoft token cache cannot be decrypted; reconnect the organizer.") from exc

    application = client(cache)
    accounts = application.get_accounts()
    if len(accounts) != 1:
        raise RuntimeError("Microsoft organizer token cache is missing or ambiguous; reconnect the account.")
    result = application.acquire_token_silent_with_error([CALENDAR_SCOPE], account=accounts[0])
    if not isinstance(result, dict) or not result.get("access_token"):
        raise RuntimeError(_auth_error(result if isinstance(result, dict) else {}))
    if cache.has_state_changed:
        credential.token_cache_encrypted = cipher().encrypt(cache.serialize().encode("utf-8"))
        credential.updated_at = now()
        session.commit()
    return result["access_token"]


def graph_datetime(value) -> datetime:
    if not isinstance(value, dict) or not isinstance(value.get("dateTime"), str):
        raise ValueError("Microsoft schedule interval is incomplete.")
    if value.get("timeZone") != "UTC":
        raise ValueError("Microsoft schedule response was not returned in UTC.")
    parsed = datetime.fromisoformat(value["dateTime"].replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return utc(parsed)


def busy_intervals(session: Session, start: datetime, end: datetime):
    token = access_token(session)
    payload = {
        "schedules": [settings.microsoft_organizer_email],
        "startTime": {"dateTime": utc(start).replace(tzinfo=None).isoformat(), "timeZone": "UTC"},
        "endTime": {"dateTime": utc(end).replace(tzinfo=None).isoformat(), "timeZone": "UTC"},
        "availabilityViewInterval": 30,
    }
    result = graph_request(
        token, "POST", "/me/calendar/getSchedule", payload=payload,
        headers={"Prefer": 'outlook.timezone="UTC"'},
    )
    schedules = result.get("value") if isinstance(result, dict) else None
    if not isinstance(schedules, list) or len(schedules) != 1 or not isinstance(schedules[0], dict):
        raise GraphRequestError("Microsoft Graph returned an incomplete schedule response.")
    schedule = schedules[0]
    if schedule.get("error"):
        raise GraphRequestError("Microsoft Graph could not read the organizer's calendar availability.")
    if str(schedule.get("scheduleId", "")).casefold() != settings.microsoft_organizer_email.casefold():
        raise GraphRequestError("Microsoft Graph returned availability for an unexpected organizer.")
    items = schedule.get("scheduleItems")
    if not isinstance(items, list):
        raise GraphRequestError("Microsoft Graph returned an incomplete schedule response.")
    busy = []
    known_statuses = {"free", "tentative", "busy", "oof", "workingElsewhere", "unknown"}
    for item in items:
        if not isinstance(item, dict) or item.get("status") not in known_statuses:
            raise GraphRequestError("Microsoft Graph returned an invalid calendar item.")
        if item["status"] == "free":
            continue
        try:
            busy_start, busy_end = graph_datetime(item.get("start")), graph_datetime(item.get("end"))
        except (ValueError, TypeError) as exc:
            raise GraphRequestError("Microsoft Graph returned an invalid calendar interval.") from exc
        if busy_end <= busy_start:
            raise GraphRequestError("Microsoft Graph returned an invalid calendar interval.")
        busy.append((busy_start, busy_end))
    return busy


@router.get("/oauth/start")
def start_oauth_route(session: Session = Depends(get_db)):
    try:
        return start_oauth(session)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/oauth/callback")
def oauth_callback_route(request: Request, session: Session = Depends(get_db)):
    try:
        return oauth_callback(request, session)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/oauth/status")
def oauth_status(session: Session = Depends(get_db)):
    credential = session.get(MicrosoftOAuthCredential, "organizer")
    return {
        "connected": bool(credential),
        "organizer_email": credential.organizer_email if credential else None,
        "tenant_id": credential.tenant_id if credential else None,
        "scopes": credential.scopes if credential else [],
    }


@router.post("/oauth/disconnect")
def disconnect_oauth(session: Session = Depends(get_db)):
    credential = session.get(MicrosoftOAuthCredential, "organizer")
    if credential is None:
        raise HTTPException(404, "Microsoft organizer is not connected.")
    session.delete(credential)
    session.commit()
    return {"connected": False, "local_tokens_removed": True}


@router.post("/availability")
def availability(data: AvailabilityRequest, session: Session = Depends(get_db)):
    start, end = utc(data.start), utc(data.end)
    current = now()
    duration = settings.meeting_duration_minutes
    window = settings.meeting_booking_window_days
    work_start, work_end = settings.meeting_workday_start_hour, settings.meeting_workday_end_hour
    if not (1 <= duration <= 240 and 1 <= window <= 90 and 0 <= work_start < work_end <= 24):
        raise HTTPException(503, "Invalid meeting duration, booking window or work hours configuration.")
    if start < current or end <= start or end > current + timedelta(days=window):
        raise HTTPException(400, "Choose a future interval within the configured booking window.")
    try:
        ZoneInfo(settings.meeting_timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(503, "MEETING_TIMEZONE must be a valid IANA timezone.") from exc
    try:
        busy = busy_intervals(session, start, end)
        slots = available_slots(start, end, busy, duration, settings.meeting_timezone, work_start, work_end)
    except (RuntimeError, ValueError, TypeError) as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"timezone": settings.meeting_timezone, "duration_minutes": duration, "slots": slots}


