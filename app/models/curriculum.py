"""修業科目表版本（2026-11-09）：代理從資管科網頁抓 PDF、程式解析，管理員確認後才生效。

status：
- candidate：解析與檢查都通過，等管理員確認（學生、畢業門檻還不會用）。
- check_failed：解析出來的數字對不上，不能確認；留著讓管理員看原因。
- published：管理員確認，畢業門檻改用這一版。同一入學年度只會有一版 published。
- superseded：被同年度較新的確認版本取代。
- rejected：管理員不採用。
"""
from datetime import datetime, timezone

from app.extensions import db


def _now():
    return datetime.now(timezone.utc)


class CurriculumVersion(db.Model):
    __tablename__ = "curriculum_versions"

    id = db.Column(db.Integer, primary_key=True)
    admission_year = db.Column(db.Integer, nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="candidate", index=True)
    source_url = db.Column(db.String(500), nullable=False)
    file_sha256 = db.Column(db.String(64), nullable=False, index=True)
    total_credits = db.Column(db.Integer, nullable=True)
    required_credits = db.Column(db.Integer, nullable=True)
    elective_credits = db.Column(db.Integer, nullable=True)
    checks_json = db.Column(db.JSON, nullable=True)
    diff_json = db.Column(db.JSON, nullable=True)
    notes_json = db.Column(db.JSON, nullable=True)
    summary = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)

    courses = db.relationship("CurriculumCourse", back_populates="version", cascade="all, delete-orphan",
                              order_by="CurriculumCourse.sort_order")
    reviewed_by = db.relationship("User")

    @property
    def checks_ok(self):
        return bool(self.checks_json) and all(check.get("ok") for check in self.checks_json)


class CurriculumCourse(db.Model):
    __tablename__ = "curriculum_courses"

    id = db.Column(db.Integer, primary_key=True)
    version_id = db.Column(db.Integer, db.ForeignKey("curriculum_versions.id"), nullable=False, index=True)
    category = db.Column(db.String(20), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    english_name = db.Column(db.String(200), nullable=True)
    credits = db.Column(db.Integer, nullable=False, default=0)
    hours = db.Column(db.Integer, nullable=False, default=0)
    note = db.Column(db.String(100), nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    version = db.relationship("CurriculumVersion", back_populates="courses")
