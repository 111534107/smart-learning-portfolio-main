"""轉學生抵免進度：只做學生自行記錄與導師確認，不介接校方系統。"""

from datetime import date, datetime, timezone

from flask import Blueprint, abort, redirect, render_template, request, url_for

from app.extensions import db
from app.models import TransferCreditRecord, User
from app.routes.main import get_current_user, role_required
from app.services.teacher_scope import can_view_student


transfer_credit_bp = Blueprint("transfer_credit", __name__)

STATUS_LABELS = {
    "not_started": "尚未申請",
    "submitted": "已送出申請",
    "needs_documents": "需要補交資料",
    "completed": "本人記錄已完成",
}


@transfer_credit_bp.route("/student/transfer-credit", methods=["GET", "POST"])
@role_required("student")
def student_transfer_credit():
    student = get_current_user()
    record = TransferCreditRecord.query.filter_by(student_id=student.id).first()
    error = None

    if request.method == "POST":
        status = request.form.get("status", "").strip()
        date_value = request.form.get("submitted_on", "").strip()
        missing_documents = request.form.get("missing_documents", "").strip()
        note = request.form.get("note", "").strip()
        if status not in STATUS_LABELS:
            abort(400, description="請選擇有效的申請狀態。")
        try:
            submitted_on = date.fromisoformat(date_value) if date_value else None
        except ValueError:
            abort(400, description="申請日期格式不正確。")
        if len(missing_documents) > 1000 or len(note) > 2000:
            abort(400, description="備註或待補資料太長，請縮短後再儲存。")

        if record is None:
            record = TransferCreditRecord(student_id=student.id)
            db.session.add(record)
        changed = (
            record.status != status
            or record.submitted_on != submitted_on
            or record.missing_documents != missing_documents
            or record.note != note
        )
        record.status = status
        record.submitted_on = submitted_on
        record.missing_documents = missing_documents
        record.note = note
        if changed:
            record.teacher_confirmed = False
            record.teacher_id = None
            record.teacher_confirmed_at = None
        db.session.commit()
        return redirect(url_for("transfer_credit.student_transfer_credit", saved=1))

    return render_template(
        "student_transfer_credit.html",
        user=student,
        record=record,
        status_labels=STATUS_LABELS,
        saved=request.args.get("saved"),
        error=error,
    )


@transfer_credit_bp.post("/teacher/students/<int:student_id>/transfer-credit/confirm")
@role_required("teacher")
def confirm_transfer_credit(student_id):
    teacher = get_current_user()
    student = db.session.get(User, student_id)
    if not student or not can_view_student(teacher, student):
        abort(403)
    record = TransferCreditRecord.query.filter_by(student_id=student.id).first()
    if not record:
        abort(404)
    if request.form.get("confirmed") == "1":
        record.teacher_confirmed = True
        record.teacher_id = teacher.id
        record.teacher_confirmed_at = datetime.now(timezone.utc)
    else:
        record.teacher_confirmed = False
        record.teacher_id = None
        record.teacher_confirmed_at = None
    db.session.commit()
    return redirect(url_for("teacher.student_detail", student_id=student.id))
