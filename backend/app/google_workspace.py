import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta

# Relax oauthlib token scope validation to allow Google's dynamic scope responses
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

logger = logging.getLogger(__name__)

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from oauthlib.oauth2 import OAuth2Error
from pydantic import AwareDatetime, BaseModel
from requests.exceptions import RequestException
from sqlalchemy import select
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.calendar_utils import available_slots, utc
from app.config import settings
from app.database import get_db
from app.models import GoogleOAuthCredential, GoogleOAuthState, now

router = APIRouter(prefix="/google")
SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email",
          "https://www.googleapis.com/auth/calendar.freebusy"]
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.freebusy"
EVENTS_SCOPE = "https://www.googleapis.com/auth/calendar.events.owned"
BOOKING_SCOPES = [*SCOPES, EVENTS_SCOPE]
MEET_SPACE_SCOPE = "https://www.googleapis.com/auth/meetings.space.created"
DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
CALENDAR_EVENTS_FULL_SCOPE = "https://www.googleapis.com/auth/calendar.events"
MEETING_FULL_SCOPES = [
    *BOOKING_SCOPES,
    CALENDAR_EVENTS_FULL_SCOPE,
    MEET_SPACE_SCOPE,
    DRIVE_READONLY_SCOPE,
]
COOKIE = "google_oauth_browser"


def digest(value: str):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def cipher():
    try:
        return Fernet(settings.google_token_encryption_key.encode("ascii"))
    except (ValueError, UnicodeError) as exc:
        raise RuntimeError("GOOGLE_TOKEN_ENCRYPTION_KEY must be a valid Fernet key.") from exc


def validate_config():
    if not settings.google_client_id or not settings.google_client_secret or not settings.google_workspace_organizer_email:
        raise RuntimeError("Google OAuth client and organizer settings are required.")
    if settings.google_redirect_uri != "http://localhost:8000/google/oauth/callback":
        raise RuntimeError("Google redirect URI must be http://localhost:8000/google/oauth/callback.")
    cipher()


def oauth_flow(state: str, verifier: str, booking: bool = False, meet: bool = True):
    scopes = MEETING_FULL_SCOPES if meet else (BOOKING_SCOPES if booking else SCOPES)
    return Flow.from_client_config({
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }, scopes=scopes, state=state, redirect_uri=settings.google_redirect_uri,
       code_verifier=verifier, autogenerate_code_verifier=False)


def connection_error(exc: Exception):
    return HTTPException(503, str(exc))


@router.get("/oauth/start")
def start_oauth(booking: bool = False, meet: bool = True, session: Session = Depends(get_db)):
    try:
        validate_config()
        state, browser, verifier = (secrets.token_urlsafe(32), secrets.token_urlsafe(32),
                                    secrets.token_urlsafe(64))
        flow = oauth_flow(state, verifier, booking=booking, meet=meet)
        url, _ = flow.authorization_url(access_type="offline", prompt="consent")
        record = GoogleOAuthState(state_hash=digest(state), browser_hash=digest(browser),
                                  verifier_encrypted=cipher().encrypt(verifier.encode()),
                                  booking_requested=booking,
                                  expires_at=now() + timedelta(minutes=10))
        session.add(record)
        session.commit()
    except RuntimeError as exc:
        raise connection_error(exc) from exc
    response = RedirectResponse(url, status_code=302, headers={"Cache-Control": "no-store"})
    response.set_cookie(COOKIE, browser, max_age=600, httponly=True, samesite="lax",
                        secure=False, path="/google/oauth")
    return response


@router.get("/oauth/callback")
def oauth_callback(request: Request, session: Session = Depends(get_db)):
    state = request.query_params.get("state", "")
    browser = request.cookies.get(COOKIE, "")

    # Check for Google error response first
    error = request.query_params.get("error")
    error_desc = request.query_params.get("error_description") or error
    if error:
        logger.warning("Google OAuth authorization error received: %s (%s)", error, error_desc)
        if error == "access_denied":
            raise HTTPException(400, "Google authorization was denied by the user.")
        raise HTTPException(400, f"Google authorization failed: {error_desc}")

    if not state or not browser:
        raise HTTPException(400, "OAuth state or browser cookie is missing.")
    record = session.scalar(select(GoogleOAuthState).where(
        GoogleOAuthState.state_hash == digest(state)
    ).with_for_update())
    if (not record or record.consumed_at is not None or utc(record.expires_at) <= now()
        or not hmac.compare_digest(record.browser_hash, digest(browser))):
        raise HTTPException(400, "OAuth state is invalid, expired or already used.")
    try:
        validate_config()
        verifier = cipher().decrypt(record.verifier_encrypted).decode("ascii")
    except (RuntimeError, InvalidToken, UnicodeError) as exc:
        raise HTTPException(503, "OAuth state cannot be decrypted; check the encryption key.") from exc
    record.consumed_at = now()
    session.commit()
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(400, "Google authorization code is missing.")
    try:
        flow = oauth_flow(state, verifier, record.booking_requested)
        flow.fetch_token(code=code)
        credentials = flow.credentials
        stored = session.get(GoogleOAuthCredential, "organizer")

        # Handle refresh token: Google may omit refresh_token on re-consent if prompt!='consent'
        refresh_token = credentials.refresh_token
        if not refresh_token:
            if stored and stored.refresh_token_encrypted:
                refresh_token = cipher().decrypt(stored.refresh_token_encrypted).decode("ascii")
            else:
                raise RuntimeError("Google did not provide an offline refresh token and identity.")

        if not credentials.id_token:
            raise RuntimeError("Google did not provide an identity token.")

        granted_scopes = credentials.granted_scopes or credentials.scopes or []
        if CALENDAR_SCOPE not in granted_scopes:
            raise RuntimeError("Google Calendar availability access was not granted.")
        if record.booking_requested and EVENTS_SCOPE not in granted_scopes:
            raise RuntimeError("Google Calendar event access was not granted.")

        identity = id_token.verify_oauth2_token(credentials.id_token, GoogleRequest(), settings.google_client_id)
        email = str(identity.get("email", "")).lower()
        configured_organizer = settings.google_workspace_organizer_email.strip().lower()
        if identity.get("email_verified") is not True or email != configured_organizer:
            raise RuntimeError(f"The authorized Google account ({email}) is not the configured organizer ({configured_organizer}).")

        encrypted = cipher().encrypt(refresh_token.encode())
    except (GoogleAuthError, RequestException, OAuth2Error, ValueError, RuntimeError, Warning) as exc:
        logger.warning("Google authorization failed: %s", exc)
        raise HTTPException(502, f"Google authorization failed: {str(exc)}") from exc
    except Exception as exc:
        logger.exception("Unexpected error in Google OAuth callback: %s", exc)
        raise HTTPException(502, "Google authorization failed due to an unexpected error.") from exc
    stored = session.get(GoogleOAuthCredential, "organizer")
    if stored is None:
        stored = GoogleOAuthCredential(id="organizer", organizer_email=email,
                                       refresh_token_encrypted=encrypted, scopes=list(granted_scopes))
        session.add(stored)
    else:
        stored.organizer_email, stored.refresh_token_encrypted = email, encrypted
        stored.scopes, stored.updated_at = list(granted_scopes), now()
    session.commit()
    response = RedirectResponse("http://localhost:3000/meetings?google=connected", status_code=303,
                                headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
    response.delete_cookie(COOKIE, path="/google/oauth")
    return response


@router.get("/oauth/status")
def oauth_status(session: Session = Depends(get_db)):
    credential = session.get(GoogleOAuthCredential, "organizer")
    return {"connected": bool(credential), "organizer_email": credential.organizer_email if credential else None,
            "booking_access": bool(credential and EVENTS_SCOPE in credential.scopes)}


def google_access_token(session: Session, required_scope: str | None = None):
    validate_config()
    credential = session.get(GoogleOAuthCredential, "organizer")
    if not credential:
        raise RuntimeError("Connect the Google organizer account first.")
    if credential.organizer_email != settings.google_workspace_organizer_email.strip().lower():
        raise RuntimeError("Connected Google organizer does not match configuration; reconnect.")
    if required_scope and required_scope not in credential.scopes:
        raise RuntimeError("Required Google Calendar permission is missing; reconnect the organizer.")
    try:
        refresh_token = cipher().decrypt(credential.refresh_token_encrypted).decode()
        credentials = Credentials(token=None, refresh_token=refresh_token,
                                  token_uri="https://oauth2.googleapis.com/token",
                                  client_id=settings.google_client_id,
                                  client_secret=settings.google_client_secret, scopes=credential.scopes)
        credentials.refresh(GoogleRequest())
    except (InvalidToken, UnicodeError, GoogleAuthError, RequestException) as exc:
        raise RuntimeError("Google credentials could not be refreshed; reconnect the organizer.") from exc
    if not credentials.token:
        raise RuntimeError("Google did not return an access token.")
    return credentials.token


@router.post("/oauth/disconnect")
def disconnect_oauth(session: Session = Depends(get_db)):
    credential = session.get(GoogleOAuthCredential, "organizer")
    if credential is None:
        raise HTTPException(404, "Google organizer is not connected.")
    try:
        validate_config()
        token = cipher().decrypt(credential.refresh_token_encrypted).decode()
        with httpx.Client(timeout=15, follow_redirects=False) as client:
            result = client.post("https://oauth2.googleapis.com/revoke", data={"token": token})
            result.raise_for_status()
    except (RuntimeError, InvalidToken, UnicodeError, httpx.HTTPError) as exc:
        raise HTTPException(502, "Google token revocation failed; credentials were retained.") from exc
    session.delete(credential)
    session.commit()
    return {"connected": False}


class AvailabilityRequest(BaseModel):
    start: AwareDatetime
    end: AwareDatetime


def freebusy(session: Session, start: datetime, end: datetime):
    try:
        access_token = google_access_token(session)
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            response = client.post(
                "https://www.googleapis.com/calendar/v3/freeBusy",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"timeMin": start.isoformat(), "timeMax": end.isoformat(),
                      "items": [{"id": settings.google_workspace_organizer_email}]},
            )
            response.raise_for_status()
            payload = response.json()
        calendar = payload["calendars"][settings.google_workspace_organizer_email]
        if not isinstance(calendar, dict) or calendar.get("errors") or not isinstance(calendar.get("busy"), list):
            raise ValueError("Google returned incomplete availability.")
        busy = []
        for item in calendar["busy"]:
            if not isinstance(item, dict) or not isinstance(item.get("start"), str) or not isinstance(item.get("end"), str):
                raise ValueError("Invalid busy interval.")
            busy_start = datetime.fromisoformat(item["start"].replace("Z", "+00:00"))
            busy_end = datetime.fromisoformat(item["end"].replace("Z", "+00:00"))
            if busy_start.tzinfo is None or busy_end.tzinfo is None or busy_end <= busy_start:
                raise ValueError("Invalid busy interval.")
            busy.append((utc(busy_start), utc(busy_end)))
        return busy
    except (RuntimeError, httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError("Google Calendar availability is unavailable; no slots can be offered.") from exc


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
        busy = freebusy(session, start, end)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    slots = available_slots(start, end, busy, duration, settings.meeting_timezone, work_start, work_end)
    return {"timezone": settings.meeting_timezone, "duration_minutes": duration, "slots": slots}
