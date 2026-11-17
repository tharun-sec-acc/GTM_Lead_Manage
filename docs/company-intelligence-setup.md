# Company Intelligence setup

1. Install backend requirements; `pypdf` enables bounded PDF text extraction. For browser fallback, also run `python -m playwright install chromium` (Linux may require `--with-deps`). The Docker image includes Chromium/dependencies.
2. Set `COMPANY_INTELLIGENCE_ENABLED=true` only when research should be available.
3. Configure `AWS_REGION` and the existing approved Bedrock model configuration in the API and worker. If a model requires a profile, the user selects its ARN explicitly in the client; this module does not auto-select or infer a cross-region profile.
4. Configure the normal `DATABASE_URL` and `REDIS_URL` used by the existing application.
5. Apply Alembic revision `0010_company_intelligence` during an approved deployment, then run the existing Celery worker.
6. Submit a public company site. The service uses only the official confirmed domain in the current implementation.

Relevant optional bounds in `.env.example`:

- `RESEARCH_MAX_CONCURRENT_AGENTS`, `RESEARCH_MAX_PAGES_PER_COMPANY`, `RESEARCH_MAX_CRAWL_DEPTH`
- `RESEARCH_REQUEST_TIMEOUT`, `RESEARCH_MAX_DURATION_SECONDS`, `RESEARCH_MAX_CONTENT_SIZE`, `RESEARCH_MAX_TOTAL_CONTENT_SIZE`
- `RESEARCH_CACHE_TTL_HOURS`, `RESEARCH_MAX_RETRIES`
- `RESEARCH_DAILY_BUDGET`, `RESEARCH_DAILY_BEDROCK_CALLS`, `RESEARCH_DAILY_SOURCE_BYTES`
- `RESEARCH_SEARCH_PROVIDER`, `RESEARCH_SEARCH_API_KEY` (reserved for a future verified adapter; currently unused)

The feature is off by default. No provider API key is assumed. The API and worker need access to the existing approved AWS credential chain; never commit credentials or select a profile implicitly.

In the combined dashboard upload/map Excel, search the saved company name/domain, and select **Research**. Check the company/site, approved inference profile and processing consent before submission. **Save domain** stores the domain without invoking Apollo or AWS. Research never activates a campaign or approves an email.

## Current local UI-test environment

On 16 November 2026, the operator requested research activation for manual UI testing. The private `.env` now explicitly contains the following non-secret research settings:

```dotenv
COMPANY_INTELLIGENCE_ENABLED=true
RESEARCH_SEARCH_PROVIDER=
RESEARCH_SEARCH_API_KEY=
RESEARCH_MAX_CONCURRENT_AGENTS=3
RESEARCH_MAX_PAGES_PER_COMPANY=12
RESEARCH_MAX_CRAWL_DEPTH=5
RESEARCH_REQUEST_TIMEOUT=12
RESEARCH_MAX_DURATION_SECONDS=120
RESEARCH_CACHE_TTL_HOURS=24
RESEARCH_MAX_RETRIES=2
RESEARCH_MAX_CONTENT_SIZE=2000000
RESEARCH_MAX_TOTAL_CONTENT_SIZE=8000000
RESEARCH_DAILY_BUDGET=100
RESEARCH_DAILY_BEDROCK_CALLS=500
RESEARCH_DAILY_SOURCE_BYTES=50000000
```

These are limits, not guaranteed completeness, a dollar spending cap or proof of AWS access. The 120-second limit applies to source collection, not the entire research job. Comprehensive mode allows up to 12 pages/depth 5; quick mode still caps collection at 5 pages/depth 1. The source must permit crawling. Search settings remain empty because external search is not implemented.

Existing AWS region/model/credentials, Apollo credentials, Gmail credentials, Microsoft settings, mail flags and daily mail limit were preserved. No inference profile was chosen automatically. `.env.example` still defaults the feature to disabled for new installations.

### Subsequently approved model and browser settings

After a real model-not-found failure, the operator approved this replacement and the JavaScript-site fallback:

```dotenv
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-5-5
RESEARCH_BROWSER_ENABLED=true
```

The profile can route across us-east-1, us-east-2 and us-west-2; this was explicitly approved, not auto-selected. Credentials and mail configuration are unchanged. The shared model helper omits `temperature` because this model rejects it; model-default sampling is used. A live synthetic server-default invocation succeeded. Browser fallback is off by default in code and `.env.example`; see [its restrictions](company-intelligence-sources.md#browser-fallback). After updating code/dependencies, rebuild API, worker and scheduler rather than only recreating old images.

The API, worker and scheduler were recreated with:

```powershell
docker compose config --quiet
docker compose up -d --no-build --no-deps api worker scheduler
```

Verified: API/frontend ready, research enabled in both API and worker with the settings above, research task registered, model configuration present, search unavailable, and zero research jobs at the check. Configuration presence does not verify credential validity or invocation permissions.

## Test from the UI

1. Refresh `http://localhost:3000/dashboard` or open `http://localhost:3000/intelligence`.
2. In the dashboard, search an imported company by name/domain and choose **Research**. If the saved domain is missing/wrong, use **Review -> Domain & people -> Save domain** first; this does not call Apollo. Alternatively, enter a company and its official public website in standalone research.
3. Choose **Quick discovery** for an initial check, or **Comprehensive research** for all seven extraction categories. Comprehensive does not guarantee financial/funding/competitor evidence will exist.
4. Select **Load AWS profiles** and choose an organization-approved profile, reviewing its routing regions. An earlier live diagnostic found that the then-configured base model required an inference profile. Use the server default only if that default is already approved and invocable. Listing profiles requires `bedrock:ListInferenceProfiles`; invocation separately requires `bedrock:InvokeModel` and access to the profile/backing models.
5. Review the company, website and AWS processing/cost notice. Check the processing-consent box, then select **Start research**. This is the action that can contact public websites and incur AWS charges; enabling the environment flag alone does not do so.
6. Watch the persisted job/agent progress. Review citations, dates, source passages, financial qualifiers and coverage limitations. **Retry failed work** retries eligible failed roles; explicit refresh can bypass cached research and incur new calls.
7. Open Lead 360/Compose outreach, select up to 20 relevant reviewed facts, supply approved product context and generate a draft. Generating does not approve or send it.

For testing research only, do not approve emails or activate campaigns. The existing local configuration already allows sending when all gates pass; it was not changed by research activation.

If profile discovery fails, read the UI error and check AWS region/credentials/discovery permission. If invocation fails, check model/profile access separately. Source robots/size/timeout errors and missing official-site evidence can result in partial findings; the system does not fabricate a completed report. Live invocation and ORIX browser text collection were subsequently verified separately; the final combined report retest remains pending. See [actual results](company-intelligence-testing.md#live-model-and-browser-follow-up).

For ORIX after the browser fix, open its old job, choose **Review & refresh research**, review the configured server model/consent, then select **Refresh with new source collection**. Do not rely on ordinary Start or failed-role retry to replace the earlier cached JavaScript shell.
