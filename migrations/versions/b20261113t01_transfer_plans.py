"""插大自填目標：transfer_plans、transfer_plan_subjects（B18）

Revision ID: b20261113t01
Revises: b20261113s01
Create Date: 2026-11-13
"""
import sqlalchemy as sa
from alembic import op

revision = "b20261113t01"
down_revision = "b20261113s01"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("transfer_plans"):
        op.create_table(
            "transfer_plans",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("school_name", sa.String(100), nullable=False),
            sa.Column("department_name", sa.String(100), nullable=False),
            sa.Column("entry_grade", sa.Integer(), nullable=True),
            sa.Column("admission_year", sa.Integer(), nullable=False),
            sa.Column("brochure_url", sa.String(500), nullable=True),
            sa.Column("apply_start", sa.Date(), nullable=True),
            sa.Column("apply_end", sa.Date(), nullable=True),
            sa.Column("exam_date", sa.Date(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("teacher_note", sa.Text(), nullable=True),
            sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        )
        op.create_index("ix_transfer_plans_student_id", "transfer_plans", ["student_id"])
    if not inspector.has_table("transfer_plan_subjects"):
        op.create_table(
            "transfer_plan_subjects",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("plan_id", sa.Integer(), sa.ForeignKey("transfer_plans.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(60), nullable=False),
            sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        )
        op.create_index("ix_transfer_plan_subjects_plan_id", "transfer_plan_subjects", ["plan_id"])


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("transfer_plan_subjects"):
        op.drop_table("transfer_plan_subjects")
    if inspector.has_table("transfer_plans"):
        op.drop_table("transfer_plans")
