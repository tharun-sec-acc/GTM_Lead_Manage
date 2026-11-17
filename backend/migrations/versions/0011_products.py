"""Add products, product_leads, product_opportunities, email_templates,
email_template_versions, email_attachments, research_fact_overrides tables;
add product_id column to campaigns and batches."""

from alembic import op
import sqlalchemy as sa

revision = "0011_products"
down_revision = "0010_company_intelligence"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "products",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("short_description", sa.String(500), nullable=True),
        sa.Column("logo_url", sa.Text, nullable=True),
        sa.Column("primary_color", sa.String(20), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("product_context", sa.Text, nullable=True),
        sa.Column("value_proposition", sa.Text, nullable=True),
        sa.Column("target_industries", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "product_leads",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("product_id", sa.String(36), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("lead_id", sa.String(36), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("stage", sa.String(50), nullable=False, server_default="prospect"),
        sa.Column("priority", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("owner_id", sa.String(36), nullable=True),
        sa.Column("sales_notes", sa.Text, nullable=True),
        sa.Column("associated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("product_id", "lead_id", name="uq_product_lead"),
    )
    op.create_table(
        "product_opportunities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("product_lead_id", sa.String(36), sa.ForeignKey("product_leads.id"), nullable=False),
        sa.Column("research_job_id", sa.String(36), sa.ForeignKey("research_jobs.id"), nullable=True),
        sa.Column("opportunity_summary", sa.Text, nullable=True),
        sa.Column("pain_points", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("use_cases", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("relevance_score", sa.Float, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("evidence_fact_ids", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("manual_override", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "email_templates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("product_id", sa.String(36), sa.ForeignKey("products.id"), nullable=True),
        sa.Column("parent_template_id", sa.String(36), sa.ForeignKey("email_templates.id"), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("type", sa.String(50), nullable=False, server_default="custom"),
        sa.Column("subject_template", sa.String(998), nullable=False, server_default=""),
        sa.Column("body_template", sa.Text, nullable=False, server_default=""),
        sa.Column("variables", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "email_template_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("template_id", sa.String(36), sa.ForeignKey("email_templates.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("subject_template", sa.String(998), nullable=False, server_default=""),
        sa.Column("body_template", sa.Text, nullable=False, server_default=""),
        sa.Column("variables", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "email_attachments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("message_id", sa.String(36), sa.ForeignKey("email_messages.id"), nullable=True),
        sa.Column("upload_session_id", sa.String(36), nullable=False),
        sa.Column("filename_safe", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(127), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("upload_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "research_fact_overrides",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("fact_id", sa.String(36), sa.ForeignKey("research_facts.id"), nullable=False),
        sa.Column("product_id", sa.String(36), sa.ForeignKey("products.id"), nullable=True),
        sa.Column("override_value", sa.Text, nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("created_by_note", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Index("ix_research_fact_overrides_fact_id", "fact_id"),
    )
    op.add_column("campaigns", sa.Column("product_id", sa.String(36), nullable=True))
    op.add_column("batches", sa.Column("product_id", sa.String(36), nullable=True))


def downgrade():
    op.drop_column("batches", "product_id")
    op.drop_column("campaigns", "product_id")
    op.drop_table("research_fact_overrides")
    op.drop_table("email_attachments")
    op.drop_table("email_template_versions")
    op.drop_table("email_templates")
    op.drop_table("product_opportunities")
    op.drop_table("product_leads")
    op.drop_table("products")