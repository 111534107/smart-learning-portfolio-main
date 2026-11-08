"""畢業缺口案件：案件頁、角色動作、通知頁、學生詢問與科辦重新檢核。

GET 一律不建立案件、不改狀態、不寫事件、不發通知；
唯一例外是打開案件頁時，把本人指向該案件的未讀通知標為已讀。
"""

from datetime import datetime, timezone

from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for

from app.extensions import db
from app.models import GraduationCase, GraduationCaseEvent, Notification, User
from app.routes.main import get_current_user, role_required
from app.services import graduation_case_actions as actions
from app.services import graduation_case_service as case_service
from app.services import graduation_check_service as check

graduation_bp = Blueprint("graduation", __name__)

STATUS_LABELS = {
    "pending": "待處理", "in_progress": "處理中",
    "awaiting_verification": "待科辦核對", "closed": "已結案",
}
ACTION_LABELS = {
    "note": "留言", "start": "開始處理", "submit": "送出待核對", "verify": "確認改善",
    "reject": "退回", "close_no_gap": "以查無缺口結案",
}
EVENT_LABELS = {
    "created": "建立案件", "student_note": "學生留言", "teacher_note": "導師留言",
    "started": "開始處理", "submitted": "送出待核對", "recalculated": "重新計算",
    "auto_verify": "資料改善，待核對", "verified": "科辦確認改善", "rejected": "科辦退回",
    "closed_no_gap": "以查無缺口結案", "data_changed": "資料變動",
}
CLOSE_REASON_LABELS = {"improved": "已確認改善", "no_gap": "查無缺口"}
CASE_TYPE_LABELS = {"gap": "缺口", "data_needed": "資料不足", "inquiry": "詢問"}


@graduation_bp.app_context_processor
def inject_unread_notifications():
    """導覽列的未讀通知數（學生、導師、科辦）。"""
    user = get_current_user()
    if user is None or user.role not in ("student", "teacher", "staff"):
        return {}
    count = Notification.query.filter_by(recipient_id=user.id, read_at=None).count()
    return {"unread_notification_count": count}


def _render_case(case, user, error=None, status=200):
    item_label = case_service.ITEM_LABELS.get(case.item, case.item)
    events = case.events.order_by(GraduationCaseEvent.id).all()
    inquiry = case.case_type == "inquiry"
    return render_template(
        "graduation_case.html", user=user, case=case, events=events, error=error,
        available=actions.available_actions(case, user), item_label=item_label,
        status_labels=STATUS_LABELS,
        action_labels={**ACTION_LABELS, "verify": "已處理"} if inquiry else ACTION_LABELS,
        event_labels={**EVENT_LABELS, "verified": "科辦已處理"} if inquiry else EVENT_LABELS,
        close_reason_labels={**CLOSE_REASON_LABELS, "improved": "已處理"} if inquiry else CLOSE_REASON_LABELS,
        type_labels=CASE_TYPE_LABELS,
        remedy=check.REMEDY_TEXT.get(case.item) if case.case_type == "gap" else None,
        disclaimer=check.DISCLAIMER,
    ), status


@graduation_bp.get("/graduation/cases/<int:case_id>")
@role_required("student", "teacher", "staff")
def case_detail(case_id):
    case = db.session.get(GraduationCase, case_id)
    if case is None:
        abort(404)
    user = get_current_user()
    if not actions.can_view(case, user):
        abort(403)
    unread = Notification.query.filter_by(recipient_id=user.id, case_id=case.id, read_at=None).all()
    if unread:
        now = datetime.now(timezone.utc)
        for note in unread:
            note.read_at = now
        db.session.commit()
    return _render_case(case, user)[0]


@graduation_bp.post("/graduation/cases/<int:case_id>/actions")
@role_required("student", "teacher", "staff")
def case_action(case_id):
    case = db.session.get(GraduationCase, case_id)
    if case is None:
        abort(404)
    user = get_current_user()
    try:
        actions.perform(case, user, request.form.get("action", ""), request.form.get("note", ""))
        db.session.commit()
    except actions.CaseActionError as exc:
        db.session.rollback()
        case = db.session.get(GraduationCase, case_id)
        if not actions.can_view(case, user):
            abort(403)  # 不能看案件的人，不回傳案件內容
        body, status = _render_case(case, user, error=str(exc), status=exc.status_code)
        return body, status
    return redirect(url_for("graduation.case_detail", case_id=case_id))


@graduation_bp.post("/student/graduation-check/inquiry")
@role_required("student")
def create_inquiry():
    user = get_current_user()
    try:
        case = actions.create_inquiry(user, request.form.get("note", ""))
        db.session.commit()
    except actions.CaseActionError as exc:
        db.session.rollback()
        return render_template("student_input_error.html", message=str(exc),
                               back_url=url_for("student.graduation_check")), exc.status_code
    return redirect(url_for("graduation.case_detail", case_id=case.id))


@graduation_bp.get("/notifications")
@role_required("student", "teacher", "staff")
def notifications():
    user = get_current_user()
    rows = (Notification.query.filter_by(recipient_id=user.id)
            .order_by(Notification.id.desc()).limit(100).all())
    return render_template("notifications.html", user=user, rows=rows)


@graduation_bp.get("/notifications/<int:notification_id>/open")
@role_required("student", "teacher", "staff")
def notification_open(notification_id):
    """開啟非案件的通知（例如電子獎狀核准或退回）：標為已讀後轉到通知裡的站內網址。"""
    user = get_current_user()
    note = db.session.get(Notification, notification_id)
    if note is None or note.recipient_id != user.id:
        abort(404)
    if note.read_at is None:
        note.read_at = datetime.now(timezone.utc)
        db.session.commit()
    if note.case_id:
        return redirect(url_for("graduation.case_detail", case_id=note.case_id))
    link = note.link or ""
    # 只轉到站內路徑，避免被拿來轉址到外站
    if link.startswith("/") and not link.startswith("//") and "\\" not in link:
        return redirect(link)
    return redirect(url_for("graduation.notifications"))


@graduation_bp.post("/staff/graduation/recheck")
@role_required("staff")
def recheck():
    raw = request.form.get("student_id", "").strip()
    if raw:
        student = db.session.get(User, _parse_id(raw))
        if student is None or student.role != "student":
            abort(404)
        case_service.sync_student(student)
    else:
        case_service.sync_all()
    db.session.commit()
    return redirect(url_for("main.staff_dashboard"))


def _parse_id(raw):
    """只接受 ASCII 數字的編號；其他（含全形、上標等 Unicode 數字）回傳 0，查無此人。"""
    if not (raw.isascii() and raw.isdigit()) or len(raw) > 18:
        return 0
    return int(raw)


def sync_after_commit(student):
    """主要資料已經提交後，再同步畢業缺口案件。

    同步失敗只回復同步這一段並記錄，原本的確認或儲存仍然有效，不讓使用者看到錯誤頁。
    """
    student_id = student.id
    try:
        case_service.sync_student(student)
        db.session.commit()
    except Exception:  # 同步是附帶動作，任何錯誤都不能讓已提交的主要動作看起來失敗
        db.session.rollback()
        current_app.logger.exception("畢業缺口同步失敗（學生 %s），主要資料已儲存", student_id)
