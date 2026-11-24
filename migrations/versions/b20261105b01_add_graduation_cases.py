"""add graduation_cases, graduation_case_events, notifications

畢業缺口案件、案件事件與站內通知。

Revision ID: b20261105b01
Revises: b20261105a01
Create Date: 2026-11-05
"""
from alembic import op
import sqlalchemy as sa


revision = "b20261105b01"
down_revision = "b20261105a01"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())

    # 測試或既有資料庫可能已用 models 建過表，有就跳過
    if not inspector.has_table("graduation_cases"):
        op.create_table(
            "graduation_cases",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("student_id", sa.Integer(), nullable=False),
            sa.Column("case_type", sa.String(length=20), nullable=False),
            sa.Column("item", sa.String(length=40), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("close_reason", sa.String(length=20), nullable=True),
            sa.Column("initial_amount", sa.Integer(), nullable=True),
            sa.Column("current_amount", sa.Integer(), nullable=True),
            sa.Column("unit", sa.String(length=20), nullable=True),
            sa.Column("basis", sa.String(length=255), nullable=False),
            sa.Column("detail", sa.Text(), nullable=False),
            sa.Column("open_key", sa.String(length=80), nullable=True),
            sa.Column("previous_case_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("closed_at", sa.DateTime(), nullable=True),
            sa.Column("closed_by_id", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["previous_case_id"], ["graduation_cases.id"]),
            sa.ForeignKeyConstraint(["closed_by_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("open_key"),
        )
        op.create_index("ix_graduation_cases_student_id", "graduation_cases", ["student_id"])

    if not inspector.has_table("graduation_case_events"):
        op.create_table(
            "graduation_case_events",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("case_id", sa.Integer(), nullable=False),
            sa.Column("actor_id", sa.Integer(), nullable=True),
            sa.Column("event_type", sa.String(length=30), nullable=False),
            sa.Column("from_status", sa.String(length=30), nullable=True),
            sa.Column("to_status", sa.String(length=30), nullable=True),
            sa.Column("amount_before", sa.Integer(), nullable=True),
            sa.Column("amount_after", sa.Integer(), nullable=True),
            sa.Column("note", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["case_id"], ["graduation_cases.id"]),
            sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_graduation_case_events_case_id", "graduation_case_events", ["case_id"])

    if not inspector.has_table("notifications"):
        op.create_table(
            "notifications",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("recipient_id", sa.Integer(), nullable=False),
            sa.Column("case_id", sa.Integer(), nullable=False),
            sa.Column("event_id", sa.Integer(), nullable=False),
            sa.Column("message", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("read_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["recipient_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["case_id"], ["graduation_cases.id"]),
            sa.ForeignKeyConstraint(["event_id"], ["graduation_case_events.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("recipient_id", "event_id", name="uq_notification_recipient_event"),
        )
        op.create_index("ix_notifications_recipient_id", "notifications", ["recipient_id"])
        op.create_index("ix_notifications_case_id", "notifications", ["case_id"])


def downgrade():
    op.drop_index("ix_notifications_case_id", table_name="notifications")
    op.drop_index("ix_notifications_recipient_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_graduation_case_events_case_id", table_name="graduation_case_events")
    op.drop_table("graduation_case_events")
    op.drop_index("ix_graduation_cases_student_id", table_name="graduation_cases")
    op.drop_table("graduation_cases")
