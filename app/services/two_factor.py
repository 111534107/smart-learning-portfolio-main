"""雙重驗證：Authenticator 六位數驗證碼（TOTP，RFC 6238）。2026-11-09 使用者決定所有使用者都要開。

- 金鑰用 pyotp 產生，存進資料庫前用 Fernet（cryptography）加密；加密金鑰取 TWO_FACTOR_KEY，沒設就由 SECRET_KEY 推導。
- 驗證接受前後 30 秒的時間誤差；同一個時間窗的碼用過就不能再用（記在 two_factor_last_counter）。
- 備用碼 10 組，只存雜湊值，用過作廢。
- 開啟、重設、備用碼重產、驗證失敗都寫操作紀錄。
教學：docs/03_開發紀錄/01_參考與環境設定/雙重驗證_Authenticator六位數驗證碼_教學.md
"""
import base64
import hashlib
import secrets
import time
from datetime import datetime, timezone

import pyotp
import segno
from cryptography.fernet import Fernet, InvalidToken
from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models import UserBackupCode
from app.services import audit_service

BACKUP_CODE_COUNT = 10
BACKUP_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # 去掉容易看錯的 0、o、1、l、i
MAX_FAILURES = 5
LOCK_SECONDS = 15 * 60


def _now():
    return datetime.now(timezone.utc)


def _fernet():
    configured = current_app.config.get("TWO_FACTOR_KEY")
    seed = configured or f"two-factor:{current_app.config['SECRET_KEY']}"
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(seed.encode()).digest()))


def encrypt_secret(secret):
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(token):
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, AttributeError, ValueError):
        return None


def required():
    return bool(current_app.config.get("TWO_FACTOR_REQUIRED"))


SCHOOL_DOMAIN = "@stu.ukn.edu.tw"


def demo_site():
    """示範站（合成帳號）：任何帳號都不要求雙重驗證（2026-11-18 使用者決定，現場報告不能卡在掃 QR code）。"""
    return bool(current_app.config.get("LOCAL_DEMO_MODE"))


def required_for(user):
    """這個帳號是不是一定要雙重驗證：只有學校信箱 @stu.ukn.edu.tw 的帳號（2026-11-18 使用者決定）。"""
    if demo_site():
        return False
    return required() and (user.email or "").strip().lower().endswith(SCHOOL_DOMAIN)


def new_secret():
    return pyotp.random_base32()


def provisioning_uri(user, secret):
    return pyotp.TOTP(secret).provisioning_uri(name=user.username, issuer_name=current_app.config["TWO_FACTOR_ISSUER"])


def qr_svg(uri):
    """QR code 的 SVG 原始碼（segno，純 Python），直接放進頁面。"""
    return segno.make(uri, error="m").svg_inline(scale=5, border=2, dark="#1c2230", light="#ffffff")


def format_secret(secret):
    """金鑰每 4 碼空一格，方便手動輸入。"""
    return " ".join(secret[i:i + 4] for i in range(0, len(secret), 4))


def _clean(code):
    return "".join((code or "").split()).replace("-", "").lower()


def _matching_counter(secret, code, at=None):
    """有效就回傳那組碼的時間窗編號（前後各一窗），否則 None。"""
    code = _clean(code)
    if not (code.isdigit() and len(code) == 6):
        return None
    totp = pyotp.TOTP(secret)
    now = at or time.time()
    current = totp.timecode(datetime.fromtimestamp(now, timezone.utc))
    for counter in (current - 1, current, current + 1):
        if secrets.compare_digest(totp.generate_otp(counter), code):
            return counter
    return None


def _new_backup_codes(user):
    UserBackupCode.query.filter_by(user_id=user.id).delete()
    codes = []
    for _ in range(BACKUP_CODE_COUNT):
        code = "".join(secrets.choice(BACKUP_ALPHABET) for _ in range(8))
        codes.append(f"{code[:4]}-{code[4:]}")
        db.session.add(UserBackupCode(user_id=user.id, code_hash=generate_password_hash(code)))
    return codes


def enable(user, secret, code):
    """用使用者輸入的第一組碼確認金鑰正確後開啟；回傳 10 組備用碼（只顯示這一次）。不正確回傳 None。"""
    counter = _matching_counter(secret, code)
    if counter is None:
        return None
    user.two_factor_secret = encrypt_secret(secret)
    user.two_factor_enabled_at = _now()
    user.two_factor_last_counter = counter
    codes = _new_backup_codes(user)
    audit_service.record(user, "two_factor.enable", "user", user.id)
    return codes


def verify(user, code):
    """登入第二步：六位數或備用碼。成功回傳 "totp" 或 "backup"，失敗回傳 None。"""
    secret = decrypt_secret(user.two_factor_secret) if user.two_factor_secret else None
    if secret:
        counter = _matching_counter(secret, code)
        if counter is not None and counter > (user.two_factor_last_counter or -1):
            user.two_factor_last_counter = counter
            return "totp"
    cleaned = _clean(code)
    if len(cleaned) == 8:
        for row in UserBackupCode.query.filter_by(user_id=user.id, used_at=None):
            if check_password_hash(row.code_hash, cleaned):
                row.used_at = _now()
                audit_service.record(user, "two_factor.backup_code", "user", user.id)
                return "backup"
    return None


def remaining_backup_codes(user):
    return UserBackupCode.query.filter_by(user_id=user.id, used_at=None).count()


def regenerate_backup_codes(user):
    codes = _new_backup_codes(user)
    audit_service.record(user, "two_factor.backup_regenerate", "user", user.id)
    return codes


def reset(user, actor, reason="admin"):
    """管理員重設或伺服器指令重設：清掉金鑰與備用碼，對方下次登入要重新設定。"""
    user.two_factor_secret = None
    user.two_factor_enabled_at = None
    user.two_factor_last_counter = None
    UserBackupCode.query.filter_by(user_id=user.id).delete()
    audit_service.record(actor, "two_factor.reset", "user", user.id, detail={"by": reason})


def record_failure(user):
    audit_service.record(user, "two_factor.failed", "user", user.id)
