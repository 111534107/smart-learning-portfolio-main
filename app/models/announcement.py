"""公告（UC-25）。資料表做成通用的；2026-11 第一版畫面只做二技公告（kind="admission"）。

status：draft（草稿，只有管理員看得到）／published（已發布）／withdrawn（已下架）。
公告不能刪除，只能下架，並記下是誰、何時（10-10 使用者決定）。
"""
from datetime import datetime, timezone

from app.extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class Announcement(db.Model):
    __tablename__ = "announcements"

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(20), nullable=False, default="admission", index=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False, default="")
    audience = db.Column(db.String(60), nullable=False, default="student,teacher,staff")
    channel = db.Column(db.String(30), nullable=True)
    admission_year = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    published_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    published_at = db.Column(db.DateTime, nullable=True)
    withdrawn_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    withdrawn_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    @property
    def audience_roles(self):
        return {role.strip() for role in (self.audience or "").split(",") if role.strip()}


class AnnouncementRead(db.Model):
    __tablename__ = "announcement_reads"
    __table_args__ = (db.UniqueConstraint("announcement_id", "user_id", name="uq_announcement_read"),)

    id = db.Column(db.Integer, primary_key=True)
    announcement_id = db.Column(db.Integer, db.ForeignKey("announcements.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    read_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
