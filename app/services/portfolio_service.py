from datetime import datetime, timezone

from flask import abort

from app.extensions import db
from app.models import (
    Portfolio,
    PortfolioGoalSnapshot,
    PortfolioSubmission,
    StudentProjectAssignment,
)


def owned_portfolio(portfolio_id, actor):
    portfolio = db.session.get(Portfolio, portfolio_id)
    if not portfolio or portfolio.deleted_at:  # 學生刪除過的（只標記）當成不存在
        abort(404)
    if actor.role not in {"admin", "staff"} and portfolio.student_id != actor.id:
        abort(403)
    return portfolio


def create_submission_snapshot(portfolio, actor):
    if actor.role not in {"admin", "staff"} and portfolio.student_id != actor.id:
        abort(403)
    previous = portfolio.submissions[-1] if portfolio.submissions else None
    submission = PortfolioSubmission(
        portfolio=portfolio,
        version_no=(previous.version_no + 1) if previous else 1,
        previous_submission=previous,
        status="submitted",
        submitted_at=datetime.now(timezone.utc),
    )
    db.session.add(submission)
    assignment = StudentProjectAssignment.query.filter_by(student_id=portfolio.student_id, status="active").first()
    if assignment:
        for item in assignment.template.items:
            submission.goal_snapshots.append(
                PortfolioGoalSnapshot(
                    requirement_item_id=item.id,
                    title=item.title,
                    description=item.description,
                )
            )
    return submission
