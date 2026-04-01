"""phase 3

Revision ID: 87d6b26f32ef
Revises: b1e798d2f7e6
Create Date: 2026-03-31 19:28:04.398776

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '87d6b26f32ef'
down_revision = 'b1e798d2f7e6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('document_requests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('organization_id', sa.Integer(), nullable=False),
    sa.Column('requester_name', sa.String(length=150), nullable=False),
    sa.Column('requester_email', sa.String(length=150), nullable=False),
    sa.Column('requester_phone', sa.String(length=50), nullable=True),
    sa.Column('requester_company', sa.String(length=150), nullable=True),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('resolved_at', sa.DateTime(), nullable=True),
    sa.Column('resolved_by_user_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
    sa.ForeignKeyConstraint(['resolved_by_user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('document_requests', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_document_requests_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_document_requests_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_document_requests_requester_email'), ['requester_email'], unique=False)
        batch_op.create_index(batch_op.f('ix_document_requests_resolved_by_user_id'), ['resolved_by_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_document_requests_status'), ['status'], unique=False)

    op.create_table('verification_codes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('organization_id', sa.Integer(), nullable=False),
    sa.Column('request_id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=20), nullable=False),
    sa.Column('purpose', sa.String(length=100), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('is_used', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
    sa.ForeignKeyConstraint(['request_id'], ['document_requests.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('verification_codes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_verification_codes_code'), ['code'], unique=False)
        batch_op.create_index(batch_op.f('ix_verification_codes_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_verification_codes_expires_at'), ['expires_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_verification_codes_is_used'), ['is_used'], unique=False)
        batch_op.create_index(batch_op.f('ix_verification_codes_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_verification_codes_purpose'), ['purpose'], unique=False)
        batch_op.create_index(batch_op.f('ix_verification_codes_request_id'), ['request_id'], unique=False)


def downgrade():
    with op.batch_alter_table('verification_codes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_verification_codes_request_id'))
        batch_op.drop_index(batch_op.f('ix_verification_codes_purpose'))
        batch_op.drop_index(batch_op.f('ix_verification_codes_organization_id'))
        batch_op.drop_index(batch_op.f('ix_verification_codes_is_used'))
        batch_op.drop_index(batch_op.f('ix_verification_codes_expires_at'))
        batch_op.drop_index(batch_op.f('ix_verification_codes_created_at'))
        batch_op.drop_index(batch_op.f('ix_verification_codes_code'))

    op.drop_table('verification_codes')
    with op.batch_alter_table('document_requests', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_document_requests_status'))
        batch_op.drop_index(batch_op.f('ix_document_requests_resolved_by_user_id'))
        batch_op.drop_index(batch_op.f('ix_document_requests_requester_email'))
        batch_op.drop_index(batch_op.f('ix_document_requests_organization_id'))
        batch_op.drop_index(batch_op.f('ix_document_requests_created_at'))

    op.drop_table('document_requests')
