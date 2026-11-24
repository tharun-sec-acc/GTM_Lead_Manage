import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import TenantContext, get_current_user, get_tenant_context, require_role
from app.auth.models import (
    AuditLog,
    Organization,
    OrganizationInvitation,
    OrganizationMember,
    User,
    now,
)
from app.auth.schemas import (
    AcceptInvitationRequest,
    InvitationResponse,
    MemberInviteRequest,
    MemberResponse,
    MemberUpdateRequest,
    OrganizationResponse,
    OrganizationUpdateRequest,
)
from app.auth.security import generate_secure_token, hash_password, hash_token, to_utc
from app.billing.service import LimitExceeded, check_limit
from app.config import settings
from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/organizations", tags=["Organization Management"])
public_router = APIRouter(prefix="/public/invitations", tags=["Public Invitations"])


@router.get("/current", response_model=OrganizationResponse)
def get_current_organization(
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    org = ctx.organization
    member_count = session.scalar(
        select(func.count(OrganizationMember.id)).where(OrganizationMember.organization_id == org.id)
    ) or 1

    return OrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        domain=org.domain,
        plan=org.plan,
        status=org.status,
        settings=org.settings or {},
        created_at=org.created_at,
        member_count=member_count,
        user_role=ctx.role,
    )


@router.put("/current", response_model=OrganizationResponse)
def update_current_organization(
    data: OrganizationUpdateRequest,
    ctx: TenantContext = Depends(require_role("admin")),
    session: Session = Depends(get_db),
):
    org = ctx.organization
    if data.name is not None:
        org.name = data.name.strip()
    if data.domain is not None:
        org.domain = data.domain.strip() or None
    if data.settings is not None:
        current_settings = dict(org.settings or {})
        current_settings.update(data.settings)
        org.settings = current_settings

    org.updated_at = now()
    session.commit()

    return OrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        domain=org.domain,
        plan=org.plan,
        status=org.status,
        settings=org.settings or {},
        created_at=org.created_at,
        user_role=ctx.role,
    )


@router.get("/members", response_model=list[MemberResponse])
def list_members(
    ctx: TenantContext = Depends(get_tenant_context),
    session: Session = Depends(get_db),
):
    rows = session.execute(
        select(OrganizationMember, User)
        .join(User, OrganizationMember.user_id == User.id)
        .where(OrganizationMember.organization_id == ctx.org_id)
        .order_by(OrganizationMember.joined_at.asc())
    ).all()

    members = []
    for member, user in rows:
        members.append(
            MemberResponse(
                id=member.id,
                user_id=user.id,
                email=user.email,
                full_name=user.full_name or user.email,
                role=member.role,
                status=member.status,
                joined_at=member.joined_at,
            )
        )
    return members


@router.post("/members/invite", response_model=InvitationResponse, status_code=status.HTTP_201_CREATED)
def invite_member(
    data: MemberInviteRequest,
    ctx: TenantContext = Depends(require_role("admin")),
    session: Session = Depends(get_db),
):
    email = data.email.lower().strip()

    # Check if already a member
    existing_user = session.scalar(select(User).where(User.email == email))
    if existing_user:
        existing_member = session.scalar(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == ctx.org_id,
                OrganizationMember.user_id == existing_user.id,
            )
        )
        if existing_member:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User is already a member of this organization.",
            )

    try:
        check_limit(session, ctx.organization, "seats", amount=1)
    except LimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=str(exc),
        ) from exc

    raw_token = generate_secure_token(32)
    invitation = OrganizationInvitation(
        organization_id=ctx.org_id,
        email=email,
        role=data.role,
        token_hash=hash_token(raw_token),
        invited_by_id=ctx.user.id if ctx.user else None,
        status="pending",
        expires_at=now() + timedelta(days=7),
    )
    session.add(invitation)
    session.commit()

    base_url = (settings.public_base_url or "http://localhost:3000").rstrip("/")
    invite_url = f"{base_url}/invite/{raw_token}"

    logger.info("Invitation created for %s to join org %s: %s", email, ctx.org_id, invite_url)

    return InvitationResponse(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        status=invitation.status,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
        invite_url=invite_url,
    )


@router.put("/members/{member_id}", response_model=MemberResponse)
def update_member(
    member_id: str,
    data: MemberUpdateRequest,
    ctx: TenantContext = Depends(require_role("admin")),
    session: Session = Depends(get_db),
):
    member = session.get(OrganizationMember, member_id)
    if not member or member.organization_id != ctx.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    if member.role == "owner" and ctx.role != "owner" and (not ctx.user or not ctx.user.is_superadmin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an organization owner can modify another owner.",
        )

    member.role = data.role
    if data.status:
        member.status = data.status
    session.commit()

    user = session.get(User, member.user_id)
    return MemberResponse(
        id=member.id,
        user_id=member.user_id,
        email=user.email if user else "",
        full_name=user.full_name if user else "",
        role=member.role,
        status=member.status,
        joined_at=member.joined_at,
    )


@router.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    member_id: str,
    ctx: TenantContext = Depends(require_role("admin")),
    session: Session = Depends(get_db),
):
    member = session.get(OrganizationMember, member_id)
    if not member or member.organization_id != ctx.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    if member.role == "owner":
        # Check if there are other owners
        other_owners = session.scalar(
            select(func.count(OrganizationMember.id)).where(
                OrganizationMember.organization_id == ctx.org_id,
                OrganizationMember.role == "owner",
                OrganizationMember.id != member_id,
            )
        )
        if not other_owners:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the sole owner of an organization.",
            )

    session.delete(member)
    session.commit()


@router.get("/invitations", response_model=list[InvitationResponse])
def list_invitations(
    ctx: TenantContext = Depends(require_role("admin")),
    session: Session = Depends(get_db),
):
    invites = session.scalars(
        select(OrganizationInvitation)
        .where(
            OrganizationInvitation.organization_id == ctx.org_id,
            OrganizationInvitation.status == "pending",
        )
        .order_by(OrganizationInvitation.created_at.desc())
    ).all()

    return [
        InvitationResponse(
            id=inv.id,
            email=inv.email,
            role=inv.role,
            status=inv.status,
            expires_at=inv.expires_at,
            created_at=inv.created_at,
        )
        for inv in invites
    ]


@router.delete("/invitations/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invitation(
    invite_id: str,
    ctx: TenantContext = Depends(require_role("admin")),
    session: Session = Depends(get_db),
):
    inv = session.get(OrganizationInvitation, invite_id)
    if not inv or inv.organization_id != ctx.org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found.")

    inv.status = "revoked"
    session.commit()


# --- Public Invitation Acceptance Endpoints ---


@public_router.get("/{token}")
def check_invitation(token: str, session: Session = Depends(get_db)):
    h = hash_token(token)
    invite = session.scalar(
        select(OrganizationInvitation).where(
            OrganizationInvitation.token_hash == h,
            OrganizationInvitation.status == "pending",
        )
    )
    if not invite or to_utc(invite.expires_at) < now():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation link is invalid or has expired.",
        )

    org = session.get(Organization, invite.organization_id)
    return {
        "status": "valid",
        "email": invite.email,
        "role": invite.role,
        "organization_name": org.name if org else "Organization",
    }


@public_router.post("/accept")
def accept_invitation(
    data: AcceptInvitationRequest,
    session: Session = Depends(get_db),
):
    h = hash_token(data.token)
    invite = session.scalar(
        select(OrganizationInvitation).where(
            OrganizationInvitation.token_hash == h,
            OrganizationInvitation.status == "pending",
        )
    )
    if not invite or to_utc(invite.expires_at) < now():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation link is invalid or has expired.",
        )

    email = invite.email.lower().strip()
    user = session.scalar(select(User).where(User.email == email))
    if not user:
        user = User(
            email=email,
            hashed_password=hash_password(data.password),
            full_name=data.full_name.strip(),
            is_active=True,
            is_verified=True,
        )
        session.add(user)
        session.flush()

    # Check existing membership
    existing_member = session.scalar(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == invite.organization_id,
            OrganizationMember.user_id == user.id,
        )
    )
    if not existing_member:
        membership = OrganizationMember(
            organization_id=invite.organization_id,
            user_id=user.id,
            role=invite.role,
            status="active",
        )
        session.add(membership)

    invite.status = "accepted"
    session.commit()

    return {"status": "ok", "message": "Invitation accepted successfully. You may now log in."}
