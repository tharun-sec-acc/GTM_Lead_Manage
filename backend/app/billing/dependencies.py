"""FastAPI dependencies for plan features and metered limits."""

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import TenantContext, get_tenant_context
from app.billing.models import Plan, Subscription
from app.billing.service import (
    LimitExceeded,
    check_limit,
    effective_plan,
    get_or_create_subscription,
    refresh_subscription,
)
from app.database import get_db


class BillingContext:
    def __init__(
        self,
        tenant: TenantContext,
        subscription: Subscription,
        plan: Plan,
    ):
        self.tenant = tenant
        self.organization = tenant.organization
        self.subscription = subscription
        self.plan = plan

    @property
    def features(self) -> list[str]:
        return list(self.plan.features or [])

    def has_feature(self, feature: str) -> bool:
        return feature in self.features


def get_billing_context(
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
) -> BillingContext:
    subscription = get_or_create_subscription(session, ctx.organization)
    subscription = refresh_subscription(session, subscription)
    plan = session.get(Plan, subscription.plan_id) or effective_plan(session, ctx.organization)
    return BillingContext(tenant=ctx, subscription=subscription, plan=plan)


def require_feature(feature: str):
    """Dependency factory: 403 when the active plan does not include a feature."""

    def _feature_checker(billing: BillingContext = Depends(get_billing_context)) -> BillingContext:
        if not billing.has_feature(feature):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"The '{feature}' capability is not included in the "
                    f"'{billing.plan.name}' plan. Upgrade the organization plan to use it."
                ),
            )
        return billing

    return _feature_checker


def require_within_limit(metric: str, amount: int = 1):
    """Dependency factory: 402 when a metered allowance is exhausted."""

    def _limit_checker(
        billing: BillingContext = Depends(get_billing_context),
        session: Session = Depends(get_db),
    ) -> BillingContext:
        try:
            check_limit(session, billing.organization, metric, amount=amount)
        except LimitExceeded as exc:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=str(exc),
            ) from exc
        return billing

    return _limit_checker
