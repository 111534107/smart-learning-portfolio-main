from datetime import datetime, timezone

from sqlalchemy.ext.hybrid import hybrid_property

from app.extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class AwardCertificate(db.Model):
    """科辦開的電子獎狀（服務證明、TA 證明；科學會證明 11-09 起改由學務處辦）。一筆紀錄最多一張；退回後學生可以再申請。

    狀態：pending（待科辦核准）→ approved（已核准，有驗證碼）或 returned（退回，附原因）。
    """

    __tablename__ = "award_certificates"

    id = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey("portfolios.id"), nullable=False, unique=True)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    # service 服務證明／ta TA 證明／club 科學會證明（11-09 起不能新申請），見 certificate_service.KINDS
    kind = db.Column(db.String(20), nullable=False, default="service", server_default="service")
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

    reviewed_by = db.relationship("User", foreign_keys=[reviewed_by_id])
    portfolio = db.relationship("Portfolio", back_populates="certificate")

    # 第三正規化（2026-11-13）：學生由「哪一筆紀錄」決定（獎狀 → 紀錄 → 學生），不另存一份，避免兩邊不一致
    # hybrid_property：物件上讀得到，查詢時 filter_by(student_id=…) 也會轉成子查詢
    @hybrid_property
    def student_id(self):
        return self.portfolio.student_id if self.portfolio else None

    @student_id.expression
    def student_id(cls):
        from app.models.portfolio import Portfolio
        return db.select(Portfolio.student_id).where(Portfolio.id == cls.portfolio_id).scalar_subquery()

    @property
    def student(self):
        return self.portfolio.student if self.portfolio else None
