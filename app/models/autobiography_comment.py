"""自傳段落註解（組員 111534107 的 46531f2 改寫併入，2026-11-18）。

- 一段可以有多則導師註解；學生和導師都可以回覆（parent_id 指向那則註解）。
- 註解記住寫在哪一版（output_id），學生之後改出新版，舊註解仍保留、照樣顯示。
- 只能標記「已處理」或改回「待處理」，不提供刪除（規格：修改紀錄完整保留）。
"""

from datetime import datetime, timezone

from app.extensions import db


class AutobiographyComment(db.Model):
    __tablename__ = "autobiography_comments"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    program_id = db.Column(db.Integer, db.ForeignKey("admission_rule_versions.id"), nullable=False)
    output_id = db.Column(db.Integer, db.ForeignKey("learning_profile_outputs.id"), nullable=False)
    paragraph = db.Column(db.Integer, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("autobiography_comments.id"))
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    resolved_at = db.Column(db.DateTime)
    resolved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    author = db.relationship("User", foreign_keys=[author_id])
    resolved_by = db.relationship("User", foreign_keys=[resolved_by_id])
    output = db.relationship("LearningProfileOutput")
