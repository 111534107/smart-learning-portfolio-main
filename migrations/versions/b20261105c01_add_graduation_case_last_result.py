"""add graduation_cases.last_result

畢業缺口案件記錄最近一次同步看到的判斷結果，同步只在結果轉變時動作。

Revision ID: b20261105c01
Revises: b20261105b01
Create Date: 2026-11-05
"""
from alembic import op
import sqlalchemy as sa


revision = "b20261105c01"
down_revision = "b20261105b01"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    # 測試或既有資料庫可能已用 models 建過欄位，有就跳過
    if not inspector.has_table("graduation_cases"):
        return
    columns = {column["name"] for column in inspector.get_columns("graduation_cases")}
    if "last_result" not in columns:
        op.add_column("graduation_cases", sa.Column("last_result", sa.String(length=30), nullable=True))


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("graduation_cases"):
        return
    if "last_result" not in {column["name"] for column in inspector.get_columns("graduation_cases")}:
        return
    if op.get_bind().dialect.name == "sqlite":
        # SQLite 3.35 起支援 DROP COLUMN；batch 模式要反射 users 表，但遷移鏈裡沒有建立它
        op.execute("ALTER TABLE graduation_cases DROP COLUMN last_result")
    else:
        op.drop_column("graduation_cases", "last_result")
