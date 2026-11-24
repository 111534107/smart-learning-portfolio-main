"""電子郵件通知（2026-11-12）：跟站內通知同一個時機寄出。

- SMTP 設定放 .env（MAIL_SMTP_HOST、MAIL_SMTP_PORT、MAIL_SMTP_USER、MAIL_SMTP_PASSWORD、MAIL_SENDER）。
  主機或寄件人沒設定、或是自動化測試（TESTING）／本機展示站（LOCAL_DEMO_MODE）時，**不寄信**，
  只寫到記錄檔（logger）與操作紀錄，狀態記為 logged。
- 管理員可全域關閉（system_settings 的 email_notify_enabled）；學生、導師在帳號設定各自關閉（users.email_notify）。
- 寄信失敗會重試（MAIL_RETRIES 次），最後仍失敗只記錄，不丟出例外，頁面照常。
- 每封信寫一筆操作紀錄 email.notify：收件者用使用者編號（target_id），detail 記主旨、種類、結果；
  依操作紀錄規則不記信箱與內容。
- 信件內容只寫「有新的提醒，請登入查看」與系統連結，不放成績、缺口數字、案件細節。
"""

import logging
import smtplib
import time
from email.message import EmailMessage

from flask import current_app, has_request_context, request

from app.extensions import db
from app.models import SystemSetting
from app.services import audit_service

logger = logging.getLogger(__name__)

SETTING_KEY = "email_notify_enabled"
SUBJECT = "【資管科學習歷程】有新的提醒"
KIND_LABELS = {
    "graduation_case": "畢業缺口案件",
    "semester_warning": "各學期預警",
    "check_countdown": "畢業檢核日期倒數",
}


def globally_enabled():
    row = SystemSetting.query.filter_by(key=SETTING_KEY).first()
    return row is None or row.value != "false"


def set_globally_enabled(enabled, actor):
    row = SystemSetting.query.filter_by(key=SETTING_KEY).first()
    if row is None:
        row = SystemSetting(key=SETTING_KEY, value="true")
        db.session.add(row)
    row.value = "true" if enabled else "false"
    row.updated_by_id = actor.id if actor else None
    audit_service.record(actor, "email.settings", "system_setting", None, {"enabled": bool(enabled)})


def smtp_ready():
    """有 SMTP 主機與寄件人、而且不是測試或展示站，才真的寄信。"""
    cfg = current_app.config
    if cfg.get("TESTING") or cfg.get("LOCAL_DEMO_MODE"):
        return False
    return bool(cfg.get("MAIL_SMTP_HOST") and cfg.get("MAIL_SENDER"))


def site_url():
    """信裡連結用的系統網址（結尾沒有 /）。

    先用 .env 的 MAIL_SITE_URL；沒設時改用這次請求的網址（B30，2026-11-16：之前沒設就變成相對路徑，學生點不到）。
    經過 Cloudflare 等通道時，請求本身是 http，依 X-Forwarded-Proto 改回 https。都拿不到才回傳空字串。
    """
    base = (current_app.config.get("MAIL_SITE_URL") or "").strip().rstrip("/")
    if base or not has_request_context():
        return base
    base = request.host_url.rstrip("/")
    if request.headers.get("X-Forwarded-Proto", "").split(",")[0].strip() == "https" and base.startswith("http://"):
        base = "https://" + base[len("http://"):]
    return base


def build_body(user, kind):
    base = site_url()
    link = f"{base}/notifications" if base else "/notifications（請從系統首頁登入）"
    label = KIND_LABELS.get(kind, "系統通知")
    return (f"{user.display_name} 您好：\n\n"
            f"資管科智慧學習歷程系統有新的提醒（{label}），請登入查看。\n"
            f"{link}\n\n"
            "這封信由系統自動寄出，請勿直接回覆。不想收到可在系統的「帳號設定」關閉電子郵件通知。\n")


def _send(to_address, subject, body, attachments=()):
    """attachments：[(檔名, bytes, MIME 類型)]。"""
    cfg = current_app.config
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["MAIL_SENDER"]
    msg["To"] = to_address
    msg.set_content(body)
    for filename, data, mime_type in attachments:
        maintype, _, subtype = (mime_type or "application/octet-stream").partition("/")
        msg.add_attachment(data, maintype=maintype, subtype=subtype or "octet-stream", filename=filename)
    port = int(cfg.get("MAIL_SMTP_PORT") or 587)
    timeout = int(cfg.get("MAIL_TIMEOUT") or 10)
    if cfg.get("MAIL_USE_SSL"):
        server = smtplib.SMTP_SSL(cfg["MAIL_SMTP_HOST"], port, timeout=timeout)
    else:
        server = smtplib.SMTP(cfg["MAIL_SMTP_HOST"], port, timeout=timeout)
    with server:
        if not cfg.get("MAIL_USE_SSL") and cfg.get("MAIL_USE_TLS", True):
            server.starttls()
        if cfg.get("MAIL_SMTP_USER"):
            server.login(cfg["MAIL_SMTP_USER"], cfg.get("MAIL_SMTP_PASSWORD") or "")
        server.send_message(msg)


def deliver(to_address, subject, body, attachments=(), user_id=None):
    """學生自己要求寄的信（驗證備用信箱、備審打包）：寄到指定信箱，可帶附件。

    回傳 sent／logged（沒有設定 SMTP，只記錄不寄）／failed。不看通知開關（那是給自動提醒用的），
    也不寫操作紀錄：由呼叫的功能自己記，而且不記信箱與內容。任何錯誤都不往外丟。
    """
    if not smtp_ready():
        logger.info("[電子郵件未寄出：沒有設定 SMTP] 使用者 %s，主旨：%s，附件 %s 個", user_id, subject, len(attachments))
        return "logged"
    retries = max(0, int(current_app.config.get("MAIL_RETRIES", 2)))
    for attempt in range(retries + 1):
        try:
            if attachments:
                _send(to_address, subject, body, attachments)
            else:
                _send(to_address, subject, body)
            return "sent"
        except Exception as exc:  # SMTP 連不上、帳密錯、逾時、附件被拒
            logger.warning("寄信失敗（使用者 %s，第 %s 次）：%s", user_id, attempt + 1, type(exc).__name__)
            if attempt < retries:
                time.sleep(float(current_app.config.get("MAIL_RETRY_DELAY", 1)))
    return "failed"


def notify(user, kind):
    """對一位使用者寄一封提醒信；回傳結果字串。任何錯誤都不往外丟。"""
    try:
        return _notify(user, kind)
    except Exception:  # 郵件是附帶動作，不能讓頁面或同步失敗
        logger.exception("電子郵件通知處理失敗（使用者 %s）", getattr(user, "id", None))
        return "failed"


def _notify(user, kind):
    if not globally_enabled():
        return "disabled"
    if not getattr(user, "email_notify", True):
        return "opted_out"
    address = (user.email or "").strip()
    if not address:
        return "no_email"
    body = build_body(user, kind)
    detail = {"kind": kind, "subject": SUBJECT}
    if not smtp_ready():
        logger.info("[電子郵件未寄出：沒有設定 SMTP] 收件者使用者 %s，主旨：%s\n%s", user.id, SUBJECT, body)
        detail["status"] = "logged"
        audit_service.record(None, "email.notify", "user", user.id, detail)
        return "logged"
    retries = max(0, int(current_app.config.get("MAIL_RETRIES", 2)))
    error = None
    for attempt in range(retries + 1):
        try:
            _send(address, SUBJECT, body)
            detail.update(status="sent", attempts=attempt + 1)
            audit_service.record(None, "email.notify", "user", user.id, detail)
            return "sent"
        except Exception as exc:  # SMTP 連不上、帳密錯、逾時
            error = type(exc).__name__
            logger.warning("寄信失敗（使用者 %s，第 %s 次）：%s", user.id, attempt + 1, error)
            if attempt < retries:
                time.sleep(float(current_app.config.get("MAIL_RETRY_DELAY", 1)))
    detail.update(status="failed", attempts=retries + 1, error=error)
    audit_service.record(None, "email.notify", "user", user.id, detail)
    return "failed"
