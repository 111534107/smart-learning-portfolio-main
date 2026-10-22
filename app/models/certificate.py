from datetime import datetime, timezone

from app.extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class AwardCertificate(db.Model):
    """科辦替科上派的服務開的電子獎狀。一筆服務紀錄最多一張；退回後學生可以再申請。

    狀態：pending（待科辦核准）→ approved（已核准，有驗證碼）或 returned（退回，附原因）。
    """

    __tablename__ = "award_certificates"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey("portfolios.id"), nullable=False, unique=True)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    title = db.Column(db.String(50), nullable=False)
    body = db.Column(db.Text, nullable=False)
    issuer = db.Column(db.String(100), nullable=False)
    issued_on = db.Column(db.Date, nullable=True)
    verify_code = db.Column(db.String(12), nullable=True, unique=True)
    return_reason = db.Column(db.String(500), nullable=True)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    student = db.relationship("User", foreign_keys=[student_id])
    reviewed_by = db.relationship("User", foreign_keys=[reviewed_by_id])
    portfolio = db.relationship("Portfolio", back_populates="certificate")
