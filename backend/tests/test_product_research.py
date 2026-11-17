"""Tests for product opportunity analysis, fact diff, and research fact overrides."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import bedrock
from app.database import Base, get_db
from app.main import app
from app.models import Lead, Product, ProductLead, now
from app.company_intelligence.models import (
    CompanyResearchProfile, ResearchFact, ResearchJob,
)


@pytest.fixture
def db(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override

    # Always mock Bedrock
    monkeypatch.setattr(bedrock, "converse_json", lambda *a, **kw: {
        "opportunity_summary": "Strong fit for fleet inspection.",
        "pain_points": ["Manual inspection is slow"],
        "use_cases": ["Digital inspection workflow"],
        "relevance_score": 0.85,
        "confidence": 0.75,
    })

    with TestClient(app) as client:
        yield client, factory
    app.dependency_overrides.clear()
    engine.dispose()


def _seed(factory):
    with factory() as s:
        product = Product(name="VDI", slug="vdi-research-test", status="active",
                          value_proposition="Speed up inspections.",
                          target_industries=[], created_at=now(), updated_at=now())
        s.add(product)
        lead = Lead(company_name="Acme", company_key="acme-research",
                    domain="acme.com", extra={})
        s.add(lead)
        s.flush()
        pl = ProductLead(product_id=product.id, lead_id=lead.id, stage="prospect",
                         priority="medium", status="active", associated_at=now(), updated_at=now())
        s.add(pl)
        profile = CompanyResearchProfile(
            lead_id=lead.id, company_name="Acme", domain="acme.com", created_at=now()
        )
        s.add(profile)
        s.flush()
        job = ResearchJob(
            company_id=profile.id, lead_id=lead.id,
            status="completed", stage="done", depth="quick",
            created_at=now(), updated_at=now(),
        )
        s.add(job)
        s.flush()
        fact = ResearchFact(
            company_id=profile.id, job_id=job.id,
            category="company", field_name="employee_count", value="2000",
            verification_status="reported", hypothesis=False,
            extraction_agent="company_agent", created_at=now(),
        )
        s.add(fact)
        s.commit()
        return product.id, lead.id, job.id, fact.id, profile.id


def test_opportunity_created_as_draft(db):
    client, factory = db
    product_id, lead_id, _, _, _ = _seed(factory)
    resp = client.post(f"/products/{product_id}/leads/{lead_id}/opportunity")
    assert resp.status_code == 201
    opp = resp.json()
    assert opp["status"] == "draft"
    assert opp["opportunity_summary"] == "Strong fit for fleet inspection."
    assert len(opp["pain_points"]) > 0


def test_opportunity_requires_completed_job(db):
    client, factory = db
    # Create lead+product with NO research
    with factory() as s:
        p2 = Product(name="P2", slug="p2-no-research", status="active",
                     target_industries=[], created_at=now(), updated_at=now())
        s.add(p2)
        l2 = Lead(company_name="Beta", company_key="beta-nores", extra={})
        s.add(l2)
        s.flush()
        pl2 = ProductLead(product_id=p2.id, lead_id=l2.id, stage="prospect",
                          priority="medium", status="active", associated_at=now(), updated_at=now())
        s.add(pl2)
        s.commit()
        p2_id, l2_id = p2.id, l2.id
    resp = client.post(f"/products/{p2_id}/leads/{l2_id}/opportunity")
    assert resp.status_code == 422


def test_opportunity_status_transition(db):
    client, factory = db
    product_id, lead_id, _, _, _ = _seed(factory)
    opp_id = client.post(f"/products/{product_id}/leads/{lead_id}/opportunity").json()["id"]
    resp = client.patch(
        f"/products/{product_id}/leads/{lead_id}/opportunity/{opp_id}/status",
        json={"status": "reviewed"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "reviewed"


def test_opportunity_invalid_status_rejected(db):
    client, factory = db
    product_id, lead_id, _, _, _ = _seed(factory)
    opp_id = client.post(f"/products/{product_id}/leads/{lead_id}/opportunity").json()["id"]
    resp = client.patch(
        f"/products/{product_id}/leads/{lead_id}/opportunity/{opp_id}/status",
        json={"status": "published"}
    )
    assert resp.status_code == 422


def test_research_fact_override_append_only(db):
    client, factory = db
    _, _, _, fact_id, _ = _seed(factory)
    override_resp = client.post(f"/research/facts/{fact_id}/override", json={
        "override_value": "2500",
        "reason": "Updated from press release.",
    })
    assert override_resp.status_code == 201
    override_id = override_resp.json()["id"]

    # Verify original fact unchanged
    with factory() as s:
        from app.company_intelligence.models import ResearchFact
        fact = s.get(ResearchFact, fact_id)
        assert fact.value == "2000"

    # PUT/PATCH/DELETE on override all return 405
    assert client.put(f"/research/fact-overrides/{override_id}").status_code == 405
    assert client.patch(f"/research/fact-overrides/{override_id}").status_code == 405
    assert client.delete(f"/research/fact-overrides/{override_id}").status_code == 405


def test_fact_diff_categorizes_all_facts(db):
    client, factory = db
    _, lead_id, job_id, _, profile_id = _seed(factory)

    # Create a second job with a changed fact
    with factory() as s:
        job2 = ResearchJob(
            company_id=profile_id, lead_id=lead_id,
            status="completed", stage="done", depth="quick",
            created_at=now(), updated_at=now(),
        )
        s.add(job2)
        s.flush()
        # Same field, different value
        fact2 = ResearchFact(
            company_id=profile_id, job_id=job2.id,
            category="company", field_name="employee_count", value="2500",
            verification_status="reported", hypothesis=False,
            extraction_agent="company_agent", created_at=now(),
        )
        # New field
        fact3 = ResearchFact(
            company_id=profile_id, job_id=job2.id,
            category="company", field_name="headquarters", value="Tokyo",
            verification_status="reported", hypothesis=False,
            extraction_agent="company_agent", created_at=now(),
        )
        s.add(fact2)
        s.add(fact3)
        s.commit()
        job2_id = job2.id

    resp = client.get(f"/research/jobs/{job2_id}/diff")
    assert resp.status_code == 200
    diff = resp.json()
    # employee_count changed (both numeric)
    assert any(d["field"] == "employee_count" for d in diff["conflicting"] + diff["changed"])
    # headquarters is new
    assert any(d["field"] == "headquarters" for d in diff["added"])