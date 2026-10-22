"""add manually tracked transfer credit records

Revision ID: a920261013tc
Revises: e6c1a3b8f215
Create Date: 2026-10-13
"""
from alembic import op
import sqlalchemy as sa


revision = "a920261013tc"
down_revision = "e6c1a3b8f215"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "transfer_credit_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("submitted_on", sa.Date(), nullable=True),
        sa.Column("missing_documents", sa.String(length=1000), nullable=False),
        sa.Column("note", sa.String(length=2000), nullable=False),
        sa.Column("teacher_confirmed", sa.Boolean(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=True),
        sa.Column("teacher_confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["teacher_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_transfer_credit_records_student_id",
        "transfer_credit_records",
        ["student_id"],
        unique=True,
    )


def downgrade():
    op.drop_index("ix_transfer_credit_records_student_id", table_name="transfer_credit_records")
    op.drop_table("transfer_credit_records")
