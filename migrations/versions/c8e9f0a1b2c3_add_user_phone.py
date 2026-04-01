"""add user phone

Revision ID: c8e9f0a1b2c3
Revises: 2f7d45396fe6
Create Date: 2026-04-01

"""
from alembic import op
import sqlalchemy as sa


revision = "c8e9f0a1b2c3"
down_revision = "2f7d45396fe6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("phone", sa.String(length=50), nullable=True))


def downgrade():
    op.drop_column("users", "phone")
