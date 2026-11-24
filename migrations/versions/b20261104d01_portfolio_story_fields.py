"""portfolios 加寫自傳用的四個細節：role、achievement、learned、domain_tags（設計書 D-1）。

portfolios 由初始建表產生；只用遷移建的測試資料庫可能沒有這張表，就跳過（同 d8f3b6a2c417）。
"""
from alembic import op
import sqlalchemy as sa


revision = "b20261104d01"
down_revision = "b20261102e01"
branch_labels = None
depends_on = None

COLUMNS = (
    ("role", sa.Text()),
    ("achievement", sa.String(length=300)),
    ("learned", sa.Text()),
    ("domain_tags", sa.String(length=200)),
)


def _existing():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("portfolios"):
        return None
    return {column["name"] for column in inspector.get_columns("portfolios")}


def upgrade():
    existing = _existing()
    if existing is None:
        return
    with op.batch_alter_table("portfolios") as batch:
        for name, column_type in COLUMNS:
            if name not in existing:
                batch.add_column(sa.Column(name, column_type, nullable=True))


def downgrade():
    existing = _existing()
    if existing is None:
        return
    with op.batch_alter_table("portfolios") as batch:
        for name, _ in COLUMNS:
            if name in existing:
                batch.drop_column(name)
