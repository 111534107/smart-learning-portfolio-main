from datetime import datetime, timezone

from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class TransferCreditRecord(db.Model):
    """轉學生自行維護的抵免進度；不代表學校正式審核結果。"""

    __tablename__ = "transfer_credit_records"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True, index=True)
    status = db.Column(db.String(30), nullable=False, default="not_started")
    submitted_on = db.Column(db.Date, nullable=True)
    missing_documents = db.Column(db.String(1000), nullable=False, default="")
    note = db.Column(db.String(2000), nullable=False, default="")
    teacher_confirmed = db.Column(db.Boolean, nullable=False, default=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    teacher_confirmed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    student = db.relationship("User", foreign_keys=[student_id])
    teacher = db.relationship("User", foreign_keys=[teacher_id])
