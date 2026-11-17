# Multi-product platform: repository audit and implementation map

Date: 17 November 2026.

Status: **historical audit.** The multi-product implementation has since landed: migrations `0011_products` and `0012_product_attribution`, product CRUD and scoped APIs, product workspaces, templates, attachments, product opportunity analysis and product/global overviews. See [multi-product architecture](multi-product-architecture.md), [product API](product-api.md) and [migration and deployment](product-migration-and-deployment.md). The baseline-gate narrative below records the state at audit time and is not the current status.

This plan follows the supplied 906-line master specification. It is an incremental extension of the existing modular monolith, not a second application. Proposed tables, paths and endpoints below are an implementation map, not currently available features.

## 1. Baseline evidence

| Check | Result in this audit |
| --- | --- |
| Backend full regression | Incomplete. `pytest -q` emitted 12 completion dots, then made no further progress and was stopped. No final pass/fail summary was produced. |
| First stalled test diagnostic | `test_company_intelligence.py::test_submission_reuse_disabled_and_domain_mismatch`, bounded with `faulthandler.dump_traceback_later(40, exit=True)`, timed out during fixture setup. |
| Diagnostic location | Fixture line 71, entering Starlette `TestClient`; AnyIO blocking portal waits while Windows asyncio Proactor initialization is blocked in `socket.accept` for its self-pipe. The test body was not reached. A subsequent isolated loopback probe returned `10013 / WSAEACCES`; see exact blockers below. |
| Frontend type-check | `npm run typecheck`: passed. |
| Frontend production build | `npm run build`: passed; Next.js 15.5.29. Existing multiple-lockfile/workspace-root and experimental proxy-agent warnings were observed. |
| Existing browser regression | `npm test -- --reporter=line`: **6 passed (53.3 seconds)**, using the existing mocked API fixtures and task-owned loopback server. |
| Docker CLI | Installed, version 29.9.3; its availability probe reported access denied while reading Docker configuration. No permission-changing workaround or alternate configuration was attempted. |
| Docker services, live database revision/counts | Not verified in this audit because Docker access is unresolved. |
| Schema revision in source | Single migration chain ends at `0010_company_intelligence`. This is not a fresh observation of the running PostgreSQL revision. |
| Backup or live migration | Not performed. Existing named volumes were not modified. |
| Live external integrations | None exercised by this audit. Previous live-provider results remain historical evidence only. |
| Credentials/configuration | Private `.env` was not read or modified. No credentials were requested, printed or changed. |

The backend diagnostic is an infrastructure/setup timeout, not an observed assertion failure and not evidence that the new product design works. Frontend/browser success does not resolve it. Per the requested phase gates, implementation must wait for a reproducible backend baseline and the remaining runtime audit.

### Baseline-only permission diagnosis

The operator explicitly requested resolution of baseline prerequisites before any application/schema change. Additional read-only checks established:

- Interpreter: workspace `.venv\Scripts\python.exe`, Python **3.14.10**.
- Asyncio policy: `asyncio.windows_events._WindowsProactorEventLoopPolicy`.
- Windows `socket.socketpair` uses the standard-library TCP fallback: bind an ephemeral loopback listener, connect a local client, then accept. This explains why `TestClient` setup needs a permitted local connection even though provider calls are mocked.
- Standalone `socket.socketpair()` with a three-second socket timeout returned `TimeoutError`.
- A minimal ordinary TCP loopback self-connection bound `127.0.0.1:53436` and returned **Winsock 10013, `WSAEACCES`**, from `connect_ex`. No accept was attempted after the denial. The port is an observation of an ephemeral allocation, not a fixed port to configure.
- No alternate socket implementation, event-loop change, permission change, elevation or denied-network workaround was attempted.
- `DOCKER_CONFIG`, `DOCKER_HOST` and `DOCKER_CONTEXT` are absent in the current process. The default configuration resolves to `C:\Users\SI1107\.docker\config.json`; the path was resolved, not opened. The earlier probe reported a configuration access-denied warning, but its exact original warning text was not retained. Docker was not retried against that denied path.
- Docker Desktop/engine connectivity, current containers, actual database revision/counts and a backup remain unverified. It would be inaccurate to say those checks passed or that the engine itself returned a particular pipe error.

**Required manual action:** update the sandbox policy to permit the workspace Python process to connect to its own IPv4 loopback listener on ephemeral local ports, and to permit Docker CLI read access to the user's Docker configuration directory plus access to the active local Docker engine endpoint. Ensure Docker Desktop is running. Do not print Docker credentials/configuration contents. No PowerShell elevation or filesystem ACL command is an appropriate substitute for updating the sandbox policy.

After the operator confirms the policy update, retry socketpair once, then the backend baseline, read-only Docker connectivity/service inspection and read-only database revision/count/integrity inspection. Stop on any new denial and report that exact path/endpoint. No application/schema implementation is authorized past the gate until these checks actually pass.

### Baseline commands

From `backend`:

```powershell
& ..\.venv\Scripts\python.exe -m pytest -q
```

From `frontend`, with the existing Node.js installation on the current process PATH:

```powershell
npm run typecheck
npm run build
npm test -- --reporter=line
```

No dependencies were installed during this audit. No application server was left running by the browser tests.

## 2. Inspected structure and integration points

- `backend/app/models.py`: all 18 existing application models.
- `backend/app/company_intelligence/models.py`: all 10 research models.
- `backend/migrations/versions/`: revision chain, additions and current head; `migrations/env.py`: shared metadata registration.
- `backend/app/main.py`: import, lead/profile, contact and Apollo API contracts, local-origin middleware and router mounting.
- `backend/app/imports.py`: workbook limits, worksheet mapping, duplicate checks, row provenance and serialized import processing.
- `backend/app/followup_api.py`: campaigns, atomic enrollments, drafts, exact-content approval, activation, generation, tracking changes and reply/task operations.
- `backend/app/mailer.py`, `mailbox.py`, `reply_actions.py`, `tasks.py`: send claims, inbox synchronization, global suppressions/reply stops, SMTP outcomes and background execution.
- `backend/app/company_intelligence/`: API/model/orchestrator/budget relationships; current source adapters and browser fallback.
- `backend/app/bedrock.py`: shared Converse client, explicit profile discovery, usage result and request overrides.
- `backend/app/microsoft_graph.py`, `google_workspace.py`: route inventory and existing availability-only calendar boundary.
- `frontend/app`, `components`, `lib`, `tests`: existing dashboard reuse, shared shell, Lead 360, outreach/research components, loaded-record metrics and six mocked browser flows.
- `docker-compose.yml`, backend/frontend Dockerfiles, package manifests and Playwright runner: process/volume/build layout.

Generated dependencies, caches and build outputs are not application architecture to duplicate or migrate.

### Existing migration chain

```text
0001
 -> 08704140955b
 -> 0003_sales_tasks
 -> 0004_google_oauth
 -> 0005_google_booking_scope
 -> 0006_multisheet_import
 -> 0007_apollo_contact_management
 -> 0008_enrollment_contact_link
 -> 0009_microsoft_oauth
 -> 0010_company_intelligence
```

New revisions must follow this head. Do not edit historical migrations to retrofit product ownership.

## 3. Current relationships and compatibility risks

| Existing records | Observed relationship | Required treatment |
| --- | --- | --- |
| `leads` | Master company-like record; indexed normalized `company_key`, not a unique company identity constraint | Preserve every ID and existing record. Add product membership rather than copying companies. Do not silently merge existing possible duplicates. |
| `contacts`, `apollo_search_results` | Owned by `lead_id`; search/contact verification states already persisted | Reuse for all products associated with that company. No separate product-contact table is necessary unless a future workflow adds independently selected product contacts. |
| `batches`, `import_rows` | Batch owns original workbook/mapping; rows retain worksheet, row number, original values and lead references | Add batch product attribution; preserve parser/limits/provenance and duplicate reporting. |
| `campaigns`, `enrollments` | Campaign owns recipient enrollments; enrollment references lead and optional contact | Add campaign product ownership; validate each enrollment's company membership and contact ownership before any writes. Derive email/thread scope through campaign. |
| `email_messages`, `email_events`, `email_replies`, `tracking_links` | Persisted per-enrollment thread and send/reply/event history | Preserve IDs, Message-ID, tokens, approvals, schedules, outcome reconciliation and history. Never recreate these records during attribution. |
| `suppressions`, `mailbox_state` | Global mailbox/recipient safety state | Keep global. A product switch must not evade suppression, reply-stop or mailbox controls. |
| `sales_tasks` | Meeting-request task references a reply, then its enrollment/campaign | Derive product through this chain. These are not scheduled meetings. |
| Google/Microsoft OAuth tables | Existing encrypted organizer credentials and expiring OAuth state | Leave unchanged and global to the current single-organizer integration. Do not infer meetings or product ownership from a login. |
| Research profiles/jobs/sources/facts/citations/reports | Company-scoped; profile has unique domain and optional unique lead; job-source associations preserve snapshots | Reuse once across products. Product opportunity/review records reference the existing immutable evidence rather than duplicating it. Standalone profiles without a lead require explicit linkage before product selection. |
| `research_usage`, `research_budgets` | Per-job usage and atomic UTC-day job/call/source-byte budgets | Preserve the shared limits; product analysis must not create an unmetered alternate Bedrock path. |

### Important observed gaps

1. Existing import duplicate detection matches email, then normalized company name; it does not establish a globally unique company domain. A possible duplicate is not permission to merge conflicting companies or assign a product based on industry/name.
2. Current Lead 360 aggregates all campaigns for a company. Reusing its existing unscoped payload inside a product workspace would leak another product's threads.
3. Current outreach UI requests all campaigns, leads, unmatched replies and tasks. A product selector alone cannot isolate it.
4. Current dashboard metrics count bounded loaded records. Product/global dashboards need server aggregates and explicit distinct-company versus association counts.
5. Current CORS methods list GET/POST/PUT only. Product PATCH/DELETE and attachment operations require directly related method updates while preserving loopback origins.
6. Existing approval compares subject/body. Rich HTML and attachments must become part of the exact reviewed content; otherwise an attachment could change after approval.
7. Research already has an opt-in bounded Playwright fallback. The supplied specification's static-only baseline is older than the current source; do not build a second renderer.
8. Research has no verified external-search/RSS/registry adapter, selected-category refresh, accepted-update comparison or manual-override workflow.
9. Research profiles are shared evidence, but product relevance/pain points are not established facts. Opportunity hypotheses must remain separately labeled.
10. The app is unauthenticated. Product-scoped checks provide workflow consistency, not tenant authorization. Intentional global management APIs remain globally accessible to local users; this must not be marketed as a secure multi-tenant boundary.
11. `SESSION_CONTEXT.md` at the repository root is historical. The maintained [project context](session-context.md) records later deployment/research milestones; runtime state still needs fresh verification.

## 4. Target ownership model

```text
Product
  -> ProductLead -> existing Lead
                    -> shared Contacts / Apollo results
                    -> shared CompanyResearchProfile
                         -> existing Jobs / Sources / Facts / Citations / Reports
  -> Campaign -> existing Enrollment -> existing EmailMessage / Reply / Event
  -> product templates / global-template overrides / signature

ProductLead
  -> versioned ProductOpportunity -> existing research job + selected fact references
  -> product-specific research selections/reviews
```

The initial catalog contains Vehicle Digital Inspection, Loss Tracker, Aftermarket Super App and clearly labeled General / Unassigned. Seed names, stable slugs/IDs and neutral administrative descriptions only; product capabilities, use cases and value propositions must be supplied/reviewed rather than invented.

Archive products instead of deleting historical ownership. Removing a company association must not cascade-delete its campaigns, contacts or evidence; preserve historical attribution and reject changes that would leave active workflows inconsistent.

## 5. Additive database map

Exact migration filenames and constraints must be finalized during milestone B after the baseline gate. Proposed first revision: `0011_products`, down-revision `0010_company_intelligence`; it does not yet exist.

### Existing tables to extend

- `batches`: product foreign key/index for existing import execution.
- `campaigns`: product foreign key/index; the campaign is the authoritative sales-thread owner.
- `email_messages`, in later template/editor milestones: immutable template-version/generation-context references, sanitized HTML and approval snapshot/digest covering all sendable content.
- Additional research job metadata only where required for selected-category refresh, parent-version comparison or bounded recovery; do not replace existing IDs or job-source snapshots.

### New tables

| Milestone | Proposed tables | Constraints/purpose |
| --- | --- | --- |
| B | `products`, `product_leads` | Unique product slug; unique `(product_id, lead_id)`; product context/stage/priority/status/notes independent of master company. |
| F | `email_templates`, `email_template_versions` | Global/product ownership, immutable versions, parent global-template reference; product override never modifies its parent. |
| G/H | Generation provenance/snapshot table if message-level references cannot preserve complete context | Pin product/company/contact, exact template version, selected evidence and sender context without logging unnecessary message bodies. |
| I | Private attachment metadata and message-attachment associations | Immutable storage key/hash/size/type; no public paths; lifecycle and approval binding. |
| J | `product_opportunities`, opportunity-to-fact references | Versioned product-lead analysis referencing existing research job/facts, confidence/missing information and explicit hypotheses. |
| J | Research update reviews/selections and manual-override records | Append-only accept/reject/override with reason/time and references to original evidence; never mutate source-reported facts. |

Do not create a second company, contact, research-fact, citation, OAuth or actual-meeting subsystem.

### Legacy attribution algorithm

1. Create General / Unassigned and initial named products using stable IDs.
2. Associate every legacy master company with General / Unassigned when no deterministic product ownership exists.
3. Attribute existing campaigns/batches to General / Unassigned; retain their IDs and all children exactly.
4. Do not inspect campaign prose, company name or industry to guess ownership.
5. Do not reassign existing research snapshots or duplicate shared contacts.
6. Add constraints/indexes after the deterministic backfill; verify references and row counts.
7. Test a seeded upgrade from 0010, including contacts/search states, paused campaign, enrollments, approved/unknown/sent messages, replies/events/tracking/suppression, OAuth rows and a complete research graph.
8. Run fresh upgrade, `alembic check`, constraint/FK checks and a non-destructive rollback rehearsal on disposable databases.

## 6. API and server-isolation map

Planned product routes:

- `GET/POST /products`; `GET/PUT /products/{product_id}`; `PATCH /products/{product_id}/status`.
- `GET/POST /products/{product_id}/leads`; `PUT/DELETE /products/{product_id}/leads/{lead_id}`.
- Product-scoped batch upload/list/preview/start/retry/report routes, reusing current workbook/parser/task code.
- Product-scoped company/profile/contact/Apollo routes; validate membership before returning shared company data or calling paid enrichment.
- Product-scoped campaigns, enrollments, message/reply operations, analytics and sales tasks.
- Product/global overview APIs with bounded date filters, explicit denominators and no join-multiplication.
- Global/product template routes, immutable version reads, override creation and validated preview.
- Product-lead opportunity/research-selection routes that validate both company evidence ownership and product membership.
- Product-scoped private attachment upload/read/remove operations, without exposing storage keys.

Existing API families to extend/reuse:

- `/batches*`, `/leads*` in `main.py`.
- `/campaigns*`, `/messages*`, `/enrollments*`, `/replies*`, `/sales-tasks*` in `followup_api.py`.
- `/intelligence*` for shared company evidence; product wrappers validate membership before resolving any ID.
- Existing Bedrock status/profile discovery and single Converse helper.
- Existing SMTP/IMAP/public unsubscribe/tracking behavior remains the sending system.

A single product-scope helper must resolve product, membership and campaign/enrollment/message/reply ancestry. Apply it on detail, mutation and bulk paths, not just list queries. Do not implement product scoping by fetching all data and filtering it in React. Return an explicit 404/409 according to the existing API pattern for wrong-product/invalid-state records.

Keep the global management entry point explicit. Do not claim that URL scoping substitutes for authentication or roles.

## 7. File-level implementation map

| Area | Existing files to modify | Planned new files |
| --- | --- | --- |
| Product schema/API | `backend/app/models.py`, `main.py`, `migrations/env.py` | `backend/app/products.py`, additive migrations, `backend/tests/test_products.py` |
| Scoped import | `backend/app/imports.py`, `main.py`, `tasks.py`, `backend/tests/test_imports.py` | Reuse existing import functions; do not add another workbook parser |
| Dynamic shell/workspaces | `frontend/components/app-shell.tsx`, `frontend/app/layout.tsx`, `app/page.tsx`, `app/style.css`, shared workspaces | `frontend/lib/products.ts`, product context/selector/workspace components, data-driven `/products/[id]/...` routes |
| Product/global aggregates | `workspace-overview.tsx`, root/shared dashboard, scoped backend routes | Shared overview API/query helper and dashboard component as needed |
| Hybrid templates | `followup_api.py`, outreach workspace, related models | `backend/app/email_templates.py`, template editor/library and focused tests |
| Contextual generation | `backend/app/bedrock.py`, `followup_api.py`, research fact picker, outreach workspace | Shared context-resolution helper only if needed across generation/preview; generation provenance tests |
| Campaign isolation | `followup_api.py`, `main.py` Lead 360 profile, `recipient-picker.tsx`, outreach workspace, `reply_actions.py`/task queries where needed | Focused cross-product campaign tests |
| Rich editor/attachments | Models, `mailer.py`, approval/generation API, `config.py`, `docker-compose.yml`, manifests, outreach editor | Private local storage adapter, attachment API/validation, sanitized editor component and attachment/MIME tests |
| Research/opportunities | Existing research API/models/orchestrator/runner/budget/source modules and report UI | Opportunity service/API, provider interface/adapters only for explicitly configured sources, review/comparison UI and tests |
| Documentation/release | `README.md`, maintained session context and related workflow docs | Product architecture, API, migration/deployment/rollback and test-status documentation as milestones actually land |

Keep existing `/` and `/dashboard` as one shared implementation. Extract reusable workspace components instead of copying pages per product. Pass product identity explicitly through request builders/components; reset or key state and abort/ignore late responses when product changes.

## 8. Required behavior by milestone

| Milestone | Deliverable | Exit gate |
| --- | --- | --- |
| A | This audit, baseline evidence and implementation map | Backend baseline reproducible; runtime schema/services verified; no unresolved safety failure. **Currently blocked.** |
| B | Products/memberships, deterministic legacy attribution, additive migrations | Seeded 0010 preservation, unique/FK enforcement, no drift; no live migration before verified backup. |
| C | Product CRUD, scoped company/import APIs and ancestry validation | Product A/B wrong-ID tests, inactive-product/import validation, no duplicate master companies, existing import tests preserved. |
| D | Dynamic selector/create-product UI and shared product navigation | No hardcoded product routes; stale-response/product-switch and responsive browser tests. |
| E | Product/global persisted-data dashboards and date filters | Unique-company/contact counts distinct from product associations; SMTP acceptance is not delivery; denominators documented. |
| F | Global/product/override templates, immutable versions and preview | Parent unchanged; unknown/unavailable variables flagged; exact version retained. |
| G | Product/company/contact/evidence/template/sender context generation | Shared Bedrock client only; per-recipient drafts; wrong-company facts rejected; missing context explicit; never approved automatically. |
| H | Scoped campaigns and bulk recipients | All-or-nothing additions, independent threads, current approval/suppression/reply/inbox/budget/reconciliation gates intact. |
| I | Sanitized rich text, autosave, signatures and private attachments | Attachment/MIME/size/extension/path tests; exact reviewed HTML/files bound to approval; failure before SMTP prevents partial sending. |
| J | Shared research extensions, reviewed comparisons, product opportunities and operational limits | Existing roles/evidence/history preserved; source-adapter restrictions/budgets tested; hypotheses/overrides distinct from facts. |
| K | Full regression, reviewed release and documentation | Backend/type/build/browser/isolation/migration tests pass; backup verified; runtime integrity/readiness checked; incomplete features explicitly listed. |

At each milestone run the relevant backend tests, frontend type-check/build and relevant existing/new browser flows; review schema/scope changes and update the status. Do not advance past a failed migration, evidence-ownership or sending-safety test.

### Specific design safeguards

- Template variables use a finite validated vocabulary, not arbitrary expression evaluation. Product override/global inheritance is version-pinned.
- Store source-supported facts separately from opportunity hypotheses and manual overrides; an override does not become an independently verified claim.
- Recipient personalization uses actual saved name/title/department/seniority only, not inferred job responsibilities.
- Attachment authorization means server-checked local workflow/product scope in this unauthenticated pilot; it is not user/tenant access control.
- Private local/Docker attachment storage needs a named volume, metadata, safe generated keys, content/MIME/extension limits and explicit deletion/retention. Report scanner availability honestly; never claim an unscanned file is malware-free.
- Validate all referenced attachments and bytes before opening SMTP. Reject missing/failed uploads rather than sending without them.
- Product signatures, rendered HTML and attachment changes invalidate exact-content/sequence approvals.
- Source discovery providers remain opt-in with verified endpoints/terms/credentials. Do not invent a search provider, transmit company data to an unapproved provider or make paid discovery calls during mocked regression.
- Preserve research model-profile choice/routing review and shared daily budgets. Configured/listed is not the same as successfully invoked.
- Current Microsoft availability stays informational. Product meeting-request tasks can be attributed through replies/campaigns; no meeting booking or Teams creation is included.

## 9. Deployment and rollback gate

After sandbox/runtime access and baseline are resolved:

1. Read-only service status and actual PostgreSQL revision/counts; inspect active jobs/sending state.
2. Create a new timestamped private PostgreSQL custom-format backup for this migration; verify it with `pg_restore --list`. Do not reuse the older research backup as evidence of the current data state.
3. Review the additive migration and preservation/isolation tests.
4. Apply to a disposable database first; verify FKs, uniqueness and Alembic drift.
5. Perform an approved local rollout with affected API/worker/scheduler/frontend images. Preserve named PostgreSQL/Redis volumes and loopback-only ports.
6. Compare legacy IDs/counts/state before and after; verify API/frontend readiness and synthetic product flows without approving/activating/sending mail.
7. Prefer application rollback with additive schema retained. Do not run a downgrade that drops new product/template/attachment history on the user's database. Any backup restore requires a separately approved maintenance procedure and rollback point.

`docker compose up --build -d` is the existing application start command, but the API service automatically runs `alembic upgrade head`. Once new migrations exist, **do not use this command on the user's data until the backup/review gates pass**. Do not delete volumes or reset PostgreSQL.

## 10. Current stop point

This section is superseded. Implementation status now lives in
[multi-product architecture](multi-product-architecture.md#deliberately-not-implemented) and the README.

Still outstanding from the master specification: rich-text HTML editing with product signatures and
sanitization, S3-compatible attachment storage, meeting booking/Teams lifecycle, and external
search/news/registry research adapters. Product isolation is server-enforced workflow scoping; the
application remains unauthenticated and local-only.
