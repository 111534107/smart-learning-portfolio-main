"""add form library (表單下載區 UC-28／F-53)

科辦上架表單的分類、表單與版本。收件暫停，不建收件的表。

Revision ID: b20261108f01
Revises: b20261105c01
Create Date: 2026-11-08
"""
from alembic import op
import sqlalchemy as sa


revision = "b20261108f01"
down_revision = "b20261105c01"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    # 測試或既有資料庫可能已用 models 建過，有就跳過。users 表只有完整資料庫才有，外鍵只在那時加
    has_users = inspector.has_table("users")
    user_fk = (lambda: [sa.ForeignKey("users.id")]) if has_users else (lambda: [])

    if not inspector.has_table("form_categories"):
        op.create_table(
            "form_categories",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=50), nullable=False, unique=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    if not inspector.has_table("form_items"):
        op.create_table(
            "form_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("category_id", sa.Integer(), sa.ForeignKey("form_categories.id"), nullable=False, index=True),
            sa.Column("title", sa.String(length=100), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("open_to_students", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("open_to_teachers", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.true(), index=True),
            sa.Column("created_by_id", sa.Integer(), *user_fk(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
    if not inspector.has_table("form_item_versions"):
        op.create_table(
            "form_item_versions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("item_id", sa.Integer(), sa.ForeignKey("form_items.id"), nullable=False, index=True),
            sa.Column("version_no", sa.Integer(), nullable=False),
            sa.Column("file_path", sa.String(length=500), nullable=False),
            sa.Column("original_filename", sa.String(length=255), nullable=False),
            sa.Column("file_size", sa.Integer(), nullable=False),
            sa.Column("file_sha256", sa.String(length=64), nullable=False),
            sa.Column("note", sa.String(length=200), nullable=True),
            sa.Column("uploaded_by_id", sa.Integer(), *user_fk(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("item_id", "version_no", name="uq_form_item_version"),
        )


def downgrade():
    inspector = sa.inspect(op.get_bind())
    for table in ("form_item_versions", "form_items", "form_categories"):
        if inspector.has_table(table):
            op.drop_table(table)
