import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth.dependencies import TenantContext, get_tenant_context, require_role
from app.auth.models import AuditLog, OrganizationMember, User, now
from app.crm import service
from app.crm.models import (
    Activity,
    CrmTask,
    CustomFieldDefinition,
    Opportunity,
    OpportunityStageEvent,
    Pipeline,
    PipelineStage,
    SavedView,
)
from app.crm.schemas import (
    ActivityCreate,
    CloseRequest,
    CustomFieldCreate,
    CustomFieldUpdate,
    LeadCrmUpdate,
    MergeRequest,
    OpportunityCreate,
    OpportunityUpdate,
    PipelineCreate,
    PipelineUpdate,
    SavedViewCreate,
    StageChangeRequest,
    StageCreate,
    StageUpdate,
    TaskCreate,
    TaskUpdate,
)
from app.crm.service import (
    VALID_ACTIVITY_TYPES,
    VALID_LIFECYCLE,
    VALID_QUALIFICATIONS,
)
from app.database import get_db
from app.models import Contact, Lead

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crm", tags=["CRM"])


def _audit(
    session: Session,
    ctx: TenantContext,
    request: Request,
    action: str,
    resource_type: str,
    resource_id: str,
    details: dict | None = None,
) -> None:
    session.add(
        AuditLog(
            organization_id=ctx.org_id,
            user_id=ctx.user.id if ctx.user else None,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            ip_address=request.client.host if request.client else None,
        )
    )


def _require_opportunity(
    session: Session, ctx: TenantContext, opportunity_id: str
) -> Opportunity:
    opportunity = session.get(Opportunity, opportunity_id)
    if not opportunity or opportunity.organization_id != ctx.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Opportunity not found.")
    return opportunity


def _require_task(session: Session, ctx: TenantContext, task_id: str) -> CrmTask:
    task = session.get(CrmTask, task_id)
    if not task or task.organization_id != ctx.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found.")
    return task


def _require_lead(
    session: Session, ctx: TenantContext, lead_id: str, claim: bool = False
) -> Lead:
    try:
        return service.resolve_lead(session, ctx.organization, lead_id, claim=claim)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


def _apply_values(instance, values: dict, required: set[str] | None = None) -> None:
    """Apply a partial update, ignoring explicit nulls for NOT NULL columns."""
    required = required or set()
    for key, value in values.items():
        if value is None and key in required:
            continue
        setattr(instance, key, value)


# ------------------------------- pipelines -------------------------------


@router.get("/pipelines")
def get_pipelines(
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    return [service.serialize_pipeline(session, item) for item in service.list_pipelines(session, ctx.organization)]


@router.post("/pipelines", status_code=201)
def create_pipeline(
    data: PipelineCreate,
    ctx: TenantContext = Depends(require_role("manager")),
    session: Session = Depends(get_db),
):
    name = data.name.strip()
    existing = session.scalar(
        select(Pipeline).where(
            Pipeline.organization_id == ctx.org_id,
            func.lower(Pipeline.name) == name.lower(),
        )
    )
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "A pipeline with that name already exists.")

    pipeline = Pipeline(
        organization_id=ctx.org_id,
        name=name,
        description=data.description,
        is_default=not session.scalar(
            select(func.count(Pipeline.id)).where(Pipeline.organization_id == ctx.org_id)
        ),
    )
    session.add(pipeline)
    session.flush()
    for spec in service.DEFAULT_STAGES:
        session.add(
            PipelineStage(
                pipeline_id=pipeline.id,
                name=spec["name"],
                position=spec["position"],
                probability=spec["probability"],
                is_won=spec.get("is_won", False),
                is_lost=spec.get("is_lost", False),
            )
        )
    session.commit()
    session.refresh(pipeline)
    return service.serialize_pipeline(session, pipeline)


@router.patch("/pipelines/{pipeline_id}")
def update_pipeline(
    pipeline_id: str,
    data: PipelineUpdate,
    ctx: TenantContext = Depends(require_role("manager")),
    session: Session = Depends(get_db),
):
    try:
        pipeline = service.ownership_checked_pipeline(session, ctx.organization, pipeline_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    values = data.model_dump(exclude_unset=True)
    if "name" in values and values["name"]:
        values["name"] = values["name"].strip()
        clash = session.scalar(
            select(Pipeline).where(
                Pipeline.organization_id == ctx.org_id,
                func.lower(Pipeline.name) == values["name"].lower(),
                Pipeline.id != pipeline.id,
            )
        )
        if clash:
            raise HTTPException(status.HTTP_409_CONFLICT, "A pipeline with that name already exists.")
    _apply_values(pipeline, values, {"name", "is_default", "is_archived", "position"})
    session.commit()
    return service.serialize_pipeline(session, pipeline)


@router.post("/pipelines/{pipeline_id}/stages", status_code=201)
def create_stage(
    pipeline_id: str,
    data: StageCreate,
    ctx: TenantContext = Depends(require_role("manager")),
    session: Session = Depends(get_db),
):
    try:
        pipeline = service.ownership_checked_pipeline(session, ctx.organization, pipeline_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    if data.is_won and data.is_lost:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A stage cannot be both won and lost.")

    clash = session.scalar(
        select(PipelineStage).where(
            PipelineStage.pipeline_id == pipeline.id,
            func.lower(PipelineStage.name) == data.name.strip().lower(),
        )
    )
    if clash:
        raise HTTPException(status.HTTP_409_CONFLICT, "A stage with that name already exists.")

    stage = PipelineStage(
        pipeline_id=pipeline.id,
        name=data.name.strip(),
        position=data.position,
        probability=data.probability,
        is_won=data.is_won,
        is_lost=data.is_lost,
    )
    session.add(stage)
    session.commit()
    return service.serialize_stage(stage)


@router.patch("/stages/{stage_id}")
def update_stage(
    stage_id: str,
    data: StageUpdate,
    ctx: TenantContext = Depends(require_role("manager")),
    session: Session = Depends(get_db),
):
    try:
        stage = service.ownership_checked_stage(session, ctx.organization, stage_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    values = data.model_dump(exclude_unset=True)
    is_won = values.get("is_won", stage.is_won)
    is_lost = values.get("is_lost", stage.is_lost)
    if is_won and is_lost:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A stage cannot be both won and lost.")

    if "name" in values and values["name"]:
        values["name"] = values["name"].strip()
        clash = session.scalar(
            select(PipelineStage).where(
                PipelineStage.pipeline_id == stage.pipeline_id,
                func.lower(PipelineStage.name) == values["name"].lower(),
                PipelineStage.id != stage.id,
            )
        )
        if clash:
            raise HTTPException(status.HTTP_409_CONFLICT, "A stage with that name already exists.")

    _apply_values(
        stage, values, {"name", "position", "probability", "is_won", "is_lost"}
    )
    session.commit()
    return service.serialize_stage(stage)


@router.delete("/stages/{stage_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_stage(
    stage_id: str,
    ctx: TenantContext = Depends(require_role("manager")),
    session: Session = Depends(get_db),
):
    try:
        stage = service.ownership_checked_stage(session, ctx.organization, stage_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    used = session.scalar(
        select(func.count(Opportunity.id)).where(Opportunity.stage_id == stage.id)
    ) or 0
    if used:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Stage still has opportunities. Move them before deleting the stage.",
        )
    total = session.scalar(
        select(func.count(PipelineStage.id)).where(PipelineStage.pipeline_id == stage.pipeline_id)
    ) or 0
    if total <= 2:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A pipeline needs at least one open and one closed stage.",
        )
    session.delete(stage)
    session.commit()


# ------------------------------ opportunities ----------------------------


@router.get("/opportunities")
def list_opportunities(
    pipeline_id: str | None = None,
    stage_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    owner_id: str | None = None,
    lead_id: str | None = None,
    q: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    query = select(Opportunity).where(Opportunity.organization_id == ctx.org_id)
    if pipeline_id:
        query = query.where(Opportunity.pipeline_id == pipeline_id)
    if stage_id:
        query = query.where(Opportunity.stage_id == stage_id)
    if status_filter:
        query = query.where(Opportunity.status == status_filter)
    if owner_id:
        query = query.where(Opportunity.owner_id == owner_id)
    if lead_id:
        query = query.where(Opportunity.lead_id == lead_id)
    if q and q.strip():
        like = f"%{q.strip()}%"
        query = query.join(Lead, Opportunity.lead_id == Lead.id).where(
            or_(Opportunity.name.ilike(like), Lead.company_name.ilike(like))
        )
    rows = session.scalars(
        query.order_by(Opportunity.updated_at.desc()).limit(limit)
    ).all()
    return [service.serialize_opportunity(session, row) for row in rows]


@router.post("/opportunities", status_code=201)
def create_opportunity(
    data: OpportunityCreate,
    request: Request,
    ctx: TenantContext = Depends(require_role("rep")),
    session: Session = Depends(get_db),
):
    lead = _require_lead(session, ctx, data.lead_id, claim=True)

    if data.pipeline_id:
        try:
            pipeline = service.ownership_checked_pipeline(session, ctx.organization, data.pipeline_id)
        except LookupError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    else:
        pipeline = service.ensure_default_pipeline(session, ctx.organization)

    stage = None
    if data.stage_id:
        try:
            stage = service.ownership_checked_stage(session, ctx.organization, data.stage_id)
        except LookupError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    if data.contact_id:
        contact = session.get(Contact, data.contact_id)
        if not contact or contact.lead_id != lead.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Contact does not belong to this company.")

    try:
        service.validate_owner(session, ctx.organization, data.owner_id)
        opportunity = service.create_opportunity(
            session,
            ctx.organization,
            lead=lead,
            pipeline=pipeline,
            stage=stage,
            name=data.name.strip(),
            amount_cents=data.amount_cents,
            currency=data.currency,
            expected_close_date=data.expected_close_date,
            owner_id=data.owner_id,
            contact_id=data.contact_id,
            source=data.source,
            source_detail=data.source_detail,
            custom_fields=data.custom_fields,
            user_id=ctx.user.id if ctx.user else None,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    _audit(
        session,
        ctx,
        request,
        "opportunity_created",
        "opportunity",
        opportunity.id,
        {"lead_id": lead.id, "amount_cents": opportunity.amount_cents},
    )
    session.commit()
    return service.serialize_opportunity(session, opportunity)


@router.get("/opportunities/{opportunity_id}")
def get_opportunity(
    opportunity_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    opportunity = _require_opportunity(session, ctx, opportunity_id)
    events = session.scalars(
        select(OpportunityStageEvent)
        .where(OpportunityStageEvent.opportunity_id == opportunity.id)
        .order_by(OpportunityStageEvent.changed_at.desc())
        .limit(100)
    ).all()
    stage_names = {
        stage.id: stage.name
        for stage in session.scalars(
            select(PipelineStage).where(PipelineStage.pipeline_id == opportunity.pipeline_id)
        ).all()
    }
    payload = service.serialize_opportunity(session, opportunity)
    payload["history"] = [
        {
            "from_stage": stage_names.get(event.from_stage_id),
            "to_stage": stage_names.get(event.to_stage_id),
            "from_status": event.from_status,
            "to_status": event.to_status,
            "note": event.note,
            "changed_at": event.changed_at,
            "changed_by_id": event.changed_by_id,
        }
        for event in events
    ]
    return payload


@router.patch("/opportunities/{opportunity_id}")
def update_opportunity(
    opportunity_id: str,
    data: OpportunityUpdate,
    ctx: TenantContext = Depends(require_role("rep")),
    session: Session = Depends(get_db),
):
    opportunity = _require_opportunity(session, ctx, opportunity_id)
    values = data.model_dump(exclude_unset=True)

    if "contact_id" in values and values["contact_id"]:
        contact = session.get(Contact, values["contact_id"])
        if not contact or contact.lead_id != opportunity.lead_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Contact does not belong to this company.")
    if "owner_id" in values:
        try:
            service.validate_owner(session, ctx.organization, values["owner_id"])
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if "currency" in values and values["currency"]:
        values["currency"] = values["currency"].upper()
    if "name" in values and values["name"]:
        values["name"] = values["name"].strip()

    _apply_values(opportunity, values, {"name", "amount_cents", "currency", "custom_fields"})
    opportunity.updated_at = now()
    session.commit()
    return service.serialize_opportunity(session, opportunity)


@router.post("/opportunities/{opportunity_id}/stage")
def move_opportunity_stage(
    opportunity_id: str,
    data: StageChangeRequest,
    ctx: TenantContext = Depends(require_role("rep")),
    session: Session = Depends(get_db),
):
    opportunity = _require_opportunity(session, ctx, opportunity_id)
    try:
        stage = service.ownership_checked_stage(session, ctx.organization, data.stage_id)
        opportunity = service.change_stage(
            session, opportunity, stage, ctx.user.id if ctx.user else None, note=data.note
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    return service.serialize_opportunity(session, opportunity)


@router.post("/opportunities/{opportunity_id}/close")
def close_opportunity(
    opportunity_id: str,
    data: CloseRequest,
    request: Request,
    ctx: TenantContext = Depends(require_role("rep")),
    session: Session = Depends(get_db),
):
    opportunity = _require_opportunity(session, ctx, opportunity_id)
    if opportunity.status != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, "This opportunity is already closed.")
    if data.status == "lost" and not (data.lost_reason or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A lost reason is required.")

    opportunity = service.close_opportunity(
        session,
        opportunity,
        won=data.status == "won",
        lost_reason=data.lost_reason,
        user_id=ctx.user.id if ctx.user else None,
    )
    _audit(
        session,
        ctx,
        request,
        f"opportunity_{data.status}",
        "opportunity",
        opportunity.id,
        {"amount_cents": opportunity.amount_cents},
    )
    session.commit()
    return service.serialize_opportunity(session, opportunity)


# -------------------------------- reporting -------------------------------


@router.get("/summary")
def get_summary(
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    return service.executive_summary(session, ctx.organization)


@router.get("/pipeline-summary")
def get_pipeline_summary(
    pipeline_id: str | None = None,
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    try:
        return service.pipeline_metrics(session, ctx.organization, pipeline_id)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


# ---------------------------------- tasks --------------------------------


@router.get("/tasks")
def list_tasks(
    status_filter: str | None = Query(default=None, alias="status"),
    owner_id: str | None = None,
    lead_id: str | None = None,
    opportunity_id: str | None = None,
    overdue: bool = False,
    limit: int = Query(default=200, ge=1, le=500),
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    query = select(CrmTask).where(CrmTask.organization_id == ctx.org_id)
    if status_filter:
        query = query.where(CrmTask.status == status_filter)
    if owner_id:
        query = query.where(CrmTask.owner_id == owner_id)
    if lead_id:
        query = query.where(CrmTask.lead_id == lead_id)
    if opportunity_id:
        query = query.where(CrmTask.opportunity_id == opportunity_id)
    if overdue:
        query = query.where(
            CrmTask.status == "open",
            CrmTask.due_at.is_not(None),
            CrmTask.due_at < now(),
        )
    rows = session.scalars(
        query.order_by(CrmTask.due_at.is_(None), CrmTask.due_at, CrmTask.created_at)
        .limit(limit)
    ).all()
    return [service.serialize_task(row) for row in rows]


@router.post("/tasks", status_code=201)
def create_task(
    data: TaskCreate,
    ctx: TenantContext = Depends(require_role("rep")),
    session: Session = Depends(get_db),
):
    if data.lead_id:
        _require_lead(session, ctx, data.lead_id, claim=True)
    if data.opportunity_id:
        _require_opportunity(session, ctx, data.opportunity_id)
    try:
        service.validate_owner(session, ctx.organization, data.owner_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    task = CrmTask(
        organization_id=ctx.org_id,
        title=data.title.strip(),
        description=data.description,
        priority=data.priority,
        due_at=data.due_at,
        lead_id=data.lead_id,
        opportunity_id=data.opportunity_id,
        owner_id=data.owner_id or (ctx.user.id if ctx.user else None),
        created_by_id=ctx.user.id if ctx.user else None,
    )
    session.add(task)
    session.commit()
    return service.serialize_task(task)


@router.patch("/tasks/{task_id}")
def update_task(
    task_id: str,
    data: TaskUpdate,
    ctx: TenantContext = Depends(require_role("rep")),
    session: Session = Depends(get_db),
):
    task = _require_task(session, ctx, task_id)
    values = data.model_dump(exclude_unset=True)
    if "owner_id" in values:
        try:
            service.validate_owner(session, ctx.organization, values["owner_id"])
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    if values.get("status") == "done" and task.status != "done":
        task.completed_at = now()
    if values.get("status") == "open":
        task.completed_at = None

    _apply_values(task, values, {"title", "status", "priority"})
    task.updated_at = now()
    session.commit()
    return service.serialize_task(task)


@router.post("/tasks/{task_id}/complete")
def complete_task(
    task_id: str,
    ctx: TenantContext = Depends(require_role("rep")),
    session: Session = Depends(get_db),
):
    task = _require_task(session, ctx, task_id)
    task.status = "done"
    task.completed_at = now()
    task.updated_at = now()

    if task.lead_id:
        lead = session.get(Lead, task.lead_id)
        if lead and lead.organization_id == ctx.org_id:
            session.add(
                Activity(
                    organization_id=ctx.org_id,
                    lead_id=lead.id,
                    opportunity_id=task.opportunity_id,
                    activity_type="task",
                    subject=f"Task completed: {task.title}",
                    owner_id=ctx.user.id if ctx.user else None,
                )
            )
    session.commit()
    return service.serialize_task(task)


# -------------------------------- activities -----------------------------


@router.get("/activities")
def list_activities(
    lead_id: str | None = None,
    opportunity_id: str | None = None,
    contact_id: str | None = None,
    activity_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    query = select(Activity).where(Activity.organization_id == ctx.org_id)
    if lead_id:
        query = query.where(Activity.lead_id == lead_id)
    if opportunity_id:
        query = query.where(Activity.opportunity_id == opportunity_id)
    if contact_id:
        query = query.where(Activity.contact_id == contact_id)
    if activity_type:
        query = query.where(Activity.activity_type == activity_type)
    rows = session.scalars(
        query.order_by(Activity.occurred_at.desc()).limit(limit)
    ).all()
    return [service.serialize_activity(row) for row in rows]


@router.post("/activities", status_code=201)
def create_activity(
    data: ActivityCreate,
    ctx: TenantContext = Depends(require_role("rep")),
    session: Session = Depends(get_db),
):
    if not (data.lead_id or data.opportunity_id or data.contact_id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Link the activity to a lead, contact or opportunity.",
        )
    if data.lead_id:
        _require_lead(session, ctx, data.lead_id, claim=True)
    if data.opportunity_id:
        _require_opportunity(session, ctx, data.opportunity_id)
    if data.activity_type not in VALID_ACTIVITY_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown activity type.")

    activity = Activity(
        organization_id=ctx.org_id,
        lead_id=data.lead_id,
        contact_id=data.contact_id,
        opportunity_id=data.opportunity_id,
        activity_type=data.activity_type,
        subject=data.subject.strip(),
        body=data.body,
        owner_id=ctx.user.id if ctx.user else None,
        occurred_at=data.occurred_at or now(),
    )
    session.add(activity)
    session.commit()
    return service.serialize_activity(activity)


# -------------------------------- CRM leads ------------------------------


@router.get("/leads")
def list_crm_leads(
    query: str | None = None,
    qualification_status: str | None = None,
    lifecycle_stage: str | None = None,
    owner_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    statement = select(Lead).where(
        Lead.organization_id == ctx.org_id,
        Lead.merged_into_id.is_(None),
    )
    if query and query.strip():
        like = f"%{query.strip()}%"
        statement = statement.where(
            or_(Lead.company_name.ilike(like), Lead.domain.ilike(like), Lead.email.ilike(like))
        )
    if qualification_status:
        statement = statement.where(Lead.qualification_status == qualification_status)
    if lifecycle_stage:
        statement = statement.where(Lead.lifecycle_stage == lifecycle_stage)
    if owner_id:
        statement = statement.where(Lead.owner_id == owner_id)
    rows = session.scalars(
        statement.order_by(Lead.score.desc(), Lead.company_name).limit(limit)
    ).all()
    return [service.serialize_lead(lead) for lead in rows]


@router.patch("/leads/{lead_id}")
def update_crm_lead(
    lead_id: str,
    data: LeadCrmUpdate,
    ctx: TenantContext = Depends(require_role("rep")),
    session: Session = Depends(get_db),
):
    lead = _require_lead(session, ctx, lead_id)
    values = data.model_dump(exclude_unset=True)

    if "owner_id" in values and values["owner_id"] != lead.owner_id and not ctx.has_role("manager"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only a manager or administrator can reassign lead ownership.",
        )
    if "owner_id" in values:
        try:
            service.validate_owner(session, ctx.organization, values["owner_id"])
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if values.get("lifecycle_stage") and values["lifecycle_stage"] not in VALID_LIFECYCLE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown lifecycle stage.")
    if values.get("qualification_status") and values["qualification_status"] not in VALID_QUALIFICATIONS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown qualification status.")

    _apply_values(
        lead,
        values,
        {"lifecycle_stage", "qualification_status", "custom_fields", "score"},
    )
    service.recalculate_lead_score(session, lead, commit=False)
    session.commit()
    return service.serialize_lead(lead)


@router.post("/leads/{lead_id}/score")
def rescore_lead(
    lead_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    lead = _require_lead(session, ctx, lead_id)
    score, factors = service.recalculate_lead_score(session, lead)
    return {"lead_id": lead.id, "score": score, "factors": factors}


@router.get("/leads/{lead_id}/duplicates")
def get_lead_duplicates(
    lead_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    lead = _require_lead(session, ctx, lead_id)
    return [
        {"lead": service.serialize_lead(item["lead"]), "reasons": item["reasons"]}
        for item in service.find_duplicate_leads(session, ctx.organization, lead)
    ]


@router.post("/leads/{lead_id}/merge")
def merge_lead_records(
    lead_id: str,
    data: MergeRequest,
    request: Request,
    ctx: TenantContext = Depends(require_role("manager")),
    session: Session = Depends(get_db),
):
    lead = _require_lead(session, ctx, lead_id)
    if lead.merged_into_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "This lead has already been merged.")
    if lead_id in data.source_lead_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A lead cannot be merged into itself.")

    moved = service.merge_leads(session, ctx.organization, lead, data.source_lead_ids)
    _audit(
        session,
        ctx,
        request,
        "leads_merged",
        "lead",
        lead.id,
        {"sources": data.source_lead_ids, "moved": moved},
    )
    session.commit()
    service.recalculate_lead_score(session, lead)
    return {"target": service.serialize_lead(lead), "moved": moved}


@router.get("/leads/{lead_id}/timeline")
def get_lead_timeline(
    lead_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    lead = _require_lead(session, ctx, lead_id)
    activities = session.scalars(
        select(Activity)
        .where(Activity.organization_id == ctx.org_id, Activity.lead_id == lead.id)
        .order_by(Activity.occurred_at.desc())
        .limit(limit)
    ).all()
    opportunities = session.scalars(
        select(Opportunity)
        .where(Opportunity.organization_id == ctx.org_id, Opportunity.lead_id == lead.id)
        .order_by(Opportunity.created_at.desc())
    ).all()
    tasks = session.scalars(
        select(CrmTask)
        .where(CrmTask.organization_id == ctx.org_id, CrmTask.lead_id == lead.id)
        .order_by(CrmTask.created_at.desc())
        .limit(limit)
    ).all()
    return {
        "lead": service.serialize_lead(lead),
        "activities": [service.serialize_activity(item) for item in activities],
        "opportunities": [service.serialize_opportunity(session, item) for item in opportunities],
        "tasks": [service.serialize_task(item) for item in tasks],
    }


@router.get("/owners")
def list_owners(
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    rows = session.execute(
        select(OrganizationMember, User)
        .join(User, OrganizationMember.user_id == User.id)
        .where(
            OrganizationMember.organization_id == ctx.org_id,
            OrganizationMember.status == "active",
        )
        .order_by(User.full_name, User.email)
    ).all()
    return [
        {
            "id": user.id,
            "name": user.full_name or user.email,
            "email": user.email,
            "role": member.role,
        }
        for member, user in rows
    ]


# ------------------------------ custom fields ----------------------------


@router.get("/custom-fields")
def list_custom_fields(
    entity: str | None = None,
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    query = select(CustomFieldDefinition).where(
        CustomFieldDefinition.organization_id == ctx.org_id
    )
    if entity:
        query = query.where(CustomFieldDefinition.entity == entity)
    rows = session.scalars(
        query.order_by(CustomFieldDefinition.entity, CustomFieldDefinition.position)
    ).all()
    return [
        {
            "id": row.id,
            "entity": row.entity,
            "key": row.key,
            "label": row.label,
            "field_type": row.field_type,
            "options": row.options or [],
            "is_required": row.is_required,
            "position": row.position,
        }
        for row in rows
    ]


@router.post("/custom-fields", status_code=201)
def create_custom_field(
    data: CustomFieldCreate,
    ctx: TenantContext = Depends(require_role("manager")),
    session: Session = Depends(get_db),
):
    clash = session.scalar(
        select(CustomFieldDefinition).where(
            CustomFieldDefinition.organization_id == ctx.org_id,
            CustomFieldDefinition.entity == data.entity,
            CustomFieldDefinition.key == data.key,
        )
    )
    if clash:
        raise HTTPException(status.HTTP_409_CONFLICT, "This custom field key already exists.")

    field = CustomFieldDefinition(
        organization_id=ctx.org_id,
        entity=data.entity,
        key=data.key,
        label=data.label.strip(),
        field_type=data.field_type,
        options=data.options,
        is_required=data.is_required,
        position=data.position,
    )
    session.add(field)
    session.commit()
    return {
        "id": field.id,
        "entity": field.entity,
        "key": field.key,
        "label": field.label,
        "field_type": field.field_type,
        "options": field.options or [],
        "is_required": field.is_required,
        "position": field.position,
    }


@router.patch("/custom-fields/{field_id}")
def update_custom_field(
    field_id: str,
    data: CustomFieldUpdate,
    ctx: TenantContext = Depends(require_role("manager")),
    session: Session = Depends(get_db),
):
    field = session.get(CustomFieldDefinition, field_id)
    if not field or field.organization_id != ctx.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Custom field not found.")
    _apply_values(
        field,
        data.model_dump(exclude_unset=True),
        {"label", "field_type", "options", "is_required", "position"},
    )
    session.commit()
    return {
        "id": field.id,
        "entity": field.entity,
        "key": field.key,
        "label": field.label,
        "field_type": field.field_type,
        "options": field.options or [],
        "is_required": field.is_required,
        "position": field.position,
    }


@router.delete("/custom-fields/{field_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_custom_field(
    field_id: str,
    ctx: TenantContext = Depends(require_role("manager")),
    session: Session = Depends(get_db),
):
    field = session.get(CustomFieldDefinition, field_id)
    if not field or field.organization_id != ctx.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Custom field not found.")
    session.delete(field)
    session.commit()


# ------------------------------- saved views -----------------------------


@router.get("/views")
def list_saved_views(
    entity: str | None = None,
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    query = select(SavedView).where(SavedView.organization_id == ctx.org_id)
    if entity:
        query = query.where(SavedView.entity == entity)
    rows = session.scalars(query.order_by(SavedView.created_at.desc())).all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "entity": row.entity,
            "filters": row.filters or {},
            "is_shared": row.is_shared,
            "user_id": row.user_id,
        }
        for row in rows
    ]


@router.post("/views", status_code=201)
def create_saved_view(
    data: SavedViewCreate,
    ctx: TenantContext = Depends(require_role("rep")),
    session: Session = Depends(get_db),
):
    view = SavedView(
        organization_id=ctx.org_id,
        user_id=ctx.user.id if ctx.user else None,
        entity=data.entity,
        name=data.name.strip(),
        filters=data.filters,
        is_shared=data.is_shared,
    )
    session.add(view)
    session.commit()
    return {
        "id": view.id,
        "name": view.name,
        "entity": view.entity,
        "filters": view.filters or {},
        "is_shared": view.is_shared,
        "user_id": view.user_id,
    }


@router.delete("/views/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_view(
    view_id: str,
    ctx: TenantContext = Depends(require_role("rep")),
    session: Session = Depends(get_db),
):
    view = session.get(SavedView, view_id)
    if not view or view.organization_id != ctx.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Saved view not found.")
    if view.user_id and ctx.user and view.user_id != ctx.user.id and not ctx.has_role("manager"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This saved view belongs to another user.")
    session.delete(view)
    session.commit()
