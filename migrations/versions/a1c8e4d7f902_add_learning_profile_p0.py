"""add learning profile p0 tables

Revision ID: a1c8e4d7f902
Revises: 52b9ba9ea108
Create Date: 2026-09-23
"""

from alembic import op
import sqlalchemy as sa


revision = "a1c8e4d7f902"
down_revision = "52b9ba9ea108"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "source_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("document_type", sa.String(length=30), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index(op.f("ix_source_documents_owner_id"), "source_documents", ["owner_id"], unique=False)
    op.create_index(op.f("ix_source_documents_document_type"), "source_documents", ["document_type"], unique=False)
    op.create_index(op.f("ix_source_documents_sha256"), "source_documents", ["sha256"], unique=False)
    op.create_index(op.f("ix_source_documents_status"), "source_documents", ["status"], unique=False)

    op.create_table(
        "document_extractions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_document_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("confirmed_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["confirmed_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["source_document_id"], ["source_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_document_id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index(op.f("ix_document_extractions_status"), "document_extractions", ["status"], unique=False)

    op.create_table(
        "learning_course_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("source_document_id", sa.Integer(), nullable=True),
        sa.Column("school_year", sa.Integer(), nullable=True),
        sa.Column("semester", sa.String(length=20), nullable=True),
        sa.Column("course_name", sa.String(length=150), nullable=False),
        sa.Column("normalized_course_name", sa.String(length=150), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("status_mark", sa.String(length=10), nullable=True),
        sa.Column("confirmation_status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["source_document_id"], ["source_documents.id"]),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index(op.f("ix_learning_course_records_student_id"), "learning_course_records", ["student_id"], unique=False)
    op.create_index(op.f("ix_learning_course_records_source_document_id"), "learning_course_records", ["source_document_id"], unique=False)
    op.create_index(op.f("ix_learning_course_records_normalized_course_name"), "learning_course_records", ["normalized_course_name"], unique=False)
    op.create_index(op.f("ix_learning_course_records_confirmation_status"), "learning_course_records", ["confirmation_status"], unique=False)

    op.create_table(
        "course_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("school_year", sa.Integer(), nullable=False),
        sa.Column("course_name", sa.String(length=150), nullable=False),
        sa.Column("normalized_course_name", sa.String(length=150), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("requirement_type", sa.String(length=30), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=True),
        sa.Column("ability_domain", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("school_year", "normalized_course_name", name="uq_course_rule_year_name"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index(op.f("ix_course_rules_school_year"), "course_rules", ["school_year"], unique=False)
    op.create_index(op.f("ix_course_rules_is_active"), "course_rules", ["is_active"], unique=False)

    op.create_table(
        "credential_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("source_document_id", sa.Integer(), nullable=True),
        sa.Column("credential_name", sa.String(length=200), nullable=False),
        sa.Column("level", sa.String(length=50), nullable=True),
        sa.Column("issuing_organization", sa.String(length=150), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("confirmation_status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["source_document_id"], ["source_documents.id"]),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index(op.f("ix_credential_records_student_id"), "credential_records", ["student_id"], unique=False)
    op.create_index(op.f("ix_credential_records_source_document_id"), "credential_records", ["source_document_id"], unique=False)
    op.create_index(op.f("ix_credential_records_confirmation_status"), "credential_records", ["confirmation_status"], unique=False)

    op.create_table(
        "learning_profile_outputs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("output_type", sa.String(length=50), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("source_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index(op.f("ix_learning_profile_outputs_student_id"), "learning_profile_outputs", ["student_id"], unique=False)
    op.create_index(op.f("ix_learning_profile_outputs_output_type"), "learning_profile_outputs", ["output_type"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_learning_profile_outputs_output_type"), table_name="learning_profile_outputs")
    op.drop_index(op.f("ix_learning_profile_outputs_student_id"), table_name="learning_profile_outputs")
    op.drop_table("learning_profile_outputs")
    op.drop_index(op.f("ix_credential_records_confirmation_status"), table_name="credential_records")
    op.drop_index(op.f("ix_credential_records_source_document_id"), table_name="credential_records")
    op.drop_index(op.f("ix_credential_records_student_id"), table_name="credential_records")
    op.drop_table("credential_records")
    op.drop_index(op.f("ix_course_rules_is_active"), table_name="course_rules")
    op.drop_index(op.f("ix_course_rules_school_year"), table_name="course_rules")
    op.drop_table("course_rules")
    op.drop_index(op.f("ix_learning_course_records_confirmation_status"), table_name="learning_course_records")
    op.drop_index(op.f("ix_learning_course_records_normalized_course_name"), table_name="learning_course_records")
    op.drop_index(op.f("ix_learning_course_records_source_document_id"), table_name="learning_course_records")
    op.drop_index(op.f("ix_learning_course_records_student_id"), table_name="learning_course_records")
    op.drop_table("learning_course_records")
    op.drop_index(op.f("ix_document_extractions_status"), table_name="document_extractions")
    op.drop_table("document_extractions")
    op.drop_index(op.f("ix_source_documents_status"), table_name="source_documents")
    op.drop_index(op.f("ix_source_documents_sha256"), table_name="source_documents")
    op.drop_index(op.f("ix_source_documents_document_type"), table_name="source_documents")
    op.drop_index(op.f("ix_source_documents_owner_id"), table_name="source_documents")
    op.drop_table("source_documents")
