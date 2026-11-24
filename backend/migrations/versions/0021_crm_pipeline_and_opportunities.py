"""Add CRM core: pipelines, stages, opportunities, tasks, activities, custom fields

Revision ID: 0021_crm_pipeline_and_opportunities
Revises: 0020_billing_foundation
Create Date: 2026-11-24 15:30:00.000000

Additive only: new tables plus nullable/defaulted columns on ``leads``. Existing
lead rows keep working with ``lifecycle_stage='lead'`` and ``score=0``.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0021_crm_pipeline_and_opportunities'
down_revision = '0020_billing_foundation'
branch_labels = None
depends_on = None


def upgrade():
    # --- lead lifecycle columns -------------------------------------------------
    op.add_column('leads', sa.Column('owner_id', sa.String(length=36), nullable=True))
    op.add_column(
        'leads',
        sa.Column('lifecycle_stage', sa.String(length=30), nullable=False, server_default='lead'),
    )
    op.add_column(
        'leads',
        sa.Column(
            'qualification_status', sa.String(length=30), nullable=False, server_default='unqualified'
        ),
    )
    op.add_column('leads', sa.Column('score', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('leads', sa.Column('source', sa.String(length=60), nullable=True))
    op.add_column('leads', sa.Column('source_detail', sa.String(length=300), nullable=True))
    op.add_column(
        'leads', sa.Column('custom_fields', sa.JSON(), nullable=False, server_default='{}')
    )
    op.add_column('leads', sa.Column('merged_into_id', sa.String(length=36), nullable=True))
    op.create_index('ix_leads_owner_id', 'leads', ['owner_id'])
    op.create_index('ix_leads_merged_into_id', 'leads', ['merged_into_id'])

    # --- pipelines ---------------------------------------------------------------
    op.create_table(
        'crm_pipelines',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column(
            'organization_id',
            sa.String(length=36),
            sa.ForeignKey('organizations.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('organization_id', 'name', name='uq_pipeline_org_name'),
    )
    op.create_index('ix_crm_pipelines_organization_id', 'crm_pipelines', ['organization_id'])

    op.create_table(
        'crm_pipeline_stages',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column(
            'pipeline_id',
            sa.String(length=36),
            sa.ForeignKey('crm_pipelines.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('probability', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_won', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('is_lost', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('pipeline_id', 'name', name='uq_stage_pipeline_name'),
    )
    op.create_index(
        'ix_crm_pipeline_stages_pipeline_id', 'crm_pipeline_stages', ['pipeline_id']
    )

    # --- opportunities ------------------------------------------------------------
    op.create_table(
        'crm_opportunities',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column(
            'organization_id',
            sa.String(length=36),
            sa.ForeignKey('organizations.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'pipeline_id', sa.String(length=36), sa.ForeignKey('crm_pipelines.id'), nullable=False
        ),
        sa.Column(
            'stage_id',
            sa.String(length=36),
            sa.ForeignKey('crm_pipeline_stages.id'),
            nullable=False,
        ),
        sa.Column(
            'lead_id',
            sa.String(length=36),
            sa.ForeignKey('leads.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'contact_id',
            sa.String(length=36),
            sa.ForeignKey('contacts.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('name', sa.String(length=300), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='INR'),
        sa.Column('expected_close_date', sa.Date(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='open'),
        sa.Column('won_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('lost_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('lost_reason', sa.Text(), nullable=True),
        sa.Column(
            'owner_id',
            sa.String(length=36),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('source', sa.String(length=60), nullable=True),
        sa.Column('source_detail', sa.String(length=300), nullable=True),
        sa.Column('custom_fields', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column(
            'created_by_id',
            sa.String(length=36),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    for column in ('organization_id', 'pipeline_id', 'stage_id', 'lead_id', 'owner_id'):
        op.create_index(f'ix_crm_opportunities_{column}', 'crm_opportunities', [column])

    op.create_table(
        'crm_opportunity_stage_events',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column(
            'opportunity_id',
            sa.String(length=36),
            sa.ForeignKey('crm_opportunities.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('from_stage_id', sa.String(length=36), nullable=True),
        sa.Column('to_stage_id', sa.String(length=36), nullable=True),
        sa.Column('from_status', sa.String(length=20), nullable=True),
        sa.Column('to_status', sa.String(length=20), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('changed_by_id', sa.String(length=36), nullable=True),
        sa.Column('changed_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        'ix_crm_opportunity_stage_events_opportunity_id',
        'crm_opportunity_stage_events',
        ['opportunity_id'],
    )

    # --- activities ---------------------------------------------------------------
    op.create_table(
        'crm_activities',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column(
            'organization_id',
            sa.String(length=36),
            sa.ForeignKey('organizations.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'lead_id',
            sa.String(length=36),
            sa.ForeignKey('leads.id', ondelete='CASCADE'),
            nullable=True,
        ),
        sa.Column('contact_id', sa.String(length=36), nullable=True),
        sa.Column(
            'opportunity_id',
            sa.String(length=36),
            sa.ForeignKey('crm_opportunities.id', ondelete='CASCADE'),
            nullable=True,
        ),
        sa.Column('activity_type', sa.String(length=30), nullable=False, server_default='note'),
        sa.Column('subject', sa.String(length=300), nullable=False, server_default=''),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('owner_id', sa.String(length=36), nullable=True),
        sa.Column('activity_metadata', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    for column in ('organization_id', 'lead_id', 'opportunity_id', 'owner_id', 'occurred_at'):
        op.create_index(f'ix_crm_activities_{column}', 'crm_activities', [column])

    # --- tasks --------------------------------------------------------------------
    op.create_table(
        'crm_tasks',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column(
            'organization_id',
            sa.String(length=36),
            sa.ForeignKey('organizations.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='open'),
        sa.Column('priority', sa.String(length=10), nullable=False, server_default='medium'),
        sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'lead_id',
            sa.String(length=36),
            sa.ForeignKey('leads.id', ondelete='CASCADE'),
            nullable=True,
        ),
        sa.Column(
            'opportunity_id',
            sa.String(length=36),
            sa.ForeignKey('crm_opportunities.id', ondelete='CASCADE'),
            nullable=True,
        ),
        sa.Column('owner_id', sa.String(length=36), nullable=True),
        sa.Column('created_by_id', sa.String(length=36), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    for column in ('organization_id', 'due_at', 'lead_id', 'opportunity_id', 'owner_id'):
        op.create_index(f'ix_crm_tasks_{column}', 'crm_tasks', [column])

    # --- custom fields and saved views ---------------------------------------------
    op.create_table(
        'crm_custom_fields',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column(
            'organization_id',
            sa.String(length=36),
            sa.ForeignKey('organizations.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('entity', sa.String(length=30), nullable=False, server_default='lead'),
        sa.Column('key', sa.String(length=60), nullable=False),
        sa.Column('label', sa.String(length=120), nullable=False),
        sa.Column('field_type', sa.String(length=20), nullable=False, server_default='text'),
        sa.Column('options', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('is_required', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            'organization_id', 'entity', 'key', name='uq_custom_field_org_entity_key'
        ),
    )
    op.create_index(
        'ix_crm_custom_fields_organization_id', 'crm_custom_fields', ['organization_id']
    )

    op.create_table(
        'crm_saved_views',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column(
            'organization_id',
            sa.String(length=36),
            sa.ForeignKey('organizations.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('user_id', sa.String(length=36), nullable=True),
        sa.Column('entity', sa.String(length=30), nullable=False, server_default='opportunity'),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('filters', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('is_shared', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_crm_saved_views_organization_id', 'crm_saved_views', ['organization_id'])
    op.create_index('ix_crm_saved_views_user_id', 'crm_saved_views', ['user_id'])


def downgrade():
    op.drop_index('ix_crm_saved_views_user_id', table_name='crm_saved_views')
    op.drop_index('ix_crm_saved_views_organization_id', table_name='crm_saved_views')
    op.drop_table('crm_saved_views')

    op.drop_index('ix_crm_custom_fields_organization_id', table_name='crm_custom_fields')
    op.drop_table('crm_custom_fields')

    for column in ('owner_id', 'opportunity_id', 'lead_id', 'due_at', 'organization_id'):
        op.drop_index(f'ix_crm_tasks_{column}', table_name='crm_tasks')
    op.drop_table('crm_tasks')

    for column in ('occurred_at', 'owner_id', 'opportunity_id', 'lead_id', 'organization_id'):
        op.drop_index(f'ix_crm_activities_{column}', table_name='crm_activities')
    op.drop_table('crm_activities')

    op.drop_index(
        'ix_crm_opportunity_stage_events_opportunity_id',
        table_name='crm_opportunity_stage_events',
    )
    op.drop_table('crm_opportunity_stage_events')

    for column in ('owner_id', 'lead_id', 'stage_id', 'pipeline_id', 'organization_id'):
        op.drop_index(f'ix_crm_opportunities_{column}', table_name='crm_opportunities')
    op.drop_table('crm_opportunities')

    op.drop_index('ix_crm_pipeline_stages_pipeline_id', table_name='crm_pipeline_stages')
    op.drop_table('crm_pipeline_stages')

    op.drop_index('ix_crm_pipelines_organization_id', table_name='crm_pipelines')
    op.drop_table('crm_pipelines')

    op.drop_index('ix_leads_merged_into_id', table_name='leads')
    op.drop_index('ix_leads_owner_id', table_name='leads')
    for column in (
        'merged_into_id',
        'custom_fields',
        'source_detail',
        'source',
        'score',
        'qualification_status',
        'lifecycle_stage',
        'owner_id',
    ):
        op.drop_column('leads', column)
