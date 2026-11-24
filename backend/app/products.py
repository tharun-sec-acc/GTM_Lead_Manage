"""Product CRUD, product-lead associations, product-scoped import, and overview APIs."""

import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth.dependencies import TenantContext, get_tenant_context

from app.database import get_db
from app.models import (
    Batch, Campaign, Contact, EmailMessage, EmailReply, Enrollment,
    Lead, Product, ProductLead, ProductOpportunity, SalesTask, now,
)
from app.company_intelligence.models import CompanyResearchProfile, ResearchJob

router = APIRouter(tags=["products"])

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$")

VALID_STAGES = {"prospect", "engaged", "qualified", "proposal", "negotiation", "won", "lost", "on_hold"}
VALID_PRIORITIES = {"high", "medium", "low"}
VALID_STATUSES = {"active", "inactive"}
VALID_PRODUCT_STATUSES = {"active", "archived"}


# ---- Pydantic schemas ----

class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=2, max_length=100)
    description: str | None = None
    short_description: str | None = Field(default=None, max_length=500)
    logo_url: str | None = None
    primary_color: str | None = Field(default=None, max_length=20)
    status: str = "active"
    product_context: str | None = None
    value_proposition: str | None = None
    target_industries: list[str] = Field(default_factory=list)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError("slug must contain only lowercase letters, numbers and hyphens, start and end with alphanumeric")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in VALID_PRODUCT_STATUSES:
            raise ValueError(f"status must be one of: {VALID_PRODUCT_STATUSES}")
        return v


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = None
    short_description: str | None = Field(default=None, max_length=500)
    logo_url: str | None = None
    primary_color: str | None = Field(default=None, max_length=20)
    product_context: str | None = None
    value_proposition: str | None = None
    target_industries: list[str] | None = None


class ProductStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in VALID_PRODUCT_STATUSES:
            raise ValueError(f"status must be active or archived")
        return v


class ProductLeadCreate(BaseModel):
    lead_id: str
    stage: str = "prospect"
    priority: str = "medium"
    status: str = "active"
    sales_notes: str | None = None

    @field_validator("stage")
    @classmethod
    def validate_stage(cls, v: str) -> str:
        if v not in VALID_STAGES:
            raise ValueError(f"stage must be one of: {sorted(VALID_STAGES)}")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        if v not in VALID_PRIORITIES:
            raise ValueError(f"priority must be one of: {sorted(VALID_PRIORITIES)}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(f"status must be active or inactive")
        return v


class ProductLeadUpdate(BaseModel):
    stage: str | None = None
    priority: str | None = None
    status: str | None = None
    sales_notes: str | None = None

    @field_validator("stage")
    @classmethod
    def validate_stage(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_STAGES:
            raise ValueError(f"stage must be one of: {sorted(VALID_STAGES)}")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_PRIORITIES:
            raise ValueError(f"priority must be one of: {sorted(VALID_PRIORITIES)}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_STATUSES:
            raise ValueError(f"status must be active or inactive")
        return v


# ---- Helpers ----

def _require_product(session: Session, product_id: str) -> Product:
    product = session.get(Product, product_id)
    if not product:
        product = session.scalar(select(Product).where(Product.slug == product_id))
    # Alias compatibility for legacy slugs
    if not product:
        aliases = {
            "vehicle-digital-inspection": "vdi",
            "loss-tracker": "ie",
            "aftermarket-super-app": "mce",
        }
        target_slug = aliases.get(product_id.lower())
        if target_slug:
            product = session.scalar(select(Product).where(Product.slug == target_slug))
    if not product:
        raise HTTPException(404, "Product not found.")
    return product


def _require_active_product(session: Session, product_id: str) -> Product:
    product = _require_product(session, product_id)
    if product.status != "active":
        raise HTTPException(422, "Product is archived and cannot receive new associations.")
    return product


def _product_response(p: Product) -> dict:
    return {
        "id": p.id, "name": p.name, "slug": p.slug,
        "description": p.description, "short_description": p.short_description,
        "logo_url": p.logo_url, "primary_color": p.primary_color,
        "status": p.status, "product_context": p.product_context,
        "value_proposition": p.value_proposition,
        "target_industries": p.target_industries or [],
        "created_at": p.created_at, "updated_at": p.updated_at,
    }


def _product_lead_response(pl: ProductLead, session: Session | None = None) -> dict:
    response = {
        "id": pl.id, "product_id": pl.product_id, "lead_id": pl.lead_id,
        "stage": pl.stage, "priority": pl.priority, "status": pl.status,
        "owner_id": pl.owner_id, "sales_notes": pl.sales_notes,
        "associated_at": pl.associated_at, "updated_at": pl.updated_at,
    }
    if session is not None:
        lead = session.get(Lead, pl.lead_id)
        if lead is not None:
            response.update({
                "company_name": lead.company_name, "domain": lead.domain,
                "email": lead.email, "industry": lead.industry,
                "location": lead.location, "designation": lead.designation,
                "revenue": lead.revenue, "phone": lead.phone,
            })
        response["active_contact_count"] = session.scalar(
            select(func.count(Contact.id)).where(
                Contact.lead_id == pl.lead_id, Contact.is_active.is_(True)
            )
        ) or 0
    return response


def _date_bound(value: str | None, end: bool = False) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(422, "Dates must be ISO-8601, for example 2026-11-01.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    if end and (parsed.hour, parsed.minute, parsed.second) == (0, 0, 0):
        parsed = parsed + timedelta(days=1)
    return parsed


# ---- Product CRUD ----

@router.get("/products")
def list_products(
    status: str | None = Query(default=None),
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    q = select(Product).where(
        or_(Product.organization_id == ctx.org_id, Product.organization_id.is_(None))
    ).order_by(Product.name)
    if status:
        if status not in VALID_PRODUCT_STATUSES:
            raise HTTPException(422, f"status must be one of: {VALID_PRODUCT_STATUSES}")
        q = q.where(Product.status == status)
    return [_product_response(p) for p in session.scalars(q).all()]


@router.post("/products", status_code=201)
def create_product(
    data: ProductCreate,
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    existing = session.scalar(select(Product).where(Product.slug == data.slug))
    if existing:
        raise HTTPException(409, f"A product with slug '{data.slug}' already exists.")
    product = Product(
        organization_id=ctx.org_id,
        name=data.name, slug=data.slug, description=data.description,
        short_description=data.short_description, logo_url=data.logo_url,
        primary_color=data.primary_color, status=data.status,
        product_context=data.product_context, value_proposition=data.value_proposition,
        target_industries=data.target_industries, created_at=now(), updated_at=now(),
    )
    session.add(product)
    session.commit()
    return _product_response(product)


@router.get("/products/{product_id}")
def get_product(product_id: str, session: Session = Depends(get_db)):
    return _product_response(_require_product(session, product_id))


@router.put("/products/{product_id}")
def update_product(product_id: str, data: ProductUpdate, session: Session = Depends(get_db)):
    product = _require_product(session, product_id)
    values = data.model_dump(exclude_unset=True)
    if "slug" in values and values["slug"] != product.slug:
        raise HTTPException(422, "Product slug is immutable after creation.")
    for key, value in values.items():
        if key != "slug":
            setattr(product, key, value)
    product.updated_at = now()
    session.commit()
    return _product_response(product)


@router.patch("/products/{product_id}/status")
def update_product_status(product_id: str, data: ProductStatusUpdate, session: Session = Depends(get_db)):
    product = _require_product(session, product_id)
    product.status = data.status
    product.updated_at = now()
    session.commit()
    return _product_response(product)


@router.delete("/products/{product_id}", status_code=405)
def delete_product_not_allowed(product_id: str):
    raise HTTPException(405, "Products cannot be deleted. Archive them instead using PATCH /products/{id}/status.")


# ---- Product-lead associations ----

@router.get("/products/{product_id}/leads")
def list_product_leads(
    product_id: str,
    stage: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    status: str | None = Query(default=None),
    session: Session = Depends(get_db),
):
    _require_product(session, product_id)
    q = select(ProductLead).where(ProductLead.product_id == product_id)
    if stage:
        q = q.where(ProductLead.stage == stage)
    if priority:
        q = q.where(ProductLead.priority == priority)
    if status:
        q = q.where(ProductLead.status == status)
    q = q.order_by(ProductLead.associated_at.desc())
    return [_product_lead_response(pl, session) for pl in session.scalars(q).all()]


@router.post("/products/{product_id}/leads", status_code=201)
def associate_lead(product_id: str, data: ProductLeadCreate, session: Session = Depends(get_db)):
    _require_active_product(session, product_id)
    lead = session.get(Lead, data.lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found.")
    existing = session.scalar(select(ProductLead).where(
        ProductLead.product_id == product_id, ProductLead.lead_id == data.lead_id
    ))
    if existing:
        raise HTTPException(409, "This lead is already associated with this product.")
    pl = ProductLead(
        product_id=product_id, lead_id=data.lead_id, stage=data.stage,
        priority=data.priority, status=data.status, sales_notes=data.sales_notes,
        associated_at=now(), updated_at=now(),
    )
    session.add(pl)
    session.commit()
    return _product_lead_response(pl, session)


@router.put("/products/{product_id}/leads/{lead_id}")
def update_product_lead(product_id: str, lead_id: str, data: ProductLeadUpdate,
                        session: Session = Depends(get_db)):
    pl = session.scalar(select(ProductLead).where(
        ProductLead.product_id == product_id, ProductLead.lead_id == lead_id
    ))
    if not pl:
        raise HTTPException(404, "Product-lead association not found.")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(pl, key, value)
    pl.updated_at = now()
    session.commit()
    return _product_lead_response(pl, session)


@router.delete("/products/{product_id}/leads/{lead_id}", status_code=204)
def remove_product_lead(product_id: str, lead_id: str, session: Session = Depends(get_db)):
    pl = session.scalar(select(ProductLead).where(
        ProductLead.product_id == product_id, ProductLead.lead_id == lead_id
    ))
    if not pl:
        raise HTTPException(404, "Product-lead association not found.")
    session.delete(pl)
    session.commit()
    # Verify master records still present
    assert session.get(Lead, lead_id) is not None


# ---- Product-scoped read APIs ----

@router.get("/products/{product_id}/contacts")
def product_contacts(product_id: str, limit: int = Query(default=250, ge=1, le=1000),
                     session: Session = Depends(get_db)):
    product = _require_product(session, product_id)
    product_id = product.id
    lead_ids = select(ProductLead.lead_id).where(ProductLead.product_id == product_id)
    rows = session.execute(
        select(Contact, Lead.company_name).join(Lead, Contact.lead_id == Lead.id)
        .where(Contact.lead_id.in_(lead_ids), Contact.is_active.is_(True))
        .order_by(Lead.company_name, Contact.name).limit(limit)
    ).all()
    return [{
        "id": contact.id, "lead_id": contact.lead_id, "name": contact.name,
        "title": contact.title, "email": contact.email,
        "department": contact.department, "seniority": contact.seniority,
        "linkedin_url": contact.linkedin_url, "location": contact.location,
        "is_key_decision_maker": contact.is_key_decision_maker,
        "verification_status": contact.verification_status,
        "source": contact.source, "retrieved_at": contact.retrieved_at,
        "updated_at": contact.updated_at, "company_name": company_name,
    } for contact, company_name in rows]


@router.get("/products/{product_id}/campaigns")
def product_campaigns(product_id: str, session: Session = Depends(get_db)):
    product = _require_product(session, product_id)
    product_id = product.id
    campaigns = session.scalars(select(Campaign).where(
        Campaign.product_id == product_id
    ).order_by(Campaign.created_at.desc())).all()
    return [{"id": c.id, "name": c.name, "mode": c.mode, "delays": c.delays,
             "status": c.status, "sequence_approved_at": c.sequence_approved_at,
             "product_id": c.product_id} for c in campaigns]


class ProductCampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    mode: str = "manual"
    delays: list[int] = Field(default_factory=lambda: [3, 4, 5], max_length=5)


@router.post("/products/{product_id}/campaigns", status_code=201)
def create_product_campaign(product_id: str, data: ProductCampaignCreate,
                             session: Session = Depends(get_db)):
    product = _require_active_product(session, product_id)
    product_id = product.id
    if data.mode not in ("manual", "automatic") or any(day < 1 or day > 365 for day in data.delays):
        raise HTTPException(422, "Choose manual or automatic mode and delays between 1 and 365 days.")
    campaign = Campaign(name=data.name.strip(), mode=data.mode, delays=data.delays,
                        status="draft", product_id=product_id)
    session.add(campaign)
    session.commit()
    return {"id": campaign.id, "name": campaign.name, "mode": campaign.mode,
            "delays": campaign.delays, "status": campaign.status,
            "sequence_approved_at": None, "product_id": product_id}


@router.get("/products/{product_id}/batches")
def product_batches(product_id: str, session: Session = Depends(get_db)):
    product = _require_product(session, product_id)
    product_id = product.id
    batches = session.scalars(select(Batch).where(
        Batch.product_id == product_id
    ).order_by(Batch.created_at.desc()).limit(100)).all()
    return [{"id": b.id, "filename": b.filename, "status": b.status, "error": b.error,
             "product_id": b.product_id} for b in batches]


@router.get("/products/{product_id}/research")
def product_research(product_id: str, session: Session = Depends(get_db)):
    product = _require_product(session, product_id)
    product_id = product.id
    lead_ids = select(ProductLead.lead_id).where(ProductLead.product_id == product_id)
    profile_ids = list(session.scalars(select(CompanyResearchProfile.id).where(
        CompanyResearchProfile.lead_id.in_(lead_ids)
    )).all())
    if not profile_ids:
        return []
    jobs = session.scalars(select(ResearchJob).where(
        ResearchJob.company_id.in_(profile_ids)
    ).order_by(ResearchJob.created_at.desc()).limit(100)).all()
    return [{
        "id": job.id, "company_id": job.company_id, "lead_id": job.lead_id,
        "status": job.status, "stage": job.stage, "depth": job.depth,
        "progress": job.progress, "facts_count": job.facts_count,
        "sources_count": job.sources_count, "error": job.error,
        "created_at": job.created_at, "finished_at": job.finished_at,
    } for job in jobs]


@router.get("/products/{product_id}/sales-tasks")
def product_sales_tasks(product_id: str, session: Session = Depends(get_db)):
    product = _require_product(session, product_id)
    product_id = product.id
    campaign_ids = select(Campaign.id).where(Campaign.product_id == product_id)
    tasks = session.execute(
        select(SalesTask, EmailReply, Enrollment.lead_id, Lead.company_name)
        .join(EmailReply, SalesTask.reply_id == EmailReply.id)
        .join(Enrollment, EmailReply.enrollment_id == Enrollment.id)
        .join(Lead, Enrollment.lead_id == Lead.id)
        .where(Enrollment.campaign_id.in_(campaign_ids))
        .order_by(SalesTask.created_at.desc()).limit(100)
    ).all()
    return [{
        "id": task.id, "reply_id": task.reply_id, "title": task.title,
        "status": task.status, "created_at": task.created_at,
        "completed_at": task.completed_at, "lead_id": lead_id,
        "company_name": company_name, "sender": reply.sender,
        "subject": reply.subject, "classification": reply.classification,
    } for task, reply, lead_id, company_name in tasks]


# ---- Product overview API ----

@router.get("/products/{product_id}/overview")
def product_overview(
    product_id: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    session: Session = Depends(get_db),
):
    product = _require_product(session, product_id)
    product_id = product.id
    start, end = _date_bound(start_date), _date_bound(end_date, end=True)

    lead_ids = list(session.scalars(
        select(ProductLead.lead_id).where(ProductLead.product_id == product_id)
    ).all())
    associated_companies = len(lead_ids)

    active_contacts = session.scalar(
        select(func.count(Contact.id)).where(
            Contact.lead_id.in_(lead_ids), Contact.is_active.is_(True)
        )
    ) or 0 if lead_ids else 0

    campaign_query = select(Campaign.id).where(Campaign.product_id == product_id)
    if start:
        campaign_query = campaign_query.where(Campaign.created_at >= start)
    if end:
        campaign_query = campaign_query.where(Campaign.created_at < end)
    campaign_ids = list(session.scalars(campaign_query).all())
    campaigns_count = len(campaign_ids)

    from sqlalchemy import or_

    enrollment_conditions = []
    if campaign_ids:
        enrollment_conditions.append(Enrollment.campaign_id.in_(campaign_ids))
    if lead_ids:
        enrollment_conditions.append(Enrollment.lead_id.in_(lead_ids))
        enrollment_conditions.append(
            Enrollment.contact_id.in_(
                select(Contact.id).where(Contact.lead_id.in_(lead_ids))
            )
        )
    enrollment_ids = list(session.scalars(select(Enrollment.id).where(
        or_(*enrollment_conditions)
    )).all()) if enrollment_conditions else []

    messages_by_status: dict[str, int] = {}
    if enrollment_ids:
        message_query = select(EmailMessage.status, func.count(EmailMessage.id)).where(
            EmailMessage.enrollment_id.in_(enrollment_ids)
        )
        if start:
            message_query = message_query.where(EmailMessage.created_at >= start)
        if end:
            message_query = message_query.where(EmailMessage.created_at < end)
        rows = session.execute(message_query.group_by(EmailMessage.status)).all()
        messages_by_status = {row[0]: row[1] for row in rows}

    replies_query = select(func.count(EmailReply.id)).where(
        EmailReply.enrollment_id.in_(enrollment_ids)
    ) if enrollment_ids else None
    if replies_query is not None and start:
        replies_query = replies_query.where(EmailReply.received_at >= start)
    if replies_query is not None and end:
        replies_query = replies_query.where(EmailReply.received_at < end)
    replies_count = (session.scalar(replies_query) or 0) if replies_query is not None else 0

    # Meeting-request sales tasks, derived through enrollment -> reply -> task.
    reply_ids = list(session.scalars(select(EmailReply.id).where(
        EmailReply.enrollment_id.in_(enrollment_ids)
    )).all()) if enrollment_ids else []
    meeting_tasks = session.scalar(
        select(func.count(SalesTask.id)).where(
            SalesTask.reply_id.in_(reply_ids), SalesTask.status == "open"
        )
    ) or 0 if reply_ids else 0

    # Companies that received at least one SMTP-accepted message.
    contacted_leads: set[str] = set()
    if enrollment_ids:
        contacted_leads = {
            lead_id for lead_id in session.scalars(
                select(Enrollment.lead_id).join(
                    EmailMessage, EmailMessage.enrollment_id == Enrollment.id
                ).where(
                    Enrollment.id.in_(enrollment_ids), EmailMessage.status == "sent"
                )
            ).all()
        }

    profile_ids = list(session.scalars(select(CompanyResearchProfile.id).where(
        CompanyResearchProfile.lead_id.in_(lead_ids)
    )).all()) if lead_ids else []
    research_jobs = session.scalars(select(ResearchJob).where(
        ResearchJob.company_id.in_(profile_ids)
    )).all() if profile_ids else []
    research_by_status: dict[str, int] = {}
    for job in research_jobs:
        research_by_status[job.status] = research_by_status.get(job.status, 0) + 1

    pipeline = {stage: 0 for stage in sorted(VALID_STAGES)}
    if lead_ids:
        for stage, count in session.execute(
            select(ProductLead.stage, func.count(ProductLead.id))
            .where(ProductLead.product_id == product_id)
            .group_by(ProductLead.stage)
        ).all():
            pipeline[stage] = count

    return {
        "product_id": product_id,
        "associated_companies": associated_companies,
        "active_contacts": active_contacts,
        "campaigns_count": campaigns_count,
        "messages_by_status": messages_by_status,
        "replies_count": replies_count,
        "meeting_tasks_open": meeting_tasks,
        "contacted_companies": len(contacted_leads),
        "contacted_company_percent": round(100 * len(contacted_leads) / associated_companies, 1)
        if associated_companies else None,
        "research_jobs": len(research_jobs),
        "research_jobs_completed": research_by_status.get("completed", 0),
        "research_jobs_active": research_by_status.get("queued", 0)
        + research_by_status.get("running", 0),
        "research_jobs_failed": research_by_status.get("failed", 0),
        "pipeline": pipeline,
        "date_range": {"start": start_date, "end": end_date},
        "metrics_note": "SMTP acceptance is not delivery. Messages and replies respect the date filter; "
        "pipeline and company counts are current state.",
    }


# ---- Global overview API ----

@router.get("/overview")
def global_overview(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    session: Session = Depends(get_db),
):
    start, end = _date_bound(start_date), _date_bound(end_date, end=True)

    # Master companies are counted once even when several products share them.
    unique_companies = session.scalar(select(func.count(Lead.id))) or 0
    product_associations = session.scalar(select(func.count(ProductLead.id))) or 0
    product_associated_companies = session.scalar(
        select(func.count(func.distinct(ProductLead.lead_id)))
    ) or 0

    unique_contacts = session.scalar(
        select(func.count(Contact.id)).where(Contact.is_active.is_(True))
    ) or 0
    product_associated_contacts = session.scalar(
        select(func.count(Contact.id)).where(
            Contact.is_active.is_(True),
            Contact.lead_id.in_(select(ProductLead.lead_id)),
        )
    ) or 0

    campaign_query = select(func.count(Campaign.id))
    if start:
        campaign_query = campaign_query.where(Campaign.created_at >= start)
    if end:
        campaign_query = campaign_query.where(Campaign.created_at < end)
    total_campaigns = session.scalar(campaign_query) or 0

    message_query = select(func.count(EmailMessage.id))
    if start:
        message_query = message_query.where(EmailMessage.created_at >= start)
    if end:
        message_query = message_query.where(EmailMessage.created_at < end)
    total_messages = session.scalar(message_query) or 0

    reply_query = select(func.count(EmailReply.id))
    if start:
        reply_query = reply_query.where(EmailReply.received_at >= start)
    if end:
        reply_query = reply_query.where(EmailReply.received_at < end)
    total_replies = session.scalar(reply_query) or 0

    per_product = []
    for p in session.scalars(select(Product).order_by(Product.name)).all():
        lead_ids = list(session.scalars(
            select(ProductLead.lead_id).where(ProductLead.product_id == p.id)
        ).all())
        camp_count = session.scalar(
            select(func.count(Campaign.id)).where(Campaign.product_id == p.id)
        ) or 0
        contact_count = session.scalar(
            select(func.count(Contact.id)).where(
                Contact.is_active.is_(True), Contact.lead_id.in_(lead_ids)
            )
        ) or 0 if lead_ids else 0
        per_product.append({
            "product_id": p.id, "product_name": p.name, "slug": p.slug,
            "status": p.status,
            "associated_companies": len(lead_ids),
            "active_contacts": contact_count,
            "campaigns_count": camp_count,
        })

    return {
        "unique_companies": unique_companies,
        "product_associations": product_associations,
        "product_associated_companies": product_associated_companies,
        "unique_contacts": unique_contacts,
        "product_associated_contacts": product_associated_contacts,
        "total_campaigns": total_campaigns,
        "total_messages": total_messages,
        "total_replies": total_replies,
        "products_count": len(per_product),
        "per_product": per_product,
        "date_range": {"start": start_date, "end": end_date},
        "metrics_note": "Companies are counted once even when associated with multiple products. "
        "SMTP acceptance is not delivery.",
    }