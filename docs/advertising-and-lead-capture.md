# Advertising & lead capture (Release 3)

Paid channels and website forms feed the same `leads` table the CRM already owns.
A captured lead is not a separate record: it is a normal tenant lead with
`source`, `source_detail`, an optional advertising campaign reference and an
`attribution_touchpoints` row that keeps the UTM parameters and landing page.

## Scope of this release

Implemented:

- Provider connector framework for Meta Ads and Google Ads (read-only).
- Organization-scoped, encrypted provider credentials.
- Campaign mirroring with per-day metrics and idempotent upserts.
- Meta Lead Ads webhooks with `X-Hub-Signature-256` verification and duplicate suppression.
- Google Ads lead-form webhooks authenticated with a shared form key.
- Website capture forms with consent, honeypot spam control and UTM attribution.
- Campaign → CRM → pipeline → won-revenue reporting with an explicit attribution caveat.
- Workspace page at `/advertising` and navigation entry.

Deliberately **not** implemented in this release:

- Campaign creation, pausing, budget edits or any other spend-affecting provider call.
- Meta/Google OAuth *app* flows (the token handoff is the documented interface; see below).
- Ad set / ad / creative level reporting and keyword reports.
- LinkedIn, Microsoft Ads, TikTok and Amazon connectors.
- Landing-page builder (Release 6).

## Data model

| Table | Purpose |
| --- | --- |
| `ads_connections` | One connected ad account per organization/provider/account id. Tokens are Fernet-encrypted (`access_token_encrypted`, `refresh_token_encrypted`). |
| `ads_campaigns` | Read-only mirror of a provider campaign. Totals are recalculated from `ads_metrics`, never invented. |
| `ads_metrics` | Daily spend/impressions/clicks/leads/conversions, unique per campaign and day. |
| `lead_capture_forms` | Website forms and mirrors of Meta/Google lead forms (`provider_form_id`). |
| `lead_capture_submissions` | Every inbound delivery, unique per `(organization, provider, provider_submission_id)`. Status: `received`, `accepted`, `duplicate`, `rejected`, `error`. |
| `attribution_touchpoints` | Lead ↔ channel/campaign/UTM evidence, including `campaign_external_id` for exact campaign joins. |
| `webhook_receipts` | Idempotency ledger keyed by `(provider, event_id)`. |

Migration: `0022_advertising_lead_capture` (revises `0021_crm_pipeline_and_opportunities`). Additive only.

## API

Mounted at `/advertising` and `/api/advertising`.

| Method | Path | Role | Notes |
| --- | --- | --- | --- |
| GET | `/advertising/providers` | tenant | Capability catalogue + whether app credentials exist. No secrets. |
| GET | `/advertising/connections` | tenant | Never returns tokens. |
| POST | `/advertising/connections` | manager | Saves account + optional provider-approved token (encrypted). |
| POST | `/advertising/connections/{id}/sync` | manager | Pulls campaigns + insights. `409` when credentials/approval are missing. |
| DELETE | `/advertising/connections/{id}` | manager | Destroys stored credentials; provider rows remain for reporting. |
| POST | `/advertising/connections/{id}/campaigns` | manager | Records campaign rows already retrieved from the provider (sync job / export). |
| GET | `/advertising/campaigns` | tenant | Filters: `provider`, `status`, `query`, `limit`. |
| GET | `/advertising/campaigns/{id}` | tenant | Campaign with `cpl_cents`. |
| POST | `/advertising/campaigns/{id}/metrics` | manager | Upserts daily provider figures; duplicates in one payload are merged. |
| GET | `/advertising/reports/campaigns` | tenant | Spend, leads, qualified, opportunities, won value, CPL, cost/qualified, ROAS + caveat. |
| GET | `/advertising/reports/summary` | tenant | Totals, channel mix, submission status mix. |
| GET/POST | `/advertising/forms` | tenant / manager | List and create capture forms (slug is unique per organization). |
| PATCH/DELETE | `/advertising/forms/{id}` | manager | Update or delete a form. |
| GET | `/advertising/forms/{id}/embed` | tenant | Ready-to-paste website snippet. |
| GET | `/advertising/forms/{id}/submissions` | tenant | Submissions for one form. |
| GET | `/advertising/submissions` | tenant | All submissions, filter by `status`/`provider`. |
| POST | `/advertising/submissions/{id}/process` | manager | Retries a Meta delivery that arrived before credentials existed. |

Public endpoints:

| Method | Path | Authentication |
| --- | --- | --- |
| POST | `/public/forms/{slug}/submit` | None (public website form). Consent + honeypot enforced. |
| GET | `/public/webhooks/meta` | `hub.verify_token` must match `META_WEBHOOK_VERIFY_TOKEN`. |
| POST | `/public/webhooks/meta` | `X-Hub-Signature-256` HMAC over the raw body using `META_APP_SECRET`. Unsigned or mismatched requests are `401`. |
| POST | `/public/webhooks/google` | Shared `google_key` compared with `GOOGLE_LEAD_FORM_KEY` in constant time. |

## Lead capture behaviour

1. A delivery is recorded in `webhook_receipts`; replays are ignored.
2. For Meta, the lead is fetched from the Graph API using the connection token. If no
   token exists yet, the submission is stored with `status='received'` and an error
   explaining the missing credential — nothing is fabricated.
3. Fields are normalised: `name`, `email`, `phone`, `company`, `title`, `message`.
4. An existing tenant lead with the same email or phone is reused instead of duplicated;
   missing fields are filled in.
5. An `attribution_touchpoints` row records channel, campaign id, UTM values, landing page
   and referrer.
6. Website forms require consent when `requires_consent` is set, require an email or phone,
   and silently discard honeypot hits.

## Attribution

`attribution_model` is reported as **last-touch lead source** and the API returns this caveat
verbatim with every report:

> Campaign attribution links each captured lead to the campaign that produced it. It shows
> correlation between spend and revenue, not proof that the campaign caused the sale.

CRM links come from real rows: `lead.qualification_status` for qualified leads,
`crm_opportunities.lead_id` for opportunities, and `status='won'` for revenue. When a campaign
has no captured leads the funnel columns stay zero rather than being estimated.

## Security

- Organization isolation is enforced in every query (`organization_id` on the row being read).
- Tokens are encrypted at rest with the same Fernet helper used for Google/Microsoft/Zoho
  tokens; `serialize_connection` exposes only `has_credentials`.
- Webhook signatures are verified against the raw request body; a missing
  `META_APP_SECRET` means webhooks are rejected rather than trusted.
- Provider calls are read-only; there is no code path that can change spend.
- Kill switches: `ADVERTISING_ENABLED=false` disables connectors and public capture,
  `ADVERTISING_SYNC_ENABLED=false` disables outbound provider calls.
- Connection writes, syncs, disconnects, campaign ingestion and form creation are audited.

## Configuration

```dotenv
ADVERTISING_ENABLED=true
ADVERTISING_SYNC_ENABLED=true
META_APP_ID=
META_APP_SECRET=
META_WEBHOOK_VERIFY_TOKEN=
META_GRAPH_VERSION=v21.0
GOOGLE_ADS_CLIENT_ID=
GOOGLE_ADS_CLIENT_SECRET=
GOOGLE_ADS_DEVELOPER_TOKEN=
GOOGLE_ADS_LOGIN_CUSTOMER_ID=
GOOGLE_ADS_API_VERSION=v19
GOOGLE_LEAD_FORM_KEY=
```

## Live validation procedure (manual)

Automated tests use SQLite and never call a provider. A live check requires:

1. **Meta**: an app with Marketing API access, a system-user token with `ads_read` and
   `leads_retrieval`, and a leadgen webhook subscription pointing at
   `POST /public/webhooks/meta` with the verify token above. Run
   `POST /advertising/connections/{id}/sync` and confirm campaigns appear with provider
   spend. Submit a real lead-ad form, confirm one `lead_capture_submissions` row and one
   CRM lead. Replay the delivery and confirm the row is not duplicated.
2. **Google**: an approved developer token, an OAuth access token, and a lead form asset.
   Sync campaigns, then submit the lead form and confirm the delivery arrives with
   `google_key` and creates a single lead.
3. Do not execute live tests against paid traffic without an explicit budget decision; no
   automated test spends money.

## Known limitations

- Meta lead fetches need a page/user token; if the connection is revoked, pending
  submissions stay `received` until an operator reconnects and calls
  `POST /advertising/submissions/{id}/process`.
- Google Ads reporting uses one `googleAds:search` call for campaign metrics; keyword and
  ad-group reports are not implemented.
- Provider-side token revocation is not automated: `DELETE /advertising/connections/{id}`
  destroys the local credential only.
- Public form submissions are protected by consent and a honeypot, not by CAPTCHA or
  IP rate limiting.
- Only website forms are embeddable; there is no landing-page builder yet.
