"""Attachment upload, download, and delete with size/MIME validation."""

import hashlib
import mimetypes
import re
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import EmailAttachment, EmailMessage, now
from app.storage import StorageAdapter, StorageKeyNotFound, get_storage

router = APIRouter(tags=["attachments"])

MAX_FILE_BYTES = 10 * 1024 * 1024       # 10 MB per file
MAX_TOTAL_BYTES = 25 * 1024 * 1024      # 25 MB total per message

ALLOWED_MIME_TYPES: frozenset[str] = frozenset({
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/png", "image/jpeg", "image/gif", "image/webp",
})

ALLOWED_EXTENSIONS: frozenset[str] = frozenset({
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
})

_SAFE_FILENAME_RE = re.compile(r"[^a-zA-Z0-9._\-]")


def _safe_filename(name: str) -> str:
    stem, _, suffix = name.rpartition(".")
    stem = _SAFE_FILENAME_RE.sub("_", stem)[:100]
    suffix = suffix.lower()[:10]
    return f"{stem}.{suffix}" if suffix else stem or "file"


def _require_message(session: Session, message_id: str) -> EmailMessage:
    msg = session.get(EmailMessage, message_id)
    if not msg:
        raise HTTPException(404, "Message not found.")
    return msg


def _current_total(session: Session, message_id: str) -> int:
    rows = session.scalars(
        select(EmailAttachment).where(
            EmailAttachment.message_id == message_id,
            EmailAttachment.upload_status == "complete",
        )
    ).all()
    return sum(r.size_bytes for r in rows)


@router.post("/attachments/upload", status_code=201)
async def upload_standalone_attachment(
    file: UploadFile = File(...),
    message_id: str | None = None,
    session: Session = Depends(get_db),
    storage: StorageAdapter = Depends(get_storage),
):
    msg = _require_message(session, message_id) if message_id else None

    filename = file.filename or "upload"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(422, f"File extension {ext!r} is not allowed.")

    data = await file.read()
    size = len(data)

    if size > MAX_FILE_BYTES:
        raise HTTPException(422, f"File exceeds the {MAX_FILE_BYTES // 1024 // 1024} MB limit.")

    detected_mime = file.content_type or ""
    if not detected_mime or detected_mime in ("application/octet-stream", "binary/octet-stream"):
        detected_mime = mimetypes.guess_type(filename)[0] or ""
    if detected_mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(422, f"Content type {detected_mime!r} is not allowed.")

    if message_id:
        current_total = _current_total(session, message_id)
        if current_total + size > MAX_TOTAL_BYTES:
            raise HTTPException(422, f"Total attachment size would exceed the {MAX_TOTAL_BYTES // 1024 // 1024} MB limit.")

    safe_name = _safe_filename(filename)
    key = f"att_{uuid4().hex}_{safe_name}"

    att = EmailAttachment(
        message_id=message_id,
        upload_session_id=str(uuid4()),
        filename_safe=safe_name,
        content_type=detected_mime,
        size_bytes=size,
        storage_key=key,
        upload_status="pending",
        created_at=now(),
    )
    session.add(att)
    session.flush()

    try:
        storage.store(key, data)
    except Exception as exc:
        session.rollback()
        raise HTTPException(500, f"Storage error: {exc}") from exc

    att.upload_status = "complete"
    if msg and msg.status == "approved":
        msg.status = "draft"
        msg.approved_at = None

    session.commit()
    return {
        "id": att.id,
        "message_id": message_id,
        "filename_safe": att.filename_safe,
        "content_type": att.content_type,
        "size_bytes": att.size_bytes,
        "upload_status": att.upload_status,
        "created_at": att.created_at,
    }


@router.post("/messages/{message_id}/attachments", status_code=201)
async def upload_attachment(
    message_id: str,
    file: UploadFile = File(...),
    session: Session = Depends(get_db),
    storage: StorageAdapter = Depends(get_storage),
):
    msg = _require_message(session, message_id)

    # Extension check
    filename = file.filename or "upload"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(422, f"File extension {ext!r} is not allowed.")

    # Read data
    data = await file.read()
    size = len(data)

    if size > MAX_FILE_BYTES:
        raise HTTPException(422, f"File exceeds the {MAX_FILE_BYTES // 1024 // 1024} MB limit.")

    # MIME check: infer from content if content_type is generic
    detected_mime = file.content_type or ""
    if not detected_mime or detected_mime in ("application/octet-stream", "binary/octet-stream"):
        detected_mime = mimetypes.guess_type(filename)[0] or ""
    if detected_mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(422, f"Content type {detected_mime!r} is not allowed.")

    # Total-size check
    current_total = _current_total(session, message_id)
    if current_total + size > MAX_TOTAL_BYTES:
        raise HTTPException(422, f"Total attachment size would exceed the {MAX_TOTAL_BYTES // 1024 // 1024} MB limit.")

    safe_name = _safe_filename(filename)
    key = f"att_{uuid4().hex}_{safe_name}"

    # Persist metadata first (pending), then write to storage
    att = EmailAttachment(
        message_id=message_id,
        upload_session_id=str(uuid4()),
        filename_safe=safe_name,
        content_type=detected_mime,
        size_bytes=size,
        storage_key=key,
        upload_status="pending",
        created_at=now(),
    )
    session.add(att)
    session.flush()

    try:
        storage.store(key, data)
    except Exception as exc:
        session.rollback()
        raise HTTPException(500, f"Storage error: {exc}") from exc

    att.upload_status = "complete"
    # Invalidate message approval if it was approved
    if msg.status == "approved":
        msg.status = "draft"
        msg.approved_at = None

    session.commit()
    return {
        "id": att.id, "message_id": message_id, "filename_safe": att.filename_safe,
        "content_type": att.content_type, "size_bytes": att.size_bytes,
        "upload_status": att.upload_status, "created_at": att.created_at,
    }


@router.get("/messages/{message_id}/attachments")
def list_attachments(message_id: str, session: Session = Depends(get_db)):
    _require_message(session, message_id)
    rows = session.scalars(
        select(EmailAttachment).where(EmailAttachment.message_id == message_id)
    ).all()
    return [
        {"id": r.id, "filename_safe": r.filename_safe, "content_type": r.content_type,
         "size_bytes": r.size_bytes, "upload_status": r.upload_status, "created_at": r.created_at}
        for r in rows
    ]


@router.get("/messages/{message_id}/attachments/{attachment_id}")
def download_attachment(
    message_id: str,
    attachment_id: str,
    session: Session = Depends(get_db),
    storage: StorageAdapter = Depends(get_storage),
):
    att = session.scalar(
        select(EmailAttachment).where(
            EmailAttachment.id == attachment_id,
            EmailAttachment.message_id == message_id,
        )
    )
    if not att or att.upload_status != "complete":
        raise HTTPException(404, "Attachment not found.")
    try:
        data = storage.retrieve(att.storage_key)
    except StorageKeyNotFound:
        raise HTTPException(404, "Attachment data not found in storage.")
    return Response(
        content=data,
        media_type=att.content_type,
        headers={"Content-Disposition": f'attachment; filename="{att.filename_safe}"'},
    )


@router.delete("/messages/{message_id}/attachments/{attachment_id}", status_code=204)
def delete_attachment(
    message_id: str,
    attachment_id: str,
    session: Session = Depends(get_db),
    storage: StorageAdapter = Depends(get_storage),
):
    msg = _require_message(session, message_id)
    att = session.scalar(
        select(EmailAttachment).where(
            EmailAttachment.id == attachment_id,
            EmailAttachment.message_id == message_id,
        )
    )
    if not att:
        raise HTTPException(404, "Attachment not found.")

    # Delete from storage first (idempotent)
    storage.delete(att.storage_key)
    session.delete(att)

    # Invalidate approval if message was approved
    if msg.status == "approved":
        msg.status = "draft"
        msg.approved_at = None

    session.commit()