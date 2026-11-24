"""自傳建議修改（導師建議、學生接受或不接受）。"""
from alembic import op
import sqlalchemy as sa

revision = 'f20261120b01'
down_revision = 'f20261120a01'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table('learning_profile_outputs') or inspector.has_table('autobiography_suggestions'):
        return
    op.create_table(
        'autobiography_suggestions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('student_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('program_id', sa.Integer(), sa.ForeignKey('admission_rule_versions.id'), nullable=False),
        sa.Column('output_id', sa.Integer(), sa.ForeignKey('learning_profile_outputs.id'), nullable=False),
        sa.Column('paragraph', sa.Integer(), nullable=False),
        sa.Column('start', sa.Integer(), nullable=False),
        sa.Column('end', sa.Integer(), nullable=False),
        sa.Column('original', sa.Text(), nullable=False),
        sa.Column('replacement', sa.Text(), nullable=False),
        sa.Column('author_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('status', sa.String(12), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('resolved_at', sa.DateTime()),
        sa.Column('resolved_by_id', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('result_output_id', sa.Integer(), sa.ForeignKey('learning_profile_outputs.id')),
    )
    op.create_index('ix_autobiography_suggestions_student_id', 'autobiography_suggestions', ['student_id'])
    op.create_index('ix_autobiography_suggestions_status', 'autobiography_suggestions', ['status'])


def downgrade():
    op.drop_table('autobiography_suggestions')
