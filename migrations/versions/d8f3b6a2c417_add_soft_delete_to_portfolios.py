"""add deleted_at to portfolios and portfolio_evidence (學生刪除先標記，資料列保留；規格 M10)

降級會拿掉 deleted_at：原本標記刪除的經歷與佐證會重新出現在畫面上（資料列一直都在）。
"""

from alembic import op
import sqlalchemy as sa


revision = "d8f3b6a2c417"
down_revision = "c4e2b7a91d05"
branch_labels = None
depends_on = None

TABLES = ("portfolios", "portfolio_evidence")


def _has_column(table, column):
    # 基本資料表由 db.create_all() 建立；從零升級時這兩張表可能還不存在（同 c4a8f1e2d903）
    inspector = sa.inspect(op.get_bind())
    return inspector.has_table(table) and column in {c["name"] for c in inspector.get_columns(table)}


def upgrade():
    for table in TABLES:
        if sa.inspect(op.get_bind()).has_table(table) and not _has_column(table, "deleted_at"):
            with op.batch_alter_table(table) as batch:
                batch.add_column(sa.Column("deleted_at", sa.DateTime(), nullable=True))


def downgrade():
    for table in reversed(TABLES):
        if _has_column(table, "deleted_at"):
            with op.batch_alter_table(table) as batch:
                batch.drop_column("deleted_at")
