# Sources, safety and evidence

## Current adapter

The implemented adapter fetches unauthenticated public pages on the user-confirmed host using standard HTTP/HTTPS ports. It checks `robots.txt` before crawling and fails closed if the policy cannot be retrieved. It extracts title, selected metadata, visible HTML text, same-host links and, when `pypdf` is installed, bounded PDF text. Static HTTP is tried first. With `RESEARCH_BROWSER_ENABLED=true`, script-bearing HTML with fewer than 200 extracted characters uses a headless Chromium fallback; rendered links then enter the same bounded crawl.

There is no production search-provider implementation. Search-provider environment values are reported as unsupported, not called. Official RSS/Atom feeds, sitemaps, outbound references, GLEIF legal-entity records and (where robots permits) Wikipedia/Wikidata and SEC EDGAR are discoverable through the autonomous discovery engine described in [autonomous discovery](company-intelligence-discovery.md); discovered URLs are fetched only after policy, robots and budget checks. Authenticated, paywalled, CAPTCHA-protected or access-controlled resources are not bypassed.

## Network controls

- Rejects URL credentials, non-HTTP(S) schemes, local/private/reserved IP literals and nonstandard ports.
- Resolves every host and rejects mixed public/private DNS answers.
- Connects directly to a validated public IP; HTTPS keeps the original host for SNI/certificate verification and the HTTP Host header.
- Revalidates destination and DNS for each redirect; redirects and discovered links are restricted to the confirmed domain (with or without `www`).
- Bounds timeout, response size, successful pages, attempted page requests (at most twice the page limit), crawl depth, source-collection duration, cumulative bytes, redirect count and PDF pages. Opt-in browser rendering additionally allows at most 60 resource fetches per crawl; their bytes share the cumulative source budget. Failed resources consume their reserved byte allowance. OS DNS resolution, PDF parsing and browser shutdown are not hard process-isolated deadlines.
- HTTP 404 robots responses mean no policy; other retrieval errors fail closed. Applicable crawl-delay/request-rate limits are honored; delays over 10 seconds are unsupported and stop collection. Redirect targets must also pass robots rules.
- Failed downloads conservatively consume their reserved byte allowance, so retries cannot evade the cumulative application budget. One validated IP is attempted per hop, rather than silently retrying an unbounded DNS address list.

## Browser fallback

The backend image installs Playwright Chromium and its Linux dependencies. A browser is started lazily and reused within a crawl; each rendered page gets a fresh context. Chromium uses a nonfunctional proxy to prevent direct network access. Context routes fulfill approved requests through the same public-IP-pinned Python HTTP fetcher, with robots/redirect/port/time/byte checks. Only same-site GET documents, scripts and fetch/XHR resources are fetched. Same-site stylesheets deliberately resolve to an explicitly empty research stylesheet: this is text-only rendering, not visual reproduction, and prevents visual font-import failures from blocking SPA content. External CDNs/APIs, images, fonts, media, non-GET requests, WebSockets and service workers are blocked. No forms are filled and no access controls are bypassed. Some sites cannot render under these restrictions; failures/short rendered content are reported rather than replaced with invented evidence. Rendered snapshots are labeled `playwright`.

Content-identical pages reuse immutable source records. Consequently an existing source's `retrieved_at` can predate a forced-refresh job even when it was freshly fetched; job/source association plus worker execution and content hash must be considered when checking freshness.

## Evidence

Source snapshots store original/canonical URL, domain, title, dates found in page metadata, retrieval time, hash, category, reliability, retrieval method and normalized text. A fact is stored only with an existing source ID and a verbatim excerpt that appears in that stored text. Unsupported quotes or claims are rejected; missing and conflicting categories remain explicit. Source publication dates are parsed from metadata, never invented.

Financial amounts preserve their extracted value; this implementation does not convert currencies or units. A numerical financial fact is accepted only when its source excerpt also supports legal-entity scope, currency, unit and reporting period; otherwise it is omitted.

The official-site crawl starts at the confirmed domain's HTTPS homepage, does not infer a different official domain and follows only `www`. Cross-domain pages are reached separately by the discovery engine, which applies the same pinned/robots/size/deadline envelope and records which page content actually supported each finding. Sites hosted on separate investor/news domains may still be missed when robots policy or budgets exclude them. Quotes are evidence to review, not independently audited conclusions.
