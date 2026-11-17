"""Store encrypted delegated Google credentials and one-time OAuth state."""

from alembic import op
import sqlalchemy as sa

revision = "0004_google_oauth"
down_revision = "0003_sales_tasks"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "google_oauth_states",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column("browser_hash", sa.String(64), nullable=False),
        sa.Column("verifier_encrypted", sa.LargeBinary, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "google_oauth_credentials",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organizer_email", sa.String(320), nullable=False),
        sa.Column("refresh_token_encrypted", sa.LargeBinary, nullable=False),
        sa.Column("scopes", sa.JSON, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("google_oauth_credentials")
    op.drop_table("google_oauth_states")
