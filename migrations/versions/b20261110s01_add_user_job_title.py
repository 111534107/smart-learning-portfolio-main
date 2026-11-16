"""add users.job_title（教職員職稱：主任、副主任、科助、其他行政人員）

2026-11-09 使用者決定：科辦帳號不限人數，加上職稱，像大學系辦一樣。

Revision ID: b20261110s01
Revises: b20261109d01
Create Date: 2026-11-10
"""
from alembic import op
import sqlalchemy as sa


revision = "b20261110s01"
down_revision = "b20261109d01"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("users"):
        existing = {column["name"] for column in inspector.get_columns("users")}
        if "job_title" not in existing:
            op.add_column("users", sa.Column("job_title", sa.String(length=30), nullable=True))


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("users"):
        existing = {column["name"] for column in inspector.get_columns("users")}
        if "job_title" in existing:
            with op.batch_alter_table("users") as batch:
                batch.drop_column("job_title")
