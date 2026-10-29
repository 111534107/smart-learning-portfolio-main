"""操作紀錄（規格 M11）：登入、確認、送審、刪除、上傳、目標校系、自傳都寫進 audit_logs。

只記「誰、做了什麼、對哪一類的第幾筆」。不記內容與個資：不放學生姓名、學號、經歷標題、
檔名或自傳文字；detail 只放代碼（例如文件種類），不放使用者打的字。
"""

from flask import has_request_context, request

from app.extensions import db
from app.models import AuditLog

# 管理者「操作紀錄」頁顯示的中文名稱；新動作記得補一筆
ACTION_LABELS = {
    "student.login": "學生登入",
    "user.login": "教職員登入",
    "student.welcome_done": "看完歡迎頁",
    "portfolio.confirm": "確認經歷",
    "portfolio.delete": "刪除經歷",
    "portfolio.delete_blocked": "刪除經歷被擋下（已送審）",
    "evidence.upload": "上傳佐證",
    "evidence.delete": "刪除佐證",
    "evidence.delete_blocked": "刪除佐證被擋下（已送審）",
    "learning_profile.document_upload": "上傳成績單或證照",
    "learning_profile.document_confirm": "確認 OCR 擷取結果",
    "student_target.add": "設定目標校系",
    "student_target.remove": "取消目標校系",
    "package_review.request": "送導師確認",
    "package_review.confirm": "導師確認",
    "package_review.needs_revision": "導師請學生修改",
    "package_review.withdraw": "導師撤回確認",
    "autobiography.generate": "產生自傳",
    "autobiography.save": "儲存自傳",
    "autobiography.teacher_edit": "導師修改自傳",
}


def record(actor, action, target_type=None, target_id=None, detail=None, commit=False):
    """加一筆操作紀錄。commit=False 時跟著呼叫端的交易一起存。"""
    db.session.add(AuditLog(
        user_id=actor.id if actor else None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        ip_address=request.remote_addr if has_request_context() else None,
        detail_json=detail,
    ))
    if commit:
        db.session.commit()


def label(action):
    return ACTION_LABELS.get(action, action)
