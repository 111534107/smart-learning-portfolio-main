"""add announcements（二技公告 UC-25）

通用公告表與已讀表；第一版畫面只做二技公告。

Revision ID: b20261110a01
Revises: b20261108f01
Create Date: 2026-11-10
"""
from alembic import op
import sqlalchemy as sa


revision = "b20261110a01"
down_revision = "b20261108f01"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    # 測試或既有資料庫可能已用 models 建過，有就跳過。users 表只有完整資料庫才有，外鍵只在那時加
    has_users = inspector.has_table("users")
    user_fk = (lambda: [sa.ForeignKey("users.id")]) if has_users else (lambda: [])

    if not inspector.has_table("announcements"):
        op.create_table(
            "announcements",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("kind", sa.String(length=20), nullable=False, server_default="admission", index=True),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("audience", sa.String(length=60), nullable=False, server_default="student,teacher,staff"),
            sa.Column("channel", sa.String(length=30), nullable=True),
            sa.Column("admission_year", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="draft", index=True),
            sa.Column("created_by", sa.Integer(), *user_fk(), nullable=False),
            sa.Column("published_by", sa.Integer(), *user_fk(), nullable=True),
            sa.Column("published_at", sa.DateTime(), nullable=True),
            sa.Column("withdrawn_by", sa.Integer(), *user_fk(), nullable=True),
            sa.Column("withdrawn_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    if not inspector.has_table("announcement_reads"):
        op.create_table(
            "announcement_reads",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("announcement_id", sa.Integer(), sa.ForeignKey("announcements.id"), nullable=False, index=True),
            sa.Column("user_id", sa.Integer(), *user_fk(), nullable=False, index=True),
            sa.Column("read_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("announcement_id", "user_id", name="uq_announcement_read"),
        )


def downgrade():
    inspector = sa.inspect(op.get_bind())
    for table in ("announcement_reads", "announcements"):
        if inspector.has_table(table):
            op.drop_table(table)
