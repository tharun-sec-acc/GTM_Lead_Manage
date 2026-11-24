"""Pipeline, opportunity, scoring and reporting services for the CRM core."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.models import Organization, OrganizationMember
from app.auth.security import to_utc
from app.crm.models import (
    Activity,
    CrmTask,
    Opportunity,
    OpportunityStageEvent,
    Pipeline,
    PipelineStage,
    now,
)
from app.models import Contact, Lead

logger = logging.getLogger(__name__)

DEFAULT_PIPELINE_NAME = "Sales pipeline"
DEFAULT_STAGES: list[dict] = [
    {"name": "New", "position": 10, "probability": 10},
    {"name": "Qualified", "position": 20, "probability": 25},
    {"name": "Meeting", "position": 30, "probability": 45},
    {"name": "Proposal", "position": 40, "probability": 65},
    {"name": "Negotiation", "position": 50, "probability": 80},
    {"name": "Won", "position": 60, "probability": 100, "is_won": True},
    {"name": "Lost", "position": 70, "probability": 0, "is_lost": True},
]

VALID_QUALIFICATIONS = {"unqualified", "qualified", "disqualified"}
VALID_LIFECYCLE = {"lead", "qualified", "opportunity", "customer", "merged"}
VALID_ACTIVITY_TYPES = {"note", "call", "email", "meeting", "task", "system"}


def ensure_default_pipeline(session: Session, organization: Organization) -> Pipeline:
    """Return the organization's default pipeline, creating the standard stages."""
    pipeline = session.scalar(
        select(Pipeline).where(
            Pipeline.organization_id == organization.id,
            Pipeline.is_default.is_(True),
        )
    )
    if pipeline:
        return pipeline

    pipeline = session.scalar(
        select(Pipeline)
        .where(Pipeline.organization_id == organization.id)
        .order_by(Pipeline.created_at.asc())
    )
    if pipeline:
        pipeline.is_default = True
        session.commit()
        return pipeline

    pipeline = Pipeline(
        organization_id=organization.id,
        name=DEFAULT_PIPELINE_NAME,
        description="Default pipeline created with the workspace.",
        is_default=True,
        position=0,
    )
    session.add(pipeline)
    session.flush()
    for spec in DEFAULT_STAGES:
        session.add(PipelineStage(pipeline_id=pipeline.id, **spec))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(
            select(Pipeline).where(Pipeline.organization_id == organization.id)
        )
        if existing:
            return existing
        raise
    session.refresh(pipeline)
    return pipeline


def list_pipelines(session: Session, organization: Organization) -> list[Pipeline]:
    ensure_default_pipeline(session, organization)
    return list(
        session.scalars(
            select(Pipeline)
            .where(Pipeline.organization_id == organization.id)
            .order_by(Pipeline.position, Pipeline.created_at)
        ).all()
    )


def pipeline_stages(session: Session, pipeline: Pipeline) -> list[PipelineStage]:
    return list(
        session.scalars(
            select(PipelineStage)
            .where(PipelineStage.pipeline_id == pipeline.id)
            .order_by(PipelineStage.position, PipelineStage.created_at)
        ).all()
    )


def ownership_checked_pipeline(
    session: Session, organization: Organization, pipeline_id: str
) -> Pipeline:
    pipeline = session.get(Pipeline, pipeline_id)
    if not pipeline or pipeline.organization_id != organization.id:
        raise LookupError("Pipeline not found.")
    return pipeline


def ownership_checked_stage(
    session: Session, organization: Organization, stage_id: str
) -> PipelineStage:
    stage = session.get(PipelineStage, stage_id)
    if not stage:
        raise LookupError("Stage not found.")
    pipeline = session.get(Pipeline, stage.pipeline_id)
    if not pipeline or pipeline.organization_id != organization.id:
        raise LookupError("Stage not found.")
    return stage


def validate_owner(session: Session, organization: Organization, user_id: str | None) -> None:
    if not user_id:
        return
    member = session.scalar(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == organization.id,
            OrganizationMember.user_id == user_id,
            OrganizationMember.status == "active",
        )
    )
    if not member:
        raise ValueError("Owner must be an active member of this organization.")


def lead_score(session: Session, lead: Lead) -> tuple[int, list[str]]:
    """Deterministic lead score from data already present, with its reasons."""
    score = 0
    factors: list[str] = []

    def add(points: int, label: str) -> None:
        nonlocal score
        score += points
        factors.append(f"+{points} {label}")

    if lead.domain:
        add(10, "company domain confirmed")
    if lead.email:
        add(10, "company email on record")
    if lead.industry:
        add(5, "industry known")
    if lead.location:
        add(5, "location known")
    if lead.revenue:
        add(5, "revenue band known")
    if lead.phone:
        add(5, "phone on record")

    contacts = session.scalars(
        select(Contact).where(Contact.lead_id == lead.id, Contact.is_active.is_(True))
    ).all()
    if contacts:
        add(min(20, 5 * len(contacts)), f"{len(contacts)} saved contact(s)")
        if any(contact.email for contact in contacts):
            add(10, "contact email captured")
        if any(contact.is_key_decision_maker for contact in contacts):
            add(10, "key decision maker identified")

    return min(score, 100), factors


def recalculate_lead_score(session: Session, lead: Lead, commit: bool = True) -> tuple[int, list[str]]:
    score, factors = lead_score(session, lead)
    lead.score = score
    if commit:
        session.commit()
    return score, factors


def find_duplicate_leads(
    session: Session, organization: Organization, lead: Lead
) -> list[dict]:
    """Same-organization leads that look like the same company or person."""
    conditions = []
    if lead.domain:
        conditions.append(func.lower(Lead.domain) == lead.domain.lower())
    if lead.company_key:
        conditions.append(func.lower(Lead.company_key) == lead.company_key.lower())
    if lead.email:
        conditions.append(func.lower(Lead.email) == lead.email.lower())
    if not conditions:
        return []

    candidates = session.scalars(
        select(Lead)
        .where(
            Lead.organization_id == organization.id,
            Lead.id != lead.id,
            Lead.merged_into_id.is_(None),
            or_(*conditions),
        )
        .order_by(Lead.created_at.asc())
        .limit(25)
    ).all()

    duplicates = []
    for candidate in candidates:
        reasons = []
        if lead.domain and candidate.domain and candidate.domain.lower() == lead.domain.lower():
            reasons.append("same domain")
        if (
            lead.company_key
            and candidate.company_key
            and candidate.company_key.lower() == lead.company_key.lower()
        ):
            reasons.append("same company name")
        if lead.email and candidate.email and candidate.email.lower() == lead.email.lower():
            reasons.append("same email")
        duplicates.append({"lead": candidate, "reasons": reasons})
    return duplicates


def merge_leads(
    session: Session,
    organization: Organization,
    target: Lead,
    source_ids: list[str],
) -> dict:
    """Merge duplicate leads into a target, keeping history attached to the target."""
    moved = {"leads": 0, "contacts": 0, "opportunities": 0, "tasks": 0, "activities": 0}

    for source_id in source_ids:
        if not source_id or source_id == target.id:
            continue
        source = session.get(Lead, source_id)
        if not source or source.organization_id != organization.id:
            continue
        if source.merged_into_id:
            continue

        contacts = session.scalars(select(Contact).where(Contact.lead_id == source.id)).all()
        for contact in contacts:
            clash_conditions = []
            if contact.email:
                clash_conditions.append(Contact.email == contact.email)
            if contact.apollo_id:
                clash_conditions.append(Contact.apollo_id == contact.apollo_id)
            clash = None
            if clash_conditions:
                clash = session.scalar(
                    select(Contact)
                    .where(
                        Contact.lead_id == target.id,
                        Contact.is_active.is_(True),
                        or_(*clash_conditions),
                    )
                    .limit(1)
                )
            if clash and clash.id != contact.id:
                contact.is_active = False
            else:
                contact.lead_id = target.id
                contact.organization_id = organization.id
                moved["contacts"] += 1

        for model, key in (
            (Opportunity, "opportunities"),
            (CrmTask, "tasks"),
            (Activity, "activities"),
        ):
            result = session.execute(
                update(model).where(model.lead_id == source.id).values(lead_id=target.id)
            )
            moved[key] += result.rowcount or 0

        source.merged_into_id = target.id
        source.lifecycle_stage = "merged"
        moved["leads"] += 1

    donors = [session.get(Lead, sid) for sid in source_ids if sid != target.id]
    for field in ("domain", "email", "industry", "location", "revenue", "phone", "key_person_info"):
        if getattr(target, field, None):
            continue
        for donor in donors:
            if donor is not None and getattr(donor, field, None):
                setattr(target, field, getattr(donor, field))
                break

    session.add(
        Activity(
            organization_id=organization.id,
            lead_id=target.id,
            activity_type="system",
            subject="Duplicate leads merged",
            body=f"Merged {moved['leads']} duplicate lead record(s) into this company.",
            activity_metadata=moved,
        )
    )
    session.commit()
    return moved


def serialize_lead(lead: Lead) -> dict:
    return {
        "id": lead.id,
        "company_name": lead.company_name,
        "company_key": lead.company_key,
        "domain": lead.domain,
        "email": lead.email,
        "industry": lead.industry,
        "location": lead.location,
        "owner_id": lead.owner_id,
        "lifecycle_stage": lead.lifecycle_stage,
        "qualification_status": lead.qualification_status,
        "score": lead.score,
        "source": lead.source,
        "custom_fields": lead.custom_fields or {},
        "merged_into_id": lead.merged_into_id,
    }


def serialize_stage(stage: PipelineStage) -> dict:
    return {
        "id": stage.id,
        "pipeline_id": stage.pipeline_id,
        "name": stage.name,
        "position": stage.position,
        "probability": stage.probability,
        "is_won": stage.is_won,
        "is_lost": stage.is_lost,
    }


def serialize_pipeline(session: Session, pipeline: Pipeline) -> dict:
    return {
        "id": pipeline.id,
        "name": pipeline.name,
        "description": pipeline.description,
        "is_default": pipeline.is_default,
        "is_archived": pipeline.is_archived,
        "position": pipeline.position,
        "stages": [serialize_stage(stage) for stage in pipeline_stages(session, pipeline)],
    }


def serialize_opportunity(session: Session, opportunity: Opportunity) -> dict:
    lead = session.get(Lead, opportunity.lead_id)
    stage = session.get(PipelineStage, opportunity.stage_id)
    return {
        "id": opportunity.id,
        "name": opportunity.name,
        "pipeline_id": opportunity.pipeline_id,
        "stage_id": opportunity.stage_id,
        "stage_name": stage.name if stage else None,
        "lead_id": opportunity.lead_id,
        "company_name": lead.company_name if lead else None,
        "contact_id": opportunity.contact_id,
        "amount_cents": opportunity.amount_cents,
        "amount": round(opportunity.amount_cents / 100, 2),
        "currency": opportunity.currency,
        "expected_close_date": (
            opportunity.expected_close_date.isoformat() if opportunity.expected_close_date else None
        ),
        "status": opportunity.status,
        "owner_id": opportunity.owner_id,
        "source": opportunity.source,
        "source_detail": opportunity.source_detail,
        "custom_fields": opportunity.custom_fields or {},
        "lost_reason": opportunity.lost_reason,
        "won_at": opportunity.won_at,
        "lost_at": opportunity.lost_at,
        "created_at": opportunity.created_at,
        "updated_at": opportunity.updated_at,
    }


def serialize_task(task: CrmTask) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "due_at": task.due_at,
        "lead_id": task.lead_id,
        "opportunity_id": task.opportunity_id,
        "owner_id": task.owner_id,
        "completed_at": task.completed_at,
        "created_at": task.created_at,
    }


def serialize_activity(activity: Activity) -> dict:
    return {
        "id": activity.id,
        "lead_id": activity.lead_id,
        "contact_id": activity.contact_id,
        "opportunity_id": activity.opportunity_id,
        "activity_type": activity.activity_type,
        "subject": activity.subject,
        "body": activity.body,
        "owner_id": activity.owner_id,
        "metadata": activity.activity_metadata or {},
        "occurred_at": activity.occurred_at,
    }


def resolve_lead(
    session: Session,
    organization: Organization,
    lead_id: str,
    claim: bool = False,
) -> Lead:
    """Resolve a lead inside the organization.

    ``claim`` is only used by authorized writes: a legacy record imported before
    multi-tenancy (NULL organization) is adopted by the writing organization.
    """
    lead = session.get(Lead, lead_id)
    if not lead:
        raise LookupError("Lead not found.")
    if lead.organization_id is None:
        if not claim:
            raise LookupError("Lead not found.")
        lead.organization_id = organization.id
    elif lead.organization_id != organization.id:
        raise LookupError("Lead not found.")
    return lead


def create_opportunity(
    session: Session,
    organization: Organization,
    *,
    lead: Lead,
    pipeline: Pipeline,
    stage: PipelineStage | None,
    name: str,
    amount_cents: int,
    currency: str,
    expected_close_date,
    owner_id: str | None,
    contact_id: str | None,
    source: str | None,
    source_detail: str | None,
    custom_fields: dict,
    user_id: str | None,
) -> Opportunity:
    stages = pipeline_stages(session, pipeline)
    if stage is None:
        open_stages = [item for item in stages if not item.is_won and not item.is_lost]
        if not open_stages:
            raise ValueError("Pipeline has no open stages.")
        stage = open_stages[0]
    if stage.pipeline_id != pipeline.id:
        raise ValueError("Stage does not belong to the selected pipeline.")

    opportunity = Opportunity(
        organization_id=organization.id,
        pipeline_id=pipeline.id,
        stage_id=stage.id,
        lead_id=lead.id,
        contact_id=contact_id,
        name=name,
        amount_cents=max(amount_cents, 0),
        currency=(currency or "INR").upper()[:3],
        expected_close_date=expected_close_date,
        status="open",
        owner_id=owner_id,
        source=source,
        source_detail=source_detail,
        custom_fields=custom_fields or {},
        created_by_id=user_id,
    )
    session.add(opportunity)
    session.flush()
    session.add(
        OpportunityStageEvent(
            opportunity_id=opportunity.id,
            from_stage_id=None,
            to_stage_id=stage.id,
            from_status=None,
            to_status="open",
            note="Opportunity created",
            changed_by_id=user_id,
        )
    )
    session.add(
        Activity(
            organization_id=organization.id,
            lead_id=lead.id,
            opportunity_id=opportunity.id,
            activity_type="system",
            subject=f"Opportunity created: {name}",
            body=f"Created in stage '{stage.name}'.",
            owner_id=user_id,
        )
    )
    if lead.lifecycle_stage in (None, "lead", "qualified"):
        lead.lifecycle_stage = "opportunity"
    session.commit()
    session.refresh(opportunity)
    return opportunity


def change_stage(
    session: Session,
    opportunity: Opportunity,
    stage: PipelineStage,
    user_id: str | None,
    note: str | None = None,
) -> Opportunity:
    if stage.pipeline_id != opportunity.pipeline_id:
        raise ValueError("Stage does not belong to the opportunity's pipeline.")

    from_stage_id = opportunity.stage_id
    from_status = opportunity.status
    opportunity.stage_id = stage.id
    at = now()

    if stage.is_won:
        opportunity.status = "won"
        opportunity.won_at = at
        opportunity.lost_at = None
        opportunity.lost_reason = None
    elif stage.is_lost:
        opportunity.status = "lost"
        opportunity.lost_at = at
        opportunity.won_at = None
    else:
        opportunity.status = "open"
        opportunity.won_at = None
        opportunity.lost_at = None

    session.add(
        OpportunityStageEvent(
            opportunity_id=opportunity.id,
            from_stage_id=from_stage_id,
            to_stage_id=stage.id,
            from_status=from_status,
            to_status=opportunity.status,
            note=note,
            changed_by_id=user_id,
        )
    )
    session.add(
        Activity(
            organization_id=opportunity.organization_id,
            lead_id=opportunity.lead_id,
            opportunity_id=opportunity.id,
            activity_type="system",
            subject=f"Stage changed to {stage.name}",
            body=note or f"Moved from previous stage to '{stage.name}'.",
            owner_id=user_id,
        )
    )
    lead = session.get(Lead, opportunity.lead_id)
    if lead and stage.is_won:
        lead.lifecycle_stage = "customer"
        lead.qualification_status = "qualified"
    session.commit()
    session.refresh(opportunity)
    return opportunity


def close_opportunity(
    session: Session,
    opportunity: Opportunity,
    *,
    won: bool,
    lost_reason: str | None,
    user_id: str | None,
) -> Opportunity:
    stage = session.scalar(
        select(PipelineStage)
        .where(
            PipelineStage.pipeline_id == opportunity.pipeline_id,
            PipelineStage.is_won.is_(True) if won else PipelineStage.is_lost.is_(True),
        )
        .limit(1)
    )
    if stage is None:
        opportunity.status = "won" if won else "lost"
        at = now()
        if won:
            opportunity.won_at = at
        else:
            opportunity.lost_at = at
            opportunity.lost_reason = lost_reason
        session.add(
            OpportunityStageEvent(
                opportunity_id=opportunity.id,
                from_stage_id=opportunity.stage_id,
                to_stage_id=None,
                from_status="open",
                to_status=opportunity.status,
                note=lost_reason,
                changed_by_id=user_id,
            )
        )
        session.commit()
        return opportunity

    opportunity = change_stage(session, opportunity, stage, user_id, note=lost_reason)
    if not won:
        opportunity.lost_reason = lost_reason
        session.commit()
    return opportunity


def pipeline_metrics(
    session: Session, organization: Organization, pipeline_id: str | None = None
) -> dict:
    if pipeline_id:
        pipeline = ownership_checked_pipeline(session, organization, pipeline_id)
    else:
        pipeline = ensure_default_pipeline(session, organization)

    stages = pipeline_stages(session, pipeline)
    stage_by_id = {stage.id: stage for stage in stages}
    opportunities = list(
        session.scalars(
            select(Opportunity).where(
                Opportunity.organization_id == organization.id,
                Opportunity.pipeline_id == pipeline.id,
            )
        ).all()
    )

    rows = []
    for stage in stages:
        items = [item for item in opportunities if item.stage_id == stage.id]
        rows.append(
            {
                "stage_id": stage.id,
                "stage_name": stage.name,
                "probability": stage.probability,
                "is_won": stage.is_won,
                "is_lost": stage.is_lost,
                "count": len(items),
                "value_cents": sum(item.amount_cents for item in items),
            }
        )

    open_opportunities = [item for item in opportunities if item.status == "open"]
    won = [item for item in opportunities if item.status == "won"]
    lost = [item for item in opportunities if item.status == "lost"]

    weighted_forecast = 0
    for item in open_opportunities:
        stage = stage_by_id.get(item.stage_id)
        weighted_forecast += int(item.amount_cents * ((stage.probability if stage else 0) / 100))

    cycle_days = [
        max((item.won_at - item.created_at).days, 0)
        for item in won
        if item.won_at and item.created_at
    ]
    win_rate = (len(won) / (len(won) + len(lost))) if (won or lost) else 0.0

    return {
        "pipeline_id": pipeline.id,
        "pipeline_name": pipeline.name,
        "stages": rows,
        "open_count": len(open_opportunities),
        "open_value_cents": sum(item.amount_cents for item in open_opportunities),
        "weighted_forecast_cents": weighted_forecast,
        "won_count": len(won),
        "won_value_cents": sum(item.amount_cents for item in won),
        "lost_count": len(lost),
        "lost_value_cents": sum(item.amount_cents for item in lost),
        "win_rate": round(win_rate, 3),
        "average_cycle_days": (round(sum(cycle_days) / len(cycle_days), 1) if cycle_days else None),
    }


def executive_summary(session: Session, organization: Organization) -> dict:
    leads = list(
        session.scalars(
            select(Lead).where(
                Lead.organization_id == organization.id,
                Lead.merged_into_id.is_(None),
            )
        ).all()
    )
    metrics = pipeline_metrics(session, organization)

    open_tasks = list(
        session.scalars(
            select(CrmTask).where(
                CrmTask.organization_id == organization.id,
                CrmTask.status == "open",
            )
        ).all()
    )
    at = now()
    overdue = [
        task for task in open_tasks
        if task.due_at and to_utc(task.due_at) < at
    ]

    opportunity_lead_ids = set(
        session.scalars(
            select(Opportunity.lead_id).where(
                Opportunity.organization_id == organization.id,
                Opportunity.status == "open",
            )
        ).all()
    )
    qualified_without_opportunity = [
        lead
        for lead in leads
        if lead.qualification_status == "qualified" and lead.id not in opportunity_lead_ids
    ]

    recent_since = at - timedelta(days=30)
    activity_count = session.scalar(
        select(func.count(Activity.id)).where(
            Activity.organization_id == organization.id,
            Activity.occurred_at >= recent_since,
        )
    ) or 0

    needs_attention = [
        {
            "kind": "overdue_task",
            "label": task.title,
            "entity_id": task.id,
            "lead_id": task.lead_id,
            "due_at": task.due_at,
        }
        for task in overdue[:10]
    ]
    needs_attention.extend(
        {
            "kind": "qualified_without_opportunity",
            "label": lead.company_name,
            "entity_id": lead.id,
            "lead_id": lead.id,
            "due_at": None,
        }
        for lead in qualified_without_opportunity[:10]
    )

    return {
        "leads": {
            "total": len(leads),
            "qualified": sum(1 for lead in leads if lead.qualification_status == "qualified"),
            "unqualified": sum(
                1 for lead in leads if lead.qualification_status in (None, "unqualified")
            ),
            "customers": sum(1 for lead in leads if lead.lifecycle_stage == "customer"),
        },
        "opportunities": metrics,
        "tasks": {
            "open": len(open_tasks),
            "overdue": len(overdue),
            "completed": session.scalar(
                select(func.count(CrmTask.id)).where(
                    CrmTask.organization_id == organization.id,
                    CrmTask.status == "done",
                )
            ) or 0,
        },
        "activities_last_30_days": activity_count,
        "needs_attention": needs_attention,
    }
