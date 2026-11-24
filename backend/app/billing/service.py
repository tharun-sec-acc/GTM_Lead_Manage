"""Subscription lifecycle, entitlement resolution and usage metering."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.models import Organization, OrganizationInvitation, OrganizationMember
from app.auth.security import to_utc
from app.billing.models import Plan, Subscription, UsageRecord, now
from app.billing.plans import DEFAULT_PLANS, LEGACY_PLAN_ALIASES
from app.config import settings

logger = logging.getLogger(__name__)


class LimitExceeded(Exception):
    """Raised when a metered action would exceed the organization's plan."""

    def __init__(self, metric: str, limit: int, used: int):
        self.metric = metric
        self.limit = limit
        self.used = used
        super().__init__(
            f"Plan limit reached for '{metric}': {used} of {limit} used."
        )


def seed_default_plans(session: Session) -> None:
    """Insert the default catalogue once, so a fresh database is never planless."""
    if session.scalar(select(func.count(Plan.id))):
        return
    for spec in DEFAULT_PLANS:
        session.add(Plan(**spec))
    try:
        session.commit()
    except IntegrityError:
        # Another worker seeded concurrently; the catalogue is still valid.
        session.rollback()


def period_start(at: datetime | None = None) -> datetime:
    at = to_utc(at or now())
    return at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def period_end(start: datetime) -> datetime:
    if start.month == 12:
        return start.replace(year=start.year + 1, month=1)
    return start.replace(month=start.month + 1)


def resolve_plan_code(organization: Organization) -> str:
    code = (organization.plan or "").strip().lower()
    code = LEGACY_PLAN_ALIASES.get(code, code)
    return code or settings.billing_default_plan_code


def get_plan(session: Session, code: str) -> Plan | None:
    seed_default_plans(session)
    return session.scalar(select(Plan).where(Plan.code == code))


def list_plans(session: Session, public_only: bool = True) -> list[Plan]:
    seed_default_plans(session)
    query = select(Plan).where(Plan.is_active.is_(True))
    if public_only:
        query = query.where(Plan.is_public.is_(True))
    return list(session.scalars(query.order_by(Plan.sort_order, Plan.name)).all())


def get_subscription(session: Session, organization: Organization) -> Subscription | None:
    return session.scalar(
        select(Subscription).where(Subscription.organization_id == organization.id)
    )


def get_or_create_subscription(session: Session, organization: Organization) -> Subscription:
    """Return the organization's subscription, creating it from its plan label.

    Trials are derived from the organization's creation date, so an organization
    that predates the billing foundation is never given a retroactive trial.
    """
    existing = get_subscription(session, organization)
    if existing:
        return existing

    plan = get_plan(session, resolve_plan_code(organization))
    if plan is None:
        plan = get_plan(session, settings.billing_default_plan_code)
    if plan is None:
        raise RuntimeError("Billing plan catalogue is empty; cannot resolve a subscription plan.")

    start = period_start()
    trial_days = int(plan.trial_days or 0)
    created_at = to_utc(organization.created_at or now())
    trial_ends_at = created_at + timedelta(days=trial_days) if trial_days else None
    status = "trialing" if trial_ends_at and trial_ends_at > now() else "active"

    subscription = Subscription(
        organization_id=organization.id,
        plan_id=plan.id,
        status=status,
        trial_ends_at=trial_ends_at,
        current_period_start=start,
        current_period_end=period_end(start),
    )
    session.add(subscription)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = get_subscription(session, organization)
        if existing:
            return existing
        raise
    session.refresh(subscription)
    return subscription


def refresh_subscription(session: Session, subscription: Subscription) -> Subscription:
    """Advance an expired trial or billing period in place."""
    changed = False
    at = now()

    trial_ends_at = to_utc(subscription.trial_ends_at)
    if subscription.status == "trialing" and trial_ends_at and trial_ends_at <= at:
        subscription.status = "active"
        changed = True

    current_period_end = to_utc(subscription.current_period_end)
    if subscription.status in ("active", "trialing") and current_period_end and current_period_end <= at:
        start = period_start(at)
        subscription.current_period_start = start
        subscription.current_period_end = period_end(start)
        if subscription.cancel_at_period_end:
            subscription.status = "canceled"
            subscription.canceled_at = at
        changed = True

    if changed:
        subscription.updated_at = at
        session.commit()
    return subscription


def effective_plan(session: Session, organization: Organization) -> Plan:
    subscription = get_subscription(session, organization)
    if subscription:
        plan = session.get(Plan, subscription.plan_id)
        if plan:
            return plan
    plan = get_plan(session, resolve_plan_code(organization))
    if plan:
        return plan
    fallback = get_plan(session, settings.billing_default_plan_code)
    if fallback is None:
        raise RuntimeError("Billing plan catalogue is empty; cannot resolve entitlements.")
    return fallback


def count_active_seats(session: Session, organization: Organization) -> int:
    members = session.scalar(
        select(func.count(OrganizationMember.id)).where(
            OrganizationMember.organization_id == organization.id,
            OrganizationMember.status == "active",
        )
    ) or 0
    pending = session.scalar(
        select(func.count(OrganizationInvitation.id)).where(
            OrganizationInvitation.organization_id == organization.id,
            OrganizationInvitation.status == "pending",
        )
    ) or 0
    return members + pending


def current_usage(
    session: Session,
    organization: Organization,
    metric: str,
    at: datetime | None = None,
) -> int:
    if metric == "seats":
        return count_active_seats(session, organization)
    start = period_start(at)
    record = session.scalar(
        select(UsageRecord).where(
            UsageRecord.organization_id == organization.id,
            UsageRecord.metric == metric,
            UsageRecord.period_start == start,
        )
    )
    return int(record.quantity) if record else 0


def get_limit(session: Session, organization: Organization, metric: str) -> int | None:
    plan = effective_plan(session, organization)
    limits = plan.limits or {}
    if metric not in limits:
        return None
    value = limits[metric]
    return int(value) if value is not None else None


def check_limit(
    session: Session,
    organization: Organization,
    metric: str,
    amount: int = 1,
) -> None:
    """Raise :class:`LimitExceeded` when the action has no room on the plan."""
    if not settings.billing_enforce_limits:
        return
    limit = get_limit(session, organization, metric)
    if limit is None:
        return
    used = current_usage(session, organization, metric)
    if used + amount > limit:
        raise LimitExceeded(metric=metric, limit=limit, used=used)


def record_usage(
    session: Session,
    organization: Organization,
    metric: str,
    amount: int = 1,
    commit: bool = True,
) -> int:
    """Add to the current period's meter and return the new total."""
    start = period_start()
    record = session.scalar(
        select(UsageRecord).where(
            UsageRecord.organization_id == organization.id,
            UsageRecord.metric == metric,
            UsageRecord.period_start == start,
        )
    )
    if record is None:
        record = UsageRecord(
            organization_id=organization.id,
            metric=metric,
            period_start=start,
            quantity=0,
        )
        session.add(record)
    record.quantity = int(record.quantity) + amount
    record.updated_at = now()
    if commit:
        session.commit()
    return int(record.quantity)


def change_plan(session: Session, organization: Organization, plan_code: str) -> Subscription:
    """Move an organization to another catalogue plan (upgrade or downgrade)."""
    plan = session.scalar(
        select(Plan).where(Plan.code == plan_code, Plan.is_active.is_(True))
    )
    if plan is None:
        raise ValueError(f"Unknown plan '{plan_code}'.")

    subscription = get_or_create_subscription(session, organization)
    subscription.plan_id = plan.id
    if subscription.status == "canceled":
        subscription.status = "active"
        subscription.canceled_at = None
        subscription.cancel_at_period_end = False
        subscription.current_period_start = period_start()
        subscription.current_period_end = period_end(subscription.current_period_start)
    subscription.updated_at = now()
    organization.plan = plan.code
    organization.updated_at = now()
    session.commit()
    session.refresh(subscription)
    return subscription


def cancel_subscription(session: Session, organization: Organization) -> Subscription:
    """Cancel at the end of the paid period; access continues until then."""
    subscription = get_or_create_subscription(session, organization)
    if subscription.status == "canceled":
        return subscription
    subscription.cancel_at_period_end = True
    subscription.updated_at = now()
    session.commit()
    session.refresh(subscription)
    return subscription


def resume_subscription(session: Session, organization: Organization) -> Subscription:
    subscription = get_or_create_subscription(session, organization)
    if subscription.status == "canceled":
        subscription.status = "active"
        subscription.canceled_at = None
        subscription.cancel_at_period_end = False
        subscription.current_period_start = period_start()
        subscription.current_period_end = period_end(subscription.current_period_start)
    else:
        subscription.cancel_at_period_end = False
    subscription.updated_at = now()
    session.commit()
    session.refresh(subscription)
    return subscription


def usage_snapshot(session: Session, organization: Organization) -> dict:
    """Current consumption against each metered limit for this organization."""
    plan = effective_plan(session, organization)
    limits = dict(plan.limits or {})
    usage: dict[str, int] = {}
    remaining: dict[str, int | None] = {}
    for metric in limits:
        used = current_usage(session, organization, metric)
        usage[metric] = used
        limit = limits[metric]
        remaining[metric] = None if limit is None else max(int(limit) - used, 0)
    return {"limits": limits, "usage": usage, "remaining": remaining}
