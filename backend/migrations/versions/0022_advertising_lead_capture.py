"""Add advertising connectors, campaign reporting, forms and lead capture

Revision ID: 0022_advertising_lead_capture
Revises: 0021_crm_pipeline_and_opportunities
Create Date: 2026-11-24 18:00:00.000000

Additive only: six new tables. Existing leads, CRM and billing rows are
untouched, and every new table is organization-scoped.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0022_advertising_lead_capture'
down_revision = '0021_crm_pipeline_and_opportunities'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ads_connections',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('provider', sa.String(length=20), nullable=False),
        sa.Column('external_account_id', sa.String(length=120), nullable=False),
        sa.Column('account_name', sa.String(length=200), nullable=True),
        sa.Column('status', sa.String(length=30), server_default='pending_credentials', nullable=False),
        sa.Column('scopes', sa.String(length=500), nullable=True),
        sa.Column('access_token_encrypted', sa.LargeBinary(), nullable=True),
        sa.Column('refresh_token_encrypted', sa.LargeBinary(), nullable=True),
        sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'organization_id', 'provider', 'external_account_id',
            name='uq_ads_connection_account',
        ),
    )
    op.create_index('ix_ads_connections_organization_id', 'ads_connections', ['organization_id'])

    op.create_table(
        'ads_campaigns',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('connection_id', sa.String(length=36), nullable=False),
        sa.Column('provider', sa.String(length=20), nullable=False),
        sa.Column('external_id', sa.String(length=120), nullable=False),
        sa.Column('name', sa.String(length=300), nullable=False),
        sa.Column('status', sa.String(length=40), nullable=True),
        sa.Column('objective', sa.String(length=120), nullable=True),
        sa.Column('currency', sa.String(length=3), server_default='INR', nullable=False),
        sa.Column('daily_budget_cents', sa.Integer(), nullable=True),
        sa.Column('spend_cents', sa.Integer(), server_default='0', nullable=False),
        sa.Column('impressions', sa.Integer(), server_default='0', nullable=False),
        sa.Column('clicks', sa.Integer(), server_default='0', nullable=False),
        sa.Column('provider_leads', sa.Integer(), server_default='0', nullable=False),
        sa.Column('conversions', sa.Integer(), server_default='0', nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('raw', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['connection_id'], ['ads_connections.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('connection_id', 'external_id', name='uq_ads_campaign_external'),
    )
    op.create_index('ix_ads_campaigns_organization_id', 'ads_campaigns', ['organization_id'])
    op.create_index('ix_ads_campaigns_connection_id', 'ads_campaigns', ['connection_id'])

    op.create_table(
        'ads_metrics',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('campaign_id', sa.String(length=36), nullable=False),
        sa.Column('metric_date', sa.Date(), nullable=False),
        sa.Column('spend_cents', sa.Integer(), server_default='0', nullable=False),
        sa.Column('impressions', sa.Integer(), server_default='0', nullable=False),
        sa.Column('clicks', sa.Integer(), server_default='0', nullable=False),
        sa.Column('leads', sa.Integer(), server_default='0', nullable=False),
        sa.Column('conversions', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['campaign_id'], ['ads_campaigns.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('campaign_id', 'metric_date', name='uq_ads_metric_campaign_day'),
    )
    op.create_index('ix_ads_metrics_organization_id', 'ads_metrics', ['organization_id'])
    op.create_index('ix_ads_metrics_campaign_id', 'ads_metrics', ['campaign_id'])

    op.create_table(
        'lead_capture_forms',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('slug', sa.String(length=120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('provider', sa.String(length=20), server_default='website', nullable=False),
        sa.Column('provider_form_id', sa.String(length=120), nullable=True),
        sa.Column('fields', sa.JSON(), nullable=False),
        sa.Column('consent_text', sa.Text(), nullable=True),
        sa.Column('requires_consent', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('success_message', sa.String(length=300), nullable=True),
        sa.Column('redirect_url', sa.String(length=500), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('submission_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'slug', name='uq_capture_form_slug'),
    )
    op.create_index('ix_lead_capture_forms_organization_id', 'lead_capture_forms', ['organization_id'])
    op.create_index('ix_lead_capture_forms_slug', 'lead_capture_forms', ['slug'])
    op.create_index(
        'ix_lead_capture_forms_provider_form_id', 'lead_capture_forms', ['provider_form_id']
    )

    op.create_table(
        'lead_capture_submissions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('form_id', sa.String(length=36), nullable=True),
        sa.Column('provider', sa.String(length=20), nullable=False),
        sa.Column('provider_submission_id', sa.String(length=200), nullable=True),
        sa.Column('provider_form_id', sa.String(length=120), nullable=True),
        sa.Column('lead_id', sa.String(length=36), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='received', nullable=False),
        sa.Column('source', sa.String(length=60), nullable=True),
        sa.Column('campaign', sa.String(length=200), nullable=True),
        sa.Column('utm', sa.JSON(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['form_id'], ['lead_capture_forms.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'organization_id', 'provider', 'provider_submission_id',
            name='uq_capture_submission_provider_id',
        ),
    )
    op.create_index(
        'ix_lead_capture_submissions_organization_id', 'lead_capture_submissions', ['organization_id']
    )
    op.create_index('ix_lead_capture_submissions_form_id', 'lead_capture_submissions', ['form_id'])
    op.create_index('ix_lead_capture_submissions_lead_id', 'lead_capture_submissions', ['lead_id'])

    op.create_table(
        'attribution_touchpoints',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('lead_id', sa.String(length=36), nullable=False),
        sa.Column('submission_id', sa.String(length=36), nullable=True),
        sa.Column('channel', sa.String(length=40), nullable=False),
        sa.Column('campaign_external_id', sa.String(length=120), nullable=True),
        sa.Column('source', sa.String(length=120), nullable=True),
        sa.Column('medium', sa.String(length=120), nullable=True),
        sa.Column('campaign', sa.String(length=200), nullable=True),
        sa.Column('term', sa.String(length=200), nullable=True),
        sa.Column('content', sa.String(length=200), nullable=True),
        sa.Column('landing_page', sa.Text(), nullable=True),
        sa.Column('referrer', sa.Text(), nullable=True),
        sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['submission_id'], ['lead_capture_submissions.id'], ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_attribution_touchpoints_organization_id', 'attribution_touchpoints', ['organization_id']
    )
    op.create_index('ix_attribution_touchpoints_lead_id', 'attribution_touchpoints', ['lead_id'])
    op.create_index(
        'ix_attribution_touchpoints_campaign_external_id',
        'attribution_touchpoints',
        ['campaign_external_id'],
    )

    op.create_table(
        'webhook_receipts',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=True),
        sa.Column('provider', sa.String(length=20), nullable=False),
        sa.Column('event_id', sa.String(length=200), nullable=False),
        sa.Column('processed', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider', 'event_id', name='uq_webhook_receipt_event'),
    )
    op.create_index('ix_webhook_receipts_organization_id', 'webhook_receipts', ['organization_id'])


def downgrade():
    op.drop_index('ix_webhook_receipts_organization_id', table_name='webhook_receipts')
    op.drop_table('webhook_receipts')
    op.drop_index(
        'ix_attribution_touchpoints_campaign_external_id', table_name='attribution_touchpoints'
    )
    op.drop_index('ix_attribution_touchpoints_lead_id', table_name='attribution_touchpoints')
    op.drop_index(
        'ix_attribution_touchpoints_organization_id', table_name='attribution_touchpoints'
    )
    op.drop_table('attribution_touchpoints')
    op.drop_index('ix_lead_capture_submissions_lead_id', table_name='lead_capture_submissions')
    op.drop_index('ix_lead_capture_submissions_form_id', table_name='lead_capture_submissions')
    op.drop_index(
        'ix_lead_capture_submissions_organization_id', table_name='lead_capture_submissions'
    )
    op.drop_table('lead_capture_submissions')
    op.drop_index('ix_lead_capture_forms_provider_form_id', table_name='lead_capture_forms')
    op.drop_index('ix_lead_capture_forms_slug', table_name='lead_capture_forms')
    op.drop_index('ix_lead_capture_forms_organization_id', table_name='lead_capture_forms')
    op.drop_table('lead_capture_forms')
    op.drop_index('ix_ads_metrics_campaign_id', table_name='ads_metrics')
    op.drop_index('ix_ads_metrics_organization_id', table_name='ads_metrics')
    op.drop_table('ads_metrics')
    op.drop_index('ix_ads_campaigns_connection_id', table_name='ads_campaigns')
    op.drop_index('ix_ads_campaigns_organization_id', table_name='ads_campaigns')
    op.drop_table('ads_campaigns')
    op.drop_index('ix_ads_connections_organization_id', table_name='ads_connections')
    op.drop_table('ads_connections')
