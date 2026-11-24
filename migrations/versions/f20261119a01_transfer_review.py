"""獨立轉科核對案件與事件。"""
from alembic import op
import sqlalchemy as sa
revision='f20261119a01'
down_revision='e20261118c01'
branch_labels=None
depends_on=None

def upgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table('users'):
        return
    if not inspector.has_table('transfer_review_cases'):
        op.create_table('transfer_review_cases',
            sa.Column('id',sa.Integer(),primary_key=True), sa.Column('student_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
            sa.Column('status',sa.String(30),nullable=False),sa.Column('version',sa.Integer(),nullable=False,server_default='1'),sa.Column('open_key',sa.Integer(),nullable=True,unique=True),
            sa.Column('class_name',sa.String(50),nullable=False),sa.Column('admission_year',sa.Integer(),nullable=False),
            sa.Column('assistant_id',sa.Integer(),sa.ForeignKey('users.id')),sa.Column('chief_id',sa.Integer(),sa.ForeignKey('users.id')),
            sa.Column('previous_case_id',sa.Integer(),sa.ForeignKey('transfer_review_cases.id')),sa.Column('created_at',sa.DateTime(),nullable=False))
        op.create_index('ix_transfer_review_cases_student_id','transfer_review_cases',['student_id'])
    if not inspector.has_table('transfer_review_events'):
        op.create_table('transfer_review_events',sa.Column('id',sa.Integer(),primary_key=True),
            sa.Column('case_id',sa.Integer(),sa.ForeignKey('transfer_review_cases.id'),nullable=False),
            sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),sa.Column('action',sa.String(30),nullable=False),
            sa.Column('reason',sa.Text(),nullable=False),sa.Column('class_name',sa.String(50),nullable=False),sa.Column('admission_year',sa.Integer(),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False))
        op.create_index('ix_transfer_review_events_case_id','transfer_review_events',['case_id'])

def downgrade():
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table('transfer_review_events'):
        op.drop_table('transfer_review_events')
    if inspector.has_table('transfer_review_cases'):
        op.drop_table('transfer_review_cases')
