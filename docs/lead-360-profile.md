# Lead 360 profile

## Current profile view

`/leads/{id}` displays an aggregate profile for data already available in the pilot:

- Company fields retained by import and current confirmed domain.
- Active contacts.
- Campaign email drafts, approval/scheduling status, send status, SMTP acceptance time and tracking events.
- Matched replies and classifications.
- A chronological timeline synthesized from import rows, Apollo contact/search records, email records/events, replies and sales tasks.

The UI separates Overview, Contacts, Emails/Follow-ups, Research/AI insights, Meetings, Commercial lifecycle and Timeline. Empty/unbuilt sections are explicit; absence of a section is not represented as a successful zero-value integration.

## People and outreach actions

- **Add people** jumps to the inline contact form. Save a name, optional designation and business email; repeat for additional people. The existing `POST /leads/{id}/contacts` endpoint is reused. Saving a person does not send mail or verify the address.
- **Compose and approve emails** jumps to the shared outreach editor. Create/select a draft campaign, check saved contacts or paste multiple plain addresses, and add up to 100 recipients atomically. New contacts appear in the picker after saving.
- Use **Research company** for embedded opt-in research, real progress, source-backed findings and reports. The same company's research is accessible from the combined dashboard after Excel import and company/domain search.
- Expand a recipient to write/save drafts, or explicitly select an approved AWS inference profile and generate from factual company/product context plus up to 20 reviewed cited facts. Draft generation does not browse a URL; run research separately first. Review the saved subject/body and approve each email. See [Bedrock setup](../README.md#bedrock-model-and-inference-profile-setup).
- Activation, pause, independent recipient controls and exact-content approvals reuse the existing Gmail workflow. The editor displays live server sending/footer/tracking settings and inbox-sync blockers; approvals, suppressions and mailbox checks remain enforced when sending is explicitly enabled. No meeting functionality was added.
- Only the current company's threads are displayed, but campaign activation/pause apply to all enrolled companies. Hidden recipients trigger a warning, and whole-sequence approval requires the full campaign view when recipients are hidden. **All campaigns** opens that view.

The embedded editor refreshes its campaign data, while the historical overview, emails and timeline are snapshots. Reload the page to refresh history after outreach actions. Contact creation reloads the profile and recipient picker.

See [multi-recipient outreach](multi-recipient-outreach.md) for validation, draft-only enrollment and independent-thread behavior. The research domain uses additive migration `0010_company_intelligence`; existing contact/outreach actions retain their prior tables.

## Profile API and limits

`GET /leads/{lead_id}/profile?limit=200` returns the profile. `limit` is bounded from 1 to 500. Email, reply, contact, Apollo and timeline lists are bounded; use the limit to request a larger recent window. Existing list endpoints remain unchanged. The profile does not currently provide server-side date/campaign filters or timeline pagination tokens.

SMTP `sent` status and `smtp_accepted` events are shown as acceptance only, never provider-confirmed delivery. Open/click signals remain approximate. Current ownership, lifecycle stage/history, proposal, contract and customer-success modules are not implemented; meeting booking and recording/transcript handling live in the [meetings and booking](meetings-and-booking.md) module. Research is loaded through its own `/intelligence` APIs, not the legacy profile aggregate's placeholder research field.

## Data aggregation

The backend bulk-loads records for a lead and its enrollments and their messages; it does not fetch whole-workspace histories. The API includes email body content for local review. Do not expose this profile outside the local pilot.

See [lead data relationships](lead-data-relationships.md) and [backward compatibility](backward-compatibility.md).
