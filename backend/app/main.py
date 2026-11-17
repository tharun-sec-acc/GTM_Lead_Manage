import re
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlsplit

from email_validator import EmailNotValidError, validate_email
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import apollo
from app.database import get_db
from app.imports import MAX_FILE_BYTES, validate_mapping, workbook_active_sheet_name, workbook_sheets
from app.models import (
    ApolloSearchResult, Batch, Campaign, Contact, EmailEvent, EmailMessage, EmailReply,
    Enrollment, ImportRow, Lead, Product, SalesTask, now,
)
from app.followup_api import router as followup_router
from app.public_tracking import router as public_router
from app.google_workspace import router as google_router
from app.microsoft_graph import router as microsoft_router
from app.company_intelligence.api import router as intelligence_router
from app.products import router as products_router
from app.email_templates import router as templates_router
from app.attachments import router as attachments_router
from app.product_research import router as product_research_router

app = FastAPI(title="DENSO Prospecting Pilot")
app.include_router(followup_router)
app.include_router(public_router)
app.include_router(google_router)
app.include_router(microsoft_router)
app.include_router(intelligence_router)
app.include_router(products_router)
app.include_router(templates_router)
app.include_router(attachments_router)
app.include_router(product_research_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def reject_cross_origin_mutations(request: Request, call_next):
    origin = request.headers.get("origin")
    if (request.method not in ("GET", "HEAD", "OPTIONS") and
        not request.url.path.startswith("/public/unsubscribe/") and origin and origin not in {
        "http://localhost:3000", "http://127.0.0.1:3000"
    }):
        return JSONResponse(status_code=403, content={"detail": "Origin not allowed."})
    return await call_next(request)


class MappingRequest(BaseModel):
    mapping: dict[str, object] = Field(default_factory=dict)


class DomainRequest(BaseModel):
    domain: str


class EnrichRequest(BaseModel):
    apollo_id: str = Field(min_length=1, max_length=100)
    organization_confirmed: bool = False


class ContactCreate(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    title: str | None = Field(default=None, max_length=500)
    email: str | None = Field(default=None, max_length=320)
    department: str | None = Field(default=None, max_length=255)
    seniority: str | None = Field(default=None, max_length=100)
    linkedin_url: str | None = Field(default=None, max_length=2048)
    location: str | None = Field(default=None, max_length=500)
    is_key_decision_maker: bool = False


class ContactUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=500)
    title: str | None = Field(default=None, max_length=500)
    email: str | None = Field(default=None, max_length=320)
    department: str | None = Field(default=None, max_length=255)
    seniority: str | None = Field(default=None, max_length=100)
    linkedin_url: str | None = Field(default=None, max_length=2048)
    location: str | None = Field(default=None, max_length=500)
    is_key_decision_maker: bool | None = None


def normalized_domain(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    parsed = urlsplit(raw if "://" in raw else f"//{raw}")
    host = (parsed.hostname or "").lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host or None


def domain_matches(candidate: str | None, expected: str | None) -> bool:
    if not candidate or not expected:
        return False
    candidate, expected = candidate.lower().rstrip("."), expected.lower().rstrip(".")
    return candidate == expected or candidate.endswith(f".{expected}")


def contact_response(contact: Contact):
    return {
        "id": contact.id, "apollo_id": contact.apollo_id, "name": contact.name,
        "title": contact.title, "email": contact.email, "department": contact.department,
        "seniority": contact.seniority, "linkedin_url": contact.linkedin_url,
        "location": contact.location, "is_key_decision_maker": contact.is_key_decision_maker,
        "verification_status": contact.verification_status, "source": contact.source,
        "retrieved_at": contact.retrieved_at, "updated_at": contact.updated_at,
    }


def validate_contact_email(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    try:
        return validate_email(value.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        raise HTTPException(400, "Invalid business email address.") from exc


def require_lead(session: Session, lead_id: str):
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found.")
    return lead


def batch_response(session: Session, batch: Batch):
    rows = session.scalars(
        select(ImportRow).where(ImportRow.batch_id == batch.id).order_by(
            ImportRow.sheet_name, ImportRow.row_number
        )
    ).all()
    return {
        "id": batch.id, "filename": batch.filename, "status": batch.status,
        "error": batch.error, "headers": batch.headers, "mapping": batch.mapping,
        "counts": dict(Counter(row.status for row in rows)),
        "rows": [{"sheet_name": r.sheet_name, "row_number": r.row_number, "status": r.status, "message": r.message,
                  "lead_id": r.lead_id, "original": r.original} for r in rows],
        "sheets": batch.sheet_headers or {},
    }


def lead_response(lead: Lead):
    return {
        "id": lead.id, "company_name": lead.company_name, "domain": lead.domain,
        "industry": lead.industry, "designation": lead.designation, "location": lead.location,
        "email": lead.email, "revenue": lead.revenue, "phone": lead.phone,
        "remarks": lead.remarks, "key_person_info": lead.key_person_info, "extra": lead.extra,
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/batches", status_code=201)
async def upload_batch(file: UploadFile = File(...), product_id: str | None = Form(default=None),
                      session: Session = Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(400, "Upload an .xlsx file.")
    if product_id:
        product = session.get(Product, product_id)
        if product is None:
            raise HTTPException(404, "Product not found.")
        if product.status != "active":
            raise HTTPException(422, "Product is archived and cannot receive imports.")
    content = await file.read(MAX_FILE_BYTES + 1)
    try:
        sheets = workbook_sheets(content)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    active_name = workbook_active_sheet_name(content)
    active = sheets.get(active_name) if active_name else None
    active = active or next((sheet for sheet in sheets.values() if sheet["headers"]), None)
    headers = active["headers"] if active else []
    batch = Batch(filename=file.filename[:255], content=content, headers=headers,
                  sheet_headers={name: sheet["headers"] for name, sheet in sheets.items()}, status="draft",
                  product_id=product_id)
    session.add(batch)
    session.commit()
    return {"id": batch.id, "headers": headers,
            "preview": [{"name": name, "headers": sheet["headers"], "row_count": len(sheet["rows"]),
                         "column_count": len(sheet["headers"]),
                         "preview": [row for _, row in sheet["rows"][:5]]}
                        for name, sheet in sheets.items()],
            "sheets": [{"name": name, "headers": sheet["headers"], "row_count": len(sheet["rows"]),
                        "column_count": len(sheet["headers"]),
                        "preview": [row for _, row in sheet["rows"][:5]]}
                       for name, sheet in sheets.items()],
            "row_count": sum(len(sheet["rows"]) for sheet in sheets.values())}


@app.post("/batches/{batch_id}/start")
def start_batch(batch_id: str, request: MappingRequest, session: Session = Depends(get_db)):
    batch = session.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404, "Batch not found.")
    if batch.status != "draft":
        raise HTTPException(409, "Batch has already been started.")
    try:
        if request.mapping and all(key in ("company_name", "domain", "email", "revenue", "phone", "remarks",
                                           "key_person_info", "designation", "industry", "location")
                                   for key in request.mapping):
            validate_mapping(request.mapping, batch.headers)
        else:
            sheets = workbook_sheets(batch.content)
            if not request.mapping or any(name not in sheets for name in request.mapping):
                raise ValueError("Select at least one valid worksheet.")
            for name, mapping in request.mapping.items():
                if not isinstance(mapping, dict):
                    raise ValueError("Each selected worksheet requires its own column mapping.")
                validate_mapping(mapping, sheets[name]["headers"])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    batch.mapping = request.mapping
    batch.status = "pending"
    session.commit()
    return batch_response(session, batch)


@app.post("/batches/{batch_id}/retry")
def retry_batch(batch_id: str, session: Session = Depends(get_db)):
    batch = session.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404, "Batch not found.")
    if batch.status != "failed":
        raise HTTPException(409, "Only failed batches can be retried.")
    batch.status = "pending"
    batch.error = None
    session.commit()
    return batch_response(session, batch)


@app.get("/batches")
def batches(product_id: str | None = Query(default=None), session: Session = Depends(get_db)):
    query = select(Batch).order_by(Batch.created_at.desc()).limit(100)
    if product_id:
        query = select(Batch).where(Batch.product_id == product_id).order_by(
            Batch.created_at.desc()
        ).limit(100)
    results = session.scalars(query).all()
    return [{"id": b.id, "filename": b.filename, "status": b.status, "error": b.error,
             "product_id": b.product_id} for b in results]


@app.get("/batches/{batch_id}")
def get_batch(batch_id: str, session: Session = Depends(get_db)):
    batch = session.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404, "Batch not found.")
    return batch_response(session, batch)


@app.get("/batches/{batch_id}/preview")
def preview_batch(batch_id: str, session: Session = Depends(get_db)):
    batch = session.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404, "Batch not found.")
    if batch.status != "draft":
        raise HTTPException(409, "Only draft batches can be mapped.")
    try:
        sheets = workbook_sheets(batch.content)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"id": batch.id, "headers": batch.headers,
            "sheets": [{"name": name, "headers": sheet["headers"], "row_count": len(sheet["rows"]),
                        "column_count": len(sheet["headers"]),
                        "preview": [row for _, row in sheet["rows"][:5]]}
                       for name, sheet in sheets.items()],
            "row_count": sum(len(sheet["rows"]) for sheet in sheets.values())}


@app.get("/leads")
def leads(session: Session = Depends(get_db)):
    return [lead_response(lead) for lead in session.scalars(
        select(Lead).order_by(Lead.created_at.desc()).limit(1000)
    ).all()]


def utc_timestamp(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@app.get("/leads/{lead_id}/profile")
def lead_profile(lead_id: str, limit: int = Query(default=200, ge=1, le=500),
                 session: Session = Depends(get_db)):
    lead = require_lead(session, lead_id)
    contacts = session.scalars(select(Contact).where(
        Contact.lead_id == lead_id
    ).order_by(Contact.is_active.desc(), Contact.name).limit(limit)).all()
    contact_count = session.scalar(select(func.count(Contact.id)).where(
        Contact.lead_id == lead_id, Contact.is_active.is_(True)
    )) or 0
    search_results = session.scalars(select(ApolloSearchResult).where(
        ApolloSearchResult.lead_id == lead_id
    ).order_by(ApolloSearchResult.retrieved_at.desc()).limit(100)).all()
    imports = session.execute(select(ImportRow, Batch.created_at).join(
        Batch, ImportRow.batch_id == Batch.id
    ).where(
        ImportRow.lead_id == lead_id, ImportRow.status == "imported"
    ).order_by(Batch.created_at.desc()).limit(100)).all()
    enrollments = session.scalars(select(Enrollment).where(
        Enrollment.lead_id == lead_id
    ).order_by(Enrollment.created_at.desc()).limit(limit)).all()
    enrollment_by_id = {item.id: item for item in enrollments}
    campaigns = session.scalars(select(Campaign).where(
        Campaign.id.in_({item.campaign_id for item in enrollments})
    )).all() if enrollments else []
    campaign_by_id = {item.id: item for item in campaigns}
    messages = session.scalars(select(EmailMessage).where(
        EmailMessage.enrollment_id.in_(enrollment_by_id)
    ).order_by(EmailMessage.created_at.desc()).limit(limit)).all() if enrollments else []
    message_ids = [item.id for item in messages]
    events = session.scalars(select(EmailEvent).where(
        EmailEvent.email_id.in_(message_ids)
    ).order_by(EmailEvent.event_time.desc()).limit(limit * 5)).all() if message_ids else []
    events_by_email: dict[str, list[EmailEvent]] = {}
    for event in events:
        events_by_email.setdefault(event.email_id, []).append(event)
    replies = session.scalars(select(EmailReply).where(
        EmailReply.enrollment_id.in_(enrollment_by_id)
    ).order_by(EmailReply.received_at.desc()).limit(limit)).all() if enrollments else []
    reply_ids = [item.id for item in replies]
    tasks = session.scalars(select(SalesTask).where(
        SalesTask.reply_id.in_(reply_ids)
    ).order_by(SalesTask.created_at.desc()).limit(limit)).all() if reply_ids else []
    timeline = []

    def add_activity(kind: str, happened_at: datetime | None, entity_id: str, summary: str, details=None):
        if happened_at is not None:
            timeline.append({"type": kind, "occurred_at": happened_at, "entity_id": entity_id,
                             "summary": summary, "details": details or {}})

    for item, imported_at in imports:
        add_activity("lead_imported", imported_at, item.id,
                     f"Imported from {item.sheet_name or 'legacy worksheet'}",
                     {"sheet_name": item.sheet_name or None, "row_number": item.row_number})
    for contact in contacts:
        add_activity("contact_added" if contact.is_active else "contact_removed",
                     contact.retrieved_at, contact.id, contact.name or "Contact",
                     {"source": contact.source, "title": contact.title,
                      "verification_status": contact.verification_status})
    for person in search_results:
        add_activity("apollo_search_result", person.retrieved_at, person.id,
                     f"Apollo result: {person.name or person.apollo_id}",
                     {"organization": person.organization_name,
                      "organization_domain": person.organization_domain})
    email_history = []
    for message in messages:
        enrollment = enrollment_by_id[message.enrollment_id]
        campaign = campaign_by_id.get(enrollment.campaign_id)
        contact = session.get(Contact, enrollment.contact_id) if enrollment.contact_id else None
        events_for_message = events_by_email.get(message.id, [])
        email_history.append({
            "id": message.id, "campaign_id": enrollment.campaign_id,
            "campaign_name": campaign.name if campaign else None, "recipient": enrollment.recipient,
            "contact_id": enrollment.contact_id,
            "contact_name": contact.name if contact else None,
            "step_number": message.step_number, "subject": message.subject, "body": message.body,
            "status": message.status, "created_at": message.created_at, "approved_at": message.approved_at,
            "due_at": message.due_at, "sent_at": message.sent_at,
            "delivery_confirmed": False,
            "events": [{"type": event.event_type, "occurred_at": event.event_time,
                        "detail": event.detail} for event in events_for_message],
        })
        add_activity("email_drafted", message.created_at, message.id, message.subject or "Email draft",
                     {"recipient": enrollment.recipient, "step_number": message.step_number})
        add_activity("email_approved", message.approved_at, message.id, message.subject or "Email approved",
                     {"recipient": enrollment.recipient})
        add_activity("followup_scheduled" if message.step_number else "email_scheduled",
                     message.due_at if message.step_number else None, message.id,
                     message.subject or "Follow-up scheduled", {"recipient": enrollment.recipient})
        add_activity("smtp_accepted", message.sent_at, message.id, message.subject or "SMTP accepted",
                     {"recipient": enrollment.recipient,
                      "delivery_confirmed": False})
        for event in events_for_message:
            if event.event_type not in ("smtp_accepted",):
                add_activity(f"email_{event.event_type}", event.event_time, message.id,
                             f"Email {event.event_type}", {"detail": event.detail})
    for reply in replies:
        add_activity("customer_reply", reply.received_at, reply.id, reply.subject or "Customer replied",
                     {"sender": reply.sender, "classification": reply.classification})
    for task in tasks:
        add_activity("sales_task_created", task.created_at, task.id, task.title, {"status": task.status})
        add_activity("sales_task_completed", task.completed_at, task.id, task.title, {"status": task.status})
    timeline.sort(key=lambda item: utc_timestamp(item["occurred_at"]), reverse=True)
    return {
        "lead": lead_response(lead),
        "overview": {
            "contact_count": contact_count,
            "email_count": len(messages), "reply_count": len(replies), "meeting_count": 0,
            "lifecycle_stage": None, "owner": None,
        },
        "contacts": [contact_response(contact) for contact in contacts if contact.is_active],
        "removed_contacts": [contact_response(contact) for contact in contacts if not contact.is_active],
        "apollo_search_results": [{
            "apollo_id": person.apollo_id, "name": person.name, "title": person.title,
            "organization": person.organization_name, "organization_domain": person.organization_domain,
            "organization_matches": domain_matches(person.organization_domain, lead.domain),
            "retrieved_at": person.retrieved_at,
        } for person in search_results],
        "email_history": email_history,
        "replies": [{
            "id": reply.id, "recipient": reply.sender, "subject": reply.subject, "body": reply.body,
            "classification": reply.classification, "received_at": reply.received_at,
        } for reply in replies],
        "campaigns": [{
            "id": campaign.id, "name": campaign.name, "status": campaign.status,
        } for campaign in campaigns],
        "meetings": {"implemented": False, "items": []},
        "company_research": {"implemented": False, "items": []},
        "commercial_lifecycle": {"implemented": False, "items": []},
        "timeline": timeline[:limit],
        "timeline_limit": limit,
    }


@app.put("/leads/{lead_id}/domain")
def set_domain(lead_id: str, request: DomainRequest, session: Session = Depends(get_db)):
    lead = require_lead(session, lead_id)
    raw = request.domain.strip()
    parsed = urlsplit(raw if "://" in raw else f"//{raw}")
    if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
        raise HTTPException(400, "Enter a company domain or an http(s) website URL.")
    try:
        has_port = parsed.port is not None
    except ValueError as exc:
        raise HTTPException(400, "Enter a valid company domain or website URL.") from exc
    domain = (parsed.hostname or "").lower().rstrip(".")
    if domain.startswith("www."):
        domain = domain[4:]
    if (parsed.username or parsed.password or has_port or len(domain) > 253 or not re.fullmatch(
        r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", domain
    )):
        raise HTTPException(400, "Enter a company domain or an http(s) website URL.")
    lead.domain = domain
    session.commit()
    return lead_response(lead)


@app.post("/leads/{lead_id}/apollo/search")
def search_contacts(lead_id: str, session: Session = Depends(get_db)):
    lead = require_lead(session, lead_id)
    if not lead.domain:
        raise HTTPException(400, "Confirm the company domain before searching.")
    try:
        people = apollo.search_people(lead.domain)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    if not isinstance(people, list):
        raise HTTPException(502, "Apollo returned an unexpected people list.")
    results = []
    for person in people:
        if not isinstance(person, dict) or not isinstance(person.get("id"), str):
            continue
        organization = person.get("organization")
        organization = organization if isinstance(organization, dict) else {}
        organization_domain = normalized_domain(
            organization.get("primary_domain") or organization.get("domain") or organization.get("website_url")
        )
        retrieved = session.scalar(select(ApolloSearchResult).where(
            ApolloSearchResult.lead_id == lead.id, ApolloSearchResult.apollo_id == person["id"]
        ))
        if retrieved is None:
            retrieved = ApolloSearchResult(lead_id=lead.id, apollo_id=person["id"])
            session.add(retrieved)
        retrieved.name = person.get("name") or " ".join(
            part for part in (person.get("first_name"), person.get("last_name_obfuscated")) if part
        ) or None
        retrieved.title = person.get("title")
        departments = person.get("departments")
        retrieved.department = ", ".join(departments) if isinstance(departments, list) and all(
            isinstance(value, str) for value in departments
        ) else None
        retrieved.seniority = person.get("seniority")
        retrieved.organization_name = organization.get("name")
        retrieved.organization_domain = organization_domain
        retrieved.linkedin_url = person.get("linkedin_url")
        retrieved.has_email = person.get("has_email") if isinstance(person.get("has_email"), bool) else None
        retrieved.retrieved_at = now()
        results.append(retrieved)
    session.commit()
    return [{
        "id": person.apollo_id, "name": person.name, "title": person.title,
        "department": person.department, "seniority": person.seniority,
        "organization": person.organization_name, "organization_domain": person.organization_domain,
        "organization_matches": domain_matches(person.organization_domain, lead.domain),
        "linkedin_url": person.linkedin_url, "has_email": person.has_email,
        "retrieved_at": person.retrieved_at,
    } for person in results]


@app.get("/leads/{lead_id}/apollo/search-results")
def saved_search_results(lead_id: str, session: Session = Depends(get_db)):
    lead = require_lead(session, lead_id)
    results = session.scalars(select(ApolloSearchResult).where(
        ApolloSearchResult.lead_id == lead.id
    ).order_by(ApolloSearchResult.retrieved_at.desc()).limit(100)).all()
    return [{
        "id": person.apollo_id, "name": person.name, "title": person.title,
        "department": person.department, "seniority": person.seniority,
        "organization": person.organization_name, "organization_domain": person.organization_domain,
        "organization_matches": domain_matches(person.organization_domain, lead.domain),
        "linkedin_url": person.linkedin_url, "has_email": person.has_email,
        "retrieved_at": person.retrieved_at,
    } for person in results]


@app.post("/leads/{lead_id}/apollo/enrich")
def enrich_contact(lead_id: str, request: EnrichRequest, session: Session = Depends(get_db)):
    lead = require_lead(session, lead_id)
    if not lead.domain:
        raise HTTPException(400, "Confirm the company domain before enriching.")
    existing = session.scalar(select(Contact).where(
        Contact.lead_id == lead_id, Contact.apollo_id == request.apollo_id
    ))
    if existing:
        raise HTTPException(409, "This contact has already been enriched.")
    candidate = session.scalar(select(ApolloSearchResult).where(
        ApolloSearchResult.lead_id == lead_id, ApolloSearchResult.apollo_id == request.apollo_id
    ))
    if candidate is None:
        raise HTTPException(409, "Search for and review this person before enrichment.")
    if not domain_matches(candidate.organization_domain, lead.domain) and not request.organization_confirmed:
        raise HTTPException(409, "Confirm that this person currently belongs to the selected company before enrichment.")
    try:
        person = apollo.enrich_person(request.apollo_id)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    if not isinstance(person, dict):
        raise HTTPException(404, "Apollo did not find an enrichable contact.")
    organization = person.get("organization")
    organization = organization if isinstance(organization, dict) else {}
    enriched_domain = normalized_domain(
        organization.get("primary_domain") or organization.get("domain") or organization.get("website_url")
    )
    verified_domain = enriched_domain or candidate.organization_domain
    organization_matches = domain_matches(verified_domain, lead.domain)
    if not organization_matches and not request.organization_confirmed:
        raise HTTPException(409, "Confirm that this person currently belongs to the selected company before saving.")
    raw_email = person.get("email")
    email = validate_contact_email(raw_email) if isinstance(raw_email, str) else None
    if email and not domain_matches(email.rsplit("@", 1)[-1], lead.domain):
        email = None
    departments = person.get("departments")
    contact = Contact(
        lead_id=lead_id, apollo_id=request.apollo_id,
        name=person.get("name") or candidate.name, title=person.get("title") or candidate.title,
        email=email, department=", ".join(departments) if isinstance(departments, list)
        and all(isinstance(value, str) for value in departments) else candidate.department,
        seniority=person.get("seniority") or candidate.seniority,
        linkedin_url=person.get("linkedin_url") or candidate.linkedin_url,
        location=person.get("city") or person.get("location"),
        source="Apollo", verification_status="organization_verified" if organization_matches else "manually_verified",
        retrieved_at=now(), updated_at=now(),
    )
    session.add(contact)
    session.commit()
    return contact_response(contact)


@app.get("/leads/{lead_id}/contacts")
def contacts(lead_id: str, session: Session = Depends(get_db)):
    require_lead(session, lead_id)
    results = session.scalars(select(Contact).where(
        Contact.lead_id == lead_id, Contact.is_active.is_(True)
    ).order_by(Contact.name)).all()
    return [contact_response(contact) for contact in results]


@app.post("/leads/{lead_id}/contacts", status_code=201)
def create_contact(lead_id: str, data: ContactCreate, session: Session = Depends(get_db)):
    require_lead(session, lead_id)
    contact = Contact(
        lead_id=lead_id, apollo_id=None, name=data.name.strip(), title=data.title,
        email=validate_contact_email(data.email), department=data.department, seniority=data.seniority,
        linkedin_url=data.linkedin_url, location=data.location,
        is_key_decision_maker=data.is_key_decision_maker, source="Manual",
        verification_status="unverified", retrieved_at=now(), updated_at=now(),
    )
    session.add(contact)
    session.commit()
    return contact_response(contact)


@app.put("/leads/{lead_id}/contacts/{contact_id}")
def update_contact(lead_id: str, contact_id: str, data: ContactUpdate,
                   session: Session = Depends(get_db)):
    contact = session.scalar(select(Contact).where(
        Contact.id == contact_id, Contact.lead_id == lead_id, Contact.is_active.is_(True)
    ))
    if contact is None:
        raise HTTPException(404, "Contact not found.")
    values = data.model_dump(exclude_unset=True)
    if "email" in values:
        values["email"] = validate_contact_email(values["email"])
    if "name" in values and values["name"] is not None:
        values["name"] = values["name"].strip()
    for key, value in values.items():
        setattr(contact, key, value)
    contact.updated_at = now()
    session.commit()
    return contact_response(contact)


@app.delete("/leads/{lead_id}/contacts/{contact_id}", status_code=204)
def remove_contact(lead_id: str, contact_id: str, session: Session = Depends(get_db)):
    contact = session.scalar(select(Contact).where(
        Contact.id == contact_id, Contact.lead_id == lead_id, Contact.is_active.is_(True)
    ))
    if contact is None:
        raise HTTPException(404, "Contact not found.")
    contact.is_active, contact.updated_at = False, now()
    session.commit()
