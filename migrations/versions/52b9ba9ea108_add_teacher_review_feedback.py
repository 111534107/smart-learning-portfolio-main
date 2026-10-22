"""add teacher review feedback

Revision ID: 52b9ba9ea108
Revises: 
Create Date: 2026-09-21 16:10:21.145982

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '52b9ba9ea108'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "teacher_review_feedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("submission_id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["submission_id"], ["portfolio_submissions.id"]),
        sa.ForeignKeyConstraint(["teacher_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index(
        op.f("ix_teacher_review_feedback_submission_id"),
        "teacher_review_feedback",
        ["submission_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_teacher_review_feedback_teacher_id"),
        "teacher_review_feedback",
        ["teacher_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_teacher_review_feedback_teacher_id"), table_name="teacher_review_feedback")
    op.drop_index(op.f("ix_teacher_review_feedback_submission_id"), table_name="teacher_review_feedback")
    op.drop_table("teacher_review_feedback")
