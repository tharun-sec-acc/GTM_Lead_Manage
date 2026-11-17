# Multi-recipient outreach

## Current behavior

A campaign can enroll multiple people associated with one lead. Each person is a separate `Enrollment` with its own recipient address, unsubscribe token, message sequence, reply matching, pause/stop state and suppression checks. Messages are sent individually; the system does not place multiple prospects in To/CC/BCC on a shared email.

When a saved contact is selected, the enrollment stores its `contact_id`. The API requires that contact to be active, belong to the selected lead and have the same normalized email address as the recipient. This avoids silently associating a manually typed, different address with a contact. The imported lead email or a manually entered address may still be enrolled without a contact association. Contact removal is soft, so existing campaign history remains connected to the original contact record.

Drafting, approval and follow-up are per enrollment. In manual mode every email needs its own approval. Automatic mode requires exact approval of the follow-up sequence. Suppression and reply blocking apply to the individual address/enrollment; neither another contact's reply nor another contact's approval should authorize sending to this recipient.

## API and interface

- `POST /campaigns/{campaign_id}/enrollments` accepts `lead_id`, `recipient`, and optional `contact_id`.
- `POST /campaigns/{campaign_id}/enrollments/bulk` accepts `{"recipients": [{"lead_id": "...", "recipient": "person@example.com", "contact_id": null}]}` with 1-100 entries; returns `ids` and `added`.
- `GET /campaigns/{campaign_id}` returns `contact_id` and saved `contact_name` when associated.
- Follow-up management and Lead 360 share the same editor. Choose a draft campaign and company, check saved contacts, optionally select the imported company email, or paste plain addresses separated by commas, semicolons or whitespace. The company is fixed when working in Lead 360.
- The picker displays a recipient count and disables already-enrolled saved contacts. Duplicate selections must be removed before adding.
- Contacts from a different lead, soft-removed contacts, and an email that differs from the saved contact email are rejected.

Both enrollment endpoints require a draft campaign and share validation under the existing mail-workflow lock. Bulk validation completes before any inserts: an invalid email, suppression, missing lead, contact mismatch, normalized duplicate within the request or existing campaign recipient rejects the whole addition. There are no partial additions. Creating recipients does not send anything or approve their drafts; each receives independent tokens and messages, and existing sequence approval is invalidated.

Expand a recipient to write/save drafts or generate them from approved company/product facts. The shared editor offers explicit Bedrock inference-profile discovery and selection; see [Bedrock setup](../README.md#bedrock-model-and-inference-profile-setup). **Add reviewed company intelligence** selects up to 20 cited findings from separately run research. `POST /enrollments/{id}/generate` receives `research_fact_ids`; the server validates the lead association, accepted status and supporting source passages. Conflicting, hypothetical, unavailable and cross-company facts are rejected. Multi-company campaigns keep fact selections separate by lead. Generation is per recipient and does not itself browse websites. Editing or successful regeneration invalidates approval; failed regeneration preserves saved drafts and approvals.

Lead 360 filters threads to the current company. Campaign activation/pause remain campaign-wide; a warning identifies hidden recipients, and whole-sequence approval is hidden when any recipients are outside the profile. Use the full follow-up page to review the complete campaign.

## Not implemented

There is no recipient file import, contact-level analytics export, organization-wide duplicate check across campaigns, or automatic Apollo enrichment for missing contact emails. Active or paused campaigns cannot accept additional recipients; use a new draft campaign. Adding a person does not establish consent or authorize sending. Sending is disabled by default and requires explicit approval to enable. Unsubscribe footer and public tracking are separate server settings; disabling the footer does not bypass recipient suppressions, reply stops or inbox checks. See [email settings](email-capacity-and-rate-limits.md).

## Migration and validation

Migration `0008_enrollment_contact_link` adds nullable `enrollments.contact_id` with a foreign key. Existing enrollments remain unassociated and retain their existing IDs and message histories. Backend tests cover matching, mismatched and cross-company contacts, plus history retention after contact soft removal.

Bulk enrollment and the shared editor add no migration. Tests cover atomic rejection, normalized duplicates, suppressions, invalid addresses/contact mismatch, independent tokens, message threads and recipient-specific approval/sending with mocked SMTP. Browser smoke checks use mocked API responses, not live mail or AWS.
