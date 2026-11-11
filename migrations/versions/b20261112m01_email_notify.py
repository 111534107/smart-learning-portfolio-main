"""電子郵件通知：users.email_notify、notifications.notify_key

2026-11-12：學生、導師可在帳號設定關閉郵件通知；各學期預警與檢核日期倒數的通知用 notify_key 去重。

Revision ID: b20261112m01
Revises: b20261110h01
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa


revision = "b20261112m01"
down_revision = "b20261110h01"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    # 遷移鏈的測試資料庫不一定有 users／notifications（同其他遷移），沒有就跳過
    if inspector.has_table("users") and "email_notify" not in {c["name"] for c in inspector.get_columns("users")}:
        with op.batch_alter_table("users") as batch:
            batch.add_column(sa.Column("email_notify", sa.Boolean(), nullable=False, server_default=sa.true()))
    if inspector.has_table("notifications") and inspector.has_table("users") and "notify_key" not in {
            c["name"] for c in inspector.get_columns("notifications")}:
        with op.batch_alter_table("notifications") as batch:
            batch.add_column(sa.Column("notify_key", sa.String(length=120), nullable=True))
            batch.create_unique_constraint("uq_notification_recipient_key", ["recipient_id", "notify_key"])


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("notifications") and inspector.has_table("users") and "notify_key" in {
            c["name"] for c in inspector.get_columns("notifications")}:
        with op.batch_alter_table("notifications") as batch:
            batch.drop_constraint("uq_notification_recipient_key", type_="unique")
            batch.drop_column("notify_key")
    if inspector.has_table("users") and "email_notify" in {c["name"] for c in inspector.get_columns("users")}:
        with op.batch_alter_table("users") as batch:
            batch.drop_column("email_notify")
