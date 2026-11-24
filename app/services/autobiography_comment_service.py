"""自傳段落註解（組員 111534107 提交 46531f2 的功能，依新版架構改寫，2026-11-18）。

- 導師可以在同一段留多則註解；導師和學生都能回覆，也都能標記「已處理」或改回「待處理」。
- 註解綁在「學生＋校系」上，並記住寫在第幾版：學生改出新版，舊註解照樣顯示並標出原本的版本。
- 不提供刪除；新增、回覆、標記都寫操作紀錄（紀錄裡不放註解原文）。
- 權限由呼叫端（路由）檢查：學生只能碰自己的，導師沿用 teacher_scope 的班級規則。
"""

from datetime import datetime, timezone

from flask import url_for

from app.extensions import db
from app.models import AutobiographyComment, Notification
from app.services import audit_service, autobiography_service

MAX_LENGTH = 2000


class CommentError(ValueError):
    """註解內容不合規定；訊息是給使用者看的中文。"""


def _clean(text):
    text = (text or "").strip()
    if not text:
        raise CommentError("請先輸入內容。")
    if len(text) > MAX_LENGTH:
        raise CommentError(f"內容最多 {MAX_LENGTH} 字。")
    return text


def threads(student, program, paragraphs):
    """依段落整理註解串：回傳 (各段的註解串清單, 對不上目前段落的舊註解串)。

    paragraphs：目前最新版的段落（決定要分幾段）。每串是 {"comment", "replies", "version", "original"}，
    original 是寫註解當時這一段的文字（和目前不同時才給，讓人看得出舊版段落意見在說哪一句）。
    """
    rows = (AutobiographyComment.query.filter_by(student_id=student.id, program_id=program.id)
            .order_by(AutobiographyComment.id).all())
    replies = {}
    for row in rows:
        if row.parent_id:
            replies.setdefault(row.parent_id, []).append(row)
    by_paragraph = [[] for _ in paragraphs]
    orphans = []
    for row in rows:
        if row.parent_id:
            continue
        old_paragraphs = (row.output.content_json or {}).get("paragraphs", []) if row.output else []
        old = old_paragraphs[row.paragraph] if row.paragraph < len(old_paragraphs) else {}
        current = paragraphs[row.paragraph] if row.paragraph < len(paragraphs) else None
        thread = {
            "comment": row,
            "replies": replies.get(row.id, []),
            "version": autobiography_service.version_of(row.output) if row.output else None,
            "paragraph_title": old.get("title", ""),
            "original": (old.get("text") if old.get("text") and (current is None or current.get("text") != old.get("text"))
                         else None),
        }
        (by_paragraph[row.paragraph] if current is not None else orphans).append(thread)
    return by_paragraph, orphans


def open_count(student, program):
    """還沒處理的註解串數（給導師頁、學生頁的小標示）。"""
    return AutobiographyComment.query.filter_by(student_id=student.id, program_id=program.id,
                                                parent_id=None, resolved_at=None).count()


def _student_link(program_id, paragraph):
    return url_for("student.autobiography", program_id=program_id, _anchor=f"paragraph-{paragraph}")


def _teacher_link(student_id, program_id, paragraph):
    return url_for("teacher.autobiography_latest", student_id=student_id, program_id=program_id,
                   _anchor=f"paragraph-{paragraph}")


def add_comment(teacher, student, output, paragraph, text):
    """導師在某一版的某一段新增註解，並通知學生。"""
    text = _clean(text)
    paragraphs = (output.content_json or {}).get("paragraphs", [])
    if paragraph is None or not 0 <= paragraph < len(paragraphs):
        raise CommentError("找不到這一段，請重新整理頁面。")
    program_id = output.content_json.get("program_id")
    comment = AutobiographyComment(student_id=student.id, program_id=program_id, output_id=output.id,
                                   paragraph=paragraph, author_id=teacher.id, text=text)
    db.session.add(comment)
    db.session.flush()
    title = paragraphs[paragraph].get("title") or f"第 {paragraph + 1} 段"
    db.session.add(Notification(
        recipient_id=student.id,
        message=f"{teacher.display_name}老師在你的自傳「{title}」留下註解，請查看。"[:255],
        link=_student_link(program_id, paragraph),
    ))
    audit_service.record(teacher, "autobiography.comment", "autobiography_comment", comment.id,
                         detail={"student_id": student.id, "program_id": program_id, "paragraph": paragraph})
    db.session.commit()
    return comment


def reply(actor, comment, text, notify_teacher=None):
    """回覆一則註解。學生回覆時通知留註解的導師（notify_teacher 由路由確認仍有權限才傳進來）；
    導師回覆時通知學生。"""
    text = _clean(text)
    row = AutobiographyComment(student_id=comment.student_id, program_id=comment.program_id,
                               output_id=comment.output_id, paragraph=comment.paragraph,
                               author_id=actor.id, parent_id=comment.id, text=text)
    db.session.add(row)
    db.session.flush()
    if actor.role == "student" and notify_teacher and notify_teacher.id != actor.id:
        db.session.add(Notification(
            recipient_id=notify_teacher.id,
            message=f"{actor.display_name} 回覆了你在自傳留下的註解。"[:255],
            link=_teacher_link(comment.student_id, comment.program_id, comment.paragraph),
        ))
    elif actor.role == "teacher":
        db.session.add(Notification(
            recipient_id=comment.student_id,
            message=f"{actor.display_name}老師回覆了自傳段落註解。"[:255],
            link=_student_link(comment.program_id, comment.paragraph),
        ))
    audit_service.record(actor, "autobiography.comment_reply", "autobiography_comment", comment.id,
                         detail={"student_id": comment.student_id, "reply_id": row.id})
    db.session.commit()
    return row


def set_resolved(actor, comment, resolved):
    """標記已處理，或改回待處理；誰、什麼時候標的都留著。"""
    if resolved:
        comment.resolved_at = datetime.now(timezone.utc)
        comment.resolved_by_id = actor.id
    else:
        comment.resolved_at = None
        comment.resolved_by_id = None
    audit_service.record(actor, "autobiography.comment_resolve" if resolved else "autobiography.comment_reopen",
                         "autobiography_comment", comment.id, detail={"student_id": comment.student_id})
    db.session.commit()
