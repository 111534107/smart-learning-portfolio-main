"""導師「建議修改」：新增、列出、學生接受或不接受。

- 導師權限由呼叫端（路由）依 teacher_scope 檢查；這裡只檢查內容與狀態。
- 接受＝把原文換成建議文字，存成學生自己的新版本（舊版保留）；原文已經被改掉就標成「過期」，請學生自己看著改。
- 新增與處理都寫操作紀錄（紀錄裡不放自傳原文與建議全文，只放編號與長度）。
"""

from datetime import datetime, timezone

from flask import url_for

from app.extensions import db
from app.models import AutobiographySuggestion, Notification
from app.services import audit_service, autobiography_service

MAX_REPLACEMENT = 1000
MAX_SELECTION = 500


class SuggestionError(ValueError):
    """建議不合規定或不能處理；訊息是給使用者看的中文。"""


def add(teacher, student, output, paragraph, start, end, replacement):
    """導師對某一版的某一段選取文字提出替換；回傳建議。"""
    paragraphs = (output.content_json or {}).get("paragraphs", [])
    if paragraph is None or not 0 <= paragraph < len(paragraphs):
        raise SuggestionError("找不到這一段，請重新整理頁面。")
    text = paragraphs[paragraph].get("text", "")
    if start is None or end is None or not 0 <= start < end <= len(text):
        raise SuggestionError("請先在這一段選取要修改的文字。")
    if end - start > MAX_SELECTION:
        raise SuggestionError(f"一次最多選取 {MAX_SELECTION} 字。")
    replacement = (replacement or "").strip()
    if not replacement:
        raise SuggestionError("請輸入建議改成的文字。")
    if len(replacement) > MAX_REPLACEMENT:
        raise SuggestionError(f"建議文字最多 {MAX_REPLACEMENT} 字。")
    program_id = output.content_json.get("program_id")
    suggestion = AutobiographySuggestion(
        student_id=student.id, program_id=program_id, output_id=output.id, paragraph=paragraph,
        start=start, end=end, original=text[start:end], replacement=replacement, author_id=teacher.id)
    db.session.add(suggestion)
    db.session.flush()
    title = paragraphs[paragraph].get("title") or f"第 {paragraph + 1} 段"
    db.session.add(Notification(
        recipient_id=student.id,
        message=f"{teacher.display_name}老師在你的自傳「{title}」提出建議修改，請查看並決定要不要接受。"[:255],
        link=url_for("student.autobiography", program_id=program_id, _anchor=f"paragraph-{paragraph}")))
    audit_service.record(teacher, "autobiography.suggest", "autobiography_suggestion", suggestion.id,
                         detail={"student_id": student.id, "program_id": program_id, "paragraph": paragraph,
                                 "chars": end - start})
    db.session.commit()
    return suggestion


def pending(student, program_id):
    return (AutobiographySuggestion.query.filter_by(student_id=student.id, program_id=program_id, status="pending")
            .order_by(AutobiographySuggestion.paragraph, AutobiographySuggestion.start).all())


def for_paragraphs(student, program_id, count):
    """依段落整理待處理的建議，給編輯畫面標在文字旁（回傳長度 count 的串列）。"""
    result = [[] for _ in range(count)]
    for item in pending(student, program_id):
        if item.paragraph < count:
            result[item.paragraph].append(item)
    return result


def _mine(student, suggestion_id):
    suggestion = db.session.get(AutobiographySuggestion, suggestion_id)
    if suggestion is None or suggestion.student_id != student.id:
        raise SuggestionError("找不到這則建議。")
    if suggestion.status != "pending":
        raise SuggestionError("這則建議已經處理過了。")
    return suggestion


def accept(student, suggestion_id):
    """學生接受建議：把原文換成建議文字，存成新的一版；回傳新版。"""
    suggestion = _mine(student, suggestion_id)
    latest = _latest(student, suggestion.program_id)
    paragraphs = [dict(p) for p in latest.content_json.get("paragraphs", [])]
    if suggestion.paragraph >= len(paragraphs):
        return _stale(suggestion, student)
    text = paragraphs[suggestion.paragraph].get("text", "")
    start = suggestion.start if text[suggestion.start:suggestion.end] == suggestion.original else None
    if start is None and text.count(suggestion.original) == 1:
        start = text.index(suggestion.original)  # 前面別處改過導致位置位移，但這句還在、只有一處
    if start is None:
        return _stale(suggestion, student)
    texts = [p.get("text", "") for p in paragraphs]
    texts[suggestion.paragraph] = text[:start] + suggestion.replacement + text[start + len(suggestion.original):]
    new_output = autobiography_service.save_edits(latest, texts, student)
    suggestion.status = "accepted"
    suggestion.resolved_at = datetime.now(timezone.utc)
    suggestion.resolved_by_id = student.id
    suggestion.result_output_id = new_output.id
    audit_service.record(student, "autobiography.suggestion_accept", "autobiography_suggestion", suggestion.id,
                         detail={"program_id": suggestion.program_id})
    db.session.commit()
    return new_output


def reject(student, suggestion_id):
    suggestion = _mine(student, suggestion_id)
    suggestion.status = "rejected"
    suggestion.resolved_at = datetime.now(timezone.utc)
    suggestion.resolved_by_id = student.id
    audit_service.record(student, "autobiography.suggestion_reject", "autobiography_suggestion", suggestion.id,
                         detail={"program_id": suggestion.program_id})
    db.session.commit()
    return suggestion


def _latest(student, program_id):
    from app.models import LearningProfileOutput
    outputs = (LearningProfileOutput.query.filter_by(student_id=student.id, output_type=autobiography_service.OUTPUT_TYPE)
               .order_by(LearningProfileOutput.id.desc()).all())
    return next(o for o in outputs if (o.content_json or {}).get("program_id") == program_id)


def _stale(suggestion, student):
    suggestion.status = "stale"
    suggestion.resolved_at = datetime.now(timezone.utc)
    suggestion.resolved_by_id = student.id
    db.session.commit()
    raise SuggestionError("這句話已經改過了，沒辦法直接套用建議；可以對照導師的建議自己修改。")
