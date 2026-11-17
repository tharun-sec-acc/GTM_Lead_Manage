"""Persist Apollo search results and enrich contact profile fields."""

from alembic import op
import sqlalchemy as sa

revision = "0007_apollo_contact_management"
down_revision = "0006_multisheet_import"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("contacts") as batch:
        batch.alter_column("apollo_id", existing_type=sa.String(length=100), nullable=True)
        batch.add_column(sa.Column("department", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("seniority", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("linkedin_url", sa.Text(), nullable=True))
        batch.add_column(sa.Column("location", sa.String(length=500), nullable=True))
        batch.add_column(sa.Column("is_key_decision_maker", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("verification_status", sa.String(length=30), nullable=False, server_default="unverified"))
        batch.add_column(sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                                  server_default=sa.func.now()))
    op.create_table(
        "apollo_search_results",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("lead_id", sa.String(length=36), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("apollo_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("department", sa.String(length=255), nullable=True),
        sa.Column("seniority", sa.String(length=100), nullable=True),
        sa.Column("organization_name", sa.String(length=500), nullable=True),
        sa.Column("organization_domain", sa.String(length=253), nullable=True),
        sa.Column("linkedin_url", sa.Text(), nullable=True),
        sa.Column("has_email", sa.Boolean(), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("lead_id", "apollo_id", name="uq_apollo_search_lead_person"),
    )
    op.create_index("ix_apollo_search_results_lead_id", "apollo_search_results", ["lead_id"])


def downgrade():
    op.drop_index("ix_apollo_search_results_lead_id", table_name="apollo_search_results")
    op.drop_table("apollo_search_results")
    with op.batch_alter_table("contacts") as batch:
        batch.drop_column("updated_at")
        batch.drop_column("is_active")
        batch.drop_column("verification_status")
        batch.drop_column("is_key_decision_maker")
        batch.drop_column("location")
        batch.drop_column("linkedin_url")
        batch.drop_column("seniority")
        batch.drop_column("department")
        batch.alter_column("apollo_id", existing_type=sa.String(length=100), nullable=False)
