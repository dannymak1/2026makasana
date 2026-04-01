"""admin layout and mailing list improvements

Revision ID: 2f7d45396fe6
Revises: 75552bf19adf
Create Date: 2026-03-31 21:11:53.158857

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2f7d45396fe6'
down_revision = '75552bf19adf'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('site_settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('site_name', sa.String(length=150), nullable=False),
    sa.Column('site_tagline', sa.String(length=255), nullable=True),
    sa.Column('logo_path', sa.String(length=255), nullable=True),
    sa.Column('favicon_path', sa.String(length=255), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('mailing_list_subscribers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=150), nullable=False),
    sa.Column('first_name', sa.String(length=100), nullable=True),
    sa.Column('last_name', sa.String(length=100), nullable=True),
    sa.Column('source', sa.String(length=100), nullable=True),
    sa.Column('organization_id', sa.Integer(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('mailing_list_subscribers', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_mailing_list_subscribers_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_mailing_list_subscribers_email'), ['email'], unique=True)
        batch_op.create_index(batch_op.f('ix_mailing_list_subscribers_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_mailing_list_subscribers_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_mailing_list_subscribers_source'), ['source'], unique=False)

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_at', sa.DateTime(), nullable=True))
        batch_op.create_index(batch_op.f('ix_users_created_at'), ['created_at'], unique=False)
    op.execute("UPDATE users SET created_at = UTC_TIMESTAMP() WHERE created_at IS NULL")
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('created_at', existing_type=sa.DateTime(), nullable=False)


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_created_at'))
        batch_op.drop_column('created_at')

    with op.batch_alter_table('mailing_list_subscribers', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mailing_list_subscribers_source'))
        batch_op.drop_index(batch_op.f('ix_mailing_list_subscribers_organization_id'))
        batch_op.drop_index(batch_op.f('ix_mailing_list_subscribers_is_active'))
        batch_op.drop_index(batch_op.f('ix_mailing_list_subscribers_email'))
        batch_op.drop_index(batch_op.f('ix_mailing_list_subscribers_created_at'))

    op.drop_table('mailing_list_subscribers')
    op.drop_table('site_settings')
