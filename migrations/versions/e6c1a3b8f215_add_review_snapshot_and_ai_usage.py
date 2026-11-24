"""add review snapshot and ai daily usage

資管科小助手「確認與版本」：導師確認的送審快照、學校 AI 金鑰每人每日用量。

Revision ID: e6c1a3b8f215
Revises: d5b9a2c7e104
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa


revision = "e6c1a3b8f215"
down_revision = "d5b9a2c7e104"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("package_reviews", sa.Column("snapshot_json", sa.JSON(), nullable=True))
    op.create_table(
        "ai_daily_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("key_kind", sa.String(length=20), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "usage_date", "key_kind", name="uq_ai_daily_usage"),
    )
    op.create_index("ix_ai_daily_usage_user_id", "ai_daily_usage", ["user_id"])


def downgrade():
    op.drop_index("ix_ai_daily_usage_user_id", table_name="ai_daily_usage")
    op.drop_table("ai_daily_usage")
    if op.get_bind().dialect.name == "sqlite":
        # SQLite 3.35 起支援 DROP COLUMN；batch 模式要反射 users 表，但遷移鏈裡沒有建立它
        op.execute("ALTER TABLE package_reviews DROP COLUMN snapshot_json")
    else:
        op.drop_column("package_reviews", "snapshot_json")
