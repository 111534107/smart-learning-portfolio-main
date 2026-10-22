from flask import Blueprint, abort, redirect, render_template, request, url_for

from app.extensions import db
from app.models import PortfolioSubmission, SubmissionAssignment, TeacherReviewFeedback
from app.routes.main import get_current_user, role_required
from app.services.review_service import record_teacher_feedback


review_bp = Blueprint("review", __name__)


def feedback_by_submission(submission_ids):
    feedback_map = {}
    if not submission_ids:
        return feedback_map
    feedback_items = (
        TeacherReviewFeedback.query.filter(TeacherReviewFeedback.submission_id.in_(submission_ids))
        .order_by(TeacherReviewFeedback.created_at.asc())
        .all()
    )
    for feedback in feedback_items:
        feedback_map.setdefault(feedback.submission_id, []).append(feedback)
    return feedback_map


@review_bp.get("/teacher/reviews")
@role_required("teacher")
def teacher_reviews():
    user = get_current_user()
    assignments = (
        SubmissionAssignment.query.filter_by(teacher_id=user.id)
        .order_by(SubmissionAssignment.assigned_at.desc())
        .all()
    )
    return render_template(
        "review_queue.html",
        user=user,
        assignments=assignments,
        feedback_by_submission=feedback_by_submission([item.submission_id for item in assignments]),
    )


@review_bp.post("/teacher/reviews/<int:submission_id>/feedback")
@role_required("teacher")
def teacher_feedback(submission_id):
    submission = db.session.get(PortfolioSubmission, submission_id)
    if not submission:
        abort(404)
    try:
        record_teacher_feedback(submission, get_current_user(), request.form.get("comment"))
    except PermissionError:
        abort(403)
    except ValueError:
        abort(400)
    db.session.commit()
    return redirect(url_for("review.teacher_reviews"))
