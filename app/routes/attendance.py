import re

from flask import Blueprint, abort, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import AttendanceSummary, User
from app.routes.main import get_current_user, role_required
from app.services import attendance_import as service
from app.services import audit_service, teacher_scope


attendance_bp = Blueprint("attendance", __name__)


def _render(user, *, rows=None, error=None, status=200, student=None, from_award=False, daily=None, preview_only=False, source_range=None):
    records = AttendanceSummary.query.filter_by(student_id=(student or user).id).order_by(
        AttendanceSummary.school_year.desc(), AttendanceSummary.semester.desc()
    ).all()
    choices = [(record.school_year * 10 + record.semester, record.school_year, record.semester)
               for record in records]
    start = end = None
    range_error = None
    if request.method == "GET":
        try:
            start = _selected_term("from_term")
            end = _selected_term("to_term")
            if start and end and start > end:
                raise ValueError("起始學年期不能晚於結束學年期。")
            records = [record for record, (term, _, _) in zip(records, choices)
                       if (start is None or term >= start) and (end is None or term <= end)]
        except ValueError as exc:
            range_error = str(exc)
            records = []
            status = 400
    response = render_template(
        "attendance_import.html", user=user, absence_labels=service.ABSENCE_LABELS, hours_labels=service.HOURS_LABELS,
        records=records, rows=rows, error=error, student=student, from_award=from_award,
        term_choices=choices, from_term=start, to_term=end, range_error=range_error,
        daily=daily, preview_only=preview_only, source_range=source_range,
    )
    return response, status, {"Cache-Control": "no-store"}


def _selected_term(parameter):
    value = request.args.get(parameter, "")
    if not value:
        return None
    if not re.fullmatch(r"[1-9][0-9]{0,2}[12]", value):
        raise ValueError("請選擇有效的學年期。")
    return int(value)


def _preview_source(user, text, *, from_award=False, pdf=False):
    daily = None
    source_range = None
    try:
        if not pdf and len(text) > 100000:
            raise ValueError("貼上的內容過長，請縮短校方查詢範圍。")
        daily = service.daily_table(text)
        start, end = service.source_term_range(text)
        if start and end and start != end:
            source_range = (start, end)
        preview_only = bool(daily and (source_range or daily["invalid_dates"] or daily["overlong_span"]))
        rows = service.parse_totals(text, allow_range_preview=preview_only)
    except service.NoTotals as error:
        if daily:
            return _render(user, rows=[{}], daily=daily, preview_only=True, from_award=from_award, source_range=source_range)
        if pdf:
            return _render(user, rows=[{}], error="無法辨識這份 PDF 的合計欄位。請對照 PDF 填寫一個學期的合計，或改貼上校方表格。")
        return _render(user, error=str(error), status=400, from_award=from_award)
    except ValueError as error:
        if daily:
            return _render(user, rows=[{}], daily=daily, preview_only=True, error=str(error),
                           from_award=from_award, source_range=source_range)
        return _render(user, error=str(error), status=400, from_award=from_award)
    return _render(user, rows=rows, daily=daily, preview_only=preview_only,
                   from_award=from_award, source_range=source_range)


def review_pasted_totals(user, text, *, from_award=False):
    return _preview_source(user, text, from_award=from_award)


@attendance_bp.route("/student/attendance-records", methods=["GET", "POST"])
@role_required("student")
def records():
    user = get_current_user()
    if request.method == "GET":
        return _render(user)
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return review_pasted_totals(user, request.form.get("pasted_table", ""))
    try:
        if not uploaded.filename.lower().endswith(".pdf"):
            raise ValueError("請選擇 PDF 檔案。")
        content = uploaded.read(service.MAX_BYTES + 1)
        if len(content) > service.MAX_BYTES:
            raise ValueError("PDF 檔案須小於或等於 5 MB。")
        text = service.pdf_text(content)
    except ValueError as error:
        return _render(user, error=str(error), status=400)
    return _preview_source(user, text, pdf=True)


@attendance_bp.post("/student/attendance-records/confirm")
@role_required("student")
def confirm():
    user = get_current_user()
    years = request.form.getlist(service.YEAR)
    if not 1 <= len(years) <= service.MAX_TERMS:
        abort(400)
    fields = (service.YEAR, service.TERM, *service.FORM_LABELS)
    columns = {field: request.form.getlist(field) or [""] * len(years) for field in fields}
    if any(len(values) != len(years) for values in columns.values()):
        abort(400)
    drafts = [dict(zip(fields, values)) for values in zip(*columns.values())]
    try:
        rows = [service.validated_row(draft) for draft in drafts]
        service.check_terms(rows)
    except ValueError as error:
        return _render(user, rows=drafts, error=str(error), status=400)

    try:
        for row in sorted(rows, key=lambda row: (row[service.YEAR], row[service.TERM])):
            year = row.pop(service.YEAR)
            semester = row.pop(service.TERM)
            summary = AttendanceSummary.query.filter_by(
                student_id=user.id, school_year=year, semester=semester
            ).with_for_update().one_or_none()
            if summary is None:
                summary = AttendanceSummary(student_id=user.id, school_year=year, semester=semester)
                db.session.add(summary)
            summary.totals = service.merged_totals(summary.totals, row)
        audit_service.record(user, "attendance.import", "attendance_summary")
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _render(user, rows=drafts, error="儲存時同學期資料已更新，請重新核對再確認。", status=409)
    return redirect(url_for("attendance.records", saved=1))


@attendance_bp.get("/teacher/students/<int:student_id>/attendance-records")
@role_required("teacher")
def advisor_records(student_id):
    teacher = get_current_user()
    student = db.session.get(User, student_id)
    if student is None or not teacher_scope.can_view_student(teacher, student):
        abort(403)
    audit_service.record(teacher, "attendance.view", "student", student.id, commit=True)
    return _render(teacher, student=student)
