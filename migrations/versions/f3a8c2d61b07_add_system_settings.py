"""add system settings (OCR device switch for administrators)"""

from alembic import op
import sqlalchemy as sa


revision = "f3a8c2d61b07"
down_revision = "e4d7a9c1b602"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "system_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("key", name="uq_system_settings_key"),
    )


def downgrade():
    op.drop_table("system_settings")
