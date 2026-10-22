"""學校 AI 金鑰的每日用量：每位學生每天最多幾次（規格 10.1 A、10.3-6）。"""

from app.extensions import db


class AiDailyUsage(db.Model):
    """一位使用者某一天、用某種金鑰呼叫 AI 的次數。

    key_kind：school（學校金鑰）。學生自己的金鑰不計次，所以目前只有 school。
    """

    __tablename__ = "ai_daily_usage"
    __table_args__ = (db.UniqueConstraint("user_id", "usage_date", "key_kind", name="uq_ai_daily_usage"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    usage_date = db.Column(db.Date, nullable=False)
    key_kind = db.Column(db.String(20), nullable=False, default="school")
    count = db.Column(db.Integer, nullable=False, default=0)
