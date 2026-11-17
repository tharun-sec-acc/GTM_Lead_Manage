# Company Intelligence data model

Alembic revision `0010_company_intelligence` follows `0009_microsoft_oauth` and adds:

- `company_research_profiles`: unique normalized domain and optional unique link to `leads`.
- `research_jobs`: lifecycle, progress, depth, selected inference-profile ARN and aggregate counts.
- `research_agent_runs`: one persisted run per job/role, status, retry/error/output/timing/token usage.
- `research_sources`: versioned public source snapshots, hashes and extracted text.
- `research_job_sources`: immutable job-to-source associations so history does not silently acquire newer sources.
- `research_facts`: canonical category, original string value and optional financial qualifiers, status, hypothesis flag and extraction role.
- `research_citations`: fact-to-source link with verbatim excerpt and optional PDF page.
- `research_reports`: versioned summary, JSON sections and limitations.
- `research_usage` and `research_budgets`: observed token counts and atomic per-day job, Bedrock-call and source-byte limits.

Facts and evidence are retained across job retries; reports remain versioned per company. Foreign keys cascade research-owned records when a profile is deleted and set lead links to null when a lead is deleted. This migration adds tables only; it does not alter or delete existing lead data. Do not run migrations against a user database without the normal deployment approval.

Sources are content-deduplicated per company. Database uniqueness indexes use bounded identifiers/hashes rather than long fact values, URLs or quotations, avoiding oversized PostgreSQL B-tree keys. Extraction deduplicates identical field/value pairs within a job/category; a duplicate queue delivery cannot claim an already-running/completed job.
