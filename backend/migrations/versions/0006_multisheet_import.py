"""Add worksheet metadata and provenance to imported batches."""

from alembic import op
import sqlalchemy as sa

revision = "0006_multisheet_import"
down_revision = "0005_google_booking_scope"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("batches", sa.Column("sheet_headers", sa.JSON(), nullable=True))
    op.add_column("leads", sa.Column("industry", sa.String(length=255), nullable=True))
    op.add_column("leads", sa.Column("designation", sa.String(length=500), nullable=True))
    op.add_column("leads", sa.Column("location", sa.String(length=500), nullable=True))
    with op.batch_alter_table("import_rows") as batch:
        batch.drop_constraint("uq_batch_row", type_="unique")
        batch.add_column(sa.Column("sheet_name", sa.String(length=255), nullable=False, server_default=""))
        batch.create_unique_constraint(
            "uq_batch_sheet_row", ["batch_id", "sheet_name", "row_number"]
        )


def downgrade():
    with op.batch_alter_table("import_rows") as batch:
        batch.drop_constraint("uq_batch_sheet_row", type_="unique")
        batch.drop_column("sheet_name")
        batch.create_unique_constraint("uq_batch_row", ["batch_id", "row_number"])
    op.drop_column("leads", "location")
    op.drop_column("leads", "designation")
    op.drop_column("leads", "industry")
    op.drop_column("batches", "sheet_headers")
