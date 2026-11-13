"""表單代理與上架核准：form_items 加 origin、approved_by_id、approved_at

Revision ID: b20261113f01
Revises: b20261113n01
Create Date: 2026-11-13

表單改由代理從學校網站抓（origin=agent），上架要主任或副主任核准。
既有的表單都視為已審過（approved_at 填建立時間），不會突然變成待核准。
"""
import sqlalchemy as sa
from alembic import op

revision = "b20261113f01"
down_revision = "b20261113n01"
branch_labels = None
depends_on = None


def _columns(bind):
    inspector = sa.inspect(bind)
    return {c["name"] for c in inspector.get_columns("form_items")} if inspector.has_table("form_items") else None


def upgrade():
    bind = op.get_bind()
    columns = _columns(bind)
    if columns is None:
        return
    # 不用 batch：重建表要反射到 users 外鍵，從零升級時 users 可能不存在
    if "origin" not in columns:
        op.add_column("form_items", sa.Column("origin", sa.String(20), nullable=False, server_default="manual"))
    if "approved_by_id" not in columns:
        op.add_column("form_items", sa.Column("approved_by_id", sa.Integer(), nullable=True))
        # MySQL 另外加外來鍵；SQLite 不能事後加限制，只留欄位
        if bind.dialect.name != "sqlite" and sa.inspect(bind).has_table("users"):
            op.create_foreign_key("fk_form_items_approved_by", "form_items", "users", ["approved_by_id"], ["id"])
    if "approved_at" not in columns:
        op.add_column("form_items", sa.Column("approved_at", sa.DateTime(), nullable=True))
        bind.execute(sa.text("UPDATE form_items SET approved_at = created_at"))


def downgrade():
    bind = op.get_bind()
    columns = _columns(bind)
    if columns is None:
        return
    with op.batch_alter_table("form_items") as batch:
        for name in ("approved_at", "approved_by_id", "origin"):
            if name in columns:
                batch.drop_column(name)
