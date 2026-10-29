"""add match_filter_options (排行篩選選項：科系／地區／學制／資格)

降級會刪掉整張表，管理員維護的選項會一併消失。
"""

from alembic import op
import sqlalchemy as sa


revision = "e5b9d1c3a826"
down_revision = "d8f3b6a2c417"
branch_labels = None
depends_on = None


def upgrade():
    if sa.inspect(op.get_bind()).has_table("match_filter_options"):
        return
    op.create_table(
        "match_filter_options",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("value", sa.String(length=100), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("category", "value", name="uq_match_filter_category_value"),
    )
    with op.batch_alter_table("match_filter_options", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_match_filter_options_category"), ["category"], unique=False)
        batch_op.create_index(batch_op.f("ix_match_filter_options_is_active"), ["is_active"], unique=False)


def downgrade():
    if sa.inspect(op.get_bind()).has_table("match_filter_options"):
        op.drop_table("match_filter_options")
