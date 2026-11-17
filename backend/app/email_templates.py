"""Global and product-scoped email template CRUD with versioning and preview."""

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import EmailTemplate, EmailTemplateVersion, Product, now

router = APIRouter(tags=["templates"])

# Finite allowed variable names
ALLOWED_TEMPLATE_VARIABLES: frozenset[str] = frozenset({
    "company_name", "company_domain", "company_industry",
    "contact_first_name", "contact_last_name", "contact_title",
    "contact_department", "contact_seniority",
    "product_name", "product_value_proposition",
    "reviewed_research_facts", "product_opportunity_summary",
    "sender_name", "sender_signature",
})

TEMPLATE_TYPES = {"initial", "followup", "product_intro", "meeting_request", "post_meeting", "custom"}

_VAR_RE = re.compile(r"\{\{(\w+)\}\}")

SAMPLE_VALUES: dict[str, str] = {
    "company_name": "Acme Corporation",
    "company_domain": "acme.example.com",
    "company_industry": "Automotive",
    "contact_first_name": "Jane",
    "contact_last_name": "Smith",
    "contact_title": "VP of Operations",
    "contact_department": "Operations",
    "contact_seniority": "vp",
    "product_name": "Vehicle Digital Inspection",
    "product_value_proposition": "Streamline your inspection workflow.",
    "reviewed_research_facts": "Acme operates 12 regional depots.",
    "product_opportunity_summary": "Strong fit for fleet inspection use case.",
    "sender_name": "Alex Johnson",
    "sender_signature": "Alex Johnson\nSales Executive, DENSO",
}


def _extract_variables(text: str) -> list[str]:
    return list(dict.fromkeys(_VAR_RE.findall(text)))


def validate_variables(subject: str, body: str) -> list[str]:
    """Return list of unknown variable names; empty list means all valid."""
    found = set(_extract_variables(subject)) | set(_extract_variables(body))
    return sorted(found - ALLOWED_TEMPLATE_VARIABLES)


def _render(text: str) -> str:
    return _VAR_RE.sub(lambda m: SAMPLE_VALUES.get(m.group(1), f"[{m.group(1)}]"), text)


def _template_response(t: EmailTemplate) -> dict:
    return {
        "id": t.id, "product_id": t.product_id, "parent_template_id": t.parent_template_id,
        "name": t.name, "type": t.type, "subject_template": t.subject_template,
        "body_template": t.body_template, "variables": t.variables,
        "is_active": t.is_active, "version": t.version,
        "created_at": t.created_at, "updated_at": t.updated_at,
    }


class TemplateCreate(BaseModel):
    product_id: str | None = None
    parent_template_id: str | None = None
    name: str = Field(min_length=1, max_length=200)
    type: str = "custom"
    subject_template: str = Field(default="", max_length=998)
    body_template: str = Field(default="", max_length=200000)

    model_config = {"validate_assignment": True}


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    type: str | None = None
    subject_template: str | None = Field(default=None, max_length=998)
    body_template: str | None = Field(default=None, max_length=200000)
    is_active: bool | None = None


class PreviewRequest(BaseModel):
    subject_template: str | None = None
    body_template: str | None = None


@router.get("/templates")
def list_templates(
    product_id: str | None = Query(default=None),
    type: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    session: Session = Depends(get_db),
):
    q = select(EmailTemplate).order_by(EmailTemplate.name)
    if product_id == "global":
        q = q.where(EmailTemplate.product_id.is_(None))
    elif product_id:
        q = q.where(EmailTemplate.product_id == product_id)
    if type:
        q = q.where(EmailTemplate.type == type)
    if is_active is not None:
        q = q.where(EmailTemplate.is_active == is_active)
    return [_template_response(t) for t in session.scalars(q).all()]


@router.post("/templates", status_code=201)
def create_template(data: TemplateCreate, session: Session = Depends(get_db)):
    if data.type not in TEMPLATE_TYPES:
        raise HTTPException(422, f"type must be one of: {sorted(TEMPLATE_TYPES)}")
    # Validate variables before persisting
    unknown = validate_variables(data.subject_template, data.body_template)
    if unknown:
        raise HTTPException(422, {"detail": "Unknown template variables.", "unknown_variables": unknown})
    # Validate product FK if given
    if data.product_id:
        if not session.get(Product, data.product_id):
            raise HTTPException(404, "Product not found.")
    # Validate parent FK if given
    if data.parent_template_id:
        if not session.get(EmailTemplate, data.parent_template_id):
            raise HTTPException(404, "Parent template not found.")
    variables = _extract_variables(data.subject_template + " " + data.body_template)
    t = EmailTemplate(
        product_id=data.product_id, parent_template_id=data.parent_template_id,
        name=data.name, type=data.type,
        subject_template=data.subject_template, body_template=data.body_template,
        variables=variables, is_active=True, version=1,
        created_at=now(), updated_at=now(),
    )
    session.add(t)
    session.flush()
    # Snapshot version 1
    v = EmailTemplateVersion(
        template_id=t.id, version=1,
        subject_template=data.subject_template, body_template=data.body_template,
        variables=variables, created_at=now(),
    )
    session.add(v)
    session.commit()
    return _template_response(t)


@router.get("/templates/{template_id}")
def get_template(template_id: str, session: Session = Depends(get_db)):
    t = session.get(EmailTemplate, template_id)
    if not t:
        raise HTTPException(404, "Template not found.")
    return _template_response(t)


@router.put("/templates/{template_id}")
def update_template(template_id: str, data: TemplateUpdate, session: Session = Depends(get_db)):
    t = session.get(EmailTemplate, template_id)
    if not t:
        raise HTTPException(404, "Template not found.")
    values = data.model_dump(exclude_unset=True)
    new_subject = values.get("subject_template", t.subject_template)
    new_body = values.get("body_template", t.body_template)
    if "subject_template" in values or "body_template" in values:
        unknown = validate_variables(new_subject, new_body)
        if unknown:
            raise HTTPException(422, {"detail": "Unknown template variables.", "unknown_variables": unknown})
    if "type" in values and values["type"] not in TEMPLATE_TYPES:
        raise HTTPException(422, f"type must be one of: {sorted(TEMPLATE_TYPES)}")
    # Apply changes
    for key, value in values.items():
        setattr(t, key, value)
    # Bump version and snapshot if content changed
    if "subject_template" in values or "body_template" in values:
        t.version += 1
        t.variables = _extract_variables(new_subject + " " + new_body)
        v = EmailTemplateVersion(
            template_id=t.id, version=t.version,
            subject_template=new_subject, body_template=new_body,
            variables=t.variables, created_at=now(),
        )
        session.add(v)
    t.updated_at = now()
    session.commit()
    return _template_response(t)


@router.patch("/templates/{template_id}/status")
def update_template_status(template_id: str, session: Session = Depends(get_db), is_active: bool = True):
    t = session.get(EmailTemplate, template_id)
    if not t:
        raise HTTPException(404, "Template not found.")
    t.is_active = is_active
    t.updated_at = now()
    session.commit()
    return _template_response(t)


@router.get("/templates/{template_id}/versions")
def list_template_versions(template_id: str, session: Session = Depends(get_db)):
    t = session.get(EmailTemplate, template_id)
    if not t:
        raise HTTPException(404, "Template not found.")
    versions = session.scalars(
        select(EmailTemplateVersion)
        .where(EmailTemplateVersion.template_id == template_id)
        .order_by(EmailTemplateVersion.version.desc())
    ).all()
    return [{"id": v.id, "version": v.version, "subject_template": v.subject_template,
             "body_template": v.body_template, "variables": v.variables,
             "created_at": v.created_at} for v in versions]


@router.post("/templates/{template_id}/preview")
def preview_template(template_id: str, data: PreviewRequest | None = None,
                     session: Session = Depends(get_db)):
    t = session.get(EmailTemplate, template_id)
    if not t:
        raise HTTPException(404, "Template not found.")
    subject = data.subject_template if data and data.subject_template is not None else t.subject_template
    body = data.body_template if data and data.body_template is not None else t.body_template
    return {"subject": _render(subject), "body": _render(body)}