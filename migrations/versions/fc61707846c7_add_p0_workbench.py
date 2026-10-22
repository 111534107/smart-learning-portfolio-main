"""add_p0_workbench

Revision ID: fc61707846c7
Revises: a1c8e4d7f902
Create Date: 2026-09-23 18:14:56.275047

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fc61707846c7'
down_revision = 'a1c8e4d7f902'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('public_sources',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('url', sa.String(length=500), nullable=False),
    sa.Column('source_type', sa.String(length=50), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    
    op.create_table('api_key_metadata',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=False),
    sa.Column('mode', sa.String(length=30), nullable=False),
    sa.Column('last_four', sa.String(length=4), nullable=False),
    sa.Column('revoked_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['student_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('api_key_metadata', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_api_key_metadata_student_id'), ['student_id'], unique=False)

    op.create_table('editable_drafts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=False),
    sa.Column('draft_type', sa.String(length=50), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('source_snapshot_json', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['student_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('editable_drafts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_editable_drafts_student_id'), ['student_id'], unique=False)

    op.create_table('public_source_snapshots',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source_id', sa.Integer(), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('fetched_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['source_id'], ['public_sources.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('public_source_snapshots', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_public_source_snapshots_source_id'), ['source_id'], unique=False)

    op.create_table('puzzle_pieces',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=False),
    sa.Column('piece_key', sa.String(length=50), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('guidance', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['student_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('student_id', 'piece_key', name='uq_puzzle_piece_student_key')
    )
    with op.batch_alter_table('puzzle_pieces', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_puzzle_pieces_student_id'), ['student_id'], unique=False)

    op.create_table('consent_records',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=False),
    sa.Column('source_document_id', sa.Integer(), nullable=False),
    sa.Column('purpose', sa.String(length=100), nullable=False),
    sa.Column('mask_version', sa.String(length=50), nullable=False),
    sa.Column('agreed_at', sa.DateTime(), nullable=False),
    sa.Column('revoked_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['source_document_id'], ['source_documents.id'], ),
    sa.ForeignKeyConstraint(['student_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('consent_records', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_consent_records_source_document_id'), ['source_document_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_consent_records_student_id'), ['student_id'], unique=False)

    op.create_table('public_source_changes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('snapshot_id', sa.Integer(), nullable=False),
    sa.Column('change_type', sa.String(length=30), nullable=False),
    sa.Column('diff_json', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.ForeignKeyConstraint(['snapshot_id'], ['public_source_snapshots.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('public_source_changes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_public_source_changes_snapshot_id'), ['snapshot_id'], unique=False)

    op.create_table('public_source_publications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('snapshot_id', sa.Integer(), nullable=False),
    sa.Column('published_by', sa.Integer(), nullable=False),
    sa.Column('published_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['published_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['snapshot_id'], ['public_source_snapshots.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('snapshot_id')
    )

    op.create_table('puzzle_evidence',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('piece_id', sa.Integer(), nullable=False),
    sa.Column('evidence_type', sa.String(length=50), nullable=False),
    sa.Column('evidence_id', sa.Integer(), nullable=False),
    sa.Column('confirmed_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['piece_id'], ['puzzle_pieces.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('puzzle_evidence', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_puzzle_evidence_piece_id'), ['piece_id'], unique=False)


def downgrade():
    with op.batch_alter_table('puzzle_evidence', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_puzzle_evidence_piece_id'))
    op.drop_table('puzzle_evidence')
    
    op.drop_table('public_source_publications')
    
    with op.batch_alter_table('public_source_changes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_public_source_changes_snapshot_id'))
    op.drop_table('public_source_changes')
    
    with op.batch_alter_table('consent_records', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_consent_records_student_id'))
        batch_op.drop_index(batch_op.f('ix_consent_records_source_document_id'))
    op.drop_table('consent_records')
    
    with op.batch_alter_table('puzzle_pieces', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_puzzle_pieces_student_id'))
    op.drop_table('puzzle_pieces')
    
    with op.batch_alter_table('public_source_snapshots', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_public_source_snapshots_source_id'))
    op.drop_table('public_source_snapshots')
    
    with op.batch_alter_table('editable_drafts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_editable_drafts_student_id'))
    op.drop_table('editable_drafts')
    
    with op.batch_alter_table('api_key_metadata', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_api_key_metadata_student_id'))
    op.drop_table('api_key_metadata')
    
    op.drop_table('public_sources')
