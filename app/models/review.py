from datetime import datetime, timezone

from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class SubmissionAssignment(db.Model):
    __tablename__ = "submission_assignments"
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey("portfolio_submissions.id"), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    assigned_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    submission = db.relationship("PortfolioSubmission", back_populates="assignments")
    teacher = db.relationship("User", back_populates="review_assignments")


class TeacherReviewFeedback(db.Model):
    __tablename__ = "teacher_review_feedback"
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey("portfolio_submissions.id"), nullable=False, index=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    comment = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    submission = db.relationship("PortfolioSubmission")
    teacher = db.relationship("User")


class ProjectReviewResult(db.Model):
    __tablename__ = "project_review_results"
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey("portfolio_submissions.id"), nullable=False)
    recorded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    decision = db.Column(db.String(30), nullable=False)
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    submission = db.relationship("PortfolioSubmission", back_populates="review_results")
    recorded_by = db.relationship("User", foreign_keys=[recorded_by_id])
    revision_records = db.relationship("ProjectRevisionRecord", back_populates="review_result", cascade="all, delete-orphan")


class ProjectRevisionRecord(db.Model):
    __tablename__ = "project_revision_records"
    id = db.Column(db.Integer, primary_key=True)
    review_result_id = db.Column(db.Integer, db.ForeignKey("project_review_results.id"), nullable=True)
    submission_id = db.Column(db.Integer, db.ForeignKey("portfolio_submissions.id"), nullable=False)
    issue = db.Column(db.Text, nullable=False)
    resolution = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), nullable=False, default="open")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    review_result = db.relationship("ProjectReviewResult", back_populates="revision_records")
    submission = db.relationship("PortfolioSubmission", back_populates="revision_records")
