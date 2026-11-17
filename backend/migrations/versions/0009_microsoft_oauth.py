"""Add encrypted Microsoft OAuth state and token-cache persistence."""

from alembic import op
import sqlalchemy as sa

revision = "0009_microsoft_oauth"
down_revision = "0008_enrollment_contact_link"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "microsoft_oauth_states",
        sa.Column("state_hash", sa.String(length=64), primary_key=True),
        sa.Column("browser_hash", sa.String(length=64), nullable=False),
        sa.Column("auth_flow_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "microsoft_oauth_credentials",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("organizer_email", sa.String(length=320), nullable=False),
        sa.Column("token_cache_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("microsoft_oauth_credentials")
    op.drop_table("microsoft_oauth_states")
