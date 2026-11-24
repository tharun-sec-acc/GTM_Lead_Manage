# Market intelligence and opportunity detection

This document describes the **implemented** automotive market-intelligence subsystem. The long-form design
narrative is in [MARKET_INTELLIGENCE_SYSTEM.md](MARKET_INTELLIGENCE_SYSTEM.md); this page is the operational
reference for what runs today.

Code: `backend/app/market_intelligence` (models, routes, schemas, `services/`, `providers/`, `ai/`),
migrations `90a32bdfdc2e_add_automotive_market_intelligence_.py` and
`a23dfc0ad970_add_market_webhook_subscriptions.py`, Celery tasks in `backend/app/tasks.py`, UI in
`frontend/app/market-intelligence/page.tsx` with `frontend/lib/market-intelligence.ts`.

## 1. Pipeline

```text
Celery Beat (300 s)
  -> MarketSource rows due for crawl
  -> SSRF-safe fetch of each source homepage/section (Playwright/HTTP provider)
  -> link filtering + URL canonicalization + SHA-256 content fingerprint
  -> new MarketArticle rows (+ MarketArticleVersion on change)
  -> Bedrock (or heuristic fallback) event classification
  -> MarketCompany resolution (match an existing lead or create a discovered company)
  -> Solwer product matching + explainable dual scoring
  -> OpportunitySignal + MarketAlert
  -> outbound webhook dispatch for high-priority signals
```

The same pipeline is executed synchronously by the inbound webhook endpoint for a single payload.

## 2. Data model

| Table | Purpose |
| --- | --- |
| `market_sources` | Monitored sources with domain, section URLs, category, industry, priority, crawl frequency and enabled flag |
| `market_source_runs` | Crawl audit trail: start/end, articles found, errors |
| `market_articles` | Extracted articles with canonical URL, publisher, author, date, body and SHA-256 fingerprint |
| `market_article_versions` | Revision history when an announcement changes |
| `market_companies` | Discovered companies, domain, parent entity, status (`pending_review`/approved/dismissed) and linked CRM lead |
| `market_events` | Classified developments with the operational problem and event category |
| `product_catalog` | Six Solwer products with segments, personas and pitch angles |
| `product_match_rules` | Weighted keyword/category rules per product |
| `opportunity_signals` | Qualified opportunities with dual scores, rationale, recommended pitch and status |
| `market_alerts` | In-app alerts (read/dismissed) and outbound notification records |
| `company_watchlists` | Domain-level monitoring for named accounts |
| `market_webhook_subscriptions` | Outbound endpoints, optional secret, target type (Slack/Teams/generic), enabled flag |

Seed data: `services/source_registry.py` contains the Solwer product catalogue and 62 Indian automotive
publication, association, government, OEM, supplier and logistics sources with per-source crawl frequencies.

## 3. Classification, matching and scoring

- `ai/event_classifier.py` asks Bedrock for a structured event category, company name, location, the concrete
  operational problem and supporting quotes. If the model is unavailable or the response is not usable, a
  heuristic keyword classifier keeps the pipeline running and the reason is recorded.
- `services/company_resolution.py` compares the extracted company against existing leads (fuzzy name/domain
  match) and against previously discovered companies so one company is not duplicated.
- `services/product_matching.py` matches the event against the six Solwer products and produces the recommended
  outreach pitch and target personas.
- `services/scorer.py` computes two 0-100 scores with a stored points breakdown:
  - **Market Signal Relevance** = product match (max 30) + event strength (max 25) + ICP fit (max 20) +
    recency (max 15) + CRM relationship (max 10);
  - **Sales Readiness** = verified domain (30) + clear operational problem (30) + supporting evidence/links (25)
    + CRM account status (15).
- Priority bands: high `>= 80`, medium `60-79`, low `< 60`. High-priority signals create alerts and trigger
  outbound webhook dispatch.

Scores are explainable heuristics over extracted text; they are not a prediction of purchase intent.

## 4. API

Base path `/api/market-intelligence`:

| Method and path | Purpose |
| --- | --- |
| `GET /overview` | KPI counts, product breakdown, source and alert totals |
| `GET /feed` | Market article/event feed with filters and pagination |
| `GET /opportunities` | Scored opportunities with pitch recommendations |
| `POST /opportunities/{id}/approve`, `/dismiss` | Review action |
| `GET /companies` | Discovered companies |
| `POST /companies/{id}/approve`, `/dismiss` | Promote a discovery into the CRM or dismiss it |
| `GET /sources`, `PATCH /sources/{id}` | List and configure monitored sources |
| `POST /sources/{id}/test`, `/crawl` | Test a source fetch or crawl it immediately |
| `GET /alerts`, `POST /alerts/{id}/read`, `/dismiss` | Alert inbox |
| `GET/POST /watchlists`, `DELETE /watchlists/{id}` | Company watchlists |
| `POST /webhook` | Inbound signal ingestion (see the security note below) |
| `GET/POST/DELETE /webhooks`, `POST /webhooks/test` | Outbound webhook subscriptions and test dispatch |

Outbound dispatch (`services/webhook_dispatcher.py`) posts JSON with `X-Webhook-Secret` and an
`X-GTM-Signature` HMAC-SHA256 of the payload when a secret is configured, and formats Slack/Teams-compatible
payloads.

## 5. UI

`/market-intelligence` provides executive cards (signals today, high-priority opportunities, new companies,
active sources), product opportunity cards, tabs for live feed, qualified opportunities, discovered companies,
source management, watchlists and webhook subscriptions, a number drill-down that shows the announcement, the
identified operational problem, the recommended pitch, target personas and score breakdown, and a webhook
simulator with realistic Indian automotive presets. The sidebar shows an unread-alert badge refreshed every
15 seconds; Lead 360 surfaces market events for that lead.

## 6. Operations

| Concern | Behavior |
| --- | --- |
| Crawl scheduling | `app.tasks.crawl_market_sources_task` every 300 s; each source is crawled when `last_crawl_at + crawl_frequency_minutes` has passed |
| Model dependency | Uses the shared Bedrock helper (`AWS_REGION`, `BEDROCK_MODEL_ID`, credentials inside the worker); a heuristic fallback avoids total failure |
| Network safety | `providers/playwright_provider.py` is the single fetch path and applies URL normalization and SSRF protections |
| Deduplication | SHA-256 of canonical URL + content; repeats are skipped |
| Retention | No automatic pruning; old articles, runs, events and logs accumulate until an operator removes them |

## 7. Security and limitations

- **The inbound `POST /api/market-intelligence/webhook` endpoint has no authentication or signature check.**
  Anyone who can reach the API can inject a signal and trigger Bedrock classification and outbound webhook
  dispatch. Keep the API on loopback, or add a shared secret check before exposing it.
- Outbound webhook targets are operator-supplied URLs; they are not validated against private address ranges,
  so only add endpoints you control.
- Sources are crawled as configured; the pipeline has no politeness budget across the whole registry beyond each
  source's crawl frequency. Disable sources you do not need.
- Classification, company resolution, product matching and scoring are heuristic/LLM-assisted and can be wrong;
  discoveries are `pending_review` until a salesperson approves them.
- Automated coverage: `backend/tests/test_market_intelligence.py` with mocked fetches and Bedrock. No live crawl
  of the seeded registry or live Bedrock classification is exercised by the test suite.
