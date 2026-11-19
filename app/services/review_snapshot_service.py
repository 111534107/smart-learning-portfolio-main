"""導師確認備審（規格 10.3、10.4）：送審時存快照，確認與撤回都寫操作紀錄。

- 學生按「請導師確認」：把當下的事實清單、自傳版本、完成度存進 PackageReview.snapshot_json。
  還在等導師時再按一次，會更新同一筆的快照；導師確認過或請學生修改後再送，會新增一筆。
- 導師確認的是那一份快照；學生之後再改資料，快照不變（舊的確認紀錄保留）。
- 確認、請學生修改、撤回確認都寫進 audit_logs，撤回要填原因；紀錄裡不放學生原文。
- 送審後自傳又存了新版：不能確認（要請學生重新送審），仍可「需要修改」（2026-11-18 併入組員 46531f2）。
"""

from datetime import datetime, timezone

from app.extensions import db
from app.models import AuditLog, LearningProfileOutput, Notification, PackageReview
from app.services import audit_service, autobiography_service, package_export, package_zip, teacher_scope
from app.services.gap_service import analyze_gap
from app.services.package_service import latest_review


def build_snapshot(student, program, *, taken_at=None):
    draft = autobiography_service.latest_draft(student, program)
    evidence_package = autobiography_service.build_evidence_package(student, program)
    return {
        "facts": evidence_package["items"],
        "evidence_package": evidence_package,
        "autobiography": ({"output_id": draft.id, "version": autobiography_service.version_of(draft)}
                          if draft else None),
        "readiness": analyze_gap(student, program)["readiness"],
        "program": {"id": program.id, "school_name": program.school_name, "department_name": program.department_name},
        "taken_at": taken_at or datetime.now(timezone.utc).isoformat(),
    }


def review_teachers(student):
    """取得學生目前學年度的啟用中班導。"""
    return teacher_scope.teachers_for_student(student)


def request_review(student, program):
    """學生送審；回傳這次的 PackageReview。"""
    snapshot = build_snapshot(student, program)
    autobiography = snapshot["autobiography"]
    draft = db.session.get(LearningProfileOutput, autobiography["output_id"]) if autobiography else None
    archive, manifest = package_zip.render_zip(student, program, draft, "confirmed")
    db.session.expire_all()
    if snapshot != build_snapshot(student, program, taken_at=snapshot["taken_at"]):
        raise ReviewChanged("changed", NOTICES["changed"])
    export = package_export.save(student.id, archive, manifest, package_zip.download_name(program))
    snapshot["export"] = export
    previous_export = None
    student_id = student.id
    try:
        review = latest_review(student, program)
        fields = {"snapshot_json": snapshot, "readiness_percent": snapshot["readiness"],
                  "requested_at": datetime.now(timezone.utc)}
        if review and review.status == "pending":
            previous_export = (review.snapshot_json or {}).get("export")
            _update_review(review, **fields)
        else:
            review = PackageReview(student_id=student_id, rule_version_id=program.id, status="pending", **fields)
            db.session.add(review)
        db.session.flush()
        audit_service.record(student, "package_review.request", "package_review", review.id,
                             detail={"program_id": program.id})
        for teacher in review_teachers(student):
            db.session.add(Notification(
                recipient_id=teacher.id,
                message=f"{student.display_name} 已送出 {program.school_name} {program.department_name} 的備審資料，請確認。"[:255],
                link=f"/teacher/students/{student.id}#teacher-target-{program.id}",
            ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        package_export.discard(student_id, export)
        raise
    if previous_export:
        package_export.discard(student_id, previous_export)
    return review


# 送審過的經歷不能刪（規格 M10）；學生看到的說明
LOCKED_MESSAGE = "這筆已經送導師確認，不能刪除；如果內容有誤，請修改後再送一次。"


def submitted_portfolio_ids(student_id):
    """出現在這位學生任何一份送審快照裡的經歷編號（不論導師確認了沒有）。"""
    ids = set()
    for review in PackageReview.query.filter_by(student_id=student_id):
        for fact in (review.snapshot_json or {}).get("facts", []):
            kind, _, value = str(fact.get("evidence_id", "")).partition(":")
            if kind == "portfolio" and value.isdigit():
                ids.add(int(value))
    return ids


def is_submitted(portfolio):
    """經歷送審過（導師確認快照，或舊流程的 PortfolioSubmission）就不能刪；它的佐證也一樣。"""
    return bool(portfolio.submissions) or portfolio.id in submitted_portfolio_ids(portfolio.student_id)


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
    "autobiography_changed": "學生送審後自傳又存了新版本，不能確認舊的那份；請選「需要修改」請學生重新送審。",
    "export_unavailable": "此版本的送審檔案無法讀取。請選「需要修改」，請學生重新送審後再確認。",
}


def autobiography_changed(review):
    """送審後自傳有沒有存出新版（組員 46531f2）：快照記的版本不是目前最新版就算。"""
    submitted = ((review.snapshot_json or {}).get("autobiography") or {}).get("output_id")
    latest = autobiography_service.latest_draft(review.student, review.program)
    return submitted != (latest.id if latest else None)


def _check_latest(review):
    newest = latest_review(review.student, review.program)
    if newest and newest.id != review.id:
        raise ReviewChanged("newer", NOTICES["newer"])


def _update_review(review, **fields):
    # 資料庫同時核對狀態與快照時間，避免更新送審和導師決定互相覆蓋。
    taken_at = (review.snapshot_json or {}).get("taken_at")
    updated = PackageReview.query.filter(
        PackageReview.id == review.id,
        PackageReview.status == review.status,
        PackageReview.snapshot_json["taken_at"].as_string() == taken_at,
    ).update(fields, synchronize_session=False)
    if updated != 1:
        raise ReviewChanged("changed", NOTICES["changed"])
    db.session.refresh(review)


def decide(review, teacher, decision, comment, seen_taken_at=None, autobiography_viewed=None):
    """導師確認（confirmed）或請學生修改（needs_revision）。

    seen_taken_at：導師頁面上看到的快照時間。學生在導師開頁後又更新送審時會不一樣，就擋下來，
    避免導師確認到自己沒看過的內容。
    """
    if review.status != "pending":
        raise ReviewChanged("done", NOTICES["done"])
    _check_latest(review)
    if (review.snapshot_json or {}).get("taken_at", "") != (seen_taken_at or ""):
        raise ReviewChanged("changed", NOTICES["changed"])
    if decision == "confirmed" and autobiography_changed(review):
        raise ReviewChanged("autobiography_changed", NOTICES["autobiography_changed"])
    if decision == "confirmed" and not package_export.submission_archive_available(review):
        raise ReviewChanged("export_unavailable", NOTICES["export_unavailable"])
    # 導師自己選有沒有看自傳；只記是／否，不存自傳內容。沒有勾選就是「未檢視」，不擋任何流程
    _update_review(review, status=decision, comment=comment or None,
                   autobiography_viewed=bool(autobiography_viewed), teacher_id=teacher.id,
                   reviewed_at=datetime.now(timezone.utc))
    _log(teacher, "package_review.confirm" if decision == "confirmed" else "package_review.needs_revision", review,
         autobiography_viewed=review.autobiography_viewed)
    result = "已確認" if decision == "confirmed" else "建議修改"
    db.session.add(Notification(
        recipient_id=review.student_id,
        message=f"導師{result}你送審的 {review.program.school_name} {review.program.department_name} 備審資料。"[:255],
        link=f"/student/package-reviews/{review.id}/result",
    ))
    db.session.commit()


def withdraw(review, teacher, reason):
    """導師按錯時撤回確認：回到等待確認，原本的確認紀錄保留在 audit_logs。"""
    if review.status != "confirmed":
        raise ValueError("這份送審還沒有被確認，不需要撤回。")
    if not reason:
        raise ValueError("撤回確認時，請寫下原因。")
    _check_latest(review)  # 學生已經送了新的一筆時，不能再把舊的改回等待中（會變成兩筆等待確認）
    _update_review(review, status="pending", teacher_id=teacher.id, reviewed_at=datetime.now(timezone.utc))
    _log(teacher, "package_review.withdraw", review, reason=reason[:500])
    db.session.commit()


def confirmed_label(review):
    """學生端看到的確認狀態文字：導師有沒有看自傳。舊資料（沒記錄）只寫「導師已確認」。"""
    if review is None or review.status != "confirmed":
        return None
    if review.autobiography_viewed is None:
        return "導師已確認"
    return "導師已確認（已檢視自傳）" if review.autobiography_viewed else "導師已確認（未檢視自傳）"
