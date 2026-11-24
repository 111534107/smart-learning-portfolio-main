"""add form_items link columns（表單下載區的學校網站連結與失效檢查）

2026-11-12 指導老師：表單下載區的學校網站連結常失效，要能檢查並提醒換成最新版。
每份表單加上連結、最後檢查的狀態、原因與時間。

Revision ID: b20261112f01
Revises: b20261110h01
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa


revision = "b20261112f01"
down_revision = "b20261110h01"
branch_labels = None
depends_on = None

TABLE = "form_items"
# 遷移鏈裡沒有建立 users 等表；batch 模式重建 SQLite 表時不要去反射外鍵指向的表
REFLECT = {"resolve_fks": False}
COLUMNS = (
    ("source_url", sa.String(length=500)),
    ("link_status", sa.String(length=20)),
    ("link_detail", sa.String(length=100)),
    ("link_checked_at", sa.DateTime()),
)


def _existing(inspector):
    return {column["name"] for column in inspector.get_columns(TABLE)}


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(TABLE):
        return
    existing = _existing(inspector)  # 測試或既有資料庫可能已用 models 建過欄位，有就跳過
    for name, column_type in COLUMNS:
        if name not in existing:
            op.add_column(TABLE, sa.Column(name, column_type, nullable=True))


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(TABLE):
        return
    existing = _existing(inspector)
    with op.batch_alter_table(TABLE, reflect_kwargs=REFLECT) as batch:
        for name, _ in COLUMNS:
            if name in existing:
                batch.drop_column(name)
