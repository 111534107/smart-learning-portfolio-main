"""主線後半：二技校系備審要求、學生目標校系、導師班級與導師確認。"""

from datetime import datetime, timezone

from app.extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class AdmissionProgram(db.Model):
    """一個志願（校系＋招生類別＋學年度）。

    status：candidate（候選，學生看不到）／published（正式）
    data_origin：manual（管理者手動或種子資料）／agent（招生資料 Agent 擷取）
    """

    __tablename__ = "admission_rule_versions"
    __table_args__ = (db.UniqueConstraint("program_code", "admission_year", name="uq_program_year"),)

    id = db.Column(db.Integer, primary_key=True)
    program_code = db.Column(db.String(20), nullable=False, index=True)
    admission_year = db.Column(db.Integer, nullable=False, index=True)
    school_name = db.Column(db.String(100), nullable=False)
    department_name = db.Column(db.String(100), nullable=False)
    admission_category = db.Column(db.String(50), nullable=True)
    source_url = db.Column(db.String(500), nullable=True)
    source_note = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="candidate", index=True)
    data_origin = db.Column(db.String(20), nullable=False, default="manual")
    checked_at = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    items = db.relationship(
        "AdmissionRequirementItem", back_populates="program", cascade="all, delete-orphan",
        order_by="AdmissionRequirementItem.sort_order",
    )

    @property
    def total_weight(self):
        return sum(item.weight_percent or 0 for item in self.items)


class AdmissionRequirementItem(db.Model):
    """簡章上的一個評分項目，以及它對應到本系統的哪些資料類別。

    mapped_categories：以逗號分隔的類別代碼，例如 "credential,competition,autobiography"
    mapping_status：confirmed（確定）／pending（待確認）
    """

    __tablename__ = "admission_rule_items"

    id = db.Column(db.Integer, primary_key=True)
    rule_version_id = db.Column(db.Integer, db.ForeignKey("admission_rule_versions.id"), nullable=False, index=True)
    source_item_name = db.Column(db.String(100), nullable=False)
    weight_percent = db.Column(db.Integer, nullable=False)
    mapped_categories = db.Column(db.String(200), nullable=False, default="")
    mapping_status = db.Column(db.String(20), nullable=False, default="pending")
    requirement = db.Column(db.Text, nullable=True)
    is_required = db.Column(db.Boolean, nullable=False, default=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    program = db.relationship("AdmissionProgram", back_populates="items")

    @property
    def category_keys(self):
        return [key for key in (self.mapped_categories or "").split(",") if key]


class AdmissionScheduleEvent(db.Model):
    """招生重要日程的一個項目（例如「網路報名」）。

    status：candidate（Agent 擷取的候選）／published（管理員核准，招生時程頁使用）／
            retired（被新核准的版本取代）／rejected（管理員退回）
    同一個招生管道、同一個學年度核准後，會整組取代 app/content/admission_schedule.csv 的日程。
    """

    __tablename__ = "admission_schedule_events"

    id = db.Column(db.Integer, primary_key=True)
    channel = db.Column(db.String(30), nullable=False, index=True)
    admission_year = db.Column(db.Integer, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    start_at = db.Column(db.DateTime, nullable=False)
    end_at = db.Column(db.DateTime, nullable=True)
    note = db.Column(db.String(255), nullable=True)
    source_url = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="candidate", index=True)
    data_origin = db.Column(db.String(20), nullable=False, default="agent")
    change_id = db.Column(db.Integer, db.ForeignKey("public_source_changes.id"), nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)


class StudentTarget(db.Model):
    """學生選擇的目標校系；可以選多個，用來切換比較。"""

    __tablename__ = "student_targets"
    __table_args__ = (db.UniqueConstraint("student_id", "rule_version_id", name="uq_student_target"),)

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    rule_version_id = db.Column(db.Integer, db.ForeignKey("admission_rule_versions.id"), nullable=False)
    selected_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    program = db.relationship("AdmissionProgram")


class ClassAdvisor(db.Model):
    """導師負責的班級。導師只能看到這些班級的學生。"""

    __tablename__ = "class_advisors"
    __table_args__ = (db.UniqueConstraint("teacher_id", "class_name", "school_year", name="uq_class_advisor"),)

    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    class_name = db.Column(db.String(50), nullable=False)
    school_year = db.Column(db.Integer, nullable=False)

    teacher = db.relationship("User")


class PackageReview(db.Model):
    """學生針對某個目標校系，請導師確認備審資料內容。

    status：pending（等待導師）／confirmed（導師已確認）／needs_revision（需要修改）
    確認、請學生修改、撤回確認都會寫進 audit_logs（services/review_snapshot_service.py）。
    """

    __tablename__ = "package_reviews"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    rule_version_id = db.Column(db.Integer, db.ForeignKey("admission_rule_versions.id"), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    comment = db.Column(db.Text, nullable=True)
    readiness_percent = db.Column(db.Integer, nullable=True)
    # 學生送審當下的內容（事實清單、自傳版本、完成度）；導師確認的就是這一份，之後學生再改也不會變
    snapshot_json = db.Column(db.JSON, nullable=True)
    requested_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    reviewed_at = db.Column(db.DateTime, nullable=True)

    student = db.relationship("User", foreign_keys=[student_id])
    teacher = db.relationship("User", foreign_keys=[teacher_id])
    program = db.relationship("AdmissionProgram")
