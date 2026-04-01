"""signup org create join

Revision ID: 75552bf19adf
Revises: 87d6b26f32ef
Create Date: 2026-03-31 20:06:25.726340

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '75552bf19adf'
down_revision = '87d6b26f32ef'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('organizations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email', sa.String(length=150), nullable=True))
        batch_op.add_column(sa.Column('phone', sa.String(length=50), nullable=True))


def downgrade():
    with op.batch_alter_table('organizations', schema=None) as batch_op:
        batch_op.drop_column('phone')
        batch_op.drop_column('email')
