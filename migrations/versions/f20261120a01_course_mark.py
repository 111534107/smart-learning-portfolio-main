"""課程記錄新增成績單「選課別」（必／選）。"""
from alembic import op
import sqlalchemy as sa
revision = 'f20261120a01'
down_revision = 'f20261119a01'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table('learning_course_records'):
        return
    columns = {c['name'] for c in inspector.get_columns('learning_course_records')}
    if 'course_mark' not in columns:
        op.add_column('learning_course_records', sa.Column('course_mark', sa.String(4), nullable=True))


def downgrade():
    op.drop_column('learning_course_records', 'course_mark')
