"""phase 2

Revision ID: b1e798d2f7e6
Revises: e5f0e41cdb25
Create Date: 2026-03-31 19:20:48.163127

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1e798d2f7e6'
down_revision = 'e5f0e41cdb25'
branch_labels = None
depends_on = None


def upgrade():
    # Add verification fields for public QR verification.
    with op.batch_alter_table('organizations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('verification_slug', sa.String(length=150), nullable=True))
        batch_op.add_column(sa.Column('qr_code_path', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('verification_views_count', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_organizations_verification_slug'), ['verification_slug'], unique=True)

    op.execute(
        "UPDATE organizations "
        "SET verification_views_count = 0 "
        "WHERE verification_views_count IS NULL"
    )
    op.execute(
        "UPDATE organizations "
        "SET verification_slug = CONCAT(slug, '-', SUBSTRING(MD5(id), 1, 8)) "
        "WHERE verification_slug IS NULL OR verification_slug = ''"
    )
    with op.batch_alter_table('organizations', schema=None) as batch_op:
        batch_op.alter_column('verification_views_count', existing_type=sa.Integer(), nullable=False)


def downgrade():
    with op.batch_alter_table('organizations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_organizations_verification_slug'))
        batch_op.drop_column('verification_views_count')
        batch_op.drop_column('qr_code_path')
        batch_op.drop_column('verification_slug')
