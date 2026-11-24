"""add grade level to confirmed learning courses"""

from alembic import op
import sqlalchemy as sa


revision = "b7e1a0c4d9f2"
down_revision = "a920261013tc"  # 原為 fc61707846c7；接到本分支目前最新遷移之後
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "learning_course_records",
        sa.Column("grade_level", sa.String(length=20), nullable=True),
    )


def downgrade():
    op.drop_column("learning_course_records", "grade_level")
