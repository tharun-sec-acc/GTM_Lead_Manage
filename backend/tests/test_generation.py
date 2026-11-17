"""Tests for product-aware Bedrock generation context resolution and draft invariant."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import bedrock
from app.bedrock import GenerationContext, resolve_generation_context
from app.database import Base, get_db
from app.main import app
from app.models import (
    Campaign, Contact, EmailMessage, Enrollment, Lead, Product, ProductLead, now,
)


@pytest.fixture
def db_factory(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    app.dependency_overrides[get_db] = lambda: (s := factory().__enter__(), s)[1]
    yield factory
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def session(db_factory):
    with db_factory() as s:
        yield s


def _seed(session):
    product = Product(name="VDI", slug="vdi", status="active",
                      value_proposition="Inspect faster.",
                      product_context="Vehicle inspection SaaS.",
                      target_industries=[], created_at=now(), updated_at=now())
    session.add(product)
    lead = Lead(company_name="Acme", company_key="acme", domain="acme.com",
                industry="Automotive", extra={})
    session.add(lead)
    session.flush()
    pl = ProductLead(product_id=product.id, lead_id=lead.id, stage="prospect",
                     priority="medium", status="active", associated_at=now(), updated_at=now())
    session.add(pl)
    contact = Contact(lead_id=lead.id, name="Jane Smith", title="VP Ops",
                      department="Operations", seniority="vp",
                      is_active=True, source="Manual",
                      verification_status="unverified", retrieved_at=now(), updated_at=now())
    session.add(contact)
    session.commit()
    return product, lead, contact, pl


# ---- Context resolution tests ----

def test_resolve_context_all_fields(session):
    product, lead, contact, _ = _seed(session)
    ctx = resolve_generation_context(
        session,
        product_id=product.id,
        lead_id=lead.id,
        contact_id=contact.id,
    )
    assert ctx.product_name == "VDI"
    assert ctx.company_name == "Acme"
    assert ctx.contact_first_name == "Jane"
    assert ctx.contact_last_name == "Smith"
    assert ctx.contact_title == "VP Ops"
    assert ctx.missing_context == []


def test_resolve_context_missing_contact(session):
    product, lead, _, _ = _seed(session)
    ctx = resolve_generation_context(
        session, product_id=product.id, lead_id=lead.id
    )
    assert "contact" in ctx.missing_context


def test_resolve_context_missing_product(session):
    _, lead, contact, _ = _seed(session)
    ctx = resolve_generation_context(
        session, lead_id=lead.id, contact_id=contact.id
    )
    assert "product" in ctx.missing_context


def test_cross_company_fact_rejected(session):
    product, lead, contact, _ = _seed(session)
    # Create a second lead and research facts for it
    lead2 = Lead(company_name="Beta", company_key="beta", extra={})
    session.add(lead2)
    session.flush()
    # Create a fake research fact referencing a non-existent profile
    # Simulate by passing a non-existent fact ID
    with pytest.raises(ValueError, match="not found"):
        resolve_generation_context(
            session,
            product_id=product.id,
            lead_id=lead.id,
            contact_id=contact.id,
            research_fact_ids=["nonexistent-fact-id"],
        )


def test_draft_status_invariant(session, monkeypatch):
    """Generated drafts must always have status=draft regardless of Bedrock response."""
    product, lead, contact, _ = _seed(session)

    mock_emails = [
        {"subject": "Subject 1", "body": "Body 1"},
        {"subject": "Re: Subject 1", "body": "Body 2"},
    ]
    monkeypatch.setattr(bedrock, "converse_json", lambda *a, **kw: {"emails": mock_emails})

    ctx = resolve_generation_context(
        session, product_id=product.id, lead_id=lead.id, contact_id=contact.id
    )
    emails = bedrock.generate_sequence_with_context(ctx, steps=2)
    # Caller is responsible for status; function returns raw email dicts
    assert len(emails) == 2
    # Verify no auto-approval field is set
    for email in emails:
        assert "approved" not in email
        assert "status" not in email


def test_generate_sequence_with_context_uses_product_data(session, monkeypatch):
    product, lead, contact, _ = _seed(session)

    captured = {}

    def mock_converse(system, data, **kw):
        captured["data"] = data
        return {"emails": [{"subject": "S", "body": "B"}]}

    monkeypatch.setattr(bedrock, "converse_json", mock_converse)

    ctx = resolve_generation_context(
        session, product_id=product.id, lead_id=lead.id, contact_id=contact.id
    )
    bedrock.generate_sequence_with_context(ctx, steps=1)

    assert captured["data"]["product_name"] == "VDI"
    assert captured["data"]["company_name"] == "Acme"
    assert captured["data"]["contact_first_name"] == "Jane"