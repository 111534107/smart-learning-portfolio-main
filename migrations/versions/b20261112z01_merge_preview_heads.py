"""合併預覽分支的三個最新版本（郵件通知、表單連結、不放進備審）

Revision ID: b20261112z01
Revises: b20261112m01, b20261112f01, b20261112x01
Create Date: 2026-11-12

只合併版本線，不改資料表。
"""

revision = "b20261112z01"
down_revision = ("b20261112m01", "b20261112f01", "b20261112x01")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
