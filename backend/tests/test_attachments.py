"""Tests for attachment upload, validation, download, delete, and approval invalidation."""

import io
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import Campaign, Contact, EmailMessage, Enrollment, Lead, now
from app import storage as storage_module
from app.storage import StorageAdapter


class InMemoryStorage(StorageAdapter):
    def __init__(self):
        self._data: dict[str, bytes] = {}

    def store(self, key: str, data: bytes) -> str:
        self._data[key] = data
        return key

    def retrieve(self, key: str) -> bytes:
        from app.storage import StorageKeyNotFound
        if key not in self._data:
            raise StorageKeyNotFound(key)
        return self._data[key]

    def delete(self, key: str) -> None:
        self._data.pop(key, None)


@pytest.fixture
def db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    mem_store = InMemoryStorage()
    storage_module.set_storage(mem_store)

    def override_db():
        with factory() as session:
            yield session

    def override_storage():
        return mem_store

    from app.attachments import router as att_router
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[storage_module.get_storage] = override_storage
    with TestClient(app) as client:
        yield client, factory, mem_store
    app.dependency_overrides.clear()
    storage_module.set_storage(None)
    engine.dispose()


def _make_message(factory):
    """Create a minimal campaign + enrollment + message and return message_id."""
    with factory() as s:
        from email.utils import make_msgid
        import secrets
        lead = Lead(company_name="Acme", company_key="acme", extra={})
        s.add(lead)
        camp = Campaign(name="C", mode="manual", delays=[], status="active")
        s.add(camp)
        s.flush()
        enr = Enrollment(
            campaign_id=camp.id, lead_id=lead.id,
            recipient="a@example.com", status="active", reply_blocked=False,
            unsubscribe_token=secrets.token_hex(32),
        )
        s.add(enr)
        s.flush()
        msg = EmailMessage(
            enrollment_id=enr.id, step_number=0, subject="Test",
            body="Body", status="draft", message_id=make_msgid(),
            open_token=secrets.token_hex(32),
        )
        s.add(msg)
        s.commit()
        return msg.id


def _pdf_bytes():
    return b"%PDF-1.4 1 0 obj<</Type/Catalog>>endobj"


# ---- Valid upload ----

def test_upload_valid_pdf(db):
    client, factory, store = db
    mid = _make_message(factory)
    resp = client.post(
        f"/messages/{mid}/attachments",
        files={"file": ("report.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
    )
    assert resp.status_code == 201
    att = resp.json()
    assert att["upload_status"] == "complete"
    assert att["filename_safe"].endswith(".pdf")
    # Data stored
    assert any(_pdf_bytes() == v for v in store._data.values())


# ---- Validation failures ----

def test_reject_disallowed_extension(db):
    client, factory, _ = db
    mid = _make_message(factory)
    resp = client.post(
        f"/messages/{mid}/attachments",
        files={"file": ("script.sh", io.BytesIO(b"#!/bin/sh"), "text/plain")},
    )
    assert resp.status_code == 422


def test_reject_oversized_file(db):
    client, factory, _ = db
    mid = _make_message(factory)
    big = b"x" * (10 * 1024 * 1024 + 1)
    resp = client.post(
        f"/messages/{mid}/attachments",
        files={"file": ("big.pdf", io.BytesIO(big), "application/pdf")},
    )
    assert resp.status_code == 422


def test_reject_disallowed_mime(db):
    client, factory, _ = db
    mid = _make_message(factory)
    resp = client.post(
        f"/messages/{mid}/attachments",
        files={"file": ("note.pdf", io.BytesIO(b"data"), "text/html")},
    )
    assert resp.status_code == 422


# ---- Approval invalidation ----

def test_upload_invalidates_approved_message(db):
    client, factory, _ = db
    mid = _make_message(factory)
    # Manually approve the message
    with factory() as s:
        from app.models import EmailMessage
        msg = s.get(EmailMessage, mid)
        msg.status = "approved"
        msg.approved_at = now()
        s.commit()
    # Upload attachment
    client.post(
        f"/messages/{mid}/attachments",
        files={"file": ("doc.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
    )
    with factory() as s:
        from app.models import EmailMessage
        msg = s.get(EmailMessage, mid)
        assert msg.status == "draft"
        assert msg.approved_at is None


def test_delete_invalidates_approved_message(db):
    client, factory, _ = db
    mid = _make_message(factory)
    att_resp = client.post(
        f"/messages/{mid}/attachments",
        files={"file": ("doc.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
    )
    att_id = att_resp.json()["id"]
    # Approve
    with factory() as s:
        from app.models import EmailMessage
        msg = s.get(EmailMessage, mid)
        msg.status = "approved"
        msg.approved_at = now()
        s.commit()
    # Delete
    client.delete(f"/messages/{mid}/attachments/{att_id}")
    with factory() as s:
        from app.models import EmailMessage
        assert s.get(EmailMessage, mid).status == "draft"


# ---- Multiple attachments + total limit ----

def test_total_size_limit(db):
    client, factory, _ = db
    mid = _make_message(factory)
    # 24 MB is fine
    chunk = b"x" * (8 * 1024 * 1024)
    for _ in range(3):
        r = client.post(
            f"/messages/{mid}/attachments",
            files={"file": ("chunk.pdf", io.BytesIO(chunk), "application/pdf")},
        )
        assert r.status_code == 201
    # 25th MB should exceed total
    r = client.post(
        f"/messages/{mid}/attachments",
        files={"file": ("extra.pdf", io.BytesIO(b"x" * (1024 * 1024 + 1)), "application/pdf")},
    )
    assert r.status_code == 422


# ---- Download ----

def test_download_attachment(db):
    client, factory, _ = db
    mid = _make_message(factory)
    client.post(
        f"/messages/{mid}/attachments",
        files={"file": ("report.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
    )
    atts = client.get(f"/messages/{mid}/attachments").json()
    att_id = atts[0]["id"]
    resp = client.get(f"/messages/{mid}/attachments/{att_id}")
    assert resp.status_code == 200
    assert resp.content == _pdf_bytes()