# Company Intelligence implementation status

## Implemented

- Opt-in research status, submission, polling, list, retry and cooperative cancel APIs.
- Standalone company profiles and optional links to existing leads.
- Celery background execution and persisted progress for nine roles: company, news, financial, funding, leadership, competitors, signals, verification and synthesis.
- Bounded official-site HTML collection, robots checks, same-host link discovery, redirects checked on every hop, public-IP-pinned sockets, HTML metadata/text, and optional PDF extraction with page references.
- Opt-in Playwright Chromium fallback for script-bearing pages with little static text, with same-site GET resources brokered through the existing pinned fetcher, fresh page contexts and shared time/byte limits.
- Per-page and cumulative source limits, per-day job/source-byte/Bedrock-call budgets, URL/content deduplication and TTL reuse.
- Seven objective-specific structured Bedrock extraction prompts, citation validation against stored source text, financial qualifier checks, conflict retention and fact-only reports.
- Paginated facts/sources, category aliases and versioned report endpoints.
- Outreach generation accepts up to 20 explicitly selected, source-backed facts only for the enrollment's lead. Conflicting, unsupported, hypothetical or cross-lead facts are rejected; generated drafts still require existing human approval.
- Combined dashboard with Excel import/mapping, company/domain search, domain saving independent of Apollo, inline company research/contact workbench, and Lead 360 outreach continuation. `/` and `/dashboard` share the same implementation.
- Job-scoped source snapshots/facts, explicit model/depth cache matching, duplicate worker claiming, report filters/citations/JSON export, and desktop/mobile UI validation.
- Migration `0010_company_intelligence` follows `0009_microsoft_oauth`.

## Not implemented / limitations

- No paid search-provider adapter. A configured search-provider label is surfaced as unsupported; its key is not used. Source discovery is keyless and self-hosted: sitemaps, RSS/Atom, outbound references, GLEIF registry records and, where robots.txt permits, Wikipedia/Wikidata and SEC EDGAR (see [autonomous discovery](company-intelligence-discovery.md)).
- No authenticated pages, paywall/CAPTCHA bypass or automated identity resolution beyond the submitted public website and optional matching lead. Cross-domain discovery only follows robot-permitted, policy-approved sources; sites that disallow automated access are skipped and recorded. Browser fallback deliberately blocks external CDNs/APIs and non-GET interactions, so not every JavaScript site is supported.
- PDF support is bounded text extraction only; scanned/OCR documents are unavailable. `pypdf` is required.
- Verification proves source/quote existence and applies conservative structural checks; it is not legal, accounting or independent human verification. Numerical financial claims without source-backed entity, currency, unit, period and reporting scope are excluded.
- No normalized financial conversions, valuations, market-share estimates, standalone external API, report PDF/Excel export, or automatic research on imports.
- No automatic recovery after a worker process dies mid-job, separate research queue, hard total-job deadline or dollar-denominated cost ceiling. Source collection and individual AWS calls have bounds; DNS/PDF parsing and in-flight work can delay cancellation.

Validation: 104 backend tests, 6 synthetic/mocked browser tests, frontend type-check/production build, disposable SQLite fresh upgrade and no-drift check, plus a migration test preserving an existing lead. No successful live AWS research or paid provider calls were made for this milestone.

Enable the feature explicitly with `COMPANY_INTELLIGENCE_ENABLED=true`. Research does not run for imports automatically and does not send mail or activate campaigns.

## Local activation follow-up

The operator subsequently requested UI testing. Research is now enabled in the private local environment, with the complete bounded research configuration documented in [setup](company-intelligence-setup.md). API/worker settings and Celery registration were verified after recreating API, worker and scheduler. No AWS model/profile/credential or mail configuration was changed, no profile was selected implicitly, and no research was submitted. External search and the other gaps above remain unimplemented; enabling a flag does not enable them.

## Bedrock/profile follow-up

The operator later approved `us.anthropic.claude-sonnet-5-5` as the local default in `us-east-1`, including routing to `us-east-2`/`us-west-2`. The old unprefixed model ID returned `ResourceNotFoundException`. A synthetic live request also established that this model rejects `temperature`; the shared Converse helper now omits that optional parameter and uses model-default sampling while retaining the output-token bound. A subsequent server-default request returned `{"ok": true}` (47 input / 9 output tokens).

A first live ORIX crawl proved that its static homepage was only a four-character JavaScript shell, not useful company evidence. This prompted the explicitly approved browser fallback. Evidence prompts now include the actual validation schema and minimum quote length, rather than inviting invalid short quotes. See [testing](company-intelligence-testing.md) for separate regression and live-run outcomes.
