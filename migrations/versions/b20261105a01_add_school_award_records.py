"""add school_award_records

保存學校獎懲記錄的每一列（獎勵與懲處），用 record_key 防止重複匯入。

Revision ID: b20261105a01
Revises: b20261104d01
Create Date: 2026-11-05
"""
from alembic import op
import sqlalchemy as sa


revision = "b20261105a01"
down_revision = "b20261104d01"
branch_labels = None
depends_on = None


def upgrade():
    # 測試或既有資料庫可能已用 models 建過這張表，有就跳過
    if sa.inspect(op.get_bind()).has_table("school_award_records"):
        return
    op.create_table(
        "school_award_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("source_document_id", sa.Integer(), nullable=True),
        sa.Column("portfolio_id", sa.Integer(), nullable=True),
        sa.Column("record_key", sa.String(length=64), nullable=False),
        sa.Column("record_type", sa.String(length=20), nullable=False),
        sa.Column("date", sa.String(length=20), nullable=True),
        sa.Column("name", sa.String(length=20), nullable=True),
        sa.Column("count", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("revoked", sa.String(length=50), nullable=False, server_default=""),
        sa.Column("school_year", sa.Integer(), nullable=True),
        sa.Column("semester", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["source_document_id"], ["source_documents.id"]),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "record_key", name="uq_school_award_student_key"),
    )
    op.create_index("ix_school_award_records_student_id", "school_award_records", ["student_id"])


def downgrade():
    op.drop_index("ix_school_award_records_student_id", table_name="school_award_records")
    op.drop_table("school_award_records")
