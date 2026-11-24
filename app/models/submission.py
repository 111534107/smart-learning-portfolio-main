from datetime import datetime, timezone

from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class PortfolioSubmission(db.Model):
    __tablename__ = "portfolio_submissions"
    id = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey("portfolios.id"), nullable=False, index=True)
    version_no = db.Column(db.Integer, nullable=False, default=1)
    previous_submission_id = db.Column(db.Integer, db.ForeignKey("portfolio_submissions.id"), nullable=True)
    status = db.Column(db.String(30), nullable=False, default="draft", index=True)
    submitted_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    portfolio = db.relationship("Portfolio", back_populates="submissions", foreign_keys=[portfolio_id])
    previous_submission = db.relationship("PortfolioSubmission", remote_side=[id], uselist=False)
    goal_snapshots = db.relationship("PortfolioGoalSnapshot", back_populates="submission", cascade="all, delete-orphan")
    evidence_links = db.relationship("SubmissionEvidence", back_populates="submission", cascade="all, delete-orphan")
    assignments = db.relationship("SubmissionAssignment", back_populates="submission", cascade="all, delete-orphan")
    review_results = db.relationship("ProjectReviewResult", back_populates="submission", cascade="all, delete-orphan")
    revision_records = db.relationship("ProjectRevisionRecord", back_populates="submission", cascade="all, delete-orphan")


class PortfolioGoalSnapshot(db.Model):
    __tablename__ = "portfolio_goal_snapshots"
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey("portfolio_submissions.id"), nullable=False)
    requirement_item_id = db.Column(db.Integer, db.ForeignKey("requirement_items.id"), nullable=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    submission = db.relationship("PortfolioSubmission", back_populates="goal_snapshots")


class SubmissionEvidence(db.Model):
    __tablename__ = "submission_evidence"
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey("portfolio_submissions.id"), nullable=False)
    evidence_id = db.Column(db.Integer, db.ForeignKey("portfolio_evidence.id"), nullable=False)
    submission = db.relationship("PortfolioSubmission", back_populates="evidence_links")
    evidence = db.relationship("PortfolioEvidence")
