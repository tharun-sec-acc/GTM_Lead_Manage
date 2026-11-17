# Autonomous Discovery Engine

The company-intelligence research job builds its own source set. It does not need an external
search API, and no third-party research provider is part of the required path. AWS Bedrock is used
only for analysis and synthesis of evidence that the crawler has already retrieved.

Code: `backend/app/company_intelligence/discovery/`

| Module | Responsibility |
| --- | --- |
| `queries.py` | Deterministic query expansion from legal/trading name, domain, subsidiaries, brands, products, former names, leaders, industry, geography and research categories. Terms that identify the company are separated from generic category words. |
| `policy.py` | URL normalisation (fragments and tracking parameters removed), SSRF/host blocking, source typing, research-category mapping, relevance scoring, reliability labels. |
| `adapters.py` | Keyless discovery sources: official sitemaps (apex and `www`), RSS/Atom feeds, references inside collected text, outbound links, Wikipedia/Wikidata search, SEC EDGAR full-text Atom feed, GLEIF legal-entity registry API. |
| `engine.py` | Orchestrates a discovery run: tasks → candidates → selection → retrieval → persisted sources → coverage metrics. |

## Operating path

1. The existing official-site crawl runs first (unchanged, robots-aware, SSRF-pinned).
2. Discovery expands roughly thirty deterministic queries across the seven research roles (deduplicated
   by text and category).
3. Adapters collect candidate URLs from the official domain **and** other domains.
4. Each candidate is normalised, checked against SSRF policy, deduplicated against already
   collected sources and the current run, and scored.
5. Candidates are capped by total count, distinct-domain count, per-domain count and minimum score.
6. Each queued candidate is fetched with robots enforcement, crawl delay, per-page byte limits and
   the job deadline. Static HTTP is tried first; when an HTML page renders as a thin shell and
   `research_browser_enabled` is on, a text-only Playwright render of the same URL is attempted.
   PDFs go through the existing PDF extractor, feeds are parsed as RSS/Atom, and public JSON
   registry/API records (for example GLEIF LEI records) are flattened into retrievable text.
7. Retrieved content is persisted as a `research_sources` row (URL, canonical URL, title, publisher,
   publication date, retrieval timestamp, content hash, extraction method, category, reliability,
   excerpt and text) and linked to the job through `research_job_sources`.
8. Analysis roles then use the same bounded source payload as before, so cross-domain evidence flows
   into Bedrock findings with citations.

A discovered URL is a **lead**, never evidence. A fact is only grounded once the page or document was
retrieved and its text persisted. Candidate states record this progression:

`discovered → queued → retrieved → extracted → relevant → evidence_bearing → verified`
plus `conflicting`, `rejected`, `unavailable`.

## Metrics

Each run stores counters and per-category coverage on `research_discovery_runs`:

- discovery tasks created, candidate URLs discovered, unique domains discovered
- URLs rejected (policy, robots, score, caps), URLs queued
- successful HTTP retrievals, browser retrievals, PDFs processed
- sources with usable content, evidence-bearing sources, extraction failures, duplicate sources
- budget-exhausted events, cross-domain candidates, distinct domains fetched
- per-category sources / evidence-bearing counts and `covered_categories` out of seven

A run that hits its page budget is reported as budget-limited. It never claims comprehensive
internet coverage.

## API

`GET /intelligence/research/{job_id}/discovery` returns the latest run for a job:

```json
{
  "job_id": "...",
  "status": "completed | failed | disabled | not_run",
  "queries_count": 78,
  "counters": {"candidate_urls_discovered": 64, "urls_queued": 22, "cross_domain_sources": 15},
  "coverage": {"company": {"sources": 3, "evidence_bearing": 2, "relevant": 1}, "covered_categories": 5},
  "tasks": [{"query": "Acme Ltd annual report", "category": "financial", "candidates_found": 2}],
  "candidates": [{"url": "...", "state": "evidence_bearing", "retrieval_method": "http_pdf"}],
  "limitations": ["..."]
}
```

`GET /intelligence/status` now reports that discovery is keyless rather than saying external search
is unimplemented.

## Configuration

| Setting | Default | Purpose |
| --- | --- | --- |
| `RESEARCH_DISCOVERY_ENABLED` | `true` | Master switch; when off only the official site is collected. |
| `RESEARCH_DISCOVERY_MAX_CANDIDATES` | `30` | Candidates queued per run. |
| `RESEARCH_DISCOVERY_MAX_DOMAINS` | `12` | Distinct domains per run. |
| `RESEARCH_DISCOVERY_MAX_CANDIDATES_PER_DOMAIN` | `4` | Per-domain candidate cap. |
| `RESEARCH_DISCOVERY_MIN_SCORE` | `0.45` | Minimum relevance score. |
| `RESEARCH_DISCOVERY_MAX_BYTES` | `4000000` | Byte budget for a discovery run (also subject to the company's daily research budget). |
| `RESEARCH_DISCOVERY_DEADLINE_SECONDS` | `90` | Wall-clock deadline for discovery. |
| `RESEARCH_DISCOVERY_WIKIPEDIA_ENABLED` | `true` | Wikipedia/Wikidata keyless index adapter. |
| `RESEARCH_DISCOVERY_SEC_ENABLED` | `true` | SEC EDGAR Atom adapter. |
| `RESEARCH_DISCOVERY_GLEIF_ENABLED` | `true` | GLEIF legal-entity registry adapter (keyless). |
| `RESEARCH_BROWSER_ENABLED` | `false` | Enables the text-only Playwright render of JavaScript shells. |
| `RESEARCH_BROWSER_WAIT_MS` | `10000` | How long the browser waits for rendered body text before collecting what is available. |

No search-provider key is read or required. External providers, if ever added, must be opt-in
adapters with explicit configuration, cost visibility and operator approval.

## Safety

- Every request and redirect goes through `_pinned_request`: scheme/port/credential rules, DNS
  resolution checks, private/loopback/link-local/metadata blocking, redirect cap, byte cap and
  deadline.
- `policy.normalize_candidate_url` rejects private hosts, unsafe ports and credential-bearing URLs
  before anything is queued.
- robots.txt is honoured per host and fails closed; crawl delays are respected.
- No CAPTCHA, paywall, authentication or access-restriction bypass is attempted.
- Retrieved text is untrusted data and is never treated as model instructions.
- Failure of any adapter or of the whole discovery run never fails the research job; it is recorded
  as a limitation.

## Recorded live runs (17 November 2026)

Each run used a throw-away SQLite database, the local crawler only and no search-provider key. The
homepage was fetched first and its links (plus up to three topical official pages) were passed in as
official-site seeds, mirroring what the orchestrator does after its official crawl. No Bedrock call
was made in these probes.

Cross-domain counts below exclude the organization's own subdomains (for example `press.siemens.com`).

| Company / domain | Candidates | Domains | Queued | Retrieved | Evidence-bearing | Cross-domain sources | Categories |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DENSO Corporation / `denso.com` | 0 | 0 | 0 | 0 | 0 | 0 | 0/7 |
| Microsoft Corporation / `www.microsoft.com` | 186 | 20 | 12 | 5 HTTP | 5 | 0 | 1/7 |
| Siemens AG / `www.siemens.com` | 47 | 5 | 9 | 7 HTTP (3 JSON registry) | 7 | 3 | 2/7 |

What these runs actually show:

- The Siemens run retrieved seven independent sources with real text (2.6k-18.7k characters), including
  three GLEIF LEI registry records on `api.gleif.org` discovered from the company name alone. All seven
  were linked to the job as citations. Failures were recorded: sitemap 404 and oversize sitemaps,
  robots-blocked Wikipedia/Wikidata/SEC APIs, and one subdomain whose robots file could not be verified.
- The Microsoft run discovered 186 candidate URLs across 20 hosts, rejected 148 on policy/score/caps,
  retrieved five in-domain pages and recorded five retrieval failures (redirect-limit and non-document
  responses).
- The DENSO run demonstrates failure handling: `denso.com` has no resolvable apex address from this
  network, so the sitemap and feed adapters reported DNS failure and the run completed with zero sources
  rather than inventing coverage.
- No PDF was encountered in these runs, and the Playwright fallback did not trigger because every
  retrieved HTML page already had usable static text. Both paths are covered by mocked tests.
- Wikipedia/Wikidata and SEC EDGAR disallow these automated requests in robots.txt, so they are skipped
  with a recorded limitation instead of being bypassed. External coverage is therefore limited by site
  policy and the per-run domain/page budgets, not claimed as comprehensive.
- Bedrock was then exercised live with the environment configuration (`us-east-1`,
  `us.anthropic.claude-sonnet-5-5`): one simple grounded-extraction prompt, and the real
  `extract_category_facts` roles run against three GLEIF sources collected in a 12.6-second discovery
  pass. The `company` role returned 14 facts and the `news` role 6 facts (4,110/2,317 and 4,078/1,431
  input/output tokens); every returned quote was an exact substring of its stored source text, usage
  was recorded, and the model explicitly flagged that the three LEI records belong to different Siemens
  entities rather than merging them. The full seven-role report synthesis and report rendering were not
  exercised in this probe.

## Tests

`backend/tests/test_research_discovery.py` covers query expansion, URL policy/SSRF rejection,
classification and scoring, a full mocked run (cross-domain sources, HTTP and PDF methods, dedupe,
persisted citations, coverage), robots rejection, budget exhaustion, retrieval failure and the API
payload. Live network coverage is not asserted by the suite.
