"""資料庫正規化（第一、第三正規化）

Revision ID: b20261113n01
Revises: b20261112z01
Create Date: 2026-11-13

1NF：一個欄位只放一個值
- admission_rule_items.mapped_categories（逗號分隔）→ 新表 admission_rule_item_categories（一個類別一列）
- portfolios.domain_tags（「、」分隔）→ 新表 portfolio_domain_tags（一個領域一列）
3NF：拿掉可以從別的欄位推得的重複資料
- award_certificates.student_id：由 portfolio_id → portfolios.student_id 決定
- notifications.case_id：由 event_id → graduation_case_events.case_id 決定
另外：student_profiles.user_id 加唯一限制（一位使用者只有一筆學生基本資料）。
既有資料會搬到新表；降版時再組回原本的欄位。
"""
import re

import sqlalchemy as sa
from alembic import op

revision = "b20261113n01"
down_revision = "b20261112z01"
branch_labels = None
depends_on = None


def _split(text, pattern):
    seen = []
    for part in re.split(pattern, text or ""):
        part = part.strip()
        if part and part not in seen:
            seen.append(part)
    return seen


def _has(bind, table, column=None):
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        return False
    return column is None or column in {c["name"] for c in inspector.get_columns(table)}


def _unique_on_user_id(bind):
    """student_profiles.user_id 已有唯一限制就回傳它的名稱（沒有名稱回傳 True），沒有就回傳 None。"""
    inspector = sa.inspect(bind)
    for item in inspector.get_unique_constraints("student_profiles") + [
            i for i in inspector.get_indexes("student_profiles") if i.get("unique")]:
        if item["column_names"] == ["user_id"]:
            return item.get("name") or True
    return None


def upgrade():
    # 舊的遷移鏈沒有建 users、portfolios（由 init_db 建），每一步都先確認表和欄位在不在
    bind = op.get_bind()
    if not _has(bind, "admission_rule_item_categories"):  # 用新模型建的資料庫已經有這張表
        op.create_table(
            "admission_rule_item_categories",
            sa.Column("item_id", sa.Integer(), sa.ForeignKey("admission_rule_items.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("category_key", sa.String(30), primary_key=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        )
    if _has(bind, "portfolios") and not _has(bind, "portfolio_domain_tags"):
        op.create_table(
            "portfolio_domain_tags",
            sa.Column("portfolio_id", sa.Integer(), sa.ForeignKey("portfolios.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("tag", sa.String(50), primary_key=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        )
    rows = [{"item_id": item_id, "category_key": key[:30], "sort_order": order}
            for item_id, text in bind.execute(sa.text("SELECT id, mapped_categories FROM admission_rule_items"))
            for order, key in enumerate(_split(text, r","))] if _has(bind, "admission_rule_items", "mapped_categories") else []
    if rows:
        bind.execute(sa.text("INSERT INTO admission_rule_item_categories (item_id, category_key, sort_order) "
                             "VALUES (:item_id, :category_key, :sort_order)"), rows)
    rows = [{"portfolio_id": pid, "tag": tag[:50], "sort_order": order}
            for pid, text in bind.execute(sa.text("SELECT id, domain_tags FROM portfolios WHERE domain_tags IS NOT NULL"))
            for order, tag in enumerate(_split(text, r"[、,，;；/\s]+"))] if _has(bind, "portfolios", "domain_tags") else []
    if rows:
        bind.execute(sa.text("INSERT INTO portfolio_domain_tags (portfolio_id, tag, sort_order) "
                             "VALUES (:portfolio_id, :tag, :sort_order)"), rows)

    if _has(bind, "admission_rule_items", "mapped_categories"):
        with op.batch_alter_table("admission_rule_items") as batch:
            batch.drop_column("mapped_categories")
    if _has(bind, "portfolios", "domain_tags"):
        with op.batch_alter_table("portfolios") as batch:
            batch.drop_column("domain_tags")
    if _has(bind, "award_certificates", "student_id") and _has(bind, "users"):  # 重建表要反射到 users 的外鍵
        with op.batch_alter_table("award_certificates") as batch:
            batch.drop_index("ix_award_certificates_student_id")
            batch.drop_column("student_id")
    if _has(bind, "notifications", "case_id") and _has(bind, "users"):  # 重建表要反射到 users 的外鍵
        with op.batch_alter_table("notifications") as batch:
            batch.drop_index("ix_notifications_case_id")
            batch.drop_column("case_id")
    if _has(bind, "student_profiles") and not _unique_on_user_id(bind):
        with op.batch_alter_table("student_profiles") as batch:
            batch.create_unique_constraint("uq_student_profiles_user_id", ["user_id"])


def downgrade():
    bind = op.get_bind()
    if _has(bind, "student_profiles") and _unique_on_user_id(bind) == "uq_student_profiles_user_id":
        with op.batch_alter_table("student_profiles") as batch:
            batch.drop_constraint("uq_student_profiles_user_id", type_="unique")
    # 升級時沒有 users 表就沒動這兩張表（見 upgrade），降版也一樣跳過
    if _has(bind, "notifications") and not _has(bind, "notifications", "case_id") and _has(bind, "users"):
        with op.batch_alter_table("notifications") as batch:
            batch.add_column(sa.Column("case_id", sa.Integer(), nullable=True))
            batch.create_foreign_key("fk_notifications_case_id", "graduation_cases", ["case_id"], ["id"])
            batch.create_index("ix_notifications_case_id", ["case_id"])
        bind.execute(sa.text("UPDATE notifications SET case_id = (SELECT case_id FROM graduation_case_events e "
                             "WHERE e.id = notifications.event_id) WHERE event_id IS NOT NULL"))
    if (_has(bind, "award_certificates") and not _has(bind, "award_certificates", "student_id")
            and _has(bind, "users") and _has(bind, "portfolios")):
        with op.batch_alter_table("award_certificates") as batch:
            batch.add_column(sa.Column("student_id", sa.Integer(), nullable=True))
        bind.execute(sa.text("UPDATE award_certificates SET student_id = (SELECT student_id FROM portfolios p "
                             "WHERE p.id = award_certificates.portfolio_id)"))
        with op.batch_alter_table("award_certificates") as batch:
            batch.alter_column("student_id", existing_type=sa.Integer(), nullable=False)
            batch.create_index("ix_award_certificates_student_id", ["student_id"])
            batch.create_foreign_key("fk_award_certificates_student_id", "users", ["student_id"], ["id"])
    has_tags = _has(bind, "portfolio_domain_tags")
    if _has(bind, "portfolios"):
        with op.batch_alter_table("portfolios") as batch:
            batch.add_column(sa.Column("domain_tags", sa.String(200), nullable=True))
    for pid, in (bind.execute(sa.text("SELECT DISTINCT portfolio_id FROM portfolio_domain_tags")).fetchall() if has_tags else []):
        tags = [t for t, in bind.execute(sa.text("SELECT tag FROM portfolio_domain_tags WHERE portfolio_id = :p "
                                                   "ORDER BY sort_order"), {"p": pid})]
        bind.execute(sa.text("UPDATE portfolios SET domain_tags = :t WHERE id = :p"), {"t": "、".join(tags)[:200], "p": pid})
    with op.batch_alter_table("admission_rule_items") as batch:
        batch.add_column(sa.Column("mapped_categories", sa.String(200), nullable=False, server_default=""))
    for item_id, in bind.execute(sa.text("SELECT DISTINCT item_id FROM admission_rule_item_categories")).fetchall():
        keys = [k for k, in bind.execute(sa.text("SELECT category_key FROM admission_rule_item_categories "
                                                   "WHERE item_id = :i ORDER BY sort_order"), {"i": item_id})]
        bind.execute(sa.text("UPDATE admission_rule_items SET mapped_categories = :k WHERE id = :i"),
                     {"k": ",".join(keys)[:200], "i": item_id})
    if has_tags:
        op.drop_table("portfolio_domain_tags")
    op.drop_table("admission_rule_item_categories")
