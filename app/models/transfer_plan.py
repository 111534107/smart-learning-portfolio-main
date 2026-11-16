"""插大自填目標（B18）：學生自己登錄轉學考的校系、簡章、考科與日期，系統依考期倒數與考科進度算準備度。

各校轉學考每年改、格式不一，不由系統維護全國資料（使用者 2026-11-13 決定學生自填）。
不提供實體刪除：學生不用的目標改成封存（archived），老師修正會寫進 audit_logs。
"""

from datetime import datetime, timezone

from app.extensions import db


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TransferPlan(db.Model):
    __tablename__ = "transfer_plans"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    school_name = db.Column(db.String(100), nullable=False)
    department_name = db.Column(db.String(100), nullable=False)
    entry_grade = db.Column(db.Integer, nullable=True)  # 插入年級：2 或 3
    admission_year = db.Column(db.Integer, nullable=False)  # 簡章的民國學年度
    brochure_url = db.Column(db.String(500), nullable=True)
    apply_start = db.Column(db.Date, nullable=True)
    apply_end = db.Column(db.Date, nullable=True)
    exam_date = db.Column(db.Date, nullable=True)
    note = db.Column(db.Text, nullable=True)
    teacher_note = db.Column(db.Text, nullable=True)
    archived = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    student = db.relationship("User", foreign_keys=[student_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_id])
    subjects = db.relationship(
        "TransferPlanSubject", back_populates="plan", cascade="all, delete-orphan",
        order_by="TransferPlanSubject.sort_order",
    )


class TransferPlanSubject(db.Model):
    __tablename__ = "transfer_plan_subjects"

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("transfer_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(60), nullable=False)
    progress = db.Column(db.Integer, nullable=False, default=0)  # 學生自評 0–100
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    plan = db.relationship("TransferPlan", back_populates="subjects")
