"""自傳段落註解與回覆。"""
from alembic import op
import sqlalchemy as sa

revision = "c20261117_comments"
down_revision = "b20261116m01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("autobiography_comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("program_id", sa.Integer(), sa.ForeignKey("admission_rule_versions.id"), nullable=False),
        sa.Column("output_id", sa.Integer(), sa.ForeignKey("learning_profile_outputs.id"), nullable=False),
        sa.Column("paragraph", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("autobiography_comments.id")),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime()),
        sa.Column("resolved_by_id", sa.Integer(), sa.ForeignKey("users.id")))
    op.create_index("ix_autobiography_comments_student_id", "autobiography_comments", ["student_id"])


def downgrade():
    op.drop_index("ix_autobiography_comments_student_id", table_name="autobiography_comments")
    op.drop_table("autobiography_comments")
