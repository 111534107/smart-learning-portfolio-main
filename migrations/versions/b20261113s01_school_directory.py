"""學校名錄：schools、school_department_links（地區、座標、官網、招生網站、科系網址）

Revision ID: b20261113s01
Revises: b20261113f01
Create Date: 2026-11-13
"""
import sqlalchemy as sa
from alembic import op

revision = "b20261113s01"
down_revision = "b20261113f01"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("schools"):
        op.create_table(
            "schools",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(100), nullable=False, unique=True),
            sa.Column("region", sa.String(10), nullable=False),
            sa.Column("city", sa.String(20), nullable=True),
            sa.Column("latitude", sa.Float(), nullable=True),
            sa.Column("longitude", sa.Float(), nullable=True),
            sa.Column("website_url", sa.String(500), nullable=True),
            sa.Column("admission_url", sa.String(500), nullable=True),
            sa.Column("checked_on", sa.Date(), nullable=True),
            sa.Column("links_checked_at", sa.DateTime(), nullable=True),
            sa.Column("link_problems", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    if not inspector.has_table("school_department_links"):
        op.create_table(
            "school_department_links",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("school_id", sa.Integer(), sa.ForeignKey("schools.id", ondelete="CASCADE"), nullable=False),
            sa.Column("department_name", sa.String(100), nullable=False),
            sa.Column("url", sa.String(500), nullable=False),
            sa.UniqueConstraint("school_id", "department_name", name="uq_school_department"),
        )
        op.create_index("ix_school_department_links_school_id", "school_department_links", ["school_id"])


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("school_department_links"):
        op.drop_table("school_department_links")
    if inspector.has_table("schools"):
        op.drop_table("schools")
