"""Add meeting tasks from classified replies."""

from alembic import op
import sqlalchemy as sa

revision = "0003_sales_tasks"
down_revision = "08704140955b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sales_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("reply_id", sa.String(36), sa.ForeignKey("email_replies.id"), nullable=False, unique=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_table("sales_tasks")
