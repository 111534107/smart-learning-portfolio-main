"""學校 AI 金鑰每人每天的次數（規格 10.1 A、10.3-6）。

- 只有學生用學校金鑰、而且真的會呼叫 AI 時才計次；用自己的金鑰、示範模式不計次。
- 導師、管理者用學校金鑰不限次數。
- consume() 用「count < 上限」的條件更新加一，同時按兩次也不會超過上限。
  它只 flush 不 commit：呼叫 AI 成功後和產出的內容一起 commit；AI 失敗時由呼叫端 rollback，次數就退回。
  次數用完時只丟 QuotaExceeded，不 rollback（條件更新沒有改到任何一列），呼叫端其他還沒存的變更不受影響。
"""

from datetime import date

from flask import current_app
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import AiDailyUsage

SCHOOL = "school"


class QuotaExceeded(RuntimeError):
    """今天學校金鑰的次數用完了。訊息是給學生看的中文。"""


def _limit():
    return current_app.config.get("SCHOOL_AI_DAILY_LIMIT", 5)


def _used(user, today):
    row = AiDailyUsage.query.filter_by(user_id=user.id, usage_date=today, key_kind=SCHOOL).first()
    return row.count if row else 0


def remaining(user, today=None):
    """今天還能用幾次；不限次數的角色回傳 None。"""
    if user.role != "student":
        return None
    return max(_limit() - _used(user, today or date.today()), 0)


def exceeded_message():
    return (f"今天學校 AI 的 {_limit()} 次已經用完了，明天會恢復。"
            "想繼續用，可以在下方貼上自己的 Gemini 金鑰（只用這一次，不會儲存）。")


def consume(user, today=None):
    """學生用學校金鑰前先扣一次；用完時丟 QuotaExceeded。"""
    if user.role != "student":
        return
    today = today or date.today()
    if not AiDailyUsage.query.filter_by(user_id=user.id, usage_date=today, key_kind=SCHOOL).first():
        try:
            with db.session.begin_nested():
                db.session.add(AiDailyUsage(user_id=user.id, usage_date=today, key_kind=SCHOOL, count=0))
        except IntegrityError:
            pass  # 同時有另一個請求先建立了，直接用那一筆
    result = db.session.execute(
        update(AiDailyUsage)
        .where(AiDailyUsage.user_id == user.id, AiDailyUsage.usage_date == today,
               AiDailyUsage.key_kind == SCHOOL, AiDailyUsage.count < _limit())
        .values(count=AiDailyUsage.count + 1)
    )
    if result.rowcount == 0:
        raise QuotaExceeded(exceeded_message())
    db.session.flush()


def refund(user, today=None):
    """AI 沒有產生結果時退回剛扣的一次（不在同一個交易裡、沒辦法 rollback 時用）。"""
    if user.role != "student":
        return
    db.session.execute(
        update(AiDailyUsage)
        .where(AiDailyUsage.user_id == user.id, AiDailyUsage.usage_date == (today or date.today()),
               AiDailyUsage.key_kind == SCHOOL, AiDailyUsage.count > 0)
        .values(count=AiDailyUsage.count - 1)
    )
    db.session.flush()
