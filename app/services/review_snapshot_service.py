"""導師確認備審（規格 10.3、10.4）：送審時存快照，確認與撤回都寫操作紀錄。

- 學生按「請導師確認」：把當下的事實清單、自傳版本、完成度存進 PackageReview.snapshot_json。
  還在等導師時再按一次，會更新同一筆的快照；導師確認過或請學生修改後再送，會新增一筆。
- 導師確認的是那一份快照；學生之後再改資料，快照不變（舊的確認紀錄保留）。
- 確認、請學生修改、撤回確認都寫進 audit_logs，撤回要填原因；紀錄裡不放學生原文。
"""

from datetime import datetime, timezone

from app.extensions import db
from app.models import AuditLog, PackageReview
from app.services import autobiography_service
from app.services.gap_service import analyze_gap
from app.services.package_service import latest_review


def build_snapshot(student, program):
    draft = autobiography_service.latest_draft(student, program)
    evidence_package = autobiography_service.build_evidence_package(student, program)
    return {
        "facts": evidence_package["items"],
        "evidence_package": evidence_package,
        "autobiography": ({"output_id": draft.id, "version": autobiography_service.version_of(draft)}
                          if draft else None),
        "readiness": analyze_gap(student, program)["readiness"],
        "program": {"id": program.id, "school_name": program.school_name, "department_name": program.department_name},
        "taken_at": datetime.now(timezone.utc).isoformat(),
    }


def request_review(student, program):
    """學生送審；回傳這次的 PackageReview。"""
    snapshot = build_snapshot(student, program)
    review = latest_review(student, program)
    if not review or review.status != "pending":
        review = PackageReview(student_id=student.id, rule_version_id=program.id, status="pending")
        db.session.add(review)
    review.snapshot_json = snapshot
    review.readiness_percent = snapshot["readiness"]
    review.requested_at = datetime.now(timezone.utc)
    db.session.commit()
    return review


def snapshot_diff(new, old):
    """兩份快照的事實差異：新增了哪些、少了哪些（比較文字）。"""
    new_texts = [fact["text"] for fact in (new or {}).get("facts", [])]
    old_texts = [fact["text"] for fact in (old or {}).get("facts", [])]
    return {
        "added": [text for text in new_texts if text not in old_texts],
        "removed": [text for text in old_texts if text not in new_texts],
    }


def previous_confirmed(review):
    """同一位學生、同一個校系，在這次之前最近一次導師確認的送審。"""
    return (PackageReview.query.filter(
        PackageReview.student_id == review.student_id,
        PackageReview.rule_version_id == review.rule_version_id,
        PackageReview.status == "confirmed",
        PackageReview.id < review.id,
    ).order_by(PackageReview.id.desc()).first())


def confirmed_facts(student, program):
    """最近一次導師確認的快照事實；給 AI 與導師摘要引用。沒有確認過回傳 None。"""
    review = (PackageReview.query.filter_by(student_id=student.id, rule_version_id=program.id, status="confirmed")
              .order_by(PackageReview.id.desc()).first())
    return review.snapshot_json.get("facts", []) if review and review.snapshot_json else None


def _log(actor, action, review, **detail):
    db.session.add(AuditLog(user_id=actor.id, action=action, target_type="package_review", target_id=review.id,
                            detail_json={"student_id": review.student_id, "program_id": review.rule_version_id,
                                         "status": review.status, **detail}))


class ReviewChanged(ValueError):
    """導師要處理的送審已經處理過、有更新的一筆，或學生剛更新了內容。訊息是給導師看的中文。"""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


# 導師頁用代碼顯示提示（不把網址裡的文字直接放進頁面）
NOTICES = {
    "done": "這份送審已經處理過了，請重新整理頁面。",
    "newer": "學生已經送出新的送審，這一筆不能再變更，請處理最新的那一筆。",
    "changed": "學生剛更新了送審內容，請先看新的內容再確認。",
}


def _check_latest(review):
    newest = latest_review(review.student, review.program)
    if newest and newest.id != review.id:
        raise ReviewChanged("newer", NOTICES["newer"])


def decide(review, teacher, decision, comment, seen_taken_at=None):
    """導師確認（confirmed）或請學生修改（needs_revision）。

    seen_taken_at：導師頁面上看到的快照時間。學生在導師開頁後又更新送審時會不一樣，就擋下來，
    避免導師確認到自己沒看過的內容。
    """
    if review.status != "pending":
        raise ReviewChanged("done", NOTICES["done"])
    _check_latest(review)
    if (review.snapshot_json or {}).get("taken_at", "") != (seen_taken_at or ""):
        raise ReviewChanged("changed", NOTICES["changed"])
    review.status = decision
    review.comment = comment or None
    review.teacher_id = teacher.id
    review.reviewed_at = datetime.now(timezone.utc)
    _log(teacher, "package_review.confirm" if decision == "confirmed" else "package_review.needs_revision", review)
    db.session.commit()


def withdraw(review, teacher, reason):
    """導師按錯時撤回確認：回到等待確認，原本的確認紀錄保留在 audit_logs。"""
    if review.status != "confirmed":
        raise ValueError("這份送審還沒有被確認，不需要撤回。")
    if not reason:
        raise ValueError("撤回確認時，請寫下原因。")
    _check_latest(review)  # 學生已經送了新的一筆時，不能再把舊的改回等待中（會變成兩筆等待確認）
    review.status = "pending"
    review.teacher_id = teacher.id
    review.reviewed_at = datetime.now(timezone.utc)
    _log(teacher, "package_review.withdraw", review, reason=reason[:500])
    db.session.commit()
