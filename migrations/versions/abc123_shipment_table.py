"""add Shipment table

Revision ID: abc123_shipment_table
Revises: c0c1f4a63d74
Create Date: 2026-10-11
"""
from alembic import op
import sqlalchemy as sa

revision = 'abc123_shipment_table'
down_revision = 'c0c1f4a63d74'
branch_labels = None
depends_on = None


def upgrade():
    # Table already created by db.create_all() in dev.
    # This migration is a no-op stamp for reproducibility.
    pass


def downgrade():
    op.drop_table('shipments')
