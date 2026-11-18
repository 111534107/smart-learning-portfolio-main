"""送審決定記錄導師有沒有看自傳：package_reviews 新增 autobiography_viewed（可為空）。

只存是／否，不存自傳內容。可為空的布林欄位，SQLite 與 MySQL 都能直接新增；舊資料維持空值。

Revision ID: e20261118c01
Revises: d20261118m01
"""

from alembic import op
import sqlalchemy as sa

revision = "e20261118c01"
down_revision = "d20261118m01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("package_reviews", sa.Column("autobiography_viewed", sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column("package_reviews", "autobiography_viewed")
