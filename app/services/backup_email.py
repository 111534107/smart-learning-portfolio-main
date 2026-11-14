"""學生綁定備用信箱（使用者 2026-11-13）：用來把備審打包寄給自己。

- 備審裡有成績與個資，所以備用信箱要先驗證：系統寄一封有連結的信，學生登入後點連結才算綁定。
- 驗證連結用 SECRET_KEY 簽章，內含使用者編號與信箱，24 小時有效；換信箱後舊連結失效。資料庫不存代碼。
- 學校信箱（users.email，由學校 Google 登入或管理員設定）不用再驗證，可以直接收。
- 操作紀錄只記動作，不記信箱。
"""
import re
from datetime import datetime, timezone

from flask import current_app
from itsdangerous import BadData, URLSafeTimedSerializer

from app.services import audit_service, email_notify

SALT = "backup-email"
MAX_AGE = 24 * 60 * 60
VERIFY_SUBJECT = "【資管科學習歷程】請確認你的備用信箱"
_ADDRESS = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class InvalidAddress(ValueError):
    """信箱格式不對；訊息給學生看。"""


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=SALT)


def make_token(user):
    return _serializer().dumps({"u": user.id, "e": user.backup_email})


def verify_path(user):
    return f"/account/backup-email/verify/{make_token(user)}"


def verify_url(user):
    base = (current_app.config.get("MAIL_SITE_URL") or "").rstrip("/")
    return f"{base}{verify_path(user)}"


def request_binding(user, address):
    """記下還沒驗證的備用信箱並寄驗證信；回傳寄信結果（sent／logged／failed）。"""
    address = (address or "").strip()
    if len(address) > 255 or not _ADDRESS.fullmatch(address):
        raise InvalidAddress("信箱格式不對，請再檢查一次。")
    user.backup_email = address
    user.backup_email_verified_at = None
    body = (f"{user.display_name} 您好：\n\n"
            "你在資管科智慧學習歷程系統填了這個信箱當備用信箱。請先登入系統，再開啟下面的連結完成確認"
            "（24 小時內有效）：\n"
            f"{verify_url(user)}\n\n"
            "如果不是你本人填的，請不要點連結，這個信箱就不會被綁定。這封信由系統自動寄出，請勿直接回覆。\n")
    status = email_notify.deliver(address, VERIFY_SUBJECT, body, user_id=user.id)
    audit_service.record(user, "user.backup_email_request", "user", user.id, {"status": status})
    return status


def verify(user, token):
    """登入的學生點驗證連結；成功回傳 True。連結過期、被改過、不是本人、信箱已換都回傳 False。"""
    try:
        data = _serializer().loads(token, max_age=MAX_AGE)
    except BadData:
        return False
    if not isinstance(data, dict) or data.get("u") != user.id or not user.backup_email \
            or data.get("e") != user.backup_email:
        return False
    user.backup_email_verified_at = datetime.now(timezone.utc)
    audit_service.record(user, "user.backup_email_verify", "user", user.id)
    return True


def remove(user):
    user.backup_email = None
    user.backup_email_verified_at = None
    audit_service.record(user, "user.backup_email_remove", "user", user.id)


def recipients(user):
    """這位學生可以收備審打包的信箱：學校信箱，以及已驗證的備用信箱。"""
    result = []
    if (user.email or "").strip():
        result.append({"key": "school", "label": "學校信箱", "address": user.email.strip()})
    if user.backup_email and user.backup_email_verified_at:
        result.append({"key": "backup", "label": "備用信箱", "address": user.backup_email})
    return result
