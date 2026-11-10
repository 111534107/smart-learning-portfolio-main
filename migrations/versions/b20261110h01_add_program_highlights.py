"""add admission_rule_versions.highlights（簡章重點提醒）

2026-11-10 使用者：小助手要能自己爬資料、整理重點。Agent 擷取簡章時一起整理每個校系的重點提醒
（特殊表格、字數頁數限制、門檻），管理員核准後學生才看得到。

Revision ID: b20261110h01
Revises: b20261110s01
Create Date: 2026-11-10
"""
from alembic import op
import sqlalchemy as sa


revision = "b20261110h01"
down_revision = "b20261110s01"
branch_labels = None
depends_on = None

TABLE = "admission_rule_versions"


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(TABLE):
        existing = {column["name"] for column in inspector.get_columns(TABLE)}
        if "highlights" not in existing:
            op.add_column(TABLE, sa.Column("highlights", sa.JSON(), nullable=True))


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(TABLE):
        existing = {column["name"] for column in inspector.get_columns(TABLE)}
        if "highlights" in existing:
            with op.batch_alter_table(TABLE) as batch:
                batch.drop_column("highlights")
