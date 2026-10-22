"""add structured admission eligibility rules

Revision ID: a20261022e01
Revises: a7c3e9d10f42
Create Date: 2026-10-22
"""
from alembic import op
import sqlalchemy as sa


revision = "a20261022e01"
down_revision = "a7c3e9d10f42"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "admission_eligibility_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("rule_version_id", sa.Integer(), nullable=False),
        sa.Column("rule_group", sa.Integer(), nullable=False),
        sa.Column("condition_type", sa.String(length=40), nullable=False),
        sa.Column("operator", sa.String(length=30), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("source_location", sa.String(length=150), nullable=True),
        sa.Column("mapping_status", sa.String(length=20), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["rule_version_id"], ["admission_rule_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_admission_eligibility_rules_rule_version_id",
        "admission_eligibility_rules", ["rule_version_id"], unique=False,
    )
    op.create_index(
        "ix_admission_eligibility_rules_mapping_status",
        "admission_eligibility_rules", ["mapping_status"], unique=False,
    )
    op.create_index(
        "ix_admission_eligibility_rule_version_status",
        "admission_eligibility_rules", ["rule_version_id", "mapping_status"], unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_admission_eligibility_rule_version_status", table_name="admission_eligibility_rules"
    )
    op.drop_index(
        "ix_admission_eligibility_rules_mapping_status", table_name="admission_eligibility_rules"
    )
    op.drop_index(
        "ix_admission_eligibility_rules_rule_version_id", table_name="admission_eligibility_rules"
    )
    op.drop_table("admission_eligibility_rules")
