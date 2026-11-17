# Company Intelligence testing

Run the backend tests from `backend/` with the project's configured test environment. The focused `test_company_intelligence.py` suite covers status and idempotent API submission, URL/IP and robots policies without external calls, evidence/citation validation, financial-claim rejection, category report availability and selected-fact outreach constraints. Existing tests remain part of the regression suite.

Tests use synthetic records and mocked source/Bedrock/Celery boundaries; they do not call a live research site, AWS, Redis or production database and do not send mail. The migration can be checked against a disposable SQLite database during development; never point test migration commands at a user database.

Current scope has no real search provider, public-registry adapter or OAuth integration for research sources. Browser fallback was added subsequently; see the separately approved live checks below.

## Verified milestone

- Full backend regression: **104 passed**, including 28 Company Intelligence cases.
- Frontend type-check and Next.js production build: passed.
- Chromium Playwright: **6 passed**. Covers research/model consent, progress/citations/financial/news filtering, retry/version/cancel, Lead 360 fact selection without approval, mobile navigation/domain search, inline Apollo confirmation, independent domain save, and Excel upload/mapping into the same-company research form.
- Disposable SQLite fresh migration through `0010_company_intelligence` and `alembic check`: passed without drift.
- Automated upgrade from `0009` with a seeded lead preserves that lead and creates empty research tables.

From `backend`, run `..\.venv\Scripts\python.exe -m pytest -q`. From `frontend`, run `npm ci`, `npx playwright install chromium`, `npm run typecheck`, `npm run build`, then `npm test`. The browser runner owns a temporary loopback server on port 3101 and stops it afterward.

Browser uploads use a synthetic mocked API fixture; backend import tests exercise real workbook parsing. These tests do not establish live scraping quality, successful AWS invocation, external email delivery or complete PostgreSQL/Celery concurrency/recovery. No paid research, real outreach or meeting invitations are part of validation.

## Environment activation verification

After the operator requested live UI testing, the private environment was updated and API, worker and scheduler recreated. Read-only checks verified:

- `/health`, `/intelligence/status`, `/intelligence/research?limit=1` and frontend `/dashboard`: HTTP 200.
- Research enabled, model configuration present, external search not configured.
- The whitelisted research settings match in API and worker, including pages 12/depth 5/agents 3 and the configured time/byte/daily bounds.
- `app.company_intelligence.run_research` registered on the Celery worker.
- Live browser research form visible with the enabled API status; Start research remains disabled until required input/processing consent is supplied. No form submission or AWS profile discovery was triggered.
- Existing records preserved: 55 leads, 1 paused campaign, 4 drafts, no accepted messages; 0 research jobs at verification.

This update changed environment/documentation only. The 104 backend and 6 browser passes above are the preceding code-validation results, not a newly repeated suite for the environment change. No live AWS generation, profile discovery, research submission, approval, activation or sending was performed during activation verification. Use [the manual UI steps](company-intelligence-setup.md#test-from-the-ui) for an explicitly approved live run.

## Live model and browser follow-up

The operator then approved the discovered US Sonnet 5.5 profile, synthetic invocation, real ORIX research and a bounded Playwright fallback.

- Runtime default changed from the invalid unprefixed ID to `us.anthropic.claude-sonnet-5-5` in `us-east-1`; API and worker settings matched.
- An initial invocation exposed the model's rejection of `temperature`. After omitting that optional parameter, server-default `converse_json` returned `{"ok": true}`, using 47 input / 9 output tokens. AWS credentials and mail settings were unchanged.
- New regression: **48 passed** across `tests/test_bedrock.py` and `tests/test_company_intelligence.py`. Includes unsupported-temperature handling, opt-in shell rendering/link discovery, private/external/non-GET/robots/media restrictions, failed-resource byte accounting and explicit text-only stylesheet handling. The full 104-test baseline was not rerun for this follow-up.
- Pylance syntax checks passed for the new browser module and modified website adapter before the final small text-only change; the final files were imported/exercised by the passing targeted tests.
- Docker API/worker/scheduler rebuild/recreation succeeded with Chromium installed. Initial Linux dependency failure (`libatomic.so.1`) was fixed in the Dockerfile. Existing database/Redis/frontend containers were retained.
- A real Chromium offline smoke rendered injected JavaScript company text and its same-site link using the pinned-fetcher stub, consuming 424 resource bytes with no notes.
- First live research job `e26f9785-0216-4f3a-9c4e-0aafb8fb3deb` was partial: static ORIX HTML contained only `ORIX`; zero facts and an invalid short company quote. The prompt now includes the actual evidence schema/minimum quote bound.
- Initial browser-backed job `f91523fa-7ea9-4990-9fd0-28012b347367` completed all roles without model errors, but remained partial with zero facts because the site failed a stylesheet preload while external font dependencies were blocked.
- After explicit text-only stylesheet handling, a live collector-only check fetched `https://orixindia.com/` as `playwright`: **763 extracted characters**, **1,383,815 fetched bytes**, **no collection notes**. This proves live JavaScript text retrieval, not a completed cited report. The two-page-budget check discovered only one page; it does not prove complete site coverage.
- The final research POST after that fix was **not attempted**: the execution environment twice failed to initialize with local-network access unavailable. No additional job, report, citation-backed findings or final full-flow success can be claimed. No environment restrictions were bypassed.

Older jobs and immutable source records remain intact. A source's original retrieval timestamp may predate a forced refresh when its content hash is unchanged; this alone is not evidence that the refresh reused the HTTP cache. No mail/draft generation, approval, campaign activation or sending was performed.

Next manual validation: open the ORIX job, select **Review & refresh research**, keep **Use configured server model**, approve processing, and use **Refresh with new source collection**. Check new `playwright` sources, actual supported facts/citations and truthful unavailable financial/news categories. The ordinary Start action may reuse an earlier partial job; retrying only failed roles does not necessarily recollect sources.
