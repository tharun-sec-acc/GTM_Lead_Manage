import logging
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Header, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import Organization, OrganizationMember, RevokedToken, User
from app.auth.security import decode_jwt_token
from app.config import settings
from app.database import get_db

logger = logging.getLogger(__name__)

optional_bearer = HTTPBearer(auto_error=False)

ROLE_HIERARCHY: dict[str, int] = {
    "super_admin": 100,
    "owner": 80,
    "admin": 60,
    "manager": 40,
    "rep": 20,
    "read_only": 10,
}


class TenantContext:
    def __init__(
        self,
        user: User | None,
        organization: Organization,
        member: OrganizationMember | None = None,
        is_anonymous_fallback: bool = False,
    ):
        self.user = user
        self.organization = organization
        self.org_id = organization.id
        self.member = member
        self.role = (
            "super_admin"
            if user and user.is_superadmin
            else (member.role if member else "owner")
        )
        self.is_anonymous_fallback = is_anonymous_fallback

    def has_role(self, minimum_role: str) -> bool:
        user_rank = ROLE_HIERARCHY.get(self.role, 0)
        req_rank = ROLE_HIERARCHY.get(minimum_role, 0)
        return user_rank >= req_rank


def get_default_organization(session: Session) -> Organization:
    """Ensure a default organization exists for the system/legacy fallback."""
    org = session.scalar(
        select(Organization).where(Organization.slug == settings.default_org_slug)
    )
    if not org:
        org = Organization(
            name=settings.default_org_name,
            slug=settings.default_org_slug,
            plan="enterprise",
            status="active",
            settings={"tier": "enterprise", "features": ["all"]},
        )
        session.add(org)
        session.commit()
    return org


def get_token_from_request(
    request: Request,
    auth_header: HTTPAuthorizationCredentials | None = Depends(optional_bearer),
) -> str | None:
    """Extract JWT token from Bearer header or HttpOnly cookie."""
    if auth_header and auth_header.credentials:
        return auth_header.credentials
    # Fallback to cookie
    return request.cookies.get("access_token")


def get_current_user_optional(
    token: str | None = Depends(get_token_from_request),
    session: Session = Depends(get_db),
) -> tuple[User | None, dict[str, Any] | None]:
    """Verify JWT and return (User, payload) if valid, or (None, None)."""
    if not token:
        return None, None
    try:
        payload = decode_jwt_token(token)
    except ValueError as exc:
        logger.debug("JWT decode failed: %s", exc)
        return None, None

    jti = payload.get("jti")
    if jti:
        revoked = session.scalar(select(RevokedToken).where(RevokedToken.jti == jti))
        if revoked:
            logger.warning("Revoked token attempted: %s", jti)
            return None, None

    user_id = payload.get("sub")
    if not user_id:
        return None, None

    user = session.get(User, user_id)
    if not user or not user.is_active:
        return None, None

    return user, payload


def get_current_user(
    user_payload: tuple[User | None, dict[str, Any] | None] = Depends(get_current_user_optional),
) -> User:
    """Strictly require authenticated user or raise 401."""
    user, _ = user_payload
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_tenant_context(
    request: Request,
    user_payload: tuple[User | None, dict[str, Any] | None] = Depends(get_current_user_optional),
    session: Session = Depends(get_db),
    x_org_id: str | None = Header(default=None, alias="X-Organization-Id"),
) -> TenantContext:
    """
    Resolve active tenant context:
    1. If user is authenticated, resolve membership in requested org (or payload org, or primary membership).
    2. If unauthenticated, but auth_allow_anonymous_fallback is True, return default organization context.
    3. Otherwise, raise 401 Unauthorized.
    """
    user, payload = user_payload

    if user and payload:
        target_org_id = x_org_id or payload.get("org_id")
        member = None
        org = None

        if target_org_id:
            member = session.scalar(
                select(OrganizationMember).where(
                    OrganizationMember.organization_id == target_org_id,
                    OrganizationMember.user_id == user.id,
                    OrganizationMember.status == "active",
                )
            )
            if member:
                org = session.get(Organization, target_org_id)

        # Fallback to first active membership
        if not org:
            member = session.scalar(
                select(OrganizationMember)
                .where(
                    OrganizationMember.user_id == user.id,
                    OrganizationMember.status == "active",
                )
                .order_by(OrganizationMember.joined_at.asc())
            )
            if member:
                org = session.get(Organization, member.organization_id)

        # Fallback if superadmin
        if not org and user.is_superadmin:
            org = session.get(Organization, target_org_id) if target_org_id else get_default_organization(session)

        if org:
            return TenantContext(user=user, organization=org, member=member)

    # Anonymous / Unauthenticated
    if settings.auth_allow_anonymous_fallback:
        default_org = get_default_organization(session)
        return TenantContext(user=None, organization=default_org, is_anonymous_fallback=True)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Valid organization context required. Please log in.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_role(minimum_role: str):
    """Dependency factory checking that the user holds at least the minimum role in the tenant."""
    def _role_checker(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
        if ctx.is_anonymous_fallback and not settings.auth_allow_anonymous_fallback:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required.",
            )
        if not ctx.has_role(minimum_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Requires at least '{minimum_role}' role.",
            )
        return ctx

    return _role_checker
