# Zoho CRM integration

Implemented in `backend/app/zoho` with migration `0018_zoho_crm_integration` and the `/zoho` screen in the
frontend (`frontend/app/zoho/page.tsx`, `frontend/lib/zoho.ts`).

## 1. Connection

The integration uses Zoho's OAuth 2.0 authorization-code flow against the configured regional domains
(`ZOHO_ACCOUNTS_DOMAIN`, `ZOHO_API_DOMAIN`, default India: `https://accounts.zoho.in` and
`https://www.zohoapis.in`) with CRM API version `ZOHO_CRM_API_VERSION` (default `v8`).

- `GET /zoho/oauth/authorize` issues the consent URL and stores an `zoho_oauth_states` row containing a hashed
  state, a browser fingerprint (user agent + client IP) and a short expiry.
- `GET /zoho/oauth/callback` rejects an expired, consumed or non-matching browser state, exchanges the code,
  resolves the Zoho organization (`org_id`, `org_name`, user email/ZUID) and stores a `zoho_connections` row.
- Refresh and access tokens are Fernet-encrypted with `ZOHO_TOKEN_ENCRYPTION_KEY`.
- `GET /zoho/connection` reports status; `POST /zoho/verify` performs a live API check; `POST /zoho/disconnect`
  clears the local connection. `GET/POST/DELETE` handlers exist for connection lifecycle and configuration.

`zoho_connections.organization_id` links a connection to an organization; `sync_direction` limits sync to
`bidirectional`, `outbound` or `inbound`. The service currently operates on the active connection; multiple
simultaneous connections from different Zoho organizations are not coordinated.

## 2. Modules, fields and mappings

| Method and path | Purpose |
| --- | --- |
| `GET /zoho/modules` | List available CRM modules |
| `GET /zoho/modules/{module}/fields` | List fields for a module |
| `GET /zoho/mappings` | List field mappings (optionally by module) |
| `PATCH /zoho/mappings/{id}` | Change the target field, direction or conflict policy |

`zoho_field_mappings` ships defaults for Accounts, Contacts, Leads, Deals, Tasks and Events, each with
`sync_direction` (`bidirectional`, `gtm_to_zoho`, `zoho_to_gtm`) and `conflict_policy` (`crm_wins`,
`gtm_wins`, `newest_wins`). Mappings are editable, so custom Zoho fields can be adopted without code changes.

The GTM lead stage is translated to a Zoho Deal stage through `DEFAULT_STAGE_MAPPING` (for example
`meeting_scheduled` -> `Proposal/Price Quote`, `qualified` -> `Negotiation/Review`, `won` -> `Closed Won`).

## 3. Synchronization

| Method and path | Purpose |
| --- | --- |
| `POST /zoho/sync` | Enqueue an inbound, outbound or bidirectional sync with optional module filter |
| `GET /zoho/sync/jobs` | List recent sync jobs with status, counts and errors |
| `GET /zoho/sync/logs` | Per-record sync log entries |
| `POST /zoho/sync/leads/{lead_id}` | Sync one lead immediately (used by the Lead 360 "Sync to Zoho" action) |
| `GET /zoho/conflicts` | Records where both sides changed and the policy could not settle it |
| `POST /zoho/conflicts/{id}/resolve` | Choose the winning side for a conflict |

`zoho_record_mappings` remembers the GTM <-> Zoho id pairs per module so repeat syncs update instead of
duplicating. Conflicts are recorded rather than silently overwritten when both sides changed and the mapping
policy is `newest_wins` without comparable timestamps, or when a required field is missing.

Celery Beat dispatches:

| Task | Interval |
| --- | --- |
| `app.tasks.zoho_outbound_sync_task` | 120 seconds |
| `app.tasks.zoho_inbound_sync_task` | 300 seconds |
| `app.tasks.zoho_token_refresh_task` | 900 seconds |

All three are no-ops until a connection exists, and respect `ZOHO_SYNC_ENABLED`.

## 4. Data direction

- Outbound: leads, contacts, products/opportunities, sales tasks, meetings and bookings are pushed using the
  module mappings and stage translation.
- Inbound: changed Zoho Leads/Contacts/Deals update the matching GTM record through `zoho_record_mappings`,
  subject to the per-field conflict policy.
- Every job writes counts, timestamps and errors to `zoho_sync_jobs` and `zoho_sync_logs`.

## 5. Configuration

| Variable | Purpose |
| --- | --- |
| `ZOHO_CLIENT_ID`, `ZOHO_CLIENT_SECRET` | Zoho API console client credentials |
| `ZOHO_REDIRECT_URI` | Must match the registered redirect, default `http://localhost:8000/zoho/oauth/callback` |
| `ZOHO_ACCOUNTS_DOMAIN`, `ZOHO_API_DOMAIN`, `ZOHO_CRM_API_VERSION` | Regional endpoints and API version |
| `ZOHO_TOKEN_ENCRYPTION_KEY` | Fernet key for stored tokens; generate once and keep private |
| `ZOHO_SYNC_ENABLED` | Master switch for scheduled sync tasks |

Generate the key with:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## 6. UI

`/zoho` shows connection status, module/field mapping editor, sync trigger and job history, sync logs and the
conflict resolution list. The Lead 360 page calls `POST /zoho/sync/leads/{id}` for the selected company.

## 7. Limitations

- No Zoho webhooks/notifications; inbound changes are found by polling.
- No automatic retry/backoff beyond the scheduled job cadence; failures are logged and surfaced, not silently
  retried.
- Field mapping changes affect future syncs only; previously mapped values are not rewritten.
- Automated coverage: `backend/tests/test_zoho_crm.py` uses mocked API responses. No live Zoho tenant has been
  exercised, so scopes, plan limits and stage picklists must be verified against the target account before use.
- Deletes are not propagated in either direction; a deleted Zoho record and its GTM counterpart must be
  reconciled manually.
