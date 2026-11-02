"""Bind existing students to a Google identity.

Revision ID: b20261102e01
Revises: a20261022e01, e5b9d1c3a826
"""
from alembic import op
import sqlalchemy as sa


revision = "b20261102e01"
down_revision = ("a20261022e01", "e5b9d1c3a826")
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("google_sub", sa.String(length=255), nullable=True))
    op.create_index("ix_users_google_sub", "users", ["google_sub"], unique=True)


def downgrade():
    op.drop_index("ix_users_google_sub", table_name="users")
    op.drop_column("users", "google_sub")
