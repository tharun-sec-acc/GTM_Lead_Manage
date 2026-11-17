# Lead data relationships

## Existing persisted relationships

`leads.id` is the stable company/lead identity. Existing foreign keys use it for:

- `contacts.lead_id` (including Apollo and manually added contacts).
- `import_rows.lead_id` (successful imports and duplicate references).
- `enrollments.lead_id`, connecting the company to campaign recipients.
- `enrollments.contact_id`, optionally connecting an individual campaign recipient to an active saved contact at enrollment time. The recipient address must match that contact's saved email.

Additional relationships:

- `email_messages.enrollment_id` connects each campaign step/draft to one enrolled recipient.
- `email_replies.enrollment_id` and `original_email_id` connect received replies to the recipient and original email where matching succeeded.
- `email_events.email_id` and `tracking_links.email_id` attach accepted/tracking events to email records.
- `sales_tasks.reply_id` connects meeting-request or sales-review tasks to a reply.
- `apollo_search_results.lead_id` retains selected-domain search snapshots before contact enrichment.
- `import_rows.batch_id` and `(sheet_name, row_number)` preserve source workbook provenance.

The Lead 360 API assembles these records into an aggregate view; it does not replace the normalized source tables.

## Not yet modeled

Meetings/participants/artifacts, company research, stage history, lead ownership, proposals/versions, ROI calculations, negotiations, contracts, approvals, handover, implementation and customer-success records remain future work. The Lead 360 response explicitly marks these sections unimplemented. It does not create speculative rows or infer a sales stage from campaign status.

## Referential integrity and limits

The schema preserves current lead IDs and existing relationships. Contact removal is soft to retain history. Each enrollment and its messages, replies, suppressions and tracking remain isolated to one email address. A campaign may enroll multiple people separately; it never sends a shared message with multiple recipients. Contact association is optional for imported or manually entered addresses that are not tied to a saved contact. A contact can later be soft-removed without deleting the enrollment or its history.
