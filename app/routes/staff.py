from flask import Blueprint, abort, redirect, render_template, request, url_for

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
    decision = request.form.get("decision", "")
    comment = request.form.get("comment", "").strip()
    issues = [value.strip() for value in request.form.getlist("revision_item") if value.strip()]
    if decision not in {"approved", "needs_revision", "rejected"} or (decision in {"needs_revision", "rejected"} and not comment):
        return render_template("staff_review_error.html"), 400
    from app.routes.main import get_current_user
    record_review_result(submission, get_current_user(), decision, comment, issues)
    db.session.commit()
    return redirect(url_for("main.staff_dashboard"))


def _chief_or_403():
    from app.routes.main import get_current_user
    from app.services import staff_roles
    user = get_current_user()
    if not staff_roles.is_chief(user):
        abort(403)  # 科助與其他行政人員不能決定誰帶哪個班
    return user


@staff_bp.get("/staff/classes")
@staff_bp.post("/staff/classes")
@role_required("staff")
def classes():
    """科主任（含副主任）決定哪位老師帶哪個班（2026-11-18 指導老師要求）；管理員頁 /admin/classes 保留作系統維護。"""
    from app.services import class_assignment_service
    user = _chief_or_403()
    error = None
    if request.method == "POST":
        try:
            class_assignment_service.add(user, request.form.get("teacher_id", type=int),
                                         request.form.get("class_name"), request.form.get("school_year", type=int))
            return redirect(url_for("staff.classes"))
        except class_assignment_service.AssignmentError as exc:
            error = str(exc)
    return render_template("admin_classes.html", user=user, error=error, form_action=url_for("staff.classes"),
                           delete_endpoint="staff.class_delete", **class_assignment_service.page_data()), (400 if error else 200)


@staff_bp.post("/staff/classes/<int:advisor_id>/delete")
@role_required("staff")
def class_delete(advisor_id):
    from app.routes.main import get_current_user  # noqa: F401
    from app.services import class_assignment_service
    user = _chief_or_403()
    class_assignment_service.remove(user, advisor_id)
    return redirect(url_for("staff.classes"))
