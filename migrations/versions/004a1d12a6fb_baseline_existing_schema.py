"""baseline - existing schema

Revision ID: 004a1d12a6fb
Revises: 
Create Date: 2026-10-11

This is a squashed baseline. Instead of capturing every column
individually, it simply invokes SQLAlchemy's metadata.create_all()
which builds the schema from the current models. This is the
standard way to start Alembic on a project that already has models.
"""
from alembic import op
import sqlalchemy as sa

revision = '004a1d12a6fb'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Import models so their tables are registered on db.metadata
    from app import create_app, db
    from app import models  # noqa: F401 - registers all models

    app = create_app()
    with app.app_context():
        db.metadata.create_all(bind=op.get_bind())


def downgrade():
    from app import create_app, db
    from app import models  # noqa: F401

    app = create_app()
    with app.app_context():
        db.metadata.drop_all(bind=op.get_bind())
