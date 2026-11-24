from datetime import datetime
from typing import Any
from pydantic import BaseModel, EmailStr, Field


class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)
    organization_name: str | None = Field(default=None, max_length=200)
    invitation_token: str | None = None


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict[str, Any]
    organization: dict[str, Any]


class RefreshTokenRequest(BaseModel):
    refresh_token: str | None = None


class UserProfileResponse(BaseModel):
    id: str
    email: str
    full_name: str
    avatar_url: str | None = None
    is_active: bool
    is_verified: bool
    is_superadmin: bool
    created_at: datetime
    active_organization: dict[str, Any] | None = None
    organizations: list[dict[str, Any]] = []


class UpdateProfileRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    avatar_url: str | None = Field(default=None, max_length=1000)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class OrganizationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=100)
    domain: str | None = Field(default=None, max_length=253)


class OrganizationUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    domain: str | None = Field(default=None, max_length=253)
    settings: dict[str, Any] | None = None


class OrganizationResponse(BaseModel):
    id: str
    name: str
    slug: str
    domain: str | None = None
    plan: str
    status: str
    settings: dict[str, Any] = {}
    created_at: datetime
    member_count: int | None = None
    user_role: str | None = None


class MemberInviteRequest(BaseModel):
    email: EmailStr
    role: str = Field(default="rep", pattern="^(owner|admin|manager|rep|read_only)$")


class MemberUpdateRequest(BaseModel):
    role: str = Field(pattern="^(owner|admin|manager|rep|read_only)$")
    status: str | None = Field(default=None, pattern="^(active|suspended)$")


class MemberResponse(BaseModel):
    id: str
    user_id: str
    email: str
    full_name: str
    role: str
    status: str
    joined_at: datetime


class InvitationResponse(BaseModel):
    id: str
    email: str
    role: str
    status: str
    expires_at: datetime
    created_at: datetime
    invite_url: str | None = None


class AcceptInvitationRequest(BaseModel):
    token: str
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=128)


class OAuthConnectionResponse(BaseModel):
    id: str
    provider: str
    account_email: str
    account_id: str | None = None
    scopes: list[str] = []
    status: str
    error_message: str | None = None
    updated_at: datetime
