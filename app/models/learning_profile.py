from datetime import datetime, timezone

from app.extensions import db
from app.services import file_preview


def _utcnow():
    return datetime.now(timezone.utc)


_GRADE_NUMBERS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5}


def grade_number(grade_level):
    """把組員確認頁的年級文字（「三年級」或「3年級」）換成 1～5；看不懂就回傳 None。"""
    text = (grade_level or "").strip()
    if text.endswith("年級") and len(text) == 3:
        return _GRADE_NUMBERS.get(text[0])
    return None


class SourceDocument(db.Model):
    """A private source file supplied by a student for learning-profile analysis."""

    __tablename__ = "source_documents"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    document_type = db.Column(db.String(30), nullable=False, index=True)
    display_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    sha256 = db.Column(db.String(64), nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False, default="uploaded", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    owner = db.relationship("User", back_populates="source_documents")
    extraction = db.relationship(
        "DocumentExtraction", back_populates="source_document", uselist=False,
        cascade="all, delete-orphan",
    )

    @property
    def extension(self):
        return file_preview.extension(self.display_name)

    @property
    def preview_kind(self):
        """"image"、"pdf" 或 None（不能預覽）。"""
        return file_preview.preview_kind(self.display_name)


class DocumentExtraction(db.Model):
    """Provider output kept separately from a student's confirmed records."""

    __tablename__ = "document_extractions"

    id = db.Column(db.Integer, primary_key=True)
    source_document_id = db.Column(
        db.Integer, db.ForeignKey("source_documents.id"), nullable=False, unique=True
    )
    provider = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="pending", index=True)
    result_json = db.Column(db.JSON, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    confirmed_at = db.Column(db.DateTime, nullable=True)
    confirmed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    source_document = db.relationship("SourceDocument", back_populates="extraction")
    confirmed_by = db.relationship("User", foreign_keys=[confirmed_by_id])


class LearningCourseRecord(db.Model):
    """A course record that the student has reviewed and confirmed."""

    __tablename__ = "learning_course_records"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    source_document_id = db.Column(db.Integer, db.ForeignKey("source_documents.id"), nullable=True, index=True)
    school_year = db.Column(db.Integer, nullable=True)
    semester = db.Column(db.String(20), nullable=True)
    grade_level = db.Column(db.String(20), nullable=True)
    course_name = db.Column(db.String(150), nullable=False)
    normalized_course_name = db.Column(db.String(150), nullable=False, index=True)
    credits = db.Column(db.Integer, nullable=True)
    score = db.Column(db.Integer, nullable=True)
    status_mark = db.Column(db.String(10), nullable=True)
    makeup_season = db.Column(db.String(10), nullable=True)
    confirmation_status = db.Column(db.String(30), nullable=False, default="confirmed", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    student = db.relationship("User", foreign_keys=[student_id])
    source_document = db.relationship("SourceDocument")

    @property
    def is_score(self):
        return self.score is not None

    @property
    def year_for_placement(self):
        """放進「我的五年」用的年級或民國學年度：先用 school_year，沒有就用組員確認頁的 grade_level。"""
        return self.school_year if self.school_year is not None else grade_number(self.grade_level)

    @property
    def acquisition_status(self):
        if self.status_mark in {"抵", "免"}:
            return "pending_rule_confirmation"
        if self.status_mark == "補":
            return "makeup_record"
        if self.score is None:
            return "unclassified"
        return "passed" if self.score >= 60 else "not_passed"


class CourseRule(db.Model):
    """A school-year-scoped curriculum rule maintained by an administrator."""

    __tablename__ = "course_rules"
    __table_args__ = (
        db.UniqueConstraint("school_year", "normalized_course_name", name="uq_course_rule_year_name"),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_year = db.Column(db.Integer, nullable=False, index=True)
    course_name = db.Column(db.String(150), nullable=False)
    normalized_course_name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    requirement_type = db.Column(db.String(30), nullable=False)
    credits = db.Column(db.Integer, nullable=True)
    ability_domain = db.Column(db.String(100), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


class CredentialRecord(db.Model):
    """A student-confirmed certificate or credential extracted from a source document."""

    __tablename__ = "credential_records"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    source_document_id = db.Column(db.Integer, db.ForeignKey("source_documents.id"), nullable=True, index=True)
    credential_name = db.Column(db.String(200), nullable=False)
    level = db.Column(db.String(50), nullable=True)
    issuing_organization = db.Column(db.String(150), nullable=True)
    issue_date = db.Column(db.Date, nullable=True)
    category = db.Column(db.String(100), nullable=True)
    confirmation_status = db.Column(db.String(30), nullable=False, default="confirmed", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    student = db.relationship("User", foreign_keys=[student_id])
    source_document = db.relationship("SourceDocument")


class LearningProfileOutput(db.Model):
    """A generated, versioned output with the rule and record IDs used to produce it."""

    __tablename__ = "learning_profile_outputs"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    output_type = db.Column(db.String(50), nullable=False, index=True)
    content_json = db.Column(db.JSON, nullable=False)
    source_snapshot_json = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    student = db.relationship("User", foreign_keys=[student_id])
