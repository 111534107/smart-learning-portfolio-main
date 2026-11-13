from datetime import datetime, timezone

from sqlalchemy.ext.hybrid import hybrid_property

from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class GraduationCase(db.Model):
    """畢業缺口案件；只做提醒與追蹤，不代表學校正式審核結果。"""

    __tablename__ = "graduation_cases"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    # gap / data_needed / inquiry
    case_type = db.Column(db.String(20), nullable=False)
    # gap：檢核項目；data_needed：certificates / credits；inquiry：general
    item = db.Column(db.String(40), nullable=False)
    # pending / in_progress / awaiting_verification / closed
    status = db.Column(db.String(30), nullable=False, default="pending")
    # improved / no_gap / None
    close_reason = db.Column(db.String(20), nullable=True)
    initial_amount = db.Column(db.Integer, nullable=True)
    current_amount = db.Column(db.Integer, nullable=True)
    unit = db.Column(db.String(20), nullable=True)
    basis = db.Column(db.String(255), nullable=False, default="")
    detail = db.Column(db.Text, nullable=False, default="")
    # 開啟中的案件用 student:item:type 防重複；結案後設為 NULL（唯一欄位允許多個 NULL）
    open_key = db.Column(db.String(80), nullable=True, unique=True)
    previous_case_id = db.Column(db.Integer, db.ForeignKey("graduation_cases.id"), nullable=True)
    # 最近一次同步看到的判斷結果：缺口案件存 gap / met / progress；資料補充案件存 insufficient / sufficient。
    # 同步只在結果「轉變」時動作，避免蓋掉人工送出、退回或結案。
    last_result = db.Column(db.String(30), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    closed_at = db.Column(db.DateTime, nullable=True)
    closed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    student = db.relationship("User", foreign_keys=[student_id])
    closed_by = db.relationship("User", foreign_keys=[closed_by_id])
    previous_case = db.relationship("GraduationCase", remote_side=[id], foreign_keys=[previous_case_id])

    @property
    def number(self):
        """案件編號，例如 G-000123。"""
        return f"G-{self.id:06d}"

    @property
    def is_open(self):
        return self.status != "closed"

    @property
    def improved_pending(self):
        """11-09 以前留下來、停在待核對的舊案件，而且最近一次同步看到的資料已改善（下次同步會自動結案）。"""
        return (self.status == "awaiting_verification" and self.case_type != "inquiry"
                and self.last_result not in ("gap", "insufficient"))

    @classmethod
    def open_key_for(cls, student_id, item, case_type):
        return f"{student_id}:{item}:{case_type}"


class GraduationCaseEvent(db.Model):
    """案件事件紀錄；actor_id 為空代表系統。"""

    __tablename__ = "graduation_case_events"

    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey("graduation_cases.id"), nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    # created / student_note / teacher_note / started / submitted / recalculated /
    # auto_closed / teacher_closed / data_changed（11-09 起）；舊資料另有 auto_verify / verified / rejected / closed_no_gap
    event_type = db.Column(db.String(30), nullable=False)
    from_status = db.Column(db.String(30), nullable=True)
    to_status = db.Column(db.String(30), nullable=True)
    amount_before = db.Column(db.Integer, nullable=True)
    amount_after = db.Column(db.Integer, nullable=True)
    note = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    case = db.relationship("GraduationCase", backref=db.backref("events", lazy="dynamic"))
    actor = db.relationship("User", foreign_keys=[actor_id])


class Notification(db.Model):
    """站內通知；同一接收者對同一事件只會有一筆。

    畢業缺口案件的通知有 case_id 與 event_id；其他通知（例如電子獎狀核准或退回）兩者為空，
    改用 link 存要開啟的站內網址。
    """

    __tablename__ = "notifications"
    __table_args__ = (db.UniqueConstraint("recipient_id", "event_id", name="uq_notification_recipient_event"),
                      db.UniqueConstraint("recipient_id", "notify_key", name="uq_notification_recipient_key"))

    id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    event_id = db.Column(db.Integer, db.ForeignKey("graduation_case_events.id"), nullable=True)
    message = db.Column(db.String(255), nullable=False, default="")
    # 各學期預警、檢核日期倒數這類沒有案件事件的提醒，用這個鍵去重（同一人同一鍵只通知一次）
    notify_key = db.Column(db.String(120), nullable=True)
    link = db.Column(db.String(255), nullable=True)  # 站內路徑，例如 /certificates/3；只接受 / 開頭
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    read_at = db.Column(db.DateTime, nullable=True)

    recipient = db.relationship("User", foreign_keys=[recipient_id])
    event = db.relationship("GraduationCaseEvent")

    # 第三正規化（2026-11-13）：案件由事件決定（通知 → 事件 → 案件），不另存 case_id。
    # 用 hybrid_property：物件上讀得到，查詢時 filter_by(case_id=…) 也會轉成子查詢
    @hybrid_property
    def case_id(self):
        return self.event.case_id if self.event else None

    @case_id.expression
    def case_id(cls):
        return (db.select(GraduationCaseEvent.case_id).where(GraduationCaseEvent.id == cls.event_id)
                .scalar_subquery())

    @property
    def case(self):
        return self.event.case if self.event else None
