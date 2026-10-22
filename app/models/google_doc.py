from datetime import datetime, timezone

from app.extensions import db


class AutobiographyGoogleDoc(db.Model):
    """學生把某個校系的自傳放到自己 My Drive 的那一份 Google 文件。

    只記文件 ID、連結和對應的自傳版本；Google 權杖不存在這裡（只放伺服器記憶體，見 google_docs_service）。
    同一位學生、同一個校系只有一份，之後再按「在 Google 文件中編輯」就開同一份。
    """

    __tablename__ = "autobiography_google_docs"
    __table_args__ = (db.UniqueConstraint("student_id", "program_id", name="uq_autobiography_google_doc"),)

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    program_id = db.Column(db.Integer, db.ForeignKey("admission_rule_versions.id"), nullable=False)
    google_file_id = db.Column(db.String(128), nullable=False)
    web_view_link = db.Column(db.String(500), nullable=False)
    based_on_output_id = db.Column(db.Integer, db.ForeignKey("learning_profile_outputs.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    last_pulled_at = db.Column(db.DateTime, nullable=True)
    last_pulled_output_id = db.Column(db.Integer, db.ForeignKey("learning_profile_outputs.id"), nullable=True)
