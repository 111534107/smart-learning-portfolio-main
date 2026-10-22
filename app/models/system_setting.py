from datetime import datetime, timezone

from app.extensions import db


class SystemSetting(db.Model):
    """系統管理員可調整的全站設定（鍵／值），例如 OCR 用 CPU 或顯示卡辨識。"""

    __tablename__ = "system_settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), nullable=False, unique=True)
    value = db.Column(db.String(255), nullable=False)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    updated_by = db.relationship("User")
