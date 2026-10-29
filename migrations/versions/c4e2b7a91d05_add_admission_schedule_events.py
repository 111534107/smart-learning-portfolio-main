"""add admission schedule events (升學 Agent 擷取的招生日程，管理員核准後使用)"""

from alembic import op
import sqlalchemy as sa


revision = "c4e2b7a91d05"
down_revision = "a7c3e9d10f42"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "admission_schedule_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel", sa.String(length=30), nullable=False),
        sa.Column("admission_year", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("start_at", sa.DateTime(), nullable=False),
        sa.Column("end_at", sa.DateTime(), nullable=True),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("data_origin", sa.String(length=20), nullable=False),
        sa.Column("change_id", sa.Integer(), sa.ForeignKey("public_source_changes.id"), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_admission_schedule_events_channel", "admission_schedule_events", ["channel"])
    op.create_index("ix_admission_schedule_events_admission_year", "admission_schedule_events", ["admission_year"])
    op.create_index("ix_admission_schedule_events_status", "admission_schedule_events", ["status"])


def downgrade():
    op.drop_index("ix_admission_schedule_events_status", table_name="admission_schedule_events")
    op.drop_index("ix_admission_schedule_events_admission_year", table_name="admission_schedule_events")
    op.drop_index("ix_admission_schedule_events_channel", table_name="admission_schedule_events")
    op.drop_table("admission_schedule_events")
