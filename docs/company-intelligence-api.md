# Company Intelligence API

All routes are under `/intelligence`. Research submission/retry return 503 when `COMPANY_INTELLIGENCE_ENABLED` is false; saved data remains readable and jobs can be cancelled. Jobs run asynchronously; API requests do not scrape synchronously.

- `GET /status` — feature/search/model configuration without credentials.
- `POST /research` — `{company_name, website, lead_id?, country?, registration_id?, depth: "quick"|"comprehensive", inference_profile_id?, force_refresh?}`; returns 202 `{job_id, company_id, reused}`. Any selected Bedrock inference profile must be an explicit ARN.
- `GET /research?lead_id=&limit=&offset=` — paginated `{items,total}`.
- `GET /research/{job_id}` and `/progress` — job summary and persisted agent status.
- `POST /research/{job_id}/retry` — retry eligible failed agents while preserving successful work.
- `POST /research/{job_id}/cancel` — cooperatively cancel pending research.
- `GET /companies/{company_id}` — profile, lead link, last job/report and limitations.
- `GET /companies/{company_id}/facts?category=&job_id=&limit=&offset=` and `/sources?job_id=&limit=&offset=` — paginated evidence. Default is the latest job; a supplied job must belong to that company. Historical data is not mixed with newer jobs.
- `GET /companies/{company_id}/{overview|financials|news|funding|leadership|competitors|signals}` — category-filtered fact aliases.
- `GET /reports/{report_id}` — versioned summary, category statuses, fact IDs and limitations.

Category names are canonicalized as `company`, `news`, `financial`, `funding`, `leadership`, `competitors` and `signals`; `overview` and `financials` are aliases. Facts include citations and explicit verification/hypothesis fields. Unavailable information is returned as a report section with `status: "not_available"` rather than a fabricated claim.

The endpoints currently use the application's existing API authorization posture; no authentication system is added by this module.

Submissions reuse active jobs only when model/depth match; different settings return 409 while active. Fresh completed/partial jobs are reused only for matching settings unless `force_refresh` is explicit. Queue failures return 503 with persisted error state. Daily application budget exhaustion returns 429. Cancelled jobs are retained but are not retryable through the failed-role action; explicitly submit a new request.
