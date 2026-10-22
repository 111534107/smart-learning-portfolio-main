"""缺件頁的送審時間軸與下載前提醒。"""

from app.models import CredentialRecord, LearningCourseRecord, PackageReview, Portfolio, SourceDocument


REVIEW_STATUS_TEXT = {
    "confirmed": "已確認",
    "needs_revision": "退回",
    "pending": "待確認",
}


def review_timeline(student, program):
    """依送審時間由舊到新列出同一校系的既有送審紀錄。"""
    reviews = (PackageReview.query.filter_by(student_id=student.id, rule_version_id=program.id)
               .order_by(PackageReview.requested_at, PackageReview.id).all())
    return [{
        "version": version,
        "status": review.status,
        "status_text": REVIEW_STATUS_TEXT.get(review.status, review.status),
        "requested_at": review.requested_at,
        "is_latest": version == len(reviews),
    } for version, review in enumerate(reviews, start=1)]


def download_checklist(student, program, gap, review, autobiography):
    """建立不影響下載權限的四項行前提醒。"""
    pending_learning_profile = (
        SourceDocument.query.filter(SourceDocument.owner_id == student.id,
                                    SourceDocument.status != "confirmed").count()
        + LearningCourseRecord.query.filter(LearningCourseRecord.student_id == student.id,
                                            LearningCourseRecord.confirmation_status != "confirmed").count()
        + CredentialRecord.query.filter(CredentialRecord.student_id == student.id,
                                        CredentialRecord.confirmation_status != "confirmed").count()
    )
    pending_portfolio = Portfolio.query.filter(
        Portfolio.student_id == student.id,
        ~Portfolio.status.in_(("confirmed", "submitted")),
    ).count()
    all_confirmed = pending_learning_profile == 0 and pending_portfolio == 0

    return [
        {
            "label": "資料都已確認",
            "complete": all_confirmed,
            "endpoint": "student.learning_profile" if pending_learning_profile else "student.portfolio_list",
            "params": {},
        },
        {
            "label": "導師已確認最新的一版",
            "complete": bool(review and review.status == "confirmed"),
            "href": "#review",
        },
        {
            "label": "這個校系的加權項目都有資料",
            "complete": gap["readiness"] == 100,
            "href": "#board-title",
        },
        {
            "label": "自傳已改成自己的話",
            # AI 剛產生的草稿（edited=False）不算；學生自己存過一版才算（會議 20261011-002400 #8）
            "complete": bool(autobiography and (autobiography.content_json or {}).get("edited")),
            "endpoint": "student.autobiography",
            "params": {"program_id": program.id},
        },
    ]
