"""Initial import and contact schema."""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content", sa.LargeBinary, nullable=False),
        sa.Column("headers", sa.JSON, nullable=False),
        sa.Column("mapping", sa.JSON, nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "leads",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_name", sa.String(500), nullable=False),
        sa.Column("company_key", sa.String(500), nullable=False),
        sa.Column("domain", sa.String(253), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("revenue", sa.Text, nullable=True),
        sa.Column("phone", sa.Text, nullable=True),
        sa.Column("remarks", sa.Text, nullable=True),
        sa.Column("key_person_info", sa.Text, nullable=True),
        sa.Column("extra", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_leads_company_key", "leads", ["company_key"])
    op.create_index("ix_leads_email", "leads", ["email"])
    op.create_table(
        "import_rows",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("batch_id", sa.String(36), sa.ForeignKey("batches.id"), nullable=False),
        sa.Column("row_number", sa.Integer, nullable=False),
        sa.Column("original", sa.JSON, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("lead_id", sa.String(36), sa.ForeignKey("leads.id"), nullable=True),
        sa.UniqueConstraint("batch_id", "row_number", name="uq_batch_row"),
    )
    op.create_table(
        "contacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("lead_id", sa.String(36), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("apollo_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(500), nullable=True),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("lead_id", "apollo_id", name="uq_contact_apollo"),
    )


def downgrade():
    op.drop_table("contacts")
    op.drop_table("import_rows")
    op.drop_index("ix_leads_email", table_name="leads")
    op.drop_index("ix_leads_company_key", table_name="leads")
    op.drop_table("leads")
    op.drop_table("batches")
