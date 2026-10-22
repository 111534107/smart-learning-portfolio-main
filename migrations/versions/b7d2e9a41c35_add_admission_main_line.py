"""add admission programs, student targets, class advisors and package reviews

Revision ID: b7d2e9a41c35
Revises: fc61707846c7
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa


revision = "b7d2e9a41c35"
down_revision = "fc61707846c7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "admission_rule_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("program_code", sa.String(length=20), nullable=False),
        sa.Column("admission_year", sa.Integer(), nullable=False),
        sa.Column("school_name", sa.String(length=100), nullable=False),
        sa.Column("department_name", sa.String(length=100), nullable=False),
        sa.Column("admission_category", sa.String(length=50), nullable=True),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("source_note", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("data_origin", sa.String(length=20), nullable=False),
        sa.Column("checked_at", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("program_code", "admission_year", name="uq_program_year"),
    )
    op.create_index("ix_admission_rule_versions_program_code", "admission_rule_versions", ["program_code"])
    op.create_index("ix_admission_rule_versions_admission_year", "admission_rule_versions", ["admission_year"])
    op.create_index("ix_admission_rule_versions_status", "admission_rule_versions", ["status"])

    op.create_table(
        "admission_rule_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rule_version_id", sa.Integer(), sa.ForeignKey("admission_rule_versions.id"), nullable=False),
        sa.Column("source_item_name", sa.String(length=100), nullable=False),
        sa.Column("weight_percent", sa.Integer(), nullable=False),
        sa.Column("mapped_categories", sa.String(length=200), nullable=False),
        sa.Column("mapping_status", sa.String(length=20), nullable=False),
        sa.Column("requirement", sa.Text(), nullable=True),
        sa.Column("is_required", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
    )
    op.create_index("ix_admission_rule_items_rule_version_id", "admission_rule_items", ["rule_version_id"])

    op.create_table(
        "student_targets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("rule_version_id", sa.Integer(), sa.ForeignKey("admission_rule_versions.id"), nullable=False),
        sa.Column("selected_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("student_id", "rule_version_id", name="uq_student_target"),
    )
    op.create_index("ix_student_targets_student_id", "student_targets", ["student_id"])

    op.create_table(
        "class_advisors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("teacher_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("class_name", sa.String(length=50), nullable=False),
        sa.Column("school_year", sa.Integer(), nullable=False),
        sa.UniqueConstraint("teacher_id", "class_name", "school_year", name="uq_class_advisor"),
    )
    op.create_index("ix_class_advisors_teacher_id", "class_advisors", ["teacher_id"])

    op.create_table(
        "package_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("rule_version_id", sa.Integer(), sa.ForeignKey("admission_rule_versions.id"), nullable=False),
        sa.Column("teacher_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("readiness_percent", sa.Integer(), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_package_reviews_student_id", "package_reviews", ["student_id"])
    op.create_index("ix_package_reviews_status", "package_reviews", ["status"])


def downgrade():
    op.drop_index("ix_package_reviews_status", table_name="package_reviews")
    op.drop_index("ix_package_reviews_student_id", table_name="package_reviews")
    op.drop_table("package_reviews")
    op.drop_index("ix_class_advisors_teacher_id", table_name="class_advisors")
    op.drop_table("class_advisors")
    op.drop_index("ix_student_targets_student_id", table_name="student_targets")
    op.drop_table("student_targets")
    op.drop_index("ix_admission_rule_items_rule_version_id", table_name="admission_rule_items")
    op.drop_table("admission_rule_items")
    op.drop_index("ix_admission_rule_versions_status", table_name="admission_rule_versions")
    op.drop_index("ix_admission_rule_versions_admission_year", table_name="admission_rule_versions")
    op.drop_index("ix_admission_rule_versions_program_code", table_name="admission_rule_versions")
    op.drop_table("admission_rule_versions")
