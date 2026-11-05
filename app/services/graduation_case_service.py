"""畢業缺口案件同步：把無狀態的判斷結果轉成共用案件、事件與站內通知。

同步是冪等的：同一份資料重複同步不會多出案件、事件或通知。
本服務只 flush，不 commit，由呼叫端決定何時提交。
只做提醒與追蹤，不宣告任何人符合或不符合畢業資格。
"""

import logging

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (ClassAdvisor, GraduationCase, GraduationCaseEvent, Notification,
                        StudentProfile, User)
from app.services import audit_service
from app.services import graduation_check_service as check

CREDIT_ITEMS = ("required_credits", "elective_credits", "total_credits")
ITEM_LABELS = {
    "certificates": "證照", "required_credits": "必修學分", "elective_credits": "選修學分",
    "total_credits": "總學分", "credits": "成績單（學分）", "general": "一般詢問",
}
_WAITING_RESULTS = ("insufficient_data", "transfer_pending", "rule_unverified")
_NOT_GAP = ("met", "progress")
logger = logging.getLogger(__name__)


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


def _create_case(student, item, case_type, data, last_result, previous=None):
    """建立案件；open_key 衝突（並行同步）時回傳 None，由呼叫端改走已有案件分支。"""
    case = GraduationCase(
        student_id=student.id, case_type=case_type, item=item, status="pending",
        initial_amount=data.get("amount"), current_amount=data.get("amount"),
        unit=data.get("unit"), basis=data.get("basis") or "", detail=data.get("detail") or "",
        open_key=GraduationCase.open_key_for(student.id, item, case_type),
        previous_case_id=previous.id if previous else None, last_result=last_result)
    try:
        with db.session.begin_nested():
            db.session.add(case)
            db.session.flush()
    except IntegrityError:
        return None
    return case


def _label(item):
    return ITEM_LABELS.get(item, item)


def _set_last_result(case, value):
    if case.last_result != value:
        case.last_result = value


def _previous_result(case, bad, good):
    """案件上次同步看到的結果；舊資料沒有 last_result 時，由狀態推回。"""
    if case.last_result:
        return case.last_result
    return good if case.status == "awaiting_verification" else bad


def _should_reopen(closed, bad, amount=None):
    """結案後同一問題又出現時，要不要開新案件。

    只在「離開問題狀態後又回來」（結案案件最後看到的結果不是問題），
    或缺口比結案時更大時才開；否則尊重科辦的結案決定，不再開案、不再通知。
    """
    if closed is None:
        return True
    if (closed.last_result or bad) != bad:
        return True
    return amount is not None and closed.current_amount is not None and amount > closed.current_amount


def _sync_gap(student, item, data, formal, advisors, staff, events):
    """缺口案件：只在判斷結果轉變（缺口 ↔ 已排除）時改狀態，不蓋掉人工送出、退回、結案。"""
    result = data["result"]
    case = _open_case(student.id, item, "gap")
    if case is None:
        closed = _latest_closed(student.id, item, "gap")
        if result != "gap" or not formal:
            if closed is not None and result in _NOT_GAP:
                _set_last_result(closed, result)
            return
        if not _should_reopen(closed, "gap", data["amount"]):
            return
        case = _create_case(student, item, "gap", data, "gap", closed)
        if case is not None:
            events.append(record_event(
                case, "created", to_status="pending", amount_after=data["amount"],
                note=data.get("detail") or "", notify=[student, *advisors],
                message=f"案件 {case.number}：{_label(item)}發現缺口，還差 {data['amount']} {data['unit']}，請留意。"))
            return
        case = _open_case(student.id, item, "gap")
        if case is None:
            return
    previous = _previous_result(case, "gap", "met")
    if result == "gap":
        amount = data["amount"]
        _set_last_result(case, "gap")
        if previous != "gap" and case.status == "awaiting_verification":
            # 系統判斷已排除、待核對期間缺口又出現：退回處理中，通知學生與導師
            events.append(record_event(
                case, "recalculated", to_status="in_progress", amount_after=amount,
                note=f"缺口再次出現，目前還差 {amount} {data['unit']}。", notify=[student, *advisors],
                message=f"案件 {case.number}：{_label(item)}的缺口再次出現，已退回處理中。"))
        elif (amount is not None and case.current_amount is not None
                and amount != case.current_amount):
            # 缺口仍在、數字變了：只更新目前缺口，不改狀態（含人工送出的待核對）、不通知
            word = "減為" if amount < case.current_amount else "增為"
            events.append(record_event(
                case, "recalculated", amount_after=amount,
                note=f"缺口由 {case.current_amount} {word} {amount} {data['unit']}。"))
    elif result in _NOT_GAP:
        _set_last_result(case, result)
        if previous == "gap" and case.status != "awaiting_verification":
            events.append(record_event(
                case, "auto_verify", to_status="awaiting_verification",
                note=f"重新判斷結果為 {result}，等待科辦核對。", notify=staff,
                message=f"案件 {case.number}：{_label(item)}的資料已改善，請科辦核對。"))
    elif result in _WAITING_RESULTS:
        # 等待中的結果不寫進 last_result，避免蓋掉「缺口 ↔ 已排除」的轉變
        note = f"判斷結果：{result}"
        last = case.events.order_by(GraduationCaseEvent.id.desc()).first()
        if not (last and last.event_type == "data_changed" and last.note == note):
            events.append(record_event(case, "data_changed", note=note))


def _sync_data_needed(student, item, needed, data, formal, staff, events):
    """資料補充案件；needed：該項資料是否仍不足。last_result 記 insufficient / sufficient。"""
    state = "insufficient" if needed else "sufficient"
    case = _open_case(student.id, item, "data_needed")
    if case is None:
        closed = _latest_closed(student.id, item, "data_needed")
        if not (needed and formal):
            if closed is not None:
                _set_last_result(closed, state)
            return
        if not _should_reopen(closed, "insufficient"):
            return
        case = _create_case(student, item, "data_needed", data, "insufficient", closed)
        if case is not None:
            events.append(record_event(
                case, "created", to_status="pending", note=data.get("detail") or "",
                notify=[student],
                message=f"案件 {case.number}：{_label(item)}資料不足，請補上傳或確認後才能判斷。"))
            return
        case = _open_case(student.id, item, "data_needed")
        if case is None:
            return
    previous = _previous_result(case, "insufficient", "sufficient")
    _set_last_result(case, state)
    if needed:
        if previous != "insufficient" and case.status == "awaiting_verification":
            events.append(record_event(
                case, "recalculated", to_status="in_progress",
                note=f"資料又變得不足：{data.get('detail') or ''}".rstrip("："), notify=[student],
                message=f"案件 {case.number}：{_label(item)}資料又不足，已退回處理中。"))
    elif previous == "insufficient" and case.status != "awaiting_verification":
        events.append(record_event(
            case, "auto_verify", to_status="awaiting_verification",
            note="資料已足夠判斷，等待科辦核對。", notify=staff,
            message=f"案件 {case.number}：{_label(item)}資料已補足，請科辦核對。"))


def sync_student(student, today=None, curriculum=None):
    """依判斷結果同步該生的案件；回傳本次新增的事件。"""
    today = check.check_today() if today is None else today
    assessment = check.assess(student, today=today, curriculum=curriculum)
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
    curriculum = check.load_curriculum()  # 全科共用一份，不必每位學生重讀 CSV
    total = 0
    for student in students:
        try:
            with db.session.begin_nested():
                total += len(sync_student(student, today=today, curriculum=curriculum))
        except Exception:  # 單一學生資料有問題時記錄後跳過，不拖垮全科
            logger.exception("畢業缺口同步失敗，已跳過學生 %s", student.id)
    return total


# ---- 導師首頁／科辦頁用的總覽（只讀，不寫入）----
_GAP_ITEM_ORDER = ("certificates", "required_credits", "total_credits", "elective_credits")
_FIRST_CHECK = "專四下學期期末考前兩週"
_SECOND_CHECK = "專五上學期期末考前兩週"
_AFTER_CHECK = "已過兩次檢核，請與科辦確認"


def next_check_text(stage):
    """下一次檢核時間的說明文字。"""
    grade, semester = stage.get("grade"), stage.get("semester")
    if grade is None or grade <= 4:
        return _FIRST_CHECK
    if grade == 5 and semester == "上":
        return _SECOND_CHECK
    return _AFTER_CHECK


WAITING_IMPROVED_LABEL = "資料已改善，待科辦核對"


def _hint(case):
    if case.status == "awaiting_verification":
        return "等待科辦核對"
    if case.case_type == "data_needed":
        return "請學生上傳並確認資料"
    if case.item == "certificates":
        return "依實施要點第五點補救"
    return "請洽科辦確認補修"


def class_overview(students, today=None):
    """一個班級的畢業門檻總覽。不建立案件、不寫事件。"""
    today = check.check_today() if today is None else today
    curriculum = check.load_curriculum()
    ids = [student.id for student in students]
    open_cases = []
    if ids:
        open_cases = (GraduationCase.query
                      .filter(GraduationCase.student_id.in_(ids), GraduationCase.status != "closed",
                              GraduationCase.case_type.in_(("gap", "data_needed")))
                      .order_by(GraduationCase.id).all())
    by_student = {}
    for case in open_cases:
        by_student.setdefault(case.student_id, []).append(case)
    overview = {"total": len(students), "met": 0, "gap": 0, "data": 0, "other": 0, "priority": []}
    ranked = []
    for student in students:
        assessment = check.assess(student, today=today, curriculum=curriculum)
        results = [data["result"] for data in assessment["items"].values()]
        cases = by_student.get(student.id, [])
        grade = assessment["stage"].get("grade") or 0
        active = [case for case in cases if case.status != "awaiting_verification"]
        # 待科辦核對的案件不算「確定有缺口」，也不算「已達門檻」：歸在 other（等待核對、修課中等）
        if any(case.case_type == "gap" for case in active):
            overview["gap"] += 1
        elif active or "insufficient_data" in results:
            overview["data"] += 1
        elif cases:
            overview["other"] += 1
        elif all(result == "met" for result in results):
            overview["met"] += 1
        else:
            overview["other"] += 1
        for case in cases:
            if case.status == "awaiting_verification":
                # 排在未處理的缺口與資料補充案件之後
                key = (2, 0, -grade, 0, case.id)
                label = (WAITING_IMPROVED_LABEL if case.improved_pending
                         else f"{_label(case.item)}已送交，待科辦核對")
            elif case.case_type == "gap":
                order = _GAP_ITEM_ORDER.index(case.item) if case.item in _GAP_ITEM_ORDER else len(_GAP_ITEM_ORDER)
                key = (0, order, -grade, -(case.current_amount or 0), case.id)
                label = (f"{_label(case.item)}還差 {case.current_amount} {case.unit or ''}".strip()
                         if case.current_amount is not None else f"{_label(case.item)}有缺口")
            else:
                key = (1, 0, -grade, 0, case.id)
                label = f"{_label(case.item)}資料待確認"
            ranked.append((key, {"student": student, "case": case, "label": label, "hint": _hint(case)}))
    overview["priority"] = [row for _, row in sorted(ranked, key=lambda pair: pair[0])]
    return overview


def awaiting_cases():
    """科辦待核對的案件。"""
    return (GraduationCase.query.filter_by(status="awaiting_verification")
            .order_by(GraduationCase.updated_at, GraduationCase.id).all())
