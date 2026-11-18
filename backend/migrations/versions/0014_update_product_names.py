"""Update product names to IE, MCE, VDI and remove General / Unassigned."""

from alembic import op
import sqlalchemy as sa

revision = "0014_update_product_names"
down_revision = "0013_research_discovery"
branch_labels = None
depends_on = None

_GENERAL_ID = "00000000-0000-0000-0000-000000000001"
_VDI_ID = "00000000-0000-0000-0000-000000000002"
_LT_ID = "00000000-0000-0000-0000-000000000003"
_ASA_ID = "00000000-0000-0000-0000-000000000004"


def upgrade():
    conn = op.get_bind()

    # 1. Update Vehicle Digital Inspection -> VDI
    conn.execute(sa.text("""
        UPDATE products
        SET name = 'VDI',
            slug = 'vdi',
            short_description = 'Vehicle Digital Inspection platform'
        WHERE id = :id OR slug = 'vehicle-digital-inspection'
    """), {"id": _VDI_ID})

    # 2. Update Loss Tracker -> IE
    conn.execute(sa.text("""
        UPDATE products
        SET name = 'IE',
            slug = 'ie',
            short_description = 'IE solution'
        WHERE id = :id OR slug = 'loss-tracker'
    """), {"id": _LT_ID})

    # 3. Update Aftermarket Super App -> MCE
    conn.execute(sa.text("""
        UPDATE products
        SET name = 'MCE',
            slug = 'mce',
            short_description = 'MCE solution'
        WHERE id = :id OR slug = 'aftermarket-super-app'
    """), {"id": _ASA_ID})

    # 4. Remove General / Unassigned (safe because 0 leads/campaigns/templates reference it)
    conn.execute(sa.text("DELETE FROM product_leads WHERE product_id = :id"), {"id": _GENERAL_ID})
    conn.execute(sa.text("DELETE FROM products WHERE id = :id OR slug = 'general-unassigned'"), {"id": _GENERAL_ID})


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE products
        SET name = 'Vehicle Digital Inspection',
            slug = 'vehicle-digital-inspection',
            short_description = 'Digital vehicle inspection platform.'
        WHERE id = :id OR slug = 'vdi'
    """), {"id": _VDI_ID})

    conn.execute(sa.text("""
        UPDATE products
        SET name = 'Loss Tracker',
            slug = 'loss-tracker',
            short_description = 'Loss and defect tracking solution.'
        WHERE id = :id OR slug = 'ie'
    """), {"id": _LT_ID})

    conn.execute(sa.text("""
        UPDATE products
        SET name = 'Aftermarket Super App',
            slug = 'aftermarket-super-app',
            short_description = 'Aftermarket sales and service super-app.'
        WHERE id = :id OR slug = 'mce'
    """), {"id": _ASA_ID})

    # Restore General / Unassigned if absent
    conn.execute(sa.text("""
        INSERT INTO products (id, name, slug, short_description, status, target_industries, created_at, updated_at)
        VALUES (:id, 'General / Unassigned', 'general-unassigned', 'Legacy and unattributed records.', 'active', '[]', NOW(), NOW())
        ON CONFLICT (id) DO NOTHING;
    """), {"id": _GENERAL_ID})
