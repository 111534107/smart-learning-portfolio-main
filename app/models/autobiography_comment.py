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
