# Multi-product architecture

Status: implemented incrementally on the existing modular monolith. This document describes the
ownership model, isolation rules and UI structure actually in the repository. It does not describe
unbuilt booking, meeting or CRM features.

## Ownership model

```text
Product
  -> ProductLead -> Lead (master company, shared)
                     -> Contact / ApolloSearchResult (shared)
                     -> CompanyResearchProfile -> ResearchJob / Source / Fact / Citation / Report
  -> Campaign -> Enrollment -> EmailMessage / EmailReply / EmailEvent

ProductLead
  -> ProductOpportunity (references a research job and its fact IDs)

EmailTemplate (global, product_id = NULL)
  -> EmailTemplateVersion
  -> Product EmailTemplate (parent_template_id points at the global original)
```

- `leads` remains the single master company identity. A company associated with three products is
  still one row in `leads`; it has three `product_leads` rows.
- `contacts` stay owned by `lead_id` and are shared by every product that includes that company.
- `campaigns.product_id` is the authoritative owner of the sales thread. Every enrollment's company
  must be associated with that campaign's product.
- `batches.product_id` attributes an import to the product whose workspace uploaded it.
- Company research is company-scoped and reusable. Product opportunity analysis references the
  existing job and fact IDs instead of duplicating evidence.
- Suppressions, mailbox state, approvals and sending safeguards are global. Product scoping never
  bypasses them.

## Isolation rules

All isolation is enforced server-side; the UI never filters data it should not have received.

1. `POST /batches` accepts an optional `product_id`. The product must exist and be active (404/422
   otherwise). The batch and every association it creates are attributed to that product.
2. Importing a company that already exists as a master record associates it with the importing
   product. If the company is already associated with that product, the row is reported as a
   duplicate and skipped. A master company is never duplicated for a product.
3. `POST /campaigns` validates `product_id`. `POST /campaigns/{id}/enrollments[/bulk]` rejects any
   company that is not associated with the campaign's product with 409, before writing anything. Bulk
   additions stay all-or-nothing.
4. Product read endpoints resolve IDs through `product_leads` and `campaigns.product_id`. A record
   that belongs to another product is simply not returned.
5. Removing a product-lead association keeps the master company, its contacts, campaigns, messages,
   replies and research. Products are archived, never deleted.

Product scoping is workflow consistency, not tenant authorization. The application requires a login by default (an anonymous fallback is configurable), but any signed-in member can use the global management routes; see [authentication and organizations](authentication-and-organizations.md).

## Workspace structure

| Route | Purpose |
| --- | --- |
| `/overview` | Consolidated totals across products and a per-product table |
| `/dashboard` | Existing combined import/company/research workspace (global) |
| `/products/{slug}` | Product overview: companies, contacts, campaigns, messages, research, meeting tasks |
| `/products/{slug}/companies` | Product companies with stage and priority, association and removal |
| `/products/{slug}/import` | Product-scoped Excel upload, sheet mapping and row report |
| `/products/{slug}/research` | Research jobs for the product's companies, plus per-company research entry |
| `/products/{slug}/contacts` | Active contacts of the product's companies |
| `/products/{slug}/campaigns` | Product campaigns and draft-campaign creation |
| `/products/{slug}/templates` | Global templates, product templates, overrides, version history, preview |
| `/products/{slug}/meetings` | Meeting-request sales tasks attributed through the campaign |
| `/products/{slug}/analytics` | Persisted product counts, date-filtered messages/replies, pipeline |

The product selector in the top bar is data-driven from `GET /products`; new products appear without
frontend changes. `Add product` creates a product through `POST /products` and navigates to it.

Product switching is handled per component: in-flight requests are aborted and state is cleared when
the product changes, so the previous product's data is never shown under the new product.

## Metrics semantics

- `unique_companies` counts master companies (`leads`), not associations.
- `product_associations` counts `product_leads` rows; `product_associated_companies` counts distinct
  companies that belong to at least one product.
- `contacted_companies` counts companies in the product with at least one SMTP-accepted message.
- SMTP acceptance is not delivery. Open/click tracking is approximate and disabled by default.
- Company, contact, pipeline and research counts are current state; date filters apply to campaigns,
  messages and replies.

## Deliberately not implemented

- Meeting booking, Outlook event creation, Teams links/invitations, recordings and transcripts.
- External search/news/registry adapters for research; source discovery remains the bounded
  official-site HTTP/PDF collector with an opt-in text-only Playwright fallback.
- Attachment storage beyond the private local volume adapter; no S3 backend.
- A dedicated rich-text HTML editor and product signatures. Draft bodies remain plain text and
  approval still covers the exact saved subject/body.
- Authentication, roles or tenant isolation.
