"""Associate campaign enrollments with saved contacts."""

from alembic import op
import sqlalchemy as sa

revision = "0008_enrollment_contact_link"
down_revision = "0007_apollo_contact_management"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("enrollments") as batch:
        batch.add_column(sa.Column("contact_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key("fk_enrollment_contact", "contacts", ["contact_id"], ["id"])


def downgrade():
    with op.batch_alter_table("enrollments") as batch:
        batch.drop_constraint("fk_enrollment_contact", type_="foreignkey")
        batch.drop_column("contact_id")
