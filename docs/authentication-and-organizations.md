# Authentication, organizations and tenancy

Implemented in `backend/app/auth` and migration `0019_saas_multi_tenant_auth`; frontend screens live under
`frontend/app/login`, `register`, `forgot-password`, `reset-password`, `invite/[token]` and `settings/*`.
The browser-side session lives in `frontend/lib/auth-context.tsx`.

## 1. What is implemented

| Area | Implementation |
| --- | --- |
| Accounts | Email + bcrypt password (12 rounds), display name, active/verified flags, super-admin flag, failed-attempt counter and lockout |
| Sessions | JWT access token (default 120 minutes) and refresh token (default 14 days), issued as HttpOnly cookies and also accepted as `Authorization: Bearer` |
| Revocation | Logout stores the access token `jti` in `revoked_tokens`; `get_current_user_optional` rejects revoked tokens |
| Organizations | `organizations` table with name, unique slug, optional domain, plan, status, JSON settings |
| Membership | `organization_members` with a unique `(organization_id, user_id)` pair and role/status |
| Roles | `super_admin` (100), `owner` (80), `admin` (60), `manager` (40), `rep` (20), `read_only` (10) |
| Invitations | SHA-256 hashed token, 7-day expiry, invited email and role, `pending`/`accepted`/`expired`/`revoked` status |
| Password reset | Hashed single-use token with expiry (`password_reset_tokens`) |
| Email verification | `email_verification_tokens` table and `users.is_verified`; no verification email is sent and no verification endpoint is exposed |
| Audit | `audit_logs` records action, resource, actor, organization and IP for the actions that write it |
| Integration connections | `oauth_connections` per organization/user/provider with encrypted refresh/access tokens, scopes, status and metadata |
| Tenant resolution | `get_tenant_context` resolves the active organization for every request; `require_role(...)` enforces minimum role |

Roles are compared by numeric rank, so `admin` satisfies a `manager` check. `super_admin` is a global user flag
that outranks organization roles when the user is not a member of the requested organization.

## 2. Session and cookie behavior

`POST /auth/login` sets two HttpOnly cookies:

- `access_token`, lifetime `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`;
- `refresh_token`, lifetime `JWT_REFRESH_TOKEN_EXPIRE_DAYS`.

`COOKIE_SECURE`, `COOKIE_SAMESITE` and `COOKIE_DOMAIN` control the cookie attributes. The defaults
(`secure=false`, `samesite=lax`) are for local HTTP only; a real HTTPS deployment must set `COOKIE_SECURE=true`.

Access tokens carry `sub`, `org_id`, `role`, `is_superadmin`, `jti`, `type`, `exp` and `iat` claims and are
signed with `JWT_SECRET_KEY`/`JWT_ALGORITHM`. **The default secret in `backend/app/config.py` is a development
placeholder**; set a private random 32+ character value in `.env` before any shared or production use.

Login locks an account for 15 minutes after 5 consecutive failures (`failed_login_attempts`, `locked_until`).
There is no IP-based rate limiting, captcha or MFA.

## 3. Auth endpoints

Mounted at both `/auth/...` and `/api/auth/...`:

| Method and path | Purpose |
| --- | --- |
| `POST /auth/register` | Create a user; without an invitation this also creates a new organization with the user as `owner`; with `invitation_token` it joins the inviting organization with the invited role |
| `POST /auth/login` | Password login, cookie + token response, lockout handling |
| `POST /auth/refresh` | Rotate/issue a new access token from a refresh token or cookie |
| `POST /auth/logout` | Revoke the current access token and clear cookies |
| `GET /auth/me` | Current profile, active organization and memberships |
| `PUT /auth/profile` | Update display name/avatar |
| `POST /auth/change-password` | Change the current user's password |
| `POST /auth/switch-org/{org_id}` | Re-issue tokens scoped to another organization the user belongs to |
| `POST /auth/forgot-password` | Create a reset token (the raw token is returned/logged for local use; no email is sent) |
| `POST /auth/reset-password` | Consume a reset token and set a new password |

Organization endpoints (`/organizations` and `/api/organizations`):

| Method and path | Minimum role | Purpose |
| --- | --- | --- |
| `GET /organizations/current`, `PUT /organizations/current` | member / `admin` | Read or update the tenant profile |
| `GET /organizations/members` | member | List members |
| `POST /organizations/members/invite` | `admin` | Create an invitation and return `invite_url` |
| `PUT /organizations/members/{id}` | `admin` | Change role or membership status |
| `DELETE /organizations/members/{id}` | `admin` | Remove a member; the sole owner cannot be removed |
| `GET /organizations/invitations`, `DELETE /organizations/invitations/{id}` | `admin` | List or revoke pending invitations |

Public invitation acceptance is mounted separately and serves the `/invite/{token}` page: the invitee registers
or logs in, then `POST /auth/register` consumes the hashed invitation token.

Invitations are **not emailed**. `POST /organizations/members/invite` returns the accept link (and logs it
server-side); an administrator must deliver it. `PUBLIC_BASE_URL` is used to build the link and falls back to
`http://localhost:3000`.

## 4. Tenant resolution

`get_tenant_context` runs on almost every business route and resolves the organization in this order:

1. `X-Organization-Id` header, if the user has an active membership there;
2. the `org_id` claim in the access token;
3. the user's oldest active membership;
4. the default organization (`DEFAULT_ORG_SLUG`) when the user is a super-admin.

If nothing matches and `AUTH_ALLOW_ANONYMOUS_FALLBACK=true`, a tenant context for the default organization is
returned with `user=None` and `is_anonymous_fallback=True`. That flag keeps legacy tests and first-run
experiments working without a login, but it means **the API accepts unauthenticated requests against the
default organization** whenever it is enabled. Set `AUTH_ALLOW_ANONYMOUS_FALLBACK=false` for any deployment that
must require sign-in. `AUTH_ENABLED=false` is intended only for throwaway local checks.

Records created through tenant-aware routes are stamped with `organization_id` (`leads`, `campaigns`,
`batches`, `products`, bookings, meetings, Zoho and market-intelligence records). Queries filter on the active
organization, so two organizations in the same database do not see each other's pipeline.

## 5. Integrations and OAuth connections

`GET /api/integrations/status` reports Google, Microsoft and Zoho connection state for the active organization,
merging new `oauth_connections` rows with the legacy single-organizer `google_oauth_credentials` and
`microsoft_oauth_credentials` tables. Each entry carries `connect_url`, scopes, capabilities and the last error.
`POST /api/integrations/{provider}/disconnect` clears the local encrypted credentials; it does **not** revoke
consent at the provider.

OAuth tokens in `oauth_connections` are encrypted with Fernet using the per-provider encryption key settings.
Never reuse a key across environments and never commit a key.

## 6. Frontend

- `/login`, `/register`, `/forgot-password`, `/reset-password`, `/invite/[token]` are public pages rendered
  outside the application shell.
- `AuthProvider` restores the session from cookies, exposes `user`, `organization`, `organizations`, `logout`
  and `switchOrganization`, and redirects unauthenticated users away from workspace pages.
- `/settings/profile`, `/settings/organization`, `/settings/team`, `/settings/integrations` and
  `/settings/email-accounts` are the account, tenant, membership and connection screens.
- The sidebar organization switcher calls `/auth/switch-org/{id}` and then reloads tenant data.

## 7. Configuration

| Variable | Purpose |
| --- | --- |
| `JWT_SECRET_KEY`, `JWT_ALGORITHM` | Token signing; replace the development default |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`, `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | Session lifetimes (120 / 14 by default) |
| `CORS_ALLOWED_ORIGINS` | Explicit browser origins allowed for credentialed requests |
| `COOKIE_SECURE`, `COOKIE_SAMESITE`, `COOKIE_DOMAIN` | Cookie attributes |
| `AUTH_ENABLED`, `AUTH_ALLOW_ANONYMOUS_FALLBACK` | Require sign-in / allow the default-organization fallback |
| `DEFAULT_ORG_NAME`, `DEFAULT_ORG_SLUG` | Organization created for the anonymous fallback and first run |
| `PUBLIC_BASE_URL` | Base URL used in invitation links |

## 8. Verification and limitations

- Automated coverage: `backend/tests/test_saas_multi_tenant_auth.py`.
- Not implemented: SSO/OIDC/SAML, MFA, email-verification delivery, captcha, login rate limiting by IP,
  organization billing, SCIM, and provider-side token revocation.
- The audit log is written by selected membership/profile actions, not every mutation.
- No live identity-provider test has been run for this module; external OAuth flows are exercised with mocks.
- The anonymous fallback and the development JWT secret are the two settings most likely to expose a local
  install; review both before sharing a deployment.
