"""成績紀錄的學期統一成「上／下」（B25）

2026-11-14 假學生實測：辨識送來的「第一學期／第二學期」原字存進 learning_course_records.semester，
畢業門檻、各學期預警與重複上傳去重只認「上／下」。這裡把舊資料改掉；寒修、暑修等其他字不動。
只改資料、不改欄位，所以 downgrade 不還原（無法分辨哪些原本就是「上／下」）。

Revision ID: b20261114s01
Revises: b20261114p01
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa


revision = "b20261114s01"
down_revision = "b20261114p01"
branch_labels = None
depends_on = None

TABLE = "learning_course_records"
REWRITE = {
    "上": ("一", "1", "上學期", "第一學期", "第1學期"),
    "下": ("二", "2", "下學期", "第二學期", "第2學期"),
}


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(TABLE) or "semester" not in {c["name"] for c in inspector.get_columns(TABLE)}:
        return
    for target, sources in REWRITE.items():
        for source in sources:
            op.execute(sa.text(f"UPDATE {TABLE} SET semester = :target WHERE semester = :source")
                       .bindparams(target=target, source=source))


def downgrade():
    pass  # 只改資料；舊字串無法還原，也不需要還原
