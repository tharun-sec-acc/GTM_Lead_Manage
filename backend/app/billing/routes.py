import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.dependencies import TenantContext, get_tenant_context, require_role
from app.auth.models import AuditLog
from app.billing.dependencies import BillingContext, get_billing_context
from app.billing.models import Plan
from app.billing.schemas import (
    PlanChangeRequest,
    PlanResponse,
    SubscriptionDetail,
    SubscriptionStateResponse,
    UsageResponse,
)
from app.billing.service import (
    cancel_subscription,
    change_plan,
    effective_plan,
    get_or_create_subscription,
    get_plan,
    list_plans,
    resume_subscription,
    usage_snapshot,
)
from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["Billing & Subscriptions"])

ACTIVE_STATUSES = ("trialing", "active")


def _plan_payload(plan: Plan) -> PlanResponse:
    return PlanResponse(
        id=plan.id,
        code=plan.code,
        name=plan.name,
        description=plan.description,
        price_cents=plan.price_cents,
        currency=plan.currency,
        billing_interval=plan.billing_interval,
        trial_days=plan.trial_days,
        limits=dict(plan.limits or {}),
        features=list(plan.features or []),
    )


def _state_payload(session: Session, billing: BillingContext) -> SubscriptionStateResponse:
    snapshot = usage_snapshot(session, billing.organization)
    subscription = billing.subscription
    plan = billing.plan
    return SubscriptionStateResponse(
        subscription=SubscriptionDetail(
            id=subscription.id,
            status=subscription.status,
            plan_code=plan.code,
            plan_name=plan.name,
            seats=subscription.seats,
            trial_ends_at=subscription.trial_ends_at,
            current_period_start=subscription.current_period_start,
            current_period_end=subscription.current_period_end,
            cancel_at_period_end=subscription.cancel_at_period_end,
            canceled_at=subscription.canceled_at,
            provider=subscription.provider,
            price_cents=plan.price_cents,
            currency=plan.currency,
            billing_interval=plan.billing_interval,
        ),
        plan=_plan_payload(plan),
        features=list(plan.features or []),
        limits=snapshot["limits"],
        usage=snapshot["usage"],
        remaining=snapshot["remaining"],
        active=subscription.status in ACTIVE_STATUSES,
    )


def _audit(
    session: Session,
    ctx: TenantContext,
    request: Request,
    action: str,
    details: dict,
) -> None:
    session.add(
        AuditLog(
            organization_id=ctx.org_id,
            user_id=ctx.user.id if ctx.user else None,
            action=action,
            resource_type="subscription",
            resource_id=ctx.org_id,
            details=details,
            ip_address=request.client.host if request.client else None,
        )
    )
    session.commit()


@router.get("/plans", response_model=list[PlanResponse])
def get_plans(
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    """The configurable plan catalogue available to this organization."""
    return [_plan_payload(plan) for plan in list_plans(session)]


@router.get("/subscription", response_model=SubscriptionStateResponse)
def get_subscription_state(
    billing: BillingContext = Depends(get_billing_context),
    session: Session = Depends(get_db),
):
    return _state_payload(session, billing)


@router.get("/usage", response_model=UsageResponse)
def get_usage(
    billing: BillingContext = Depends(get_billing_context),
    session: Session = Depends(get_db),
):
    snapshot = usage_snapshot(session, billing.organization)
    return UsageResponse(
        plan_code=billing.plan.code,
        limits=snapshot["limits"],
        usage=snapshot["usage"],
        remaining=snapshot["remaining"],
    )


@router.post("/subscription/change", response_model=SubscriptionStateResponse)
def change_subscription_plan(
    data: PlanChangeRequest,
    request: Request,
    ctx: TenantContext = Depends(require_role("admin")),
    session: Session = Depends(get_db),
):
    """Move the organization onto another catalogue plan."""
    plan_code = data.plan_code.strip().lower()
    # get_plan seeds the default catalogue, so the first request on a fresh
    # database can switch plans instead of reporting a missing plan.
    target = get_plan(session, plan_code)
    if target is None or not target.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan '{plan_code}' was not found.",
        )

    previous = effective_plan(session, ctx.organization)
    if previous.code == target.code:
        billing = BillingContext(
            tenant=ctx,
            subscription=get_or_create_subscription(session, ctx.organization),
            plan=target,
        )
        return _state_payload(session, billing)

    subscription = change_plan(session, ctx.organization, target.code)
    _audit(
        session,
        ctx,
        request,
        action="billing_plan_changed",
        details={"from": previous.code, "to": target.code},
    )
    billing = BillingContext(tenant=ctx, subscription=subscription, plan=target)
    return _state_payload(session, billing)


@router.post("/subscription/cancel", response_model=SubscriptionStateResponse)
def cancel_current_subscription(
    request: Request,
    ctx: TenantContext = Depends(require_role("owner")),
    session: Session = Depends(get_db),
):
    """Cancel at the end of the paid period; access continues until then."""
    subscription = cancel_subscription(session, ctx.organization)
    _audit(
        session,
        ctx,
        request,
        action="billing_subscription_canceled",
        details={"plan_code": effective_plan(session, ctx.organization).code},
    )
    billing = BillingContext(
        tenant=ctx, subscription=subscription, plan=effective_plan(session, ctx.organization)
    )
    return _state_payload(session, billing)


@router.post("/subscription/resume", response_model=SubscriptionStateResponse)
def resume_current_subscription(
    request: Request,
    ctx: TenantContext = Depends(require_role("owner")),
    session: Session = Depends(get_db),
):
    subscription = resume_subscription(session, ctx.organization)
    _audit(
        session,
        ctx,
        request,
        action="billing_subscription_resumed",
        details={"plan_code": effective_plan(session, ctx.organization).code},
    )
    billing = BillingContext(
        tenant=ctx, subscription=subscription, plan=effective_plan(session, ctx.organization)
    )
    return _state_payload(session, billing)
