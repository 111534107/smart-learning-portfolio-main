"""add users.backup_email（學生備用信箱，用來收備審打包）

2026-11-13 使用者：學生要能綁定自己的另一個信箱，把備審資料一鍵打包寄過去。
備用信箱要驗證過（backup_email_verified_at 有值）才會寄。

Revision ID: b20261114p01
Revises: b20261113t01
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa


revision = "b20261114p01"
down_revision = "b20261113t01"
branch_labels = None
depends_on = None

TABLE = "users"
COLUMNS = (("backup_email", sa.String(255)), ("backup_email_verified_at", sa.DateTime()))


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(TABLE):
        return
    existing = {column["name"] for column in inspector.get_columns(TABLE)}
    for name, column_type in COLUMNS:
        if name not in existing:
            op.add_column(TABLE, sa.Column(name, column_type, nullable=True))


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(TABLE):
        return
    existing = {column["name"] for column in inspector.get_columns(TABLE)}
    for name, _ in reversed(COLUMNS):
        if name in existing:
            op.drop_column(TABLE, name)  # 不用 batch：重建整張表要反射外鍵，從零升級時相關表可能不存在
