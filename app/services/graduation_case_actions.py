"""畢業缺口案件的角色動作與權限：學生與導師共用同一份案件紀錄。

2026-11-09 起科辦不參與畢業缺口：科長訪談說明正式畢業資格審查由教務處負責
（學生專四下、專五上各填一次自評表），科辦只做電子獎狀、二技公告、表單下載區。
因此拿掉「送出待核對 → 科辦確認／退回」：
- 系統重新對照後缺口已排除，案件自動結案（見 graduation_case_service）。
- 系統看不到的改善（例如教務處已確認補救），由導師填寫原因後結案。
舊資料裡的 submitted / verified / rejected 事件照樣顯示，不刪。

perform / create_inquiry 只 flush，不 commit，由呼叫端提交。
只做提醒與追蹤，不宣告任何人符合或不符合畢業資格。
"""

from app.extensions import db
from app.models import GraduationCase
from app.services import graduation_case_service as svc
from app.services import teacher_scope

ACTIONS = ("note", "start", "close")

# action -> (允許角色, 允許起始狀態(None 表非 closed), 結果狀態, 事件, 通知對象, 原因必填)
_RULES = {
    "note": (("student", "teacher"), None, None, None, None, True),
    "start": (("student", "teacher"), ("pending",), "in_progress", "started", (), False),
    "close": (("teacher",), None, "closed", "teacher_closed", ("student",), True),
}
_ACTION_LABELS = {"note": "留言", "start": "開始處理", "close": "結案"}


class CaseActionError(Exception):
    """403 權限不足；400 狀態不允許或缺原因。"""

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def can_view(case, user):
    """學生本人、導師本班；其他（含科辦、管理員）不可看。"""
    if user is None:
        return False
    if user.role == "student":
        return case.student_id == user.id
    if user.role == "teacher":
        return teacher_scope.can_view_student(user, case.student)
    return False


def _state_ok(case, allowed_states):
    if allowed_states is None:
        return case.status != "closed"
    return case.status in allowed_states


def available_actions(case, user):
    if not can_view(case, user):
        return []
    return [name for name in ACTIONS
            if user.role in _RULES[name][0] and _state_ok(case, _RULES[name][1])]


def _recipients(case, kinds):
    people = []
    if "student" in kinds:
        people.append(case.student)
    if "teacher" in kinds:
        people.extend(svc.advisors_for(case.student))
    return people


def perform(case, user, action, note=""):
    if action not in _RULES:
        raise CaseActionError(f"案件 {case.number}：不認得的動作。", 400)
    roles, states, to_status, event_type, notify, need_note = _RULES[action]
    label = _ACTION_LABELS[action]
    if not can_view(case, user) or user.role not in roles:
        raise CaseActionError(f"案件 {case.number}：您沒有「{label}」的權限。", 403)
    if not _state_ok(case, states):
        raise CaseActionError(f"案件 {case.number}：目前狀態不能{label}。", 400)
    note = (note or "").strip()
    if need_note and not note and not (action == "close" and case.case_type == "inquiry"):
        raise CaseActionError(f"案件 {case.number}：{label}必須填寫原因（例如教務處已確認）。", 400)

    if action == "note":
        event_type = "student_note" if user.role == "student" else "teacher_note"
        notify = ("teacher",) if user.role == "student" else ("student",)
        to_status = "in_progress" if case.status == "pending" else None
        message = f"案件 {case.number} 有新留言，請查看。"
    elif action == "close" and case.case_type == "inquiry":
        message = f"案件 {case.number}：導師已回覆，這一筆詢問已處理。"
        case.close_reason = "answered"
    elif action == "close":
        message = f"案件 {case.number}：導師已結案。原因：{note}"
        case.close_reason = "teacher"
    else:
        message = f"案件 {case.number}：{label}。"
    event = svc.record_event(case, event_type, user, to_status=to_status, note=note,
                             notify=[p for p in _recipients(case, notify) if p.id != user.id],
                             message=message)
    return event


def create_inquiry(student, note):
    """學生的一般詢問：不綁特定缺口項目、不列入風險名單；通知導師。"""
    note = (note or "").strip()
    if student.role != "student":
        raise CaseActionError("只有學生可以提出詢問。", 403)
    if not note:
        raise CaseActionError("詢問必須填寫內容。", 400)
    case = GraduationCase(student_id=student.id, case_type="inquiry", item="general",
                          status="pending", open_key=None, detail=note)
    db.session.add(case)
    db.session.flush()
    svc.record_event(case, "created", student, to_status="pending", note=note,
                     notify=svc.advisors_for(student),
                     message=f"案件 {case.number}：學生提出詢問，請查看。")
    return case
