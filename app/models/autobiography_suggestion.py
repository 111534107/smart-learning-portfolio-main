"""自傳「建議修改」（像 Google 文件的建議模式，2026-11-20）。

導師選取某一段裡的一句話提出替換；學生接受（存成新的一版）或不接受。
原文在學生接受前不動；紀錄不提供刪除（規格：修改紀錄完整保留）。
"""

from datetime import datetime, timezone

from app.extensions import db


class AutobiographySuggestion(db.Model):
    __tablename__ = "autobiography_suggestions"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    program_id = db.Column(db.Integer, db.ForeignKey("admission_rule_versions.id"), nullable=False)
    output_id = db.Column(db.Integer, db.ForeignKey("learning_profile_outputs.id"), nullable=False)  # 提出建議時的那一版
    paragraph = db.Column(db.Integer, nullable=False)
    start = db.Column(db.Integer, nullable=False)
    end = db.Column(db.Integer, nullable=False)
    original = db.Column(db.Text, nullable=False)       # 被建議修改的原文（接受時用它確認文字還在）
    replacement = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(12), nullable=False, default="pending", index=True)  # pending／accepted／rejected／stale
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    resolved_at = db.Column(db.DateTime)
    resolved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    result_output_id = db.Column(db.Integer, db.ForeignKey("learning_profile_outputs.id"))  # 接受後產生的新版

    author = db.relationship("User", foreign_keys=[author_id])
    resolved_by = db.relationship("User", foreign_keys=[resolved_by_id])
    output = db.relationship("LearningProfileOutput", foreign_keys=[output_id])
