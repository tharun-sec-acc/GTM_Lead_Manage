"""Add autonomous research discovery runs, tasks and candidate sources."""

from alembic import op
import sqlalchemy as sa

revision = "0013_research_discovery"
down_revision = "0012_product_attribution"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "research_discovery_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("research_jobs.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("company_id", sa.String(36),
                  sa.ForeignKey("company_research_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="running"),
        sa.Column("queries_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("counters", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("coverage", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("limitations", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_research_discovery_runs_job", "research_discovery_runs",
                    ["job_id", "created_at"])

    op.create_table(
        "research_discovery_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36),
                  sa.ForeignKey("research_discovery_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("category", sa.String(40), nullable=False, server_default="company"),
        sa.Column("source_type", sa.String(40), nullable=False, server_default="query"),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("candidates_found", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "query", "category", name="uq_research_discovery_task"),
    )
    op.create_index("ix_research_discovery_tasks_run_id", "research_discovery_tasks", ["run_id"])

    op.create_table(
        "research_candidate_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36),
                  sa.ForeignKey("research_discovery_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.String(36),
                  sa.ForeignKey("company_research_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("normalized_url", sa.Text, nullable=False),
        sa.Column("domain", sa.String(253), nullable=False, server_default=""),
        sa.Column("title", sa.String(1000), nullable=False, server_default=""),
        sa.Column("source_category", sa.String(40), nullable=False, server_default="other"),
        sa.Column("discovered_via", sa.String(60), nullable=False, server_default=""),
        sa.Column("state", sa.String(30), nullable=False, server_default="discovered"),
        sa.Column("score", sa.Float, nullable=False, server_default="0"),
        sa.Column("matched_terms", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("relevance_note", sa.Text, nullable=True),
        sa.Column("http_status", sa.Integer, nullable=True),
        sa.Column("retrieval_method", sa.String(24), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("source_id", sa.String(36),
                  sa.ForeignKey("research_sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "normalized_url", name="uq_research_candidate_run_url"),
    )
    op.create_index("ix_research_candidate_sources_run_id", "research_candidate_sources", ["run_id"])
    op.create_index("ix_research_candidate_run_state", "research_candidate_sources",
                    ["run_id", "state"])


def downgrade():
    op.drop_index("ix_research_candidate_run_state", table_name="research_candidate_sources")
    op.drop_index("ix_research_candidate_sources_run_id", table_name="research_candidate_sources")
    op.drop_table("research_candidate_sources")
    op.drop_index("ix_research_discovery_tasks_run_id", table_name="research_discovery_tasks")
    op.drop_table("research_discovery_tasks")
    op.drop_index("ix_research_discovery_runs_job", table_name="research_discovery_runs")
    op.drop_table("research_discovery_runs")
