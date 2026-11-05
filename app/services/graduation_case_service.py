"""畢業缺口案件同步：把無狀態的判斷結果轉成共用案件、事件與站內通知。

同步是冪等的：同一份資料重複同步不會多出案件、事件或通知。
本服務只 flush，不 commit，由呼叫端決定何時提交。
只做提醒與追蹤，不宣告任何人符合或不符合畢業資格。
"""

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (ClassAdvisor, GraduationCase, GraduationCaseEvent, Notification,
                        StudentProfile, User)
from app.services import audit_service
from app.services import graduation_check_service as check

CREDIT_ITEMS = ("required_credits", "elective_credits", "total_credits")
ITEM_LABELS = {
    "certificates": "證照", "required_credits": "必修學分", "elective_credits": "選修學分",
    "total_credits": "總學分", "credits": "成績單（學分）",
}
_WAITING_RESULTS = ("insufficient_data", "transfer_pending", "rule_unverified")


def advisors_for(student):
    """學生班級的所有導師（啟用中）。"""
    profile = student.student_profile
    if profile is None or not profile.class_name:
        return []
    ids = {row.teacher_id for row in ClassAdvisor.query.filter_by(class_name=profile.class_name).all()}
    if not ids:
        return []
    return (User.query.filter(User.id.in_(ids), User.is_active.is_(True))
            .order_by(User.id).all())


def staff_users():
    """所有啟用中的科辦人員。"""
    return User.query.filter(User.role == "staff", User.is_active.is_(True)).order_by(User.id).all()


def record_event(case, event_type, actor=None, *, to_status=None, amount_after=None, note="",
                 notify=(), message=""):
    """寫一筆案件事件；有 to_status 時改狀態並寫操作紀錄；對 notify 每人建一則通知（同人去重）。"""
    from_status = case.status
    amount_before = case.current_amount
    event = GraduationCaseEvent(
        case_id=case.id, actor_id=actor.id if actor else None, event_type=event_type,
        from_status=from_status, to_status=to_status, amount_before=amount_before,
        amount_after=amount_after, note=note)
    if amount_after is not None:
        case.current_amount = amount_after
    if to_status is not None:
        case.status = to_status
        if to_status == "closed":
            case.open_key = None
            case.closed_at = check_now()
            case.closed_by_id = actor.id if actor else None
    db.session.add(event)
    db.session.flush()
    if to_status is not None and to_status != from_status:
        audit_service.record(actor, "graduation_case.status", "graduation_case", case.id,
                             detail={"from": from_status, "to": to_status, "event": event_type})
    seen = set()
    for user in notify:
        if user.id in seen:
            continue
        seen.add(user.id)
        db.session.add(Notification(recipient_id=user.id, case_id=case.id, event_id=event.id,
                                    message=(message or f"案件 {case.number} 有更新")[:255]))
    db.session.flush()
    return event


def check_now():
    from app.models.graduation_case import utcnow
    return utcnow()


def _latest_closed(student_id, item, case_type):
    return (GraduationCase.query
            .filter_by(student_id=student_id, item=item, case_type=case_type, status="closed")
            .order_by(GraduationCase.id.desc()).first())


def _open_case(student_id, item, case_type):
    return GraduationCase.query.filter_by(
        open_key=GraduationCase.open_key_for(student_id, item, case_type)).first()


def _create_case(student, item, case_type, data):
    """建立案件；open_key 衝突（並行同步）時回傳 None，由呼叫端改走已有案件分支。"""
    previous = _latest_closed(student.id, item, case_type)
    case = GraduationCase(
        student_id=student.id, case_type=case_type, item=item, status="pending",
        initial_amount=data.get("amount"), current_amount=data.get("amount"),
        unit=data.get("unit"), basis=data.get("basis") or "", detail=data.get("detail") or "",
        open_key=GraduationCase.open_key_for(student.id, item, case_type),
        previous_case_id=previous.id if previous else None)
    try:
        with db.session.begin_nested():
            db.session.add(case)
            db.session.flush()
    except IntegrityError:
        return None
    return case


def _label(item):
    return ITEM_LABELS.get(item, item)


def _sync_gap(student, item, data, formal, advisors, staff, events):
    result = data["result"]
    case = _open_case(student.id, item, "gap")
    if case is None:
        if result != "gap" or not formal:
            return
        case = _create_case(student, item, "gap", data)
        if case is not None:
            events.append(record_event(
                case, "created", to_status="pending", amount_after=data["amount"],
                note=data.get("detail") or "", notify=[student, *advisors],
                message=f"案件 {case.number}：{_label(item)}發現缺口，還差 {data['amount']} {data['unit']}，請留意。"))
            return
        case = _open_case(student.id, item, "gap")
        if case is None:
            return
    if result == "gap":
        if (data["amount"] is not None and case.current_amount is not None
                and data["amount"] < case.current_amount):
            events.append(record_event(
                case, "recalculated", amount_after=data["amount"],
                note=f"缺口由 {case.current_amount} 減為 {data['amount']} {data['unit']}。"))
    elif result in ("met", "progress"):
        if case.status != "awaiting_verification":
            events.append(record_event(
                case, "auto_verify", to_status="awaiting_verification",
                note=f"重新判斷結果為 {result}，等待科辦核對。", notify=staff,
                message=f"案件 {case.number}：{_label(item)}的資料已改善，請科辦核對。"))
    elif result in _WAITING_RESULTS:
        note = f"判斷結果：{result}"
        last = case.events.order_by(GraduationCaseEvent.id.desc()).first()
        if not (last and last.event_type == "data_changed" and last.note == note):
            events.append(record_event(case, "data_changed", note=note))


def _sync_data_needed(student, item, needed, data, formal, staff, events):
    """needed：該項資料是否仍不足。"""
    case = _open_case(student.id, item, "data_needed")
    if case is None:
        if not (needed and formal):
            return
        case = _create_case(student, item, "data_needed", data)
        if case is not None:
            events.append(record_event(
                case, "created", to_status="pending", note=data.get("detail") or "",
                notify=[student],
                message=f"案件 {case.number}：{_label(item)}資料不足，請補上傳或確認後才能判斷。"))
            return
        case = _open_case(student.id, item, "data_needed")
        if case is None:
            return
    if not needed and case.status != "awaiting_verification":
        events.append(record_event(
            case, "auto_verify", to_status="awaiting_verification",
            note="資料已足夠判斷，等待科辦核對。", notify=staff,
            message=f"案件 {case.number}：{_label(item)}資料已補足，請科辦核對。"))


def sync_student(student, today=None):
    """依判斷結果同步該生的案件；回傳本次新增的事件。"""
    today = check.check_today() if today is None else today
    assessment = check.assess(student, today=today)
    formal = assessment["stage"]["formal"]
    items = assessment["items"]
    advisors = advisors_for(student)
    staff = staff_users()
    events = []
    for item, data in items.items():
        _sync_gap(student, item, data, formal, advisors, staff, events)
    cert = items["certificates"]
    _sync_data_needed(student, "certificates", cert["result"] == "insufficient_data", cert, formal, staff, events)
    credit_rows = [items[name] for name in CREDIT_ITEMS]
    needed = any(row["result"] == "insufficient_data" for row in credit_rows)
    source = next((row for row in credit_rows if row["result"] == "insufficient_data"), credit_rows[0])
    _sync_data_needed(student, "credits", needed, source, formal, staff, events)
    return events


def sync_all(today=None):
    """同步所有啟用中的學生；回傳新增事件數。"""
    today = check.check_today() if today is None else today
    students = (User.query.join(StudentProfile, StudentProfile.user_id == User.id, isouter=True)
                .filter(User.role == "student", User.is_active.is_(True)).order_by(User.id).all())
    return sum(len(sync_student(student, today=today)) for student in students)
