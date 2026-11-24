"""合併兩條遷移分叉：二技公告（b20261110a01）與自傳段落註解（c20261118a01）。

兩邊各自接在不同的上一版，沒有互相依賴，也沒有改同一張表；這個遷移本身不做任何資料表變更，
只讓遷移歷史回到單一終點，`flask db upgrade` 才不會因為「多個終點」失敗。

Revision ID: d20261118m01
Revises: b20261110a01, c20261118a01
"""

revision = "d20261118m01"
down_revision = ("b20261110a01", "c20261118a01")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
