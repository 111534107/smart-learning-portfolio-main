"""preserve summer and winter makeup-course categories"""

from alembic import op
import sqlalchemy as sa


revision = "e4d7a9c1b602"
down_revision = "b7e1a0c4d9f2"  # 原為組員的學生個人資料遷移 c4f2a1b8e7d3（本次未搬）
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "learning_course_records",
        sa.Column("makeup_season", sa.String(length=10), nullable=True),
    )


def downgrade():
    op.drop_column("learning_course_records", "makeup_season")
