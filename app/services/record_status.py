"""學習歷程清單共用的三態判斷。"""


def portfolio_state(record):
    """回傳活動與經歷的顯示狀態。"""
    if record.status != "confirmed":
        return "draft"
    if record.source != "student" or record.evidence_items:
        return "confirmed"
    return "pending-source"


def learning_profile_state(record):
    """回傳來源文件、成績或證照的顯示狀態。"""
    if getattr(record, "status", None) == "confirmed":
        return "confirmed"
    if getattr(record, "confirmation_status", None) == "confirmed":
        return "confirmed"
    source_document = getattr(record, "source_document", None)
    if source_document and source_document.status == "confirmed":
        return "confirmed"
    return "draft"
