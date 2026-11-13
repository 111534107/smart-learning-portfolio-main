"""certificate kinds and non-case notifications

電子獎狀加類別（服務證明、TA 證明、社團證明）；站內通知可以不屬於畢業缺口案件，
case_id、event_id 改成可空，另加 link 存要開啟的站內網址（電子獎狀核准或退回通知用）。

Revision ID: b20261108a01
Revises: b20261105c01
Create Date: 2026-11-08
"""
from alembic import op
import sqlalchemy as sa


revision = "b20261108a01"
down_revision = "b20261105c01"
branch_labels = None
depends_on = None

# 遷移鏈裡沒有建立 users 等表；batch 模式重建 SQLite 表時不要去反射外鍵指向的表
REFLECT = {"resolve_fks": False}


def _columns(inspector, table):
    return {column["name"]: column for column in inspector.get_columns(table)}


def upgrade():
    inspector = sa.inspect(op.get_bind())
    # 測試或既有資料庫可能已用 models 建過欄位，有就跳過
    if inspector.has_table("award_certificates") and "kind" not in _columns(inspector, "award_certificates"):
        op.add_column("award_certificates", sa.Column(
            "kind", sa.String(length=20), nullable=False, server_default="service"))

    if inspector.has_table("notifications"):
        columns = _columns(inspector, "notifications")
        with op.batch_alter_table("notifications", reflect_kwargs=REFLECT) as batch:
            if "link" not in columns:
                batch.add_column(sa.Column("link", sa.String(length=255), nullable=True))
            # case_id 在 2026-11-13 正規化後移除；用新模型建的資料庫沒有這欄就跳過
            if "case_id" in columns and not columns["case_id"]["nullable"]:
                batch.alter_column("case_id", existing_type=sa.Integer(), nullable=True)
            if not columns["event_id"]["nullable"]:
                batch.alter_column("event_id", existing_type=sa.Integer(), nullable=True)


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("notifications"):
        columns = _columns(inspector, "notifications")
        # 非案件的通知回不到舊表結構（舊版 case_id、event_id 不可空），先刪掉
        op.execute("DELETE FROM notifications WHERE event_id IS NULL" + (" OR case_id IS NULL" if "case_id" in columns else ""))
        with op.batch_alter_table("notifications", reflect_kwargs=REFLECT) as batch:
            if "link" in columns:
                batch.drop_column("link")
            if "case_id" in columns:
                batch.alter_column("case_id", existing_type=sa.Integer(), nullable=False)
            batch.alter_column("event_id", existing_type=sa.Integer(), nullable=False)

    if inspector.has_table("award_certificates") and "kind" in _columns(inspector, "award_certificates"):
        if op.get_bind().dialect.name == "sqlite":
            op.execute("ALTER TABLE award_certificates DROP COLUMN kind")
        else:
            op.drop_column("award_certificates", "kind")
