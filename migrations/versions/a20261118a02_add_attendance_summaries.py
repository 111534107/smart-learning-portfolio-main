"""Add private attendance totals.

Revision ID: a20261118a02
Revises: c20261118a01
"""
from alembic import op
import sqlalchemy as sa


revision = "a20261118a02"
down_revision = "c20261118a01"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("attendance_summaries"):
        columns = {column["name"] for column in inspector.get_columns("attendance_summaries")}
        term_key = ["student_id", "school_year", "semester"]
        keys = inspector.get_unique_constraints("attendance_summaries")
        if not {"id", *term_key, "totals"} <= columns or not any(
            key["column_names"] == term_key for key in keys
        ):
            raise RuntimeError("Existing attendance_summaries schema is incompatible with revision a20261118a02.")
        return
    op.create_table(
        "attendance_summaries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("school_year", sa.Integer(), nullable=False),
        sa.Column("semester", sa.Integer(), nullable=False),
        sa.Column("totals", sa.JSON(), nullable=False),
        sa.UniqueConstraint("student_id", "school_year", "semester", name="uq_attendance_student_term"),
    )


def downgrade():
    if sa.inspect(op.get_bind()).has_table("attendance_summaries"):
        op.drop_table("attendance_summaries")
