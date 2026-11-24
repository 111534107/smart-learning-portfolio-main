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


# ---------- 科主任：全年級學生檢視（唯讀，2026-11-19） ----------
def _chief_student_filters():
    return {key: value for key in ("grade", "class_name", "q", "status")
            if (value := request.args.get(key, "").strip())}


@staff_bp.get("/staff/students")
@role_required("staff")
def chief_students():
    from app.services import chief_student_view as view
    user = _chief_or_403()
    grade = request.args.get("grade", type=int)
    class_name = request.args.get("class_name", "").strip()
    query = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    rows = view.students(grade if grade in view.GRADE_LABELS else None, class_name, query,
                         status if status in view.STATUS_FILTERS else "")
    return render_template("staff_students.html", user=user, rows=rows, grade=grade, class_name=class_name, query=query,
                           status=status, grades=view.GRADE_LABELS, classes=view.class_names(), statuses=view.STATUS_FILTERS,
                           filters=_chief_student_filters())


@staff_bp.get("/staff/students/<int:student_id>")
@role_required("staff")
def chief_student_detail(student_id):
    return _render_chief_student_detail(student_id, "learning")


@staff_bp.get("/staff/students/<int:student_id>/admissions")
@role_required("staff")
def chief_student_admissions(student_id):
    return _render_chief_student_detail(student_id, "admissions")


def _render_chief_student_detail(student_id, page):
    from app.models import User
    from app.services import audit_service, chief_student_view as view
    user = _chief_or_403()
    student = db.session.get(User, student_id)
    if not student:
        student = User.query.filter_by(username=str(student_id), role="student").first()
    if not student or student.role != "student" or not student.student_profile:
        abort(404)
    detail = view.detail(student, page)
    sections = view.DETAIL_SECTIONS[page]
    if detail.get("transfer"):
        sections = [*sections, "轉學抵免進度"]
    audit_service.record(user, "staff.student_view", "user", student.id, {"sections": sections}, commit=True)
    return render_template("staff_student_detail.html", user=user, d=detail, detail_page=page,
                           filters=_chief_student_filters())


@staff_bp.get("/staff/documents/<int:document_id>/view")
@role_required("staff")
def chief_document_view(document_id):
    """科主任看學生已確認的成績單、證照原始檔。"""
    from app.extensions import db
    from app.models import SourceDocument
    from app.services import audit_service
    from app.services.file_preview import inline_file
    user = _chief_or_403()
    document = db.session.get(SourceDocument, document_id)
    if not document or document.status != "confirmed":
        abort(404)
    audit_service.record(user, "staff.student_document_view", "source_document", document.id,
                         {"student_id": document.owner_id}, commit=True)
    return inline_file(document.file_path, document.display_name)


# ---------- 轉學生：科主任與科辦處理（2026-11-19） ----------
@staff_bp.get("/staff/transfer-students")
@staff_bp.post("/staff/transfer-students")
@role_required("staff")
def transfer_students():
    from app.extensions import db
    from app.routes.main import get_current_user
    from app.services import chief_student_view, transfer_student_service as service
    user = get_current_user()
    if request.method == "POST":
        abort(403)
    return render_template("staff_transfer_students.html", user=user, rows=service.rows(), error=None, created=None,
                           classes=chief_student_view.class_names(), status_labels=STATUS_LABELS())



def STATUS_LABELS():
    from app.routes.transfer_credit import STATUS_LABELS as labels
    return labels


@staff_bp.post("/staff/transfer-students/<int:student_id>/confirm")
@role_required("staff")
def transfer_confirm(student_id):
    from app.extensions import db
    from app.models import User
    from app.routes.graduation import sync_after_commit
    from app.routes.main import get_current_user
    from app.services import transfer_student_service as service
    user = get_current_user()
    student = db.session.get(User, student_id)
    if not student or student.role != "student":
        abort(404)
    if service.confirm(user, student, request.form.get("confirmed") == "1") is None:
        abort(404)
    db.session.commit()
    sync_after_commit(student)
    return redirect(url_for("staff.transfer_students"))
