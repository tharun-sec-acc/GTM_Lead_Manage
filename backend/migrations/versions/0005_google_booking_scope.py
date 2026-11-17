"""Record whether an OAuth request includes Calendar event access."""

from alembic import op
import sqlalchemy as sa

revision = "0005_google_booking_scope"
down_revision = "0004_google_oauth"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "google_oauth_states",
        sa.Column("booking_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("google_oauth_states", "booking_requested")
