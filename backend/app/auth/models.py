from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    false,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def new_id() -> str:
    return str(uuid4())


def now() -> datetime:
    return datetime.now(timezone.utc)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    domain: Mapped[str | None] = mapped_column(String(253), nullable=True)
    plan: Mapped[str] = mapped_column(String(50), default="pro", nullable=False)  # free, pro, enterprise
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)  # active, trial, suspended
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    # Relationships
    members: Mapped[list["OrganizationMember"]] = relationship(
        "OrganizationMember", back_populates="organization", cascade="all, delete-orphan"
    )
    invitations: Mapped[list["OrganizationInvitation"]] = relationship(
        "OrganizationInvitation", back_populates="organization", cascade="all, delete-orphan"
    )
    oauth_connections: Mapped[list["OAuthConnection"]] = relationship(
        "OAuthConnection", back_populates="organization", cascade="all, delete-orphan"
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    # Relationships
    memberships: Mapped[list["OrganizationMember"]] = relationship(
        "OrganizationMember", back_populates="user", cascade="all, delete-orphan"
    )
    oauth_connections: Mapped[list["OAuthConnection"]] = relationship(
        "OAuthConnection", back_populates="user", cascade="all, delete-orphan"
    )


class OrganizationMember(Base):
    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_org_member"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # Roles: owner, admin, manager, rep, read_only
    role: Mapped[str] = mapped_column(String(50), default="rep", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)  # active, suspended
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    organization: Mapped["Organization"] = relationship("Organization", back_populates="members")
    user: Mapped["User"] = relationship("User", back_populates="memberships")


class OrganizationInvitation(Base):
    __tablename__ = "organization_invitations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), default="rep", nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    invited_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)  # pending, accepted, expired, revoked
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    organization: Mapped["Organization"] = relationship("Organization", back_populates="invitations")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class OAuthConnection(Base):
    __tablename__ = "oauth_connections"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", "provider", "account_email", name="uq_org_user_provider_account"),
        Index("ix_oauth_conn_org_provider", "organization_id", "provider"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # google, microsoft, zoho
    account_email: Mapped[str] = mapped_column(String(320), nullable=False)
    account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    refresh_token_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    access_token_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    access_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    # Lifecycle: not_connected, connected, expired, reauth_required, error, disconnected
    status: Mapped[str] = mapped_column(String(30), default="connected", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    connection_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    organization: Mapped["Organization"] = relationship("Organization", back_populates="oauth_connections")
    user: Mapped["User"] = relationship("User", back_populates="oauth_connections")
