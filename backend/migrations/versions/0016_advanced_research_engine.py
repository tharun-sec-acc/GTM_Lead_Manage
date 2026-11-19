"""Advanced Autonomous Research Engine schema extensions.

Revision ID: 0016_advanced_research_engine
Revises: 0015_unified_meetings
"""

from alembic import op
import sqlalchemy as sa

revision = "0016_advanced_research_engine"
down_revision = "0015_unified_meetings"
branch_labels = None
depends_on = None


def upgrade():
    # research_jobs
    op.add_column("research_jobs", sa.Column("documents_analyzed", sa.Integer(), nullable=False, server_default="0"))

    # research_sources
    op.add_column("research_sources", sa.Column("is_document", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("research_sources", sa.Column("mime_type", sa.String(120), nullable=False, server_default="text/html"))
    op.add_column("research_sources", sa.Column("total_pages", sa.Integer(), nullable=True))

    # research_reports
    op.add_column("research_reports", sa.Column("one_page_summary", sa.JSON(), nullable=True))
    op.add_column("research_reports", sa.Column("analysis_data", sa.JSON(), nullable=True))
    op.add_column("research_reports", sa.Column("product_opportunities", sa.JSON(), nullable=True))
    op.add_column("research_reports", sa.Column("what_changed", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("research_reports", "what_changed")
    op.drop_column("research_reports", "product_opportunities")
    op.drop_column("research_reports", "analysis_data")
    op.drop_column("research_reports", "one_page_summary")

    op.drop_column("research_sources", "total_pages")
    op.drop_column("research_sources", "mime_type")
    op.drop_column("research_sources", "is_document")

    op.drop_column("research_jobs", "documents_analyzed")
