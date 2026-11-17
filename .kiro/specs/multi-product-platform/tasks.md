# Implementation Plan: Multi-Product Sales Platform

## Overview

Tasks are grouped into milestones B through K. Each task is independently executable by a single subagent. All implementations use Python (FastAPI/SQLAlchemy/Alembic) for backend and TypeScript (Next.js 15 / React 19) for frontend. The existing 113 backend tests must pass after every milestone.

---

## Tasks

### Milestone B — Product Data Model

- [ ] 1. Add SQLAlchemy models for new tables
  - [ ] 1.1 Add `Product`, `ProductLead`, `ProductOpportunity` model classes to `backend/app/models.py`
    - Use `Mapped[]` annotation style consistent with existing models
    - Add `UniqueConstraint("product_id", "lead_id")` to `ProductLead.__table_args__`
    - Add CHECK constraints for all enum-valued columns (status, stage, priority)
    - _Requirements: 1.1, 2.1, 2.2, 3.1_
  - [ ] 1.2 Add `EmailTemplate`, `EmailTemplateVersion`, `EmailAttachment`, `ResearchFactOverride` model classes to `backend/app/models.py`
    - `EmailTemplateVersion` has no `updated_at` (immutable after create)
    - `ResearchFactOverride` has no `updated_at` (append-only)
    - _Requirements: 8.1, 11.3, 12.7_
  - [ ] 1.3 Add nullable `product_id` FK column to `Campaign` model and `Batch` model in `backend/app/models.py`
    - `ForeignKey("products.id")`, nullable=True, no server default
    - _Requirements: 10.1, 4.1_

- [ ] 2. Write migration 0011_products
  - [ ] 2.1 Create `backend/migrations/versions/0011_products.py` with `down_revision = "0010_company_intelligence"`
    - `upgrade()`: CREATE TABLE products, product_leads, product_opportunities, email_templates, email_template_versions, email_attachments, research_fact_overrides; ALTER TABLE campaigns ADD COLUMN product_id UUID; ALTER TABLE batches ADD COLUMN product_id UUID
    - `downgrade()`: DROP the 7 new tables; ALTER TABLE campaigns DROP COLUMN product_id; ALTER TABLE batches DROP COLUMN product_id
    - Use `op.create_table` and `op.add_column`; never use `op.drop_table` on existing tables in `upgrade()`
    - _Requirements: 4.1, 4.6_

- [ ] 3. Write migration 0012_product_attribution
  - [ ] 3.1 Create `backend/migrations/versions/0012_product_attribution.py` with `down_revision = "0011_products"`
    - `upgrade()`: INSERT four product rows with deterministic UUIDs; INSERT one `product_leads` row for every existing `leads` row (stage=prospect, priority=medium, status=active); UPDATE campaigns SET product_id = general_unassigned_id; UPDATE batches SET product_id = general_unassigned_id
    - Use `op.execute()` with parameterized SQL; store the General/Unassigned UUID as a module-level constant
    - `downgrade()`: DELETE seeded product_leads; UPDATE campaigns/batches SET product_id = NULL; DELETE seeded products
    - _Requirements: 4.2, 4.3, 4.4, 4.5, 4.7_

- [ ] 4. Write migration tests
  - [ ]* 4.1 Create `backend/tests/test_migrations.py`
    - Use Alembic `MigrationContext` with SQLite in-process
    - Seed leads (IDs 1–55), 1 campaign, 4 batches, 2 contacts, 4 suppressions at revision 0010
    - Apply 0011 then 0012; assert all original IDs preserved; assert 55 `product_leads` rows created; assert campaigns.product_id is set
    - _Requirements: 4.7, 4.8, 13.1_

- [ ] 5. Checkpoint — existing 113 tests still pass
  - Run `pytest backend/tests/ -x --tb=short`; resolve any import or model conflicts before proceeding.

---

### Milestone C — Product Backend APIs

- [ ] 6. Create `backend/app/products.py` router — product CRUD
  - [ ] 6.1 Implement `GET /products` and `POST /products`
    - GET: return all products ordered by name; accept optional `?status=` filter
    - POST: validate slug format with `^[a-z0-9][a-z0-9\-]*[a-z0-9]$`; return 409 on duplicate slug; set created_at and updated_at
    - _Requirements: 1.1, 1.2, 1.8_
  - [ ] 6.2 Implement `GET /products/{id}`, `PUT /products/{id}`, `PATCH /products/{id}/status`, and block `DELETE /products/{id}`
    - PUT: return 422 if the slug field in the body differs from the stored slug
    - PATCH: accept only `{"status": "active"}` or `{"status": "archived"}`; return 422 for any other value
    - DELETE handler: return 405 Method Not Allowed
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 1.9_
  - [ ] 6.3 Implement `GET /products/{id}/leads`, `POST /products/{id}/leads`, `PUT /products/{id}/leads/{lead_id}`, `DELETE /products/{id}/leads/{lead_id}`
    - POST: return 409 if (product_id, lead_id) already exists; validate stage/priority/status enums
    - DELETE: remove ProductLead row only; verify Lead and Contact rows remain after deletion
    - GET: support `?stage=`, `?priority=`, `?status=` filter query params
    - _Requirements: 2.1–2.8_
  - [ ] 6.4 Implement `POST /products/{id}/batches` (product-scoped import)
    - Validate product is active; return 422 if archived
    - After batch import completes, for each Lead: check if ProductLead exists; if not, create it; if yes, return existing id in `product_lead_id` response field
    - Delegate all Lead-level create/update logic to existing `imports.py` functions
    - _Requirements: 5.3, 5.4, 5.7_

- [ ] 7. Update CORS and mount routers in `main.py`
  - [ ] 7.1 Add PATCH and DELETE to `allow_methods` in `CORSMiddleware`; mount `products_router` from `products.py`
    - _Requirements: 5.6_

- [ ] 8. Modify `imports.py` for product-scoped import
  - [ ] 8.1 Add optional `product_id: str | None` parameter to `process_batch()`
    - After each Lead upsert, if `product_id` provided: check for existing `ProductLead`; create if absent; return `product_lead_id` in row result
    - Do not alter any existing Lead-level logic
    - _Requirements: 5.3, 5.4_

- [ ] 9. Modify `followup_api.py` for product-scoped campaigns
  - [ ] 9.1 Accept `product_id` in `POST /campaigns` body; store on Campaign row
    - _Requirements: 10.2_
  - [ ] 9.2 Add enrollment validation: before enrolling a contact, assert the contact's Lead has a ProductLead association to the campaign's product; return 422 if not
    - _Requirements: 10.3, 10.5_

- [ ] 10. Write product and campaign API tests
  - [ ]* 10.1 Create `backend/tests/test_products.py`
    - Use Hypothesis: `@given(slug_strategy)` where slug_strategy generates strings failing the slug regex; assert all rejected with 422 (**Property 2: Slug format enforcement**)
    - Use Hypothesis: `@given(lead_id_strategy)` create association twice; assert 409 (**Property 3: Product-lead uniqueness**)
    - Example test: create Lead + ProductLead, delete association, assert Lead row present (**Property 4: Association deletion preserves master records**)
    - Cover: product CRUD happy paths, slug immutability, status transitions, 405 on DELETE product, archived product returns 422
    - _Requirements: 1.1–1.9, 2.1–2.8, 13.2, 13.3_
  - [ ]* 10.2 Extend `backend/tests/test_followups.py` with product-scoped paths
    - Test campaign created with product_id stored; enrollment rejected when ProductLead absent; enrollment accepted when ProductLead present
    - _Requirements: 10.2, 10.3, 13.6_

- [ ] 11. Checkpoint — existing 113 tests + new Milestone C tests pass
  - Run `pytest backend/tests/ -x --tb=short`

---

### Milestone D — Dynamic Frontend Navigation

- [ ] 12. Create product context and API client
  - [ ] 12.1 Create `frontend/lib/products.ts` with `Product` and `ProductLead` TypeScript interfaces, `fetchProducts()` and `fetchProduct(slug)` API functions, and `useProducts()` React hook
    - Hook provides `{ products, loading, error }`; caches result for the session
    - _Requirements: 6.1_

- [ ] 13. Create product selector component
  - [ ] 13.1 Create `frontend/components/product-selector.tsx`
    - Load from `useProducts()`; render active products only plus "Add product" link
    - On API error: render error state with retry button (no full page reload)
    - Use DENSO design tokens from `style.css`
    - _Requirements: 6.2, 6.8_

- [ ] 14. Create product workspace shell
  - [ ] 14.1 Create `frontend/components/product-workspace.tsx`
    - Accept `productSlug: string` and `section: string` props
    - Render sub-nav: Overview, Companies, Import, Research, Contacts, Lead 360, Campaigns, Templates, Meetings, Analytics
    - Render breadcrumb: `DENSO / {Product Name} / {Section}`
    - On product switch: cancel in-flight requests via `AbortController`; clear product-scoped React state
    - _Requirements: 6.3, 6.4, 6.5, 6.6_

- [ ] 15. Create product workspace pages
  - [ ] 15.1 Create `frontend/app/products/[slug]/page.tsx`, `companies/page.tsx`, `import/page.tsx`, `research/page.tsx`, `contacts/page.tsx`, `campaigns/page.tsx`, `templates/page.tsx`, `meetings/page.tsx`, `analytics/page.tsx`
    - Each page wraps content in `<ProductWorkspace>` with its section name; no product name hardcoded in routes
    - _Requirements: 6.3, 6.6_
  - [ ] 15.2 Create `frontend/app/products/[slug]/lead360/[leadId]/page.tsx` for Lead 360 view
    - _Requirements: 6.3_

- [ ] 16. Update `app-shell.tsx` and global layout
  - [ ] 16.1 Add `<ProductSelector>` to the top bar in `frontend/components/app-shell.tsx`
    - Existing sidebar global nav (Dashboard, Intelligence, Outreach, Calendar) remains unchanged
    - Global Overview link remains in sidebar
    - _Requirements: 6.7_

- [ ] 17. Add CSS for new components
  - [ ] 17.1 Extend `frontend/app/style.css` with styles for: product-selector dropdown, breadcrumbs, workspace sub-nav active state, product-switching loading indicator
    - Follow existing DENSO design tokens: `#d20f32`, `#fff`, `#f6f7fa`, `#e8eaf0`
    - _Requirements: 6.3, 6.5_

---

### Milestone E — Dashboards

- [ ] 18. Product overview API
  - [ ] 18.1 Implement `GET /products/{id}/overview` in `backend/app/products.py`
    - Return: associated_companies_count, active_contacts_count, research_jobs_by_status (dict), campaigns_count, messages_by_status (dict), replies_count, meeting_tasks_count
    - Accept optional `?start_date=` and `?end_date=` ISO-8601 query params
    - All counts from live DB queries; never return hardcoded values
    - _Requirements: 7.1, 7.5, 7.6_

- [ ] 19. Global overview API
  - [ ] 19.1 Implement `GET /overview` in `backend/app/products.py`
    - Return: unique_companies (COUNT DISTINCT lead_id across product_leads), unique_contacts (deduplicated by lead_id), total_campaigns, total_messages, total_replies, per_product_pipeline array
    - Deduplicate: a Lead in 3 products counts as 1 unique company
    - Accept same date-range query params
    - _Requirements: 7.2, 7.3, 7.4, 7.5, 7.7_

- [ ] 20. Product overview frontend page
  - [ ] 20.1 Implement `frontend/app/products/[slug]/page.tsx` to call `GET /products/{id}/overview` and render metric cards
    - Date range selector buttons: "7 days", "30 days", "90 days", and custom date picker
    - Use DENSO card and status-pill CSS patterns
    - _Requirements: 7.1, 7.4_

- [ ] 21. Global overview frontend component
  - [ ] 21.1 Create `frontend/components/global-overview.tsx` calling `GET /overview`
    - Render per-product pipeline rows + global totals; date-range filter
    - Integrate into `frontend/app/page.tsx` as the default view when no product is selected
    - _Requirements: 7.2, 7.3, 7.4_

---

### Milestone F — Templates

- [ ] 22. Create `backend/app/email_templates.py` router
  - [ ] 22.1 Implement `GET /templates`, `POST /templates`, `GET /templates/{id}`, `PUT /templates/{id}`, `PATCH /templates/{id}/status`
    - POST/PUT: call `validate_variables(subject, body)`; if unknown vars found, return 422 with `{"unknown_variables": [...]}` and do NOT persist
    - POST: set version = 1; create an `EmailTemplateVersion` record immediately
    - `product_id = null` means global template
    - Define `ALLOWED_TEMPLATE_VARIABLES` frozenset and `validate_variables()` in this module
    - _Requirements: 8.1–8.3, 8.6, 8.7, 8.10_
  - [ ] 22.2 Implement template versioning on `PUT /templates/{id}`
    - Increment `email_templates.version`; INSERT new `EmailTemplateVersion` with the new version number
    - Previous versions remain immutable in `email_template_versions`
    - _Requirements: 8.5, 8.9_
  - [ ] 22.3 Implement product override creation
    - When `POST /templates` includes `parent_template_id`: create new template with requesting product's `product_id`; leave parent template row unmodified
    - _Requirements: 8.4_
  - [ ] 22.4 Implement `POST /templates/{id}/preview`
    - Resolve all `{{variable}}` placeholders with sample data (defined sample dict in module)
    - Return `{"subject": "...", "body": "..."}` rendered HTML
    - _Requirements: 8.8_

- [ ] 23. Write template tests
  - [ ]* 23.1 Create `backend/tests/test_templates.py`
    - Use Hypothesis: `@given(st.integers(min_value=2, max_value=20))` save N times; assert version numbers are 1..N with no gaps (**Property 7: Template version monotonicity**)
    - Use Hypothesis: `@given(variable_name_strategy)` where strategy generates names not in ALLOWED_TEMPLATE_VARIABLES; assert all rejected with 422 (**Property 8: Template variable allowlist enforcement**)
    - Cover: global template creation, product-scoped template, override without parent mutation, version history retrieval, preview endpoint
    - _Requirements: 8.1–8.10, 13.4_

- [ ] 24. Template editor frontend
  - [ ] 24.1 Create `frontend/app/products/[slug]/templates/page.tsx` with template list and "New Template" button
    - List shows name, type, version, is_active status, global vs. product badge
    - _Requirements: 8.1_
  - [ ] 24.2 Create template editor component with variable validation feedback
    - Highlight unknown `{{variables}}` in red inline as the user types
    - "Preview" button calls `POST /templates/{id}/preview` and renders result in modal
    - Save button disabled when unknown variables present
    - _Requirements: 8.6, 8.7, 8.8_

---

### Milestone G — Contextual AI Generation

- [ ] 25. Extend `backend/app/bedrock.py` with product and template context
  - [ ] 25.1 Define `GenerationContext` dataclass in `bedrock.py`
    - Fields: product, lead, contact, template, template_version (int), research_facts (list), opportunity (optional), sender_name, sender_signature, missing_context (list[str])
    - _Requirements: 9.1_
  - [ ] 25.2 Implement `resolve_generation_context(product_id, lead_id, contact_id, template_id, db)` function
    - Collect: product row, lead row, contact row, template at pinned version, reviewed ResearchFacts for that lead's company only, approved ProductOpportunity if exists
    - For each missing optional field, append its name to `missing_context`; do NOT raise for missing optional fields
    - Assert all fact IDs belong to the same company; raise ValueError (→ 422) if any cross-company fact found
    - _Requirements: 9.1, 9.3, 9.4, 9.8_
  - [ ] 25.3 Modify `generate_email_draft()` to accept `GenerationContext`
    - Build Bedrock prompt using resolved context fields
    - Pin `template_id` and `version` on the created EmailMessage draft
    - Set draft status = `draft` unconditionally; never set to any other status
    - Add `requires_user_review: bool` field to response when inference profile needs cross-region routing
    - _Requirements: 9.2, 9.5, 9.6, 9.7_

- [ ] 26. Write generation tests
  - [ ]* 26.1 Create `backend/tests/test_bedrock_generation.py`
    - Mock Bedrock Converse client throughout
    - Use Hypothesis: `@given(context_strategy)` assert generated draft always has status=`draft` (**Property 5: Opportunity draft invariant**)
    - Use Hypothesis: `@given(fact_id_strategy)` where fact belongs to different lead; assert 422 (**Property 6: Cross-company fact rejection**)
    - Cover: missing_context populated correctly, template version pinned, single draft per recipient
    - _Requirements: 9.1–9.8, 13.5_

---

### Milestone H — Product Campaigns

- [ ] 27. Product campaign UI
  - [ ] 27.1 Implement `frontend/app/products/[slug]/campaigns/page.tsx`
    - Campaign creation form pre-fills product context from workspace slug
    - Recipient selection shows only contacts whose Lead has a ProductLead for this product
    - _Requirements: 10.3, 10.4_

- [ ] 28. Checkpoint — all backend campaign tests pass
  - Run `pytest backend/tests/test_followups.py -x --tb=short`

---

### Milestone I — Rich Text Editor and Attachments

- [ ] 29. Create storage adapter
  - [ ] 29.1 Create `backend/app/storage.py` with `StorageAdapter` ABC and `LocalStorageAdapter`
    - `LocalStorageAdapter.store()`: write bytes to `/app/attachments/{key}` using atomic rename via temp file; raise `StorageQuotaExceeded` if volume full
    - `LocalStorageAdapter.retrieve()`: raise `StorageKeyNotFound` if path missing
    - `LocalStorageAdapter.delete()`: silently succeed if file not found (idempotent)
    - Inject via FastAPI `Depends()` so future S3 adapter requires no route changes
    - _Requirements: 11.3_

- [ ] 30. Create `backend/app/attachments.py` router
  - [ ] 30.1 Implement `POST /messages/{message_id}/attachments` upload endpoint
    - Validate: size ≤ 10 MB per file; cumulative total ≤ 25 MB; content_type in allowed set (PDF, DOCX, XLSX, PNG, JPG, GIF, WEBP); extension in whitelist
    - On validation failure: return 422; do NOT create attachment record with status=`complete`
    - On success: set upload_status = `complete`; store via `StorageAdapter.store()`
    - _Requirements: 11.3, 11.4, 11.8_
  - [ ] 30.2 Implement `GET /messages/{message_id}/attachments/{att_id}` download endpoint
    - Retrieve bytes from StorageAdapter; return as `FileResponse` with correct content-type header
    - Return 404 if attachment not found or if storage key missing
    - _Requirements: 11.7_
  - [ ] 30.3 Implement `DELETE /messages/{message_id}/attachments/{att_id}`
    - Delete storage file via `StorageAdapter.delete()`; delete DB row; return 204
    - If message was approved, reset message status to `draft`
    - _Requirements: 11.6_
  - [ ] 30.4 Add send-blocking check to existing send flow in `followup_api.py`
    - Before SMTP dispatch, query attachments for this message; if any have upload_status ≠ `complete`, return 422
    - _Requirements: 11.5_

- [ ] 31. Write attachment tests
  - [ ]* 31.1 Create `backend/tests/test_attachments.py`
    - Use Hypothesis: `@given(size_strategy, mime_strategy)` generating out-of-spec values; assert all rejected (**Property 9: Attachment size and type constraints**)
    - Use Hypothesis: `@given(message_strategy)` set approved, modify body or attachment, assert status=`draft` (**Property 10: Approval invalidation on content change**)
    - Cover: valid upload, invalid extension, oversized, MIME mismatch, send blocking, download authorization
    - _Requirements: 11.1–11.9, 13.7_

- [ ] 32. Rich text editor frontend component
  - [ ] 32.1 Create `frontend/components/rich-text-editor.tsx`
    - Use `contentEditable` with `document.execCommand` or equivalent; no external component library
    - Support: bold, italic, underline, ordered list, unordered list, hyperlink insertion
    - Autosave: debounce 2 s after last keystroke; call `PUT /messages/{id}` with sanitized HTML
    - _Requirements: 11.1, 11.9_
  - [ ] 32.2 Create `frontend/components/attachment-upload.tsx`
    - File picker with drag-and-drop; show per-file upload progress
    - Display error inline when file rejected (size, type)
    - Show cumulative total vs. 25 MB limit
    - _Requirements: 11.4_

- [ ] 33. HTML sanitization utility
  - [ ] 33.1 Create `sanitize_html(html: str) -> str` in `backend/app/html_utils.py`
    - Strip `<script>`, `<iframe>`, all `on*` event handler attributes using `bleach` library
    - Add `bleach` to `backend/requirements.txt` if not already present
    - Apply in template save, message draft save, and rich-text autosave endpoints
    - _Requirements: 11.2_

---

### Milestone J — Research Expansion

- [ ] 34. Define `SourceProvider` interface
  - [ ] 34.1 Create `backend/app/company_intelligence/sources/base.py` with `SourceProvider` ABC and `SourceResult` dataclass
    - `SourceProvider.fetch(url: str) -> SourceResult`
    - Modify `website.py` and `browser.py` to inherit from `SourceProvider`
    - Add `RESEARCH_PROVIDER_ORDER: list[str] = ["http", "pdf", "browser"]` config key to `backend/app/config.py`
    - _Requirements: 12.1, 12.2_

- [ ] 35. Create `backend/app/product_research.py` router
  - [ ] 35.1 Implement `POST /products/{product_id}/leads/{lead_id}/opportunity`
    - Assert a completed `ResearchJob` exists for this lead's domain; return 422 if none
    - Collect reviewed ResearchFacts for this company only
    - Call Bedrock with product_context + value_proposition + reviewed facts (separate call from email generation)
    - Create `ProductOpportunity` with status = `draft`; populate evidence_fact_ids
    - _Requirements: 3.1–3.8, 12.3_
  - [ ] 35.2 Implement `GET .../opportunity` and `PATCH .../opportunity/{opp_id}/status`
    - PATCH: accept only `reviewed` or `approved`; return 422 for other values
    - _Requirements: 3.2_
  - [ ] 35.3 Implement `GET /research/jobs/{job_id}/diff`
    - Query latest previous completed ResearchJob for the same domain
    - Compute diff: fact content hash comparison → added / changed / unchanged / conflicting
    - Return categorized lists of `{fact_id, field, old_value, new_value}` items
    - _Requirements: 12.4, 12.5_
  - [ ] 35.4 Implement `POST /research/facts/{fact_id}/accept-update` and `POST /research/facts/{fact_id}/reject-update`
    - accept-update: UPDATE ResearchFact with new value from diff
    - reject-update: no DB change; mark diff item as rejected in diff result
    - _Requirements: 12.6_
  - [ ] 35.5 Implement `POST /research/facts/{fact_id}/override`
    - INSERT `ResearchFactOverride`; return 405 on any PUT/PATCH/DELETE request against override records
    - Never modify the original ResearchFact row
    - _Requirements: 12.7, 12.9_

- [ ] 36. Write research tests
  - [ ]* 36.1 Create `backend/tests/test_product_research.py`
    - Use Hypothesis: `@given(opportunity_params)` assert status=`draft` after generation (**Property 5 shared**)
    - Use Hypothesis: `@given(fact_id_strategy)` where fact belongs to different lead; assert 422 (**Property 6 shared**)
    - Use Hypothesis: `@given(override_id_strategy)` attempt PUT/PATCH/DELETE; assert 405 (**Property 11: ResearchFactOverride append-only**)
    - Use Hypothesis: `@given(old_facts, new_facts)` assert every fact categorized exactly once (**Property 12: Research diff completeness**)
    - Cover: SSRF blocking (mocked), budget enforcement, existing ResearchFact unchanged after opportunity analysis
    - _Requirements: 12.1–12.9, 13.8_

---

### Milestone K — Integration Regression

- [ ] 37. Full backend test suite verification
  - [ ] 37.1 Run `pytest backend/tests/ --tb=short -q` and verify all tests pass including 113 original tests plus all new milestone tests
    - Fix any import conflicts or fixture gaps introduced during milestones B–J
    - Add `hypothesis` to `backend/requirements-dev.txt` if not already present
    - _Requirements: 13.9, 13.10_

- [ ] 38. Frontend typecheck and build verification
  - [ ] 38.1 Run `npx tsc --noEmit` in the frontend directory; fix all TypeScript errors
    - Run `next build` to confirm no build-time errors
    - _Requirements: 6.1–6.8_

- [ ] 39. Playwright end-to-end tests
  - [ ]* 39.1 Write Playwright tests in `frontend/tests/e2e/` covering
    - Product switching: select Product A → load workspace; switch to Product B → Product A state cleared
    - Product creation: fill form, submit, new product appears in selector
    - Dashboard date-range filter: select "7 days" → metrics update
    - Responsive layout at 1280px and 768px viewports
    - _Requirements: 6.3, 6.4, 7.4_

- [ ] 40. Update documentation
  - [ ] 40.1 Update `docs/` README with multi-product architecture overview, new migration commands (`alembic upgrade 0012_product_attribution`), and deployment gate: backup PostgreSQL → verify → apply → verify row counts
    - Note: no live data changes until backup gate confirmed
    - _Requirements: 4.6, 4.8_

---

## Notes

- Tasks marked `*` are optional and can be skipped for a faster MVP delivery.
- Each task references specific requirements for traceability.
- Milestones B and C must complete before D, E, F, G, H, I, J can begin (DB schema must exist).
- Milestones D through J are largely independent of each other and can run in parallel after Milestone C completes.
- Milestone K runs after all other milestones.
- All Bedrock, Apollo, Gmail, and Microsoft Graph calls must be mocked in tests — no live API calls.
- `MAIL_SEND_ENABLED` behavior and all existing safety checks are preserved unchanged.
- Property tests use Hypothesis; add `hypothesis` to `backend/requirements-dev.txt` if not present.
- Property test tag format: `# Feature: multi-product-platform, Property N: <property_text>`

---

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["3.1"] },
    { "id": 3, "tasks": ["4.1", "5"] },
    { "id": 4, "tasks": ["6.1", "7.1", "8.1"] },
    { "id": 5, "tasks": ["6.2", "6.3", "9.1"] },
    { "id": 6, "tasks": ["6.4", "9.2"] },
    { "id": 7, "tasks": ["10.1", "10.2", "11"] },
    { "id": 8, "tasks": ["12.1", "18.1", "22.1", "25.1", "29.1", "34.1"] },
    { "id": 9, "tasks": ["13.1", "19.1", "22.2", "25.2", "30.1", "35.1"] },
    { "id": 10, "tasks": ["14.1", "20.1", "22.3", "25.3", "30.2", "35.2"] },
    { "id": 11, "tasks": ["15.1", "15.2", "21.1", "22.4", "26.1", "30.3", "33.1", "35.3"] },
    { "id": 12, "tasks": ["16.1", "17.1", "23.1", "24.1", "27.1", "30.4", "32.1", "35.4"] },
    { "id": 13, "tasks": ["24.2", "28", "31.1", "32.2", "35.5", "36.1"] },
    { "id": 14, "tasks": ["37.1", "38.1"] },
    { "id": 15, "tasks": ["39.1", "40.1"] }
  ]
}
```
