from datetime import datetime

from sqlalchemy import (DateTime, Float, ForeignKey, Index, Integer, JSON, String,
                        Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models import new_id, now


class CompanyResearchProfile(Base):
    __tablename__ = "company_research_profiles"
    __table_args__ = (
        UniqueConstraint("domain", name="uq_research_company_domain"),
        UniqueConstraint("lead_id", name="uq_research_company_lead"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"), nullable=True)
    company_name: Mapped[str] = mapped_column(String(500))
    domain: Mapped[str] = mapped_column(String(253), nullable=False)
    country: Mapped[str | None] = mapped_column(String(100))
    registration_id: Mapped[str | None] = mapped_column(String(200))
    latest_job_id: Mapped[str | None] = mapped_column(String(36))
    last_researched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ResearchJob(Base):
    __tablename__ = "research_jobs"
    __table_args__ = (Index("ix_research_jobs_company_created", "company_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("company_research_profiles.id", ondelete="CASCADE"))
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="queued")
    stage: Mapped[str] = mapped_column(String(80), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    depth: Mapped[str] = mapped_column(String(20), default="quick")
    force_refresh: Mapped[bool] = mapped_column(default=False)
    inference_profile_id: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    error: Mapped[str | None] = mapped_column(Text)
    pages_processed: Mapped[int] = mapped_column(Integer, default=0)
    sources_count: Mapped[int] = mapped_column(Integer, default=0)
    facts_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchAgentRun(Base):
    __tablename__ = "research_agent_runs"
    __table_args__ = (UniqueConstraint("job_id", "agent", name="uq_research_job_agent"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("research_jobs.id", ondelete="CASCADE"), index=True)
    agent: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(24), default="pending")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    output: Mapped[dict | None] = mapped_column(JSON)
    token_usage: Mapped[dict | None] = mapped_column(JSON)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchJobSource(Base):
    __tablename__ = "research_job_sources"

    job_id: Mapped[str] = mapped_column(ForeignKey("research_jobs.id", ondelete="CASCADE"), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("research_sources.id", ondelete="CASCADE"), primary_key=True)


class ResearchSource(Base):
    __tablename__ = "research_sources"
    __table_args__ = (
        UniqueConstraint("company_id", "content_hash", name="uq_research_source_company_hash"),
        Index("ix_research_source_hash", "content_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("company_research_profiles.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(Text)
    canonical_url: Mapped[str] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(String(253))
    title: Mapped[str] = mapped_column(String(1000), default="")
    publisher: Mapped[str | None] = mapped_column(String(500))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    content_hash: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(40), default="company")
    reliability: Mapped[str] = mapped_column(String(24), default="official")
    retrieval_method: Mapped[str] = mapped_column(String(24), default="http")
    excerpt: Mapped[str] = mapped_column(Text, default="")
    content_text: Mapped[str] = mapped_column(Text, default="")
    page_number: Mapped[int | None] = mapped_column(Integer)


class ResearchFact(Base):
    __tablename__ = "research_facts"
    __table_args__ = (
        Index("ix_research_facts_company_category", "company_id", "category"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("company_research_profiles.id", ondelete="CASCADE"))
    job_id: Mapped[str] = mapped_column(ForeignKey("research_jobs.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(40))
    field_name: Mapped[str] = mapped_column(String(200))
    value: Mapped[str] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(80))
    currency: Mapped[str | None] = mapped_column(String(20))
    reporting_period: Mapped[str | None] = mapped_column(String(100))
    entity_scope: Mapped[str | None] = mapped_column(String(300))
    verification_status: Mapped[str] = mapped_column(String(32), default="reported")
    confidence: Mapped[float | None] = mapped_column(Float)
    hypothesis: Mapped[bool] = mapped_column(default=False)
    extraction_agent: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ResearchCitation(Base):
    __tablename__ = "research_citations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    fact_id: Mapped[str] = mapped_column(ForeignKey("research_facts.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("research_sources.id", ondelete="CASCADE"), index=True)
    excerpt: Mapped[str] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)


class ResearchReport(Base):
    __tablename__ = "research_reports"
    __table_args__ = (UniqueConstraint("company_id", "version", name="uq_research_report_company_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("company_research_profiles.id", ondelete="CASCADE"))
    job_id: Mapped[str] = mapped_column(ForeignKey("research_jobs.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    summary: Mapped[str] = mapped_column(Text, default="")
    sections: Mapped[list] = mapped_column(JSON, default=list)
    limitations: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ResearchUsage(Base):
    __tablename__ = "research_usage"
    __table_args__ = (Index("ix_research_usage_created", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("research_jobs.id", ondelete="CASCADE"), index=True)
    agent: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(2048), default="")
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ResearchBudget(Base):
    __tablename__ = "research_budgets"

    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    jobs: Mapped[int] = mapped_column(Integer, default=0)
    bedrock_calls: Mapped[int] = mapped_column(Integer, default=0)
    source_bytes: Mapped[int] = mapped_column(Integer, default=0)


class ResearchDiscoveryRun(Base):
    __tablename__ = "research_discovery_runs"
    __table_args__ = (Index("ix_research_discovery_runs_job", "job_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("research_jobs.id", ondelete="CASCADE"))
    company_id: Mapped[str] = mapped_column(ForeignKey("company_research_profiles.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(24), default="running")
    queries_count: Mapped[int] = mapped_column(Integer, default=0)
    counters: Mapped[dict] = mapped_column(JSON, default=dict)
    coverage: Mapped[dict] = mapped_column(JSON, default=dict)
    limitations: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ResearchDiscoveryTask(Base):
    __tablename__ = "research_discovery_tasks"
    __table_args__ = (
        UniqueConstraint("run_id", "query", "category", name="uq_research_discovery_task"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("research_discovery_runs.id", ondelete="CASCADE"), index=True)
    query: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40), default="company")
    source_type: Mapped[str] = mapped_column(String(40), default="query")
    status: Mapped[str] = mapped_column(String(24), default="pending")
    candidates_found: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ResearchCandidateSource(Base):
    __tablename__ = "research_candidate_sources"
    __table_args__ = (
        UniqueConstraint("run_id", "normalized_url", name="uq_research_candidate_run_url"),
        Index("ix_research_candidate_run_state", "run_id", "state"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("research_discovery_runs.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("company_research_profiles.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(Text)
    normalized_url: Mapped[str] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(String(253), default="")
    title: Mapped[str] = mapped_column(String(1000), default="")
    source_category: Mapped[str] = mapped_column(String(40), default="other")
    discovered_via: Mapped[str] = mapped_column(String(60), default="")
    state: Mapped[str] = mapped_column(String(30), default="discovered")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    matched_terms: Mapped[list] = mapped_column(JSON, default=list)
    relevance_note: Mapped[str | None] = mapped_column(Text)
    http_status: Mapped[int | None] = mapped_column(Integer)
    retrieval_method: Mapped[str | None] = mapped_column(String(24))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    source_id: Mapped[str | None] = mapped_column(ForeignKey("research_sources.id", ondelete="SET NULL"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
