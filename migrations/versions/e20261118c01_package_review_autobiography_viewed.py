"""送審決定記錄導師有沒有看自傳：package_reviews 新增 autobiography_viewed（可為空）。

只存是／否，不存自傳內容。可為空的布林欄位，SQLite 與 MySQL 都能直接新增；舊資料維持空值。

Revision ID: e20261118c01
Revises: a20261118a02
"""

from alembic import op
import sqlalchemy as sa

revision = "e20261118c01"
down_revision = "a20261118a02"
branch_labels = None
depends_on = None


TABLE = "package_reviews"


def _columns():
    inspector = sa.inspect(op.get_bind())
    return {c["name"] for c in inspector.get_columns(TABLE)} if inspector.has_table(TABLE) else None


def upgrade():
    existing = _columns()
    if existing is not None and "autobiography_viewed" not in existing:
        op.add_column(TABLE, sa.Column("autobiography_viewed", sa.Boolean(), nullable=True))


def downgrade():
    existing = _columns()
    if existing is not None and "autobiography_viewed" in existing:
        op.drop_column(TABLE, "autobiography_viewed")
