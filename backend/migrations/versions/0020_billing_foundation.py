"""Add SaaS billing foundation: plans, subscriptions and usage metering

Revision ID: 0020_billing_foundation
Revises: 0019_saas_multi_tenant_auth
Create Date: 2026-11-24 11:00:00.000000

The plan catalogue itself is seeded by ``app.billing.service.seed_default_plans``
on first use, so pricing stays data that can be changed without a migration.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0020_billing_foundation'
down_revision = '0019_saas_multi_tenant_auth'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'billing_plans',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('price_cents', sa.Integer(), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='INR'),
        sa.Column('billing_interval', sa.String(length=20), nullable=False, server_default='month'),
        sa.Column('trial_days', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('limits', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('features', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_billing_plans_code', 'billing_plans', ['code'], unique=True)

    op.create_table(
        'billing_subscriptions',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column(
            'organization_id',
            sa.String(length=36),
            sa.ForeignKey('organizations.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'plan_id',
            sa.String(length=36),
            sa.ForeignKey('billing_plans.id'),
            nullable=False,
        ),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        sa.Column('seats', sa.Integer(), nullable=True),
        sa.Column('trial_ends_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('current_period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('cancel_at_period_end', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('canceled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('provider', sa.String(length=50), nullable=True),
        sa.Column('provider_customer_id', sa.String(length=255), nullable=True),
        sa.Column('provider_subscription_id', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('organization_id', name='uq_subscription_org'),
    )
    op.create_index(
        'ix_billing_subscriptions_organization_id', 'billing_subscriptions', ['organization_id']
    )
    op.create_index('ix_billing_subscriptions_plan_id', 'billing_subscriptions', ['plan_id'])

    op.create_table(
        'billing_usage_records',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column(
            'organization_id',
            sa.String(length=36),
            sa.ForeignKey('organizations.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('metric', sa.String(length=60), nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            'organization_id', 'metric', 'period_start', name='uq_usage_org_metric_period'
        ),
    )
    op.create_index(
        'ix_billing_usage_records_organization_id', 'billing_usage_records', ['organization_id']
    )
    op.create_index('ix_billing_usage_records_metric', 'billing_usage_records', ['metric'])

    # The catalogue is seeded by app.billing.service.seed_default_plans on first
    # use, so pricing stays editable data rather than a migration-time constant.


def downgrade():
    op.drop_index('ix_billing_usage_records_metric', table_name='billing_usage_records')
    op.drop_index('ix_billing_usage_records_organization_id', table_name='billing_usage_records')
    op.drop_table('billing_usage_records')
    op.drop_index('ix_billing_subscriptions_plan_id', table_name='billing_subscriptions')
    op.drop_index('ix_billing_subscriptions_organization_id', table_name='billing_subscriptions')
    op.drop_table('billing_subscriptions')
    op.drop_index('ix_billing_plans_code', table_name='billing_plans')
    op.drop_table('billing_plans')
