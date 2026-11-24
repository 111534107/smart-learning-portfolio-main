"""add excluded_from_package（學生選擇不放進備審）

2026-11-12 導師：學生要能選擇某些資料不放進備審（例如覺得成績不好看），簡章規定必備的不能拿掉。
成績、證照、經歷三張表各加一個欄位，預設都放。

Revision ID: b20261112x01
Revises: b20261110h01
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa


revision = "b20261112x01"
down_revision = "b20261110h01"
branch_labels = None
depends_on = None

TABLES = ("learning_course_records", "credential_records", "portfolios")
COLUMN = "excluded_from_package"


def upgrade():
    inspector = sa.inspect(op.get_bind())
    for table in TABLES:
        if inspector.has_table(table) and COLUMN not in {c["name"] for c in inspector.get_columns(table)}:
            op.add_column(table, sa.Column(COLUMN, sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    inspector = sa.inspect(op.get_bind())
    for table in TABLES:
        if inspector.has_table(table) and COLUMN in {c["name"] for c in inspector.get_columns(table)}:
            op.drop_column(table, COLUMN)  # 不用 batch：重建整張表要反射外鍵，從零升級時 users 表可能不存在
