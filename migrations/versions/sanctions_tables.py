"""add sanctions tables

Revision ID: sanctions_tables
Revises: abc123_shipment_table
Create Date: 2026-10-12
"""
from alembic import op
import sqlalchemy as sa

revision = 'sanctions_tables'
down_revision = 'abc123_shipment_table'
branch_labels = None
depends_on = None


def upgrade():
    # Tables already created by db.create_all() in dev.
    # This migration is a no-op stamp for reproducibility.
    pass


def downgrade():
    op.drop_table('sanctions_hits')
    op.drop_table('sanctions_screens')
    op.drop_table('sanctions_entities')
