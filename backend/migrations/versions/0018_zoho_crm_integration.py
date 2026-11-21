"""Zoho CRM Integration Models and Sync Infrastructure.

Revision ID: 0018_zoho_crm_integration
Revises: 0017_public_booking_system
"""

from alembic import op
import sqlalchemy as sa

revision = "0018_zoho_crm_integration"
down_revision = "0017_public_booking_system"
branch_labels = None
depends_on = None


def upgrade():
    # 1. zoho_oauth_states
    op.create_table(
        "zoho_oauth_states",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column("browser_hash", sa.String(64), nullable=False),
        sa.Column("accounts_domain", sa.String(255), nullable=False, server_default="https://accounts.zoho.in"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 2. zoho_connections
    op.create_table(
        "zoho_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(100), nullable=False),
        sa.Column("org_name", sa.String(255), nullable=False),
        sa.Column("user_email", sa.String(320), nullable=True),
        sa.Column("user_zuid", sa.String(100), nullable=True),
        sa.Column("accounts_domain", sa.String(255), nullable=False, server_default="https://accounts.zoho.in"),
        sa.Column("api_domain", sa.String(255), nullable=False, server_default="https://www.zohoapis.in"),
        sa.Column("crm_api_version", sa.String(10), nullable=False, server_default="v8"),
        sa.Column("refresh_token_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("access_token_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sync_direction", sa.String(20), nullable=False, server_default="bidirectional"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_zoho_connections_org_id", "zoho_connections", ["org_id"], unique=True)

    # 3. zoho_field_mappings
    op.create_table(
        "zoho_field_mappings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("zoho_module", sa.String(50), nullable=False),
        sa.Column("gtm_field", sa.String(100), nullable=False),
        sa.Column("zoho_field", sa.String(100), nullable=False),
        sa.Column("field_type", sa.String(50), nullable=False, server_default="string"),
        sa.Column("sync_direction", sa.String(20), nullable=False, server_default="bidirectional"),
        sa.Column("conflict_policy", sa.String(30), nullable=False, server_default="crm_wins"),
        sa.Column("is_custom", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("zoho_module", "gtm_field", name="uq_zoho_module_gtm_field"),
    )
    op.create_index("ix_zoho_field_mappings_zoho_module", "zoho_field_mappings", ["zoho_module"])

    # 4. zoho_record_mappings
    op.create_table(
        "zoho_record_mappings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("gtm_entity_type", sa.String(50), nullable=False),
        sa.Column("gtm_entity_id", sa.String(36), nullable=False),
        sa.Column("zoho_module", sa.String(50), nullable=False),
        sa.Column("zoho_record_id", sa.String(100), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=True),
        sa.Column("sync_hash", sa.String(64), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("sync_status", sa.String(20), nullable=False, server_default="synced"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("gtm_entity_type", "gtm_entity_id", name="uq_zoho_gtm_entity"),
        sa.UniqueConstraint("zoho_module", "zoho_record_id", name="uq_zoho_module_record_id"),
    )
    op.create_index("ix_zoho_record_mappings_gtm_entity", "zoho_record_mappings", ["gtm_entity_type", "gtm_entity_id"])
    op.create_index("ix_zoho_record_mappings_zoho_record", "zoho_record_mappings", ["zoho_module", "zoho_record_id"])

    # 5. zoho_sync_jobs
    op.create_table(
        "zoho_sync_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("records_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_succeeded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 6. zoho_sync_logs
    op.create_table(
        "zoho_sync_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("zoho_sync_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=True),
        sa.Column("zoho_module", sa.String(50), nullable=False),
        sa.Column("zoho_record_id", sa.String(100), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("payload_snapshot", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_zoho_sync_logs_job_id", "zoho_sync_logs", ["job_id"])
    op.create_index("ix_zoho_sync_logs_entity", "zoho_sync_logs", ["entity_type", "entity_id"])

    # 7. zoho_sync_conflicts
    op.create_table(
        "zoho_sync_conflicts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("record_mapping_id", sa.String(36), sa.ForeignKey("zoho_record_mappings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("gtm_entity_type", sa.String(50), nullable=False),
        sa.Column("gtm_entity_id", sa.String(36), nullable=False),
        sa.Column("zoho_module", sa.String(50), nullable=False),
        sa.Column("zoho_record_id", sa.String(100), nullable=False),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("gtm_value", sa.Text(), nullable=True),
        sa.Column("zoho_value", sa.Text(), nullable=True),
        sa.Column("resolution_status", sa.String(20), nullable=False, server_default="unresolved"),
        sa.Column("resolved_by", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_table("zoho_sync_conflicts")
    op.drop_table("zoho_sync_logs")
    op.drop_table("zoho_sync_jobs")
    op.drop_table("zoho_record_mappings")
    op.drop_table("zoho_field_mappings")
    op.drop_table("zoho_connections")
    op.drop_table("zoho_oauth_states")
