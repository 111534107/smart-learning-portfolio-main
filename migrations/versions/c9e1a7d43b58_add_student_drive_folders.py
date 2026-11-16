"""add student_drive_folders (學生雲端硬碟的「備審資料」與各校資料夾編號)

降級會刪掉資料夾編號表；Drive 上的資料夾不會被刪，只是系統忘記編號。
"""

from alembic import op
import sqlalchemy as sa


revision = "c9e1a7d43b58"
down_revision = "e5b9d1c3a826"
branch_labels = None
depends_on = None


def upgrade():
    if sa.inspect(op.get_bind()).has_table("student_drive_folders"):
        return
    op.create_table(
        "student_drive_folders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("folder_key", sa.String(length=40), nullable=False),
        sa.Column("google_folder_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("student_id", "folder_key", name="uq_student_drive_folder"),
    )
    op.create_index("ix_student_drive_folders_student_id", "student_drive_folders", ["student_id"])


def downgrade():
    op.drop_index("ix_student_drive_folders_student_id", table_name="student_drive_folders")
    op.drop_table("student_drive_folders")
