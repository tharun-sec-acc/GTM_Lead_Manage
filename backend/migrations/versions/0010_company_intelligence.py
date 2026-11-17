"""Create evidence-backed company intelligence tables."""

from alembic import op
import sqlalchemy as sa

revision = "0010_company_intelligence"
down_revision = "0009_microsoft_oauth"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "company_research_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("lead_id", sa.String(36), sa.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True),
        sa.Column("company_name", sa.String(500), nullable=False),
        sa.Column("domain", sa.String(253), nullable=False),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("registration_id", sa.String(200), nullable=True),
        sa.Column("latest_job_id", sa.String(36), nullable=True),
        sa.Column("last_researched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("domain", name="uq_research_company_domain"),
        sa.UniqueConstraint("lead_id", name="uq_research_company_lead"),
    )
    op.create_table(
        "research_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("company_research_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lead_id", sa.String(36), sa.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("stage", sa.String(80), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("depth", sa.String(20), nullable=False),
        sa.Column("force_refresh", sa.Boolean(), nullable=False),
        sa.Column("inference_profile_id", sa.String(2048), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("pages_processed", sa.Integer(), nullable=False),
        sa.Column("sources_count", sa.Integer(), nullable=False),
        sa.Column("facts_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_research_jobs_company_created", "research_jobs", ["company_id", "created_at"])
    op.create_table(
        "research_agent_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent", sa.String(80), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("token_usage", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("job_id", "agent", name="uq_research_job_agent"),
    )
    op.create_index("ix_research_agent_runs_job_id", "research_agent_runs", ["job_id"])
    op.create_table(
        "research_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("company_research_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(253), nullable=False),
        sa.Column("title", sa.String(1000), nullable=False),
        sa.Column("publisher", sa.String(500), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("reliability", sa.String(24), nullable=False),
        sa.Column("retrieval_method", sa.String(24), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.UniqueConstraint("company_id", "content_hash", name="uq_research_source_company_hash"),
    )
    op.create_index("ix_research_source_hash", "research_sources", ["content_hash"])
    op.create_table(
        "research_job_sources",
        sa.Column("job_id", sa.String(36), sa.ForeignKey("research_jobs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("research_sources.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "research_facts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("company_research_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("field_name", sa.String(200), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("unit", sa.String(80), nullable=True),
        sa.Column("currency", sa.String(20), nullable=True),
        sa.Column("reporting_period", sa.String(100), nullable=True),
        sa.Column("entity_scope", sa.String(300), nullable=True),
        sa.Column("verification_status", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("hypothesis", sa.Boolean(), nullable=False),
        sa.Column("extraction_agent", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_research_facts_company_category", "research_facts", ["company_id", "category"])
    op.create_table(
        "research_citations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("fact_id", sa.String(36), sa.ForeignKey("research_facts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("research_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
    )
    op.create_index("ix_research_citations_fact_id", "research_citations", ["fact_id"])
    op.create_index("ix_research_citations_source_id", "research_citations", ["source_id"])
    op.create_table(
        "research_reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("company_research_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("sections", sa.JSON(), nullable=False),
        sa.Column("limitations", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "version", name="uq_research_report_company_version"),
    )
    op.create_index("ix_research_reports_job_id", "research_reports", ["job_id"])
    op.create_table(
        "research_usage",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent", sa.String(80), nullable=False),
        sa.Column("model", sa.String(2048), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_research_usage_job_id", "research_usage", ["job_id"])
    op.create_index("ix_research_usage_created", "research_usage", ["created_at"])
    op.create_table(
        "research_budgets",
        sa.Column("day", sa.String(10), primary_key=True),
        sa.Column("jobs", sa.Integer(), nullable=False),
        sa.Column("bedrock_calls", sa.Integer(), nullable=False),
        sa.Column("source_bytes", sa.Integer(), nullable=False),
    )


def downgrade():
    op.drop_table("research_budgets")
    op.drop_table("research_usage")
    op.drop_table("research_reports")
    op.drop_table("research_citations")
    op.drop_table("research_facts")
    op.drop_table("research_job_sources")
    op.drop_table("research_sources")
    op.drop_table("research_agent_runs")
    op.drop_index("ix_research_jobs_company_created", table_name="research_jobs")
    op.drop_table("research_jobs")
    op.drop_table("company_research_profiles")
