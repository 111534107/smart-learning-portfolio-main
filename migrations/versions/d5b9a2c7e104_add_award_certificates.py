"""add award certificates

科辦替科上派的服務開的電子獎狀（申請、核准或退回、驗證碼）。

Revision ID: d5b9a2c7e104
Revises: c4a8f1e2d903
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa


revision = "d5b9a2c7e104"
down_revision = "c4a8f1e2d903"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "award_certificates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("portfolio_id", sa.Integer(), sa.ForeignKey("portfolios.id"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=50), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("issuer", sa.String(length=100), nullable=False),
        sa.Column("issued_on", sa.Date(), nullable=True),
        sa.Column("verify_code", sa.String(length=12), nullable=True),
        sa.Column("return_reason", sa.String(length=500), nullable=True),
        sa.Column("reviewed_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("portfolio_id", name="uq_award_certificates_portfolio_id"),
        sa.UniqueConstraint("verify_code", name="uq_award_certificates_verify_code"),
    )
    op.create_index("ix_award_certificates_student_id", "award_certificates", ["student_id"])
    op.create_index("ix_award_certificates_status", "award_certificates", ["status"])


def downgrade():
    op.drop_index("ix_award_certificates_status", table_name="award_certificates")
    op.drop_index("ix_award_certificates_student_id", table_name="award_certificates")
    op.drop_table("award_certificates")
