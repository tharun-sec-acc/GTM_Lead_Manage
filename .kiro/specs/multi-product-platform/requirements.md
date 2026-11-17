# Requirements Document

## Introduction

DENSO GTMProspecting is a multi-product B2B sales platform used by DENSO sales teams to manage prospecting campaigns for distinct automotive-aftermarket software products. Currently the system is single-product and implicitly treats every lead, campaign, and research job as belonging to one unnamed product context. This feature converts the platform into a multi-product workspace where:

- Each product (Vehicle Digital Inspection, Loss Tracker, Aftermarket Super App, General/Unassigned) has its own pipeline of associated companies, contacts, campaigns, templates, and research opportunities.
- The master company record (`Lead`) remains a single shared entity, deduplicated by `company_key`.
- Product-specific sales context (stage, priority, notes, opportunity analysis) is layered on top of shared company data without duplicating it.
- Dynamic navigation allows future products to be added through the UI without frontend code changes.
- All 55 existing leads, 1 campaign, and 4 batches are attributed to General/Unassigned during migration, preserving every existing ID and row.

The backend is FastAPI + SQLAlchemy 2.0 + Alembic + PostgreSQL 17. The frontend is Next.js 15 + React 19 + TypeScript with custom CSS.

---

## Glossary

- **Product**: A DENSO software offering tracked in the platform (e.g., Vehicle Digital Inspection). Identified by an immutable `slug`.
- **Lead**: The master company record in the `leads` table. Shared across products; never duplicated.
- **ProductLead**: A join record associating one Product with one Lead, carrying per-product sales context (stage, priority, status, notes).
- **ProductOpportunity**: An AI-generated or manually authored analysis of one product's fit for one company, stored per ProductLead.
- **Campaign**: An outreach sequence. Gains a nullable `product_id` FK; existing campaigns attributed to General/Unassigned.
- **EmailTemplate**: A reusable email template, either global (product_id = null) or product-scoped. Product overrides reference a parent global template.
- **EmailTemplateVersion**: An immutable snapshot of a template at a specific version number.
- **EmailAttachment**: A file uploaded for inclusion in a draft message; stored in a private Docker volume via StorageAdapter.
- **ResearchFactOverride**: An append-only override record for a ResearchFact; never mutates the source fact.
- **StorageAdapter**: An abstract interface for binary file storage, with a local Docker-volume implementation and a future S3 implementation.
- **Workspace**: The product-scoped UI shell with its own sub-navigation (Overview, Companies, Import, Research, Contacts, Lead 360, Campaigns, Templates, Meetings, Analytics).
- **Global Overview**: A cross-product summary dashboard accessible regardless of product selection.
- **company_key**: The deduplication key on the `leads` table used to prevent duplicate company records.
- **General/Unassigned**: The catch-all product (slug: `general-unassigned`) that receives all pre-existing records during migration.
- **SSRF**: Server-Side Request Forgery — blocked for all outbound research HTTP requests.
- **Bedrock**: AWS Bedrock Converse API, used for AI email generation and opportunity analysis.

---

## Requirements

### Requirement 1: Product Catalogue

**User Story:** As a DENSO sales administrator, I want to create and manage products in a central catalogue, so that the platform can organize sales activity by product line without hardcoding product names in the application.

#### Acceptance Criteria

1. THE System SHALL store each product with the fields: id, name, slug (unique, URL-safe, immutable after creation), description, short_description, logo_url, primary_color, status, product_context, value_proposition, target_industries (JSON array), created_at, updated_at.
2. WHEN a product is created, THE System SHALL reject the request if the slug is not unique or is not URL-safe (lowercase alphanumeric and hyphens only).
3. WHEN a product's slug is set at creation time, THE System SHALL treat the slug as immutable; subsequent PUT requests that include a changed slug SHALL be rejected with a 422 error.
4. THE System SHALL support exactly two status values for products: `active` and `archived`.
5. WHEN a status transition is requested via `PATCH /products/{id}/status`, THE System SHALL allow transitions between `active` and `archived` only; requests for any other status value SHALL be rejected with a 422 error.
6. THE System SHALL NOT support hard deletion of products; `DELETE /products/{id}` SHALL return 405 Method Not Allowed.
7. WHEN the migration `0012_product_attribution` is applied, THE System SHALL seed four products: Vehicle Digital Inspection (slug: `vehicle-digital-inspection`), Loss Tracker (slug: `loss-tracker`), Aftermarket Super App (slug: `aftermarket-super-app`), and General/Unassigned (slug: `general-unassigned`).
8. THE System SHALL expose `GET /products` returning all products ordered by name, with optional `status` filter query parameter.
9. WHEN a client requests `GET /products/{id}`, THE System SHALL return 404 if no product with that id exists.

---

### Requirement 2: Product–Lead Associations

**User Story:** As a sales representative, I want to associate companies with the products I am selling to them, so that each product has its own sales pipeline without duplicating company records.

#### Acceptance Criteria

1. THE System SHALL store each product–lead association with the fields: id, product_id (FK → products.id), lead_id (FK → leads.id), stage, priority, status, owner_id (nullable), sales_notes, associated_at, updated_at.
2. THE System SHALL enforce a unique constraint on (product_id, lead_id) in the `product_leads` table.
3. THE System SHALL accept `stage` values: `prospect`, `qualified`, `engaged`, `proposal`, `closed_won`, `closed_lost`.
4. THE System SHALL accept `priority` values: `high`, `medium`, `low`.
5. THE System SHALL accept `status` values: `active`, `inactive`.
6. WHEN `DELETE /products/{id}/leads/{lead_id}` is called, THE System SHALL remove the ProductLead association record only; the Lead, Contact, and Campaign records SHALL remain intact.
7. WHEN a client attempts to associate a lead with the same product twice, THE System SHALL return 409 Conflict.
8. THE System SHALL filter `GET /products/{id}/leads` by optional query parameters: stage, priority, status.
9. WHEN the migration `0012_product_attribution` is applied, THE System SHALL create a ProductLead record for every existing Lead, associating it with the General/Unassigned product, with status = `active`, priority = `medium`, stage = `prospect`.

---

### Requirement 3: Product Opportunity Analysis

**User Story:** As a sales representative, I want an AI-generated analysis of how well a product fits a specific company, so that I can prioritize outreach with evidence-backed context.

#### Acceptance Criteria

1. THE System SHALL store each product opportunity with the fields: id, product_lead_id (FK → product_leads.id), research_job_id (FK → research_jobs.id, nullable), opportunity_summary, pain_points (JSON array), use_cases (JSON array), relevance_score (float 0.0–1.0), confidence (float 0.0–1.0), evidence_fact_ids (JSON array of research_fact IDs), status, manual_override (boolean), created_at, updated_at.
2. THE System SHALL accept `status` values for opportunities: `draft`, `reviewed`, `approved`.
3. WHEN an opportunity analysis is generated by Bedrock, THE System SHALL reference only ResearchFact IDs from the same company's existing research; THE System SHALL NOT copy or duplicate fact content.
4. WHEN manual_override is set to true, THE System SHALL preserve the original AI-generated record and store the override as a ResearchFactOverride record, never mutating the source ResearchFact.
5. WHEN a Bedrock opportunity analysis call is made, THE System SHALL include product_context, value_proposition, company details, and reviewed ResearchFacts for that company only.
6. THE System SHALL NOT generate opportunity analysis for a company that has no completed ResearchJob.
7. WHEN a Bedrock opportunity analysis call responds, THE System SHALL create the ProductOpportunity with status = `draft`; THE System SHALL NOT auto-approve the result.
8. THE System SHALL validate that relevance_score and confidence are floats in the range [0.0, 1.0]; values outside this range SHALL be rejected with a 422 error.

---

### Requirement 4: Legacy Data Migration

**User Story:** As the system operator, I want all existing data migrated to the multi-product schema without data loss, so that the team can continue working immediately after deployment.

#### Acceptance Criteria

1. THE Migration_0011 SHALL create the tables `products`, `product_leads`, `product_opportunities`, `email_templates`, `email_template_versions`, `email_attachments`, `research_fact_overrides`, and add nullable columns `product_id` to `campaigns` and `batches`; THE Migration_0011 SHALL NOT drop, truncate, or recreate any existing table.
2. THE Migration_0012 SHALL seed the four initial product records with the slugs defined in Requirement 1.7.
3. WHEN Migration_0012 runs, THE System SHALL create one ProductLead record for every existing Lead row, associating it with General/Unassigned.
4. WHEN Migration_0012 runs, THE System SHALL set the `product_id` column on every existing `campaigns` row to the id of the General/Unassigned product.
5. WHEN Migration_0012 runs, THE System SHALL set the `product_id` column on every existing `batches` row to the id of the General/Unassigned product.
6. THE Migration_0012 `down_revision` SHALL be `0011_products`; THE Migration_0011 `down_revision` SHALL be `0010_company_intelligence`.
7. WHEN both migrations are applied to a database that already contains the 55 leads, 1 campaign, 4 batches, 2 contacts, and 4 suppressions, ALL existing primary key values SHALL be preserved exactly.
8. THE System SHALL provide a migration test that starts from revision `0010_company_intelligence`, seeds all existing record types, applies `0011` and `0012`, and asserts all original IDs and row counts are preserved.

---

### Requirement 5: Product-Scoped Backend APIs

**User Story:** As a frontend developer, I want REST endpoints for all product and product-lead operations, so that the UI can manage multi-product data without direct database access.

#### Acceptance Criteria

1. THE API SHALL expose: `GET /products`, `POST /products`, `GET /products/{id}`, `PUT /products/{id}`, `PATCH /products/{id}/status`.
2. THE API SHALL expose: `GET /products/{id}/leads`, `POST /products/{id}/leads`, `PUT /products/{id}/leads/{lead_id}`, `DELETE /products/{id}/leads/{lead_id}`.
3. WHEN `POST /products/{id}/batches` is called with a valid Excel file and an active product_id, THE System SHALL validate the product is active, reuse any existing Lead where `company_key` matches, create a new Lead only when no matching `company_key` exists, and create a ProductLead association for each Lead processed; THE System SHALL delegate to the existing import pipeline for all Lead-level operations.
4. WHEN `POST /products/{id}/batches` is called with a Lead that already has a ProductLead association to that product, THE System SHALL skip creating a duplicate association and return the existing association id in the response.
5. THE System SHALL enforce cross-product data isolation server-side: campaign enrollment queries SHALL be filterable to leads associated with the requesting product; THE System SHALL return 403 if a campaign's product_id does not match the product context in the request.
6. THE System SHALL update CORS configuration to allow PATCH and DELETE HTTP methods from `http://localhost:3000`.
7. WHEN any product-scoped endpoint receives a product_id that is `archived`, THE System SHALL return 422 with a message indicating the product is archived.
8. WHEN `PUT /products/{id}` is called with a changed slug, THE System SHALL return 422.

---

### Requirement 6: Dynamic Navigation and Product Workspaces

**User Story:** As a sales user, I want to switch between product workspaces in the UI, so that I can focus on one product's pipeline at a time without seeing other products' data.

#### Acceptance Criteria

1. THE Frontend SHALL load the product list from `GET /products` at application startup and render a product selector in the top bar.
2. THE Product_Selector SHALL display only products with status = `active` plus an "Add product" option.
3. WHEN a user selects a product in the Product_Selector, THE Frontend SHALL load the product workspace with sub-navigation sections: Overview, Companies, Import, Research, Contacts, Lead 360, Campaigns, Templates, Meetings, Analytics.
4. WHEN a user switches products, THE Frontend SHALL clear all product-scoped state and cancel any in-flight API requests for the previous product.
5. THE Frontend SHALL render breadcrumbs in the format `DENSO / {Product Name} / {Section}` on every product workspace page.
6. THE Frontend product workspace pages SHALL use dynamic routes with `[productSlug]` segments; no product name SHALL be hardcoded in route definitions.
7. THE Frontend SHALL make the Global Overview accessible from the sidebar regardless of which product is selected.
8. WHEN the product list API call fails, THE Frontend SHALL display an error state in the product selector and allow retry without a full page reload.

---

### Requirement 7: Product and Global Dashboards

**User Story:** As a DENSO sales manager, I want dashboards showing pipeline health per product and across all products, so that I can track progress without counting the same company twice.

#### Acceptance Criteria

1. THE Product_Dashboard SHALL display for the selected product: count of associated companies, count of active contacts (via Lead associations), count of research jobs by status (queued/running/completed/failed), campaign count, message counts by status (draft/approved/sent), reply count, and meeting-request task count.
2. THE Global_Dashboard SHALL display: total unique companies (deduplicated by lead_id), total unique contacts (deduplicated by lead_id), total campaigns, total messages, total replies, and per-product pipeline totals.
3. THE Global_Dashboard SHALL NOT double-count a company that appears in multiple products.
4. WHEN a date range filter is applied (last 7 days, 30 days, 90 days, or custom range), THE Dashboard SHALL recalculate all metrics using only records with timestamps within the selected range.
5. ALL dashboard metric values SHALL be computed from live database queries; THE System SHALL NOT return hard-coded or fabricated metric values.
6. THE Product_Dashboard API SHALL be exposed at `GET /products/{id}/overview`.
7. THE Global_Dashboard API SHALL be exposed at `GET /overview`.

---

### Requirement 8: Hybrid Email Templates

**User Story:** As a sales representative, I want global and product-specific email templates with version history, so that I can maintain brand-consistent messaging while customizing content per product.

#### Acceptance Criteria

1. THE System SHALL store templates with fields: id, product_id (FK nullable = global), parent_template_id (FK nullable), name, type, subject_template, body_template, variables (JSON array), is_active (boolean), version (integer), created_at, updated_at.
2. THE System SHALL accept `type` values: `initial`, `followup`, `product_intro`, `meeting_request`, `post_meeting`, `custom`.
3. WHEN a template with product_id = null is created, THE System SHALL treat it as a global template accessible to all products.
4. WHEN a product-scoped override is created with a parent_template_id, THE System SHALL create a new template record with the product's id; THE System SHALL NOT modify the parent template record in any way.
5. THE System SHALL store an immutable EmailTemplateVersion record every time a template's subject_template or body_template is saved; version numbers SHALL increment by 1 from the previous version.
6. THE System SHALL accept exactly these variable placeholders in templates: `{{company_name}}`, `{{company_domain}}`, `{{company_industry}}`, `{{contact_first_name}}`, `{{contact_last_name}}`, `{{contact_title}}`, `{{contact_department}}`, `{{contact_seniority}}`, `{{product_name}}`, `{{product_value_proposition}}`, `{{reviewed_research_facts}}`, `{{product_opportunity_summary}}`, `{{sender_name}}`, `{{sender_signature}}`.
7. WHEN a template is saved containing a variable placeholder not in the validated set (Requirement 8.6), THE System SHALL flag the unknown variables in the response body with a 422 status and SHALL NOT persist the template.
8. THE System SHALL expose a `POST /templates/{id}/preview` endpoint that resolves all validated variables with sample data and returns the rendered HTML.
9. WHEN an EmailMessage draft is generated, THE System SHALL record the exact template_id and version number used; subsequent template edits SHALL NOT alter existing drafts.
10. THE System SHALL expose CRUD endpoints: `GET /templates`, `POST /templates`, `GET /templates/{id}`, `PUT /templates/{id}`, `PATCH /templates/{id}/status`.

---

### Requirement 9: Contextual AI Email Generation

**User Story:** As a sales representative, I want AI-generated email drafts that incorporate product context, company research, and contact role, so that each message is relevant and evidence-backed without inventing details.

#### Acceptance Criteria

1. WHEN a generation request is submitted, THE Generation_Service SHALL resolve and pass to Bedrock: product_context, product value_proposition, company details (Lead fields), selected contact details, reviewed ResearchFacts for that company only, ProductOpportunity summary (if approved), selected template + pinned version, and sender identity.
2. THE Generation_Service SHALL generate one independent draft per recipient; THE System SHALL NOT copy a single generated draft to multiple recipients.
3. THE Generation_Service SHALL NOT invent company operations, financial figures, business relationships, pain points, product capabilities, or contact responsibilities that are not present in the resolved context.
4. WHEN resolved context is missing required fields (e.g., no approved opportunity, no research facts), THE Generation_Service SHALL include a `missing_context` array in the draft metadata listing each missing item by name.
5. ALL generated drafts SHALL be created with status = `draft`; THE System SHALL NOT auto-approve any generated draft.
6. THE Generation_Service SHALL reuse the existing `bedrock.py` Converse client; THE System SHALL NOT instantiate a second Bedrock client.
7. WHEN an inference profile requires cross-region routing, THE Generation_Service SHALL add a `requires_user_review` flag to the response rather than routing automatically.
8. WHEN a generation request references ResearchFacts from a different company's research job, THE System SHALL return 422 and SHALL NOT proceed with generation.

---

### Requirement 10: Product-Scoped Campaigns

**User Story:** As a sales representative, I want campaigns linked to a specific product, so that enrollments and recipient selection are automatically filtered to companies in that product's pipeline.

#### Acceptance Criteria

1. THE System SHALL add a nullable `product_id` column (FK → products.id) to the `campaigns` table; THE System SHALL NOT remove any existing campaign columns.
2. WHEN a new campaign is created via `POST /campaigns`, THE System SHALL accept and store the `product_id` field.
3. WHEN enrolling a contact in a campaign, THE System SHALL verify that the contact's parent Lead has a ProductLead association to the campaign's product; THE System SHALL return 422 if the association does not exist.
4. THE Bulk_Recipient_Selector SHALL only display contacts whose parent Lead is associated with the campaign's product when a product_id is set on the campaign.
5. ALL existing approval, suppression, inbox-sync, reply-stop, unsubscribe, budget, and SMTP safety checks SHALL remain active and unchanged for product-scoped campaigns.
6. THE System SHALL NOT auto-send or auto-approve any campaign message.
7. WHEN Migration_0012 runs, THE System SHALL set every existing campaign's product_id to the id of the General/Unassigned product (covered also by Requirement 4.4).

---

### Requirement 11: Rich Text Editor and File Attachments

**User Story:** As a sales representative, I want to compose rich text emails and attach files, so that my outreach includes formatted content and supporting documents without leaving the platform.

#### Acceptance Criteria

1. THE Rich_Text_Editor SHALL support: bold, italic, underline, ordered lists, unordered lists, and hyperlinks.
2. WHEN email content is saved, THE System SHALL sanitize all HTML before storage; script tags, event-handler attributes, and iframe elements SHALL be stripped.
3. THE System SHALL store each attachment with fields: id, message_id (FK nullable during upload phase), upload_session_id, filename_safe, content_type, size_bytes, storage_key, upload_status, created_at.
4. WHEN a file is uploaded, THE System SHALL reject files larger than 10 MB per file, reject any message where cumulative attachment size exceeds 25 MB, reject files whose content_type is not in the allowed set (PDF, DOCX, XLSX, PNG, JPG, GIF, WEBP), and reject files whose extension does not match the allowed extension whitelist.
5. WHEN a send operation is requested for a message with one or more attachments in a non-`complete` upload_status, THE System SHALL block the send and return 422.
6. WHEN the HTML body or attachments of a message are modified after the message has been approved, THE System SHALL reset the message approval status to `draft`.
7. THE System SHALL provide `GET /messages/{id}/attachments/{attachment_id}` returning the file bytes only to authorized requests; no public URL SHALL expose attachment content.
8. WHEN an attachment upload fails, THE System SHALL mark upload_status = `failed` and SHALL NOT make the attachment available for send.
9. THE Rich_Text_Editor SHALL autosave draft content with a debounce of 2 seconds after the last keystroke.

---

### Requirement 12: Research Expansion

**User Story:** As a sales representative, I want product-specific opportunity analysis derived from shared company research, plus the ability to review and override individual facts, so that research serves multiple products without data duplication.

#### Acceptance Criteria

1. THE System SHALL define a `SourceProvider` abstract base class with a `fetch(url: str) -> SourceResult` method; existing HTTP, PDF, and browser source implementations SHALL conform to this interface.
2. THE Source_Discovery service SHALL attempt source providers in order: official site HTTP → PDF → browser; additional providers SHALL be configurable via application config without code changes.
3. WHEN a product opportunity analysis is requested, THE System SHALL execute a separate Bedrock call using product_context, value_proposition, and only the reviewed ResearchFacts for that company; THE System SHALL NOT reuse the email generation Bedrock call for this purpose.
4. WHEN a new ResearchJob completes for a company that has a previous completed ResearchJob, THE System SHALL compute a diff of new vs. previous facts, categorized as: added, changed, unchanged, conflicting.
5. WHEN a research diff is available, THE Research_API SHALL expose `GET /research/jobs/{job_id}/diff` returning the categorized fact changes.
6. WHEN a user accepts an individual fact update from a diff, THE System SHALL update the ResearchFact record; WHEN a user rejects an update, THE System SHALL preserve the original fact unchanged.
7. WHEN a manual override is applied to a ResearchFact, THE System SHALL create a ResearchFactOverride record (fields: id, fact_id FK, product_id FK nullable, override_value, reason, created_by_note, created_at); THE System SHALL NOT modify the original ResearchFact record.
8. THE System SHALL preserve all existing research orchestrator behavior: 7 extraction roles, SSRF protection, robots policy, byte budgets, budget enforcement, and ResearchReport versioning.
9. THE ResearchFactOverride table SHALL be append-only; existing ResearchFactOverride records SHALL NOT be updated or deleted through any API endpoint.

---

### Requirement 13: Testing Coverage

**User Story:** As a backend engineer, I want comprehensive automated tests for all new and modified code, so that regressions are caught before they reach production.

#### Acceptance Criteria

1. THE Migration_Test_Suite SHALL start from revision `0010_company_intelligence`, seed all existing record types (leads, campaigns, batches, contacts, suppressions), apply migrations `0011` and `0012`, and assert that all original IDs, row counts, and column values are preserved.
2. THE Product_Isolation_Tests SHALL verify that a request authenticated to Product A cannot read campaigns, opportunities, or enrollment records belonging to Product B.
3. THE Import_Tests SHALL cover: (a) import of a new company under a new product creates Lead + ProductLead, (b) import of an existing company (matching company_key) under a new product creates ProductLead only, (c) import of an existing company under the same product skips duplicate ProductLead and returns existing association id.
4. THE Template_Tests SHALL cover: global template creation, product-scoped template creation, override creation without parent mutation, version history retrieval, and rejection of templates with invalid variable placeholders.
5. THE Generation_Tests SHALL cover: context resolution (product + company + contact + research), rejection of cross-company research facts, presence of missing_context flag when required fields are absent, and verification that generated drafts remain in `draft` status.
6. THE Campaign_Tests SHALL cover: product ownership validation on enrollment, suppression check preservation, reply-stop preservation, and all-or-nothing enrollment rollback.
7. THE Attachment_Tests SHALL cover: valid upload, rejection of invalid extension, rejection of oversized file, rejection of MIME mismatch, blocking send when attachment status is not `complete`, and approval invalidation on body edit.
8. THE Research_Tests SHALL cover: existing ResearchFact preservation after opportunity analysis, opportunity analysis draft status, SSRF blocking, budget enforcement, and ResearchFactOverride append-only behavior.
9. ALL tests for external services (Apollo, Bedrock, Gmail, Microsoft Graph) SHALL use mocks; no live API calls SHALL be made during test execution.
10. THE existing 113 backend tests SHALL continue to pass after all milestone implementations.
