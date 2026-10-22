from flask import Blueprint, redirect, request, url_for

from app.extensions import db
from app.models import PortfolioSubmission
from app.routes.main import role_required
from app.services.review_service import record_review_result


staff_bp = Blueprint("staff", __name__)


@staff_bp.post("/staff/reviews/<int:submission_id>/result")
@role_required("staff", "admin")
def staff_review_result(submission_id):
    submission = db.session.get(PortfolioSubmission, submission_id)
    if not submission:
        from flask import abort
        abort(404)
    decision = request.form.get("decision", "needs_revision")
    comment = request.form.get("comment", "").strip()
    issues = [value.strip() for value in request.form.getlist("revision_item") if value.strip()]
    from app.routes.main import get_current_user
    record_review_result(submission, get_current_user(), decision, comment, issues)
    db.session.commit()
    return redirect(url_for("main.staff_dashboard"))
