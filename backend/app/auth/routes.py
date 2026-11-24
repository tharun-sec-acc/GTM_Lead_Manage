import logging
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import TenantContext, get_current_user, get_tenant_context, optional_bearer
from app.auth.models import (
    AuditLog,
    EmailVerificationToken,
    Organization,
    OrganizationInvitation,
    OrganizationMember,
    PasswordResetToken,
    RevokedToken,
    User,
    now,
)
from app.auth.schemas import (
    ChangePasswordRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshTokenRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserLoginRequest,
    UserProfileResponse,
    UserRegisterRequest,
)
from app.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_jwt_token,
    generate_secure_token,
    hash_password,
    hash_token,
    to_utc,
    verify_password,
)
from app.config import settings
from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[-\s]+", "-", cleaned) or "org"


def set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    """Set secure cookies for authentication."""
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
        max_age=settings.jwt_access_token_expire_minutes * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
        max_age=settings.jwt_refresh_token_expire_days * 86400,
    )


def clear_auth_cookies(response: Response):
    """Clear authentication cookies."""
    response.delete_cookie(key="access_token", domain=settings.cookie_domain)
    response.delete_cookie(key="refresh_token", domain=settings.cookie_domain)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    data: UserRegisterRequest,
    response: Response,
    request: Request,
    session: Session = Depends(get_db),
):
    email = data.email.lower().strip()
    existing_user = session.scalar(select(User).where(User.email == email))
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )

    # Create User
    user = User(
        email=email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name.strip(),
        is_active=True,
        is_verified=False,
    )
    session.add(user)
    session.flush()

    org = None
    role = "owner"

    # Check invitation token if provided
    if data.invitation_token:
        h = hash_token(data.invitation_token)
        invite = session.scalar(
            select(OrganizationInvitation).where(
                OrganizationInvitation.token_hash == h,
                OrganizationInvitation.status == "pending",
            )
        )
        if invite and to_utc(invite.expires_at) > now():
            org = session.get(Organization, invite.organization_id)
            role = invite.role
            invite.status = "accepted"

    # Otherwise create new organization
    if not org:
        org_name = (
            data.organization_name.strip()
            if data.organization_name
            else f"{data.full_name.strip()}'s Workspace"
        )
        base_slug = slugify(org_name)
        slug = base_slug
        counter = 1
        while session.scalar(select(Organization).where(Organization.slug == slug)):
            slug = f"{base_slug}-{counter}"
            counter += 1

        org = Organization(
            name=org_name,
            slug=slug,
            plan="pro",
            status="active",
            settings={"tier": "pro"},
        )
        session.add(org)
        session.flush()
        role = "owner"

    # Add Organization Membership
    membership = OrganizationMember(
        organization_id=org.id,
        user_id=user.id,
        role=role,
        status="active",
    )
    session.add(membership)

    # Log audit
    audit = AuditLog(
        organization_id=org.id,
        user_id=user.id,
        action="user_registered",
        resource_type="user",
        resource_id=user.id,
        ip_address=request.client.host if request.client else None,
    )
    session.add(audit)
    session.commit()

    # Generate tokens
    access_token, _, _ = create_access_token(user.id, org.id, role, user.is_superadmin)
    refresh_token, _, _ = create_refresh_token(user.id, org.id)
    set_auth_cookies(response, access_token, refresh_token)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user={"id": user.id, "email": user.email, "full_name": user.full_name, "role": role},
        organization={"id": org.id, "name": org.name, "slug": org.slug, "plan": org.plan},
    )


@router.post("/login", response_model=TokenResponse)
def login(
    data: UserLoginRequest,
    response: Response,
    request: Request,
    session: Session = Depends(get_db),
):
    email = data.email.lower().strip()
    user = session.scalar(select(User).where(User.email == email))

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    # Lockout check
    if user.locked_until and to_utc(user.locked_until) > now():
        wait_seconds = int((to_utc(user.locked_until) - now()).total_seconds())
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Account temporarily locked due to multiple failed attempts. Try again in {wait_seconds // 60 + 1} minutes.",
        )

    # Verify password
    if not verify_password(data.password, user.hashed_password):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
            user.locked_until = now() + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    # Reset failure tracking
    user.failed_login_attempts = 0
    user.locked_until = None

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact support.",
        )

    # Find active organization membership
    member = session.scalar(
        select(OrganizationMember)
        .where(OrganizationMember.user_id == user.id, OrganizationMember.status == "active")
        .order_by(OrganizationMember.joined_at.asc())
    )

    if not member:
        # Fallback or create default org
        from app.auth.dependencies import get_default_organization
        org = get_default_organization(session)
        member = OrganizationMember(organization_id=org.id, user_id=user.id, role="owner")
        session.add(member)
        session.flush()
    else:
        org = session.get(Organization, member.organization_id)

    # Audit log
    audit = AuditLog(
        organization_id=org.id if org else None,
        user_id=user.id,
        action="user_login",
        resource_type="session",
        ip_address=request.client.host if request.client else None,
    )
    session.add(audit)
    session.commit()

    role = "super_admin" if user.is_superadmin else member.role
    access_token, _, _ = create_access_token(user.id, org.id, role, user.is_superadmin)
    refresh_token, _, _ = create_refresh_token(user.id, org.id)
    set_auth_cookies(response, access_token, refresh_token)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user={"id": user.id, "email": user.email, "full_name": user.full_name, "role": role},
        organization={"id": org.id, "name": org.name, "slug": org.slug, "plan": org.plan},
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(
    response: Response,
    data: RefreshTokenRequest | None = None,
    refresh_token_cookie: str | None = Cookie(default=None, alias="refresh_token"),
    session: Session = Depends(get_db),
):
    token = (data.refresh_token if data and data.refresh_token else None) or refresh_token_cookie
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token required.")

    try:
        payload = decode_jwt_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type.")

    user_id = payload.get("sub")
    org_id = payload.get("org_id")
    user = session.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive or not found.")

    org = session.get(Organization, org_id)
    member = session.scalar(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user_id,
            OrganizationMember.status == "active",
        )
    )
    role = "super_admin" if user.is_superadmin else (member.role if member else "rep")

    new_access, _, _ = create_access_token(user.id, org.id, role, user.is_superadmin)
    new_refresh, _, _ = create_refresh_token(user.id, org.id)
    set_auth_cookies(response, new_access, new_refresh)

    return TokenResponse(
        access_token=new_access,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user={"id": user.id, "email": user.email, "full_name": user.full_name, "role": role},
        organization={"id": org.id, "name": org.name, "slug": org.slug, "plan": org.plan},
    )


@router.post("/logout")
def logout(
    response: Response,
    request: Request,
    session: Session = Depends(get_db),
):
    token = request.cookies.get("access_token")
    if not token and request.headers.get("authorization", "").startswith("Bearer "):
        token = request.headers.get("authorization", "").split(" ", 1)[1]

    if token:
        try:
            payload = decode_jwt_token(token)
            jti = payload.get("jti")
            exp = payload.get("exp")
            if jti and exp:
                expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
                revoked = RevokedToken(jti=jti, expires_at=expires_at)
                session.add(revoked)
                session.commit()
        except Exception:
            pass

    clear_auth_cookies(response)
    return {"status": "ok", "message": "Successfully logged out."}


@router.get("/me", response_model=UserProfileResponse)
def get_me(
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    user = ctx.user
    if not user:
        # Anonymous demo user
        return UserProfileResponse(
            id="demo-user",
            email="pilot@workspace.local",
            full_name="Pilot User",
            is_active=True,
            is_verified=True,
            is_superadmin=False,
            created_at=now(),
            active_organization={"id": ctx.org_id, "name": ctx.organization.name, "slug": ctx.organization.slug, "role": "owner"},
            organizations=[{"id": ctx.org_id, "name": ctx.organization.name, "slug": ctx.organization.slug, "role": "owner"}],
        )

    # Load all user org memberships
    memberships = session.scalars(
        select(OrganizationMember)
        .where(OrganizationMember.user_id == user.id, OrganizationMember.status == "active")
    ).all()

    org_list = []
    for m in memberships:
        o = session.get(Organization, m.organization_id)
        if o:
            org_list.append({
                "id": o.id,
                "name": o.name,
                "slug": o.slug,
                "plan": o.plan,
                "role": m.role,
            })

    active_org_dict = {
        "id": ctx.organization.id,
        "name": ctx.organization.name,
        "slug": ctx.organization.slug,
        "plan": ctx.organization.plan,
        "role": ctx.role,
    }

    return UserProfileResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
        is_active=user.is_active,
        is_verified=user.is_verified,
        is_superadmin=user.is_superadmin,
        created_at=user.created_at,
        active_organization=active_org_dict,
        organizations=org_list,
    )


@router.put("/profile")
def update_profile(
    data: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    if data.full_name is not None:
        user.full_name = data.full_name.strip()
    if data.avatar_url is not None:
        user.avatar_url = data.avatar_url.strip() or None
    user.updated_at = now()
    session.commit()
    return {"status": "ok", "message": "Profile updated successfully."}


@router.post("/change-password")
def change_password(
    data: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    if not verify_password(data.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )
    user.hashed_password = hash_password(data.new_password)
    user.updated_at = now()
    session.commit()
    return {"status": "ok", "message": "Password changed successfully."}


@router.post("/switch-org/{org_id}", response_model=TokenResponse)
def switch_organization(
    org_id: str,
    response: Response,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    member = session.scalar(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user.id,
            OrganizationMember.status == "active",
        )
    )
    if not member and not user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not an active member of this organization.",
        )

    org = session.get(Organization, org_id)
    if not org or org.status != "active":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found or inactive.",
        )

    role = "super_admin" if user.is_superadmin else (member.role if member else "rep")
    new_access, _, _ = create_access_token(user.id, org.id, role, user.is_superadmin)
    new_refresh, _, _ = create_refresh_token(user.id, org.id)
    set_auth_cookies(response, new_access, new_refresh)

    return TokenResponse(
        access_token=new_access,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user={"id": user.id, "email": user.email, "full_name": user.full_name, "role": role},
        organization={"id": org.id, "name": org.name, "slug": org.slug, "plan": org.plan},
    )


@router.post("/forgot-password")
def forgot_password(
    data: PasswordResetRequest,
    session: Session = Depends(get_db),
):
    email = data.email.lower().strip()
    user = session.scalar(select(User).where(User.email == email))
    if user:
        raw_token = generate_secure_token(32)
        reset = PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=now() + timedelta(hours=2),
        )
        session.add(reset)
        session.commit()
        logger.info("Password reset token generated for %s: %s", email, raw_token)
        return {
            "status": "ok",
            "message": "If this email is registered, a password reset link has been dispatched.",
            "reset_token": raw_token,  # provided for local/testing convenience
        }
    return {
        "status": "ok",
        "message": "If this email is registered, a password reset link has been dispatched.",
    }


@router.post("/reset-password")
def reset_password(
    data: PasswordResetConfirm,
    session: Session = Depends(get_db),
):
    h = hash_token(data.token)
    reset = session.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == h,
            PasswordResetToken.consumed_at.is_(None),
        )
    )
    if not reset or to_utc(reset.expires_at) <= now():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password reset token is invalid or has expired.",
        )

    user = session.get(User, reset.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    user.hashed_password = hash_password(data.new_password)
    user.failed_login_attempts = 0
    user.locked_until = None
    user.updated_at = now()
    reset.consumed_at = now()
    session.commit()

    return {"status": "ok", "message": "Password reset successfully. You may now log in."}
