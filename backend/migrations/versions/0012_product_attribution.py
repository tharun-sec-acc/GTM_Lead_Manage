"""Seed initial products and attribute all existing leads, campaigns and batches
to General / Unassigned."""

from datetime import datetime, timezone
from alembic import op
import sqlalchemy as sa

revision = "0012_product_attribution"
down_revision = "0011_products"
branch_labels = None
depends_on = None

# Deterministic IDs - never change these after the first migration run.
_GENERAL_ID = "00000000-0000-0000-0000-000000000001"
_VDI_ID     = "00000000-0000-0000-0000-000000000002"
_LT_ID      = "00000000-0000-0000-0000-000000000003"
_ASA_ID     = "00000000-0000-0000-0000-000000000004"

_NOW = "2026-11-17T00:00:00+00:00"

_PRODUCTS = [
    {
        "id": _GENERAL_ID,
        "name": "General / Unassigned",
        "slug": "general-unassigned",
        "short_description": "Legacy and unattributed records.",
        "status": "active",
        "target_industries": "[]",
        "created_at": _NOW,
        "updated_at": _NOW,
    },
    {
        "id": _VDI_ID,
        "name": "Vehicle Digital Inspection",
        "slug": "vehicle-digital-inspection",
        "short_description": "Digital vehicle inspection platform.",
        "status": "active",
        "target_industries": "[]",
        "created_at": _NOW,
        "updated_at": _NOW,
    },
    {
        "id": _LT_ID,
        "name": "Loss Tracker",
        "slug": "loss-tracker",
        "short_description": "Loss and defect tracking solution.",
        "status": "active",
        "target_industries": "[]",
        "created_at": _NOW,
        "updated_at": _NOW,
    },
    {
        "id": _ASA_ID,
        "name": "Aftermarket Super App",
        "slug": "aftermarket-super-app",
        "short_description": "Aftermarket sales and service super-app.",
        "status": "active",
        "target_industries": "[]",
        "created_at": _NOW,
        "updated_at": _NOW,
    },
]

def _uuid_expr(dialect_name: str) -> str:
    """Return a SQL expression that generates a UUID string for the dialect."""
    if dialect_name == "sqlite":
        # SQLite: use hex/randomblob trick
        return (
            "lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || "
            "substr(lower(hex(randomblob(2))),2) || '-' || "
            "substr('89ab', abs(random()) % 4 + 1, 1) || "
            "substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))"
        )
    else:
        # PostgreSQL and others: use gen_random_uuid() cast to text
        return "gen_random_uuid()::text"


def upgrade():
    conn = op.get_bind()
    dialect = conn.dialect.name

    for p in _PRODUCTS:
        conn.execute(
            sa.text(
                "INSERT INTO products (id, name, slug, short_description, status, "
                "target_industries, created_at, updated_at) VALUES "
                "(:id, :name, :slug, :short_description, :status, "
                ":target_industries, :created_at, :updated_at)"
            ),
            p,
        )

    uuid_expr = _uuid_expr(dialect)
    conn.execute(
        sa.text(
            "INSERT INTO product_leads "
            "(id, product_id, lead_id, stage, priority, status, associated_at, updated_at) "
            f"SELECT {uuid_expr}, "
            ":product_id, id, 'prospect', 'medium', 'active', :now, :now "
            "FROM leads"
        ),
        {"product_id": _GENERAL_ID, "now": _NOW},
    )

    conn.execute(
        sa.text("UPDATE campaigns SET product_id = :product_id WHERE product_id IS NULL"),
        {"product_id": _GENERAL_ID},
    )

    conn.execute(
        sa.text("UPDATE batches SET product_id = :product_id WHERE product_id IS NULL"),
        {"product_id": _GENERAL_ID},
    )


def downgrade():
    conn = op.get_bind()

    conn.execute(sa.text("UPDATE batches SET product_id = NULL WHERE product_id = :id"),
                 {"id": _GENERAL_ID})
    conn.execute(sa.text("UPDATE campaigns SET product_id = NULL WHERE product_id = :id"),
                 {"id": _GENERAL_ID})
    conn.execute(
        sa.text("DELETE FROM product_leads WHERE product_id = :id"),
        {"id": _GENERAL_ID},
    )
    for p in _PRODUCTS:
        conn.execute(sa.text("DELETE FROM products WHERE id = :id"), {"id": p["id"]})