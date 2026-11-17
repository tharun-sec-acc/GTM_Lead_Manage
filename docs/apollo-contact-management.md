# Apollo search and contact management

## Implemented behavior

The salesperson selects a lead and confirms its company domain before invoking Apollo. The domain field accepts a bare domain such as `orixindia.com` or an `http(s)` website URL such as `https://www.orixindia.com/`; the API validates the host and stores the normalized domain without `www`, path, query, credentials, or port. Unsupported schemes and malformed hosts are rejected before Apollo is called. The Apollo API client sends a `POST` to `/api/v1/mixed_people/api_search`, authenticates with `APOLLO_API_KEY` in the `x-api-key` header, and searches up to 25 people for that domain and seniority set. The API persists normalized search result fields against the existing lead ID in `apollo_search_results`; repeated searches refresh the saved snapshot for each `(lead_id, apollo_id)`. Search candidates are therefore available after navigation without retaining the full vendor response.

The UI shows the candidate's available name, title, department, seniority, organization name/domain and LinkedIn URL. It indicates whether the Apollo organization domain matches the confirmed company domain. Selecting a candidate requires the search result to be saved first. If Apollo did not return a matching domain, an inline checkbox asks sales to explicitly confirm current employment before enabling enrichment; there is no blocking browser confirmation popup. Confirmation resets when selecting another company or running a new search. The UI explains limited search names, missing emails and possible enrichment credits. The enrichment response is checked again; a domain-mismatched email is not retained. The association is marked `organization_verified` only when an organization domain matches, otherwise `manually_verified`. Company research does not independently verify a contact's current employer or email.

The contact table links each person to `leads.id`. It stores Apollo ID where applicable, name, title, email, department, seniority, LinkedIn URL, location, source, retrieval/update timestamps, decision-maker flag and verification status. Apollo email is retained only when its domain matches the confirmed company domain. This is a conservative filter, not an independent proof of deliverability.

Sales can add a contact manually, edit contact fields and decision-maker status through the API, or remove a contact association. Removal is soft (`is_active=false`), preserving historical references. Manually entered addresses are validated syntactically and marked unverified; adding one does not infer a verified company association.

## API

- `POST /leads/{lead_id}/apollo/search`: search, persist and return candidates.
- `GET /leads/{lead_id}/apollo/search-results`: return up to 100 saved candidates.
- `POST /leads/{lead_id}/apollo/enrich`: enrich a previously saved candidate. Body supports `organization_confirmed` for an explicit human-confirmed employer.
- `GET /leads/{lead_id}/contacts`: list active contacts.
- `POST /leads/{lead_id}/contacts`: create a manual contact.
- `PUT /leads/{lead_id}/contacts/{contact_id}`: update an active contact.
- `DELETE /leads/{lead_id}/contacts/{contact_id}`: soft-remove the association.

## Limits

The pilot does not currently call Apollo's organization enrichment endpoint and does not persist full company firmographics, technologies or a raw vendor response. Search result pagination, automatic verification, contact ownership, personal email/phone support and bulk contact management are not implemented. Search candidates may include prior-employer associations; the current-company confirmation step is intentional. Apollo access/credit requirements apply. No external Apollo account is exercised by the automated tests.

## Validation

`backend/tests/test_imports.py` uses mocked Apollo results to cover website URL normalization and rejection, documented API method/path/auth/query parameters, persistence and selection, wrong-organization review, cross-domain email filtering, manual contact edit/removal and existing search behavior. Apollo search does not return email addresses or phone numbers; enrichment is a separate API request and may consume credits. No live Apollo request is made by tests.

Official references: [Build with Apollo](https://docs.apollo.io/docs/build-with-apollo), [Authentication](https://docs.apollo.io/reference/authentication), [People API Search](https://docs.apollo.io/reference/people-api-search), and [People Enrichment](https://docs.apollo.io/reference/people-enrichment).
