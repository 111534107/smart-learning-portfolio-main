"""add curriculum versions (修業科目表代理)

代理從資管科網頁抓修業科目表 PDF、程式解析後存成候選版本；管理員確認才生效。

Revision ID: b20261109c01
Revises: b20261108f01
Create Date: 2026-11-09
"""
from alembic import op
import sqlalchemy as sa


revision = "b20261109c01"
down_revision = "b20261108f01"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    # 測試或既有資料庫可能已用 models 建過，有就跳過。users 表只有完整資料庫才有，外鍵只在那時加
    user_fk = [sa.ForeignKey("users.id")] if inspector.has_table("users") else []

    if not inspector.has_table("curriculum_versions"):
        op.create_table(
            "curriculum_versions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("admission_year", sa.Integer(), nullable=False, index=True),
            sa.Column("status", sa.String(length=20), nullable=False, index=True),
            sa.Column("source_url", sa.String(length=500), nullable=False),
            sa.Column("file_sha256", sa.String(length=64), nullable=False, index=True),
            sa.Column("total_credits", sa.Integer(), nullable=True),
            sa.Column("required_credits", sa.Integer(), nullable=True),
            sa.Column("elective_credits", sa.Integer(), nullable=True),
            sa.Column("checks_json", sa.JSON(), nullable=True),
            sa.Column("diff_json", sa.JSON(), nullable=True),
            sa.Column("notes_json", sa.JSON(), nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("reviewed_by_id", sa.Integer(), *user_fk, nullable=True),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        )
    if not inspector.has_table("curriculum_courses"):
        op.create_table(
            "curriculum_courses",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("version_id", sa.Integer(), sa.ForeignKey("curriculum_versions.id"), nullable=False, index=True),
            sa.Column("category", sa.String(length=20), nullable=True),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("english_name", sa.String(length=200), nullable=True),
            sa.Column("credits", sa.Integer(), nullable=False),
            sa.Column("hours", sa.Integer(), nullable=False),
            sa.Column("note", sa.String(length=100), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False),
        )


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("curriculum_courses"):
        op.drop_table("curriculum_courses")
    if inspector.has_table("curriculum_versions"):
        op.drop_table("curriculum_versions")
