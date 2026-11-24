"""Add SaaS Multi-Tenant and Authentication Architecture

Revision ID: 0019_saas_multi_tenant_auth
Revises: a23dfc0ad970
Create Date: 2026-11-21 10:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0019_saas_multi_tenant_auth'
down_revision = 'a23dfc0ad970'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create organizations table
    op.create_table(
        'organizations',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('domain', sa.String(length=253), nullable=True),
        sa.Column('plan', sa.String(length=50), nullable=False, server_default='pro'),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='active'),
        sa.Column('settings', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_organizations_slug', 'organizations', ['slug'], unique=True)

    # 2. Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=200), nullable=False, server_default=''),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('is_superadmin', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('avatar_url', sa.String(length=1000), nullable=True),
        sa.Column('failed_login_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    # 3. Create organization_members table
    op.create_table(
        'organization_members',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False, server_default='rep'),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='active'),
        sa.Column('joined_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('organization_id', 'user_id', name='uq_org_member'),
    )
    op.create_index('ix_organization_members_organization_id', 'organization_members', ['organization_id'])
    op.create_index('ix_organization_members_user_id', 'organization_members', ['user_id'])

    # 4. Create organization_invitations table
    op.create_table(
        'organization_invitations',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False, server_default='rep'),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('invited_by_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='pending'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_organization_invitations_token_hash', 'organization_invitations', ['token_hash'], unique=True)
    op.create_index('ix_organization_invitations_organization_id', 'organization_invitations', ['organization_id'])
    op.create_index('ix_organization_invitations_email', 'organization_invitations', ['email'])

    # 5. Create password_reset_tokens table
    op.create_table(
        'password_reset_tokens',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_password_reset_tokens_user_id', 'password_reset_tokens', ['user_id'])
    op.create_index('ix_password_reset_tokens_token_hash', 'password_reset_tokens', ['token_hash'], unique=True)

    # 6. Create email_verification_tokens table
    op.create_table(
        'email_verification_tokens',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_email_verification_tokens_user_id', 'email_verification_tokens', ['user_id'])
    op.create_index('ix_email_verification_tokens_token_hash', 'email_verification_tokens', ['token_hash'], unique=True)

    # 7. Create revoked_tokens table
    op.create_table(
        'revoked_tokens',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('jti', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_revoked_tokens_jti', 'revoked_tokens', ['jti'], unique=True)

    # 8. Create audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), nullable=True),
        sa.Column('user_id', sa.String(length=36), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('resource_type', sa.String(length=50), nullable=False),
        sa.Column('resource_id', sa.String(length=100), nullable=True),
        sa.Column('details', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_audit_logs_organization_id', 'audit_logs', ['organization_id'])
    op.create_index('ix_audit_logs_user_id', 'audit_logs', ['user_id'])

    # 9. Create oauth_connections table
    op.create_table(
        'oauth_connections',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('organization_id', sa.String(length=36), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('account_email', sa.String(length=320), nullable=False),
        sa.Column('account_id', sa.String(length=255), nullable=True),
        sa.Column('refresh_token_encrypted', sa.LargeBinary(), nullable=False),
        sa.Column('access_token_encrypted', sa.LargeBinary(), nullable=True),
        sa.Column('access_token_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('scopes', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='connected'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('connection_metadata', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('organization_id', 'user_id', 'provider', 'account_email', name='uq_org_user_provider_account'),
    )
    op.create_index('ix_oauth_connections_organization_id', 'oauth_connections', ['organization_id'])
    op.create_index('ix_oauth_connections_user_id', 'oauth_connections', ['user_id'])
    op.create_index('ix_oauth_conn_org_provider', 'oauth_connections', ['organization_id', 'provider'])

    # 10. Add organization_id columns to existing business tables
    business_tables = [
        'batches',
        'leads',
        'contacts',
        'campaigns',
        'products',
        'email_templates',
        'meetings',
        'booking_profiles',
        'company_research_profiles',
        'zoho_connections',
    ]
    for table_name in business_tables:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(
                sa.Column('organization_id', sa.String(length=36), nullable=True)
            )
            batch_op.create_foreign_key(
                f'fk_{table_name}_org_id', 'organizations', ['organization_id'], ['id'], ondelete='CASCADE'
            )
            batch_op.create_index(f'ix_{table_name}_organization_id', ['organization_id'])

    # Add user_id column to meetings
    with op.batch_alter_table('meetings') as batch_op:
        batch_op.add_column(
            sa.Column('user_id', sa.String(length=36), nullable=True)
        )
        batch_op.create_foreign_key(
            'fk_meetings_user_id', 'users', ['user_id'], ['id'], ondelete='SET NULL'
        )
        batch_op.create_index('ix_meetings_user_id', ['user_id'])


def downgrade():
    with op.batch_alter_table('meetings') as batch_op:
        batch_op.drop_index('ix_meetings_user_id')
        batch_op.drop_constraint('fk_meetings_user_id', type_='foreignkey')
        batch_op.drop_column('user_id')

    business_tables = [
        'batches',
        'leads',
        'contacts',
        'campaigns',
        'products',
        'email_templates',
        'meetings',
        'booking_profiles',
        'company_research_profiles',
        'zoho_connections',
    ]
    for table_name in business_tables:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_index(f'ix_{table_name}_organization_id')
            batch_op.drop_constraint(f'fk_{table_name}_org_id', type_='foreignkey')
            batch_op.drop_column('organization_id')

    op.drop_table('oauth_connections')
    op.drop_table('audit_logs')
    op.drop_table('revoked_tokens')
    op.drop_table('email_verification_tokens')
    op.drop_table('password_reset_tokens')
    op.drop_table('organization_invitations')
    op.drop_table('organization_members')
    op.drop_table('users')
    op.drop_table('organizations')
