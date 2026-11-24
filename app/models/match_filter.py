from datetime import datetime, timezone

from app.extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


MATCH_FILTER_CATEGORIES = ("department", "region", "level", "eligible")


class MatchFilterOption(db.Model):
    """管理員維護的排行篩選選項（科系、地區、學制、資格），學生端排行頁只顯示啟用中的。"""

    __tablename__ = "match_filter_options"
    __table_args__ = (
        db.UniqueConstraint("category", "value", name="uq_match_filter_category_value"),
    )

    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(30), nullable=False, index=True)
    label = db.Column(db.String(100), nullable=False)
    value = db.Column(db.String(100), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    @db.validates("category")
    def validate_category(self, key, value):
        if value not in MATCH_FILTER_CATEGORIES:
            raise ValueError(f"Invalid category: {value}")
        return value

    @classmethod
    def active_options(cls, category):
        return (
            cls.query.filter_by(category=category, is_active=True)
            .order_by(cls.sort_order, cls.id)
            .all()
        )
