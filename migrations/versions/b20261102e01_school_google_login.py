"""Bind existing students to a Google identity.

Revision ID: b20261102e01
Revises: a20261022e01

組員 111534107 原版接在 (a20261022e01, e5b9d1c3a826) 兩個版本後面；本專案已是單一直線，改接 a20261022e01。
"""
from alembic import op
import sqlalchemy as sa


revision = "b20261102e01"
down_revision = "a20261022e01"
branch_labels = None
depends_on = None


def _has_google_sub():
    inspector = sa.inspect(op.get_bind())
    return inspector.has_table("users") and "google_sub" in {c["name"] for c in inspector.get_columns("users")}


def upgrade():
    # users 表由初始建表產生，不在遷移鏈裡；只用遷移建的測試資料庫沒有這張表，就跳過（同 d8f3b6a2c417 的做法）
    if not sa.inspect(op.get_bind()).has_table("users") or _has_google_sub():
        return
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("google_sub", sa.String(length=255), nullable=True))
    op.create_index("ix_users_google_sub", "users", ["google_sub"], unique=True)


def downgrade():
    if not _has_google_sub():
        return
    op.drop_index("ix_users_google_sub", table_name="users")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("google_sub")
