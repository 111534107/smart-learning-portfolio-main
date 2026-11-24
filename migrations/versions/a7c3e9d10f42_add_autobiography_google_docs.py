"""add autobiography google docs (student's own My Drive copy of the draft)"""

from alembic import op
import sqlalchemy as sa


revision = "a7c3e9d10f42"
down_revision = "f3a8c2d61b07"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "autobiography_google_docs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("program_id", sa.Integer(), sa.ForeignKey("admission_rule_versions.id"), nullable=False),
        sa.Column("google_file_id", sa.String(length=128), nullable=False),
        sa.Column("web_view_link", sa.String(length=500), nullable=False),
        sa.Column("based_on_output_id", sa.Integer(), sa.ForeignKey("learning_profile_outputs.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_pulled_at", sa.DateTime(), nullable=True),
        sa.Column("last_pulled_output_id", sa.Integer(), sa.ForeignKey("learning_profile_outputs.id"), nullable=True),
        sa.UniqueConstraint("student_id", "program_id", name="uq_autobiography_google_doc"),
    )
    op.create_index("ix_autobiography_google_docs_student_id", "autobiography_google_docs", ["student_id"])


def downgrade():
    op.drop_index("ix_autobiography_google_docs_student_id", table_name="autobiography_google_docs")
    op.drop_table("autobiography_google_docs")
