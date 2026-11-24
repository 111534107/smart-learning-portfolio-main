"""add two-factor authentication (Authenticator 六位數驗證碼)

users 加三欄（加密後的金鑰、開啟時間、最後用過的時間窗）；新增備用碼表。

Revision ID: b20261109d01
Revises: b20261109c01
Create Date: 2026-11-09
"""
from alembic import op
import sqlalchemy as sa


revision = "b20261109d01"
down_revision = "b20261109c01"
branch_labels = None
depends_on = None

COLUMNS = (
    ("two_factor_secret", sa.Text()),
    ("two_factor_enabled_at", sa.DateTime()),
    ("two_factor_last_counter", sa.Integer()),
)


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("users"):
        existing = {column["name"] for column in inspector.get_columns("users")}
        for name, column_type in COLUMNS:
            if name not in existing:
                op.add_column("users", sa.Column(name, column_type, nullable=True))
    if not inspector.has_table("user_backup_codes"):
        user_fk = [sa.ForeignKey("users.id")] if inspector.has_table("users") else []
        op.create_table(
            "user_backup_codes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), *user_fk, nullable=False, index=True),
            sa.Column("code_hash", sa.String(length=255), nullable=False),
            sa.Column("used_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("user_backup_codes"):
        op.drop_table("user_backup_codes")
    if inspector.has_table("users"):
        existing = {column["name"] for column in inspector.get_columns("users")}
        with op.batch_alter_table("users") as batch:
            for name, _ in COLUMNS:
                if name in existing:
                    batch.drop_column(name)
