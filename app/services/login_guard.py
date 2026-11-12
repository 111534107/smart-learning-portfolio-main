"""登入錯誤次數限制（2026-11-12，比照管理員登入頁 2026-11-10 的規則）。

- 密碼：只用在管理員登入頁（同一個帳號或同一個 IP，15 分鐘內錯 5 次鎖 15 分鐘）。
  學生與教職員頁不鎖：學號容易被別人知道，鎖帳號等於讓任何人都能把同學擋在外面（使用者 2026-11-12 決定）。
- 雙重驗證（六位數驗證碼）：同一個帳號錯 5 次鎖 15 分鐘。
- 次數全部從操作紀錄（audit_logs，資料庫）算，清掉瀏覽器 Cookie 也不會重算。
- 登入成功、或管理員在帳號管理按「解除鎖定」之後，之前的錯誤不再計入。
- 鎖定（account.locked）與解鎖（account.unlocked）都寫進操作紀錄。
"""
from datetime import datetime, timedelta, timezone

from flask import request

from app.extensions import db
from app.models import AuditLog, User
from app.services import audit_service

MAX_FAILURES = 5
LOCK_MINUTES = 15
IP_LIMITS = {"admin": 5, "student": 30, "staff": 30}
PASSWORD_ACTIONS = {"admin": "admin.login_failed", "student": "student.login_failed", "staff": "staff.login_failed"}
TWO_FACTOR_ACTION = "two_factor.failed"
LOCKED_ACTION = "account.locked"
UNLOCKED_ACTION = "account.unlocked"
SUCCESS_ACTIONS = ("student.login", "user.login")
SCAN_LIMIT = 500


def _now():
    return datetime.now(timezone.utc)


def _aware(moment):
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _recent(actions):
    since = _now() - timedelta(minutes=LOCK_MINUTES)
    rows = (AuditLog.query.filter(AuditLog.action.in_(actions))
            .order_by(AuditLog.id.desc()).limit(SCAN_LIMIT).all())
    return [row for row in rows if _aware(row.created_at) >= since]


def _username(row):
    return (row.detail_json or {}).get("username")


def _reset_id(username):
    """這個帳號最近一次「登入成功」或「被解鎖」的紀錄編號；之前的錯誤不算。"""
    user = User.query.filter_by(username=username).first() if username else None
    newest = 0
    unlock = (AuditLog.query.filter_by(action=UNLOCKED_ACTION).order_by(AuditLog.id.desc()).limit(50).all())
    newest = max([row.id for row in unlock if _username(row) == username] or [0])
    if user is not None:
        success = (AuditLog.query.filter(AuditLog.user_id == user.id, AuditLog.action.in_(SUCCESS_ACTIONS))
                   .order_by(AuditLog.id.desc()).first())
        if success:
            newest = max(newest, success.id)
    return newest


def _account_failures(rows, username, user_id=None):
    reset = _reset_id(username)
    return [row for row in rows if row.id > reset
            and (_username(row) == username or (user_id is not None and row.user_id == user_id))]


def _wait_minutes(failures):
    """最早那一筆（第 N 筆裡最舊的）滿 15 分鐘就解鎖。"""
    oldest = min(_aware(row.created_at) for row in failures[:MAX_FAILURES])
    remaining = oldest + timedelta(minutes=LOCK_MINUTES) - _now()
    return max(1, -(-int(remaining.total_seconds()) // 60))


# ---------- 密碼 ----------

def password_status(portal, username):
    """回傳 (被鎖住了嗎, 還要等幾分鐘)。"""
    rows = _recent([PASSWORD_ACTIONS[portal]])
    mine = _account_failures(rows, username)
    if len(mine) >= MAX_FAILURES:
        return True, _wait_minutes(mine)
    ip = request.remote_addr
    by_ip = [row for row in rows if row.ip_address == ip]
    if len(by_ip) >= IP_LIMITS[portal]:
        return True, _wait_minutes(by_ip[:IP_LIMITS[portal]][-MAX_FAILURES:])
    return False, 0


def record_password_failure(portal, username):
    """記一次密碼錯誤；回傳還能試幾次（0 表示這次之後就鎖了）。"""
    username = (username or "")[:100]
    audit_service.record(None, PASSWORD_ACTIONS[portal], detail={"username": username})
    db.session.flush()
    mine = _account_failures(_recent([PASSWORD_ACTIONS[portal]]), username)
    left = MAX_FAILURES - len(mine)
    if left <= 0 and len(mine) == MAX_FAILURES:
        user = User.query.filter_by(username=username).first()
        audit_service.record(None, LOCKED_ACTION, "user", user.id if user else None,
                             detail={"username": username, "kind": "password", "portal": portal})
    db.session.commit()
    return max(0, left)


def locked_message(minutes):
    return f"密碼錯太多次，這個帳號暫時鎖住了。請 {minutes} 分鐘後再試，或請系統管理員解除鎖定。"


def wrong_password_message(left):
    if left <= 0:
        return locked_message(LOCK_MINUTES)
    return f"帳號或密碼錯誤（還可以再試 {left} 次，錯 {MAX_FAILURES} 次會鎖 {LOCK_MINUTES} 分鐘）。"


# ---------- 雙重驗證 ----------

def two_factor_status(user):
    mine = _account_failures(_recent([TWO_FACTOR_ACTION]), user.username, user.id)
    if len(mine) >= MAX_FAILURES:
        return True, _wait_minutes(mine)
    return False, 0


def record_two_factor_failure(user):
    audit_service.record(user, TWO_FACTOR_ACTION, "user", user.id, detail={"username": user.username})
    db.session.flush()
    mine = _account_failures(_recent([TWO_FACTOR_ACTION]), user.username, user.id)
    left = MAX_FAILURES - len(mine)
    if len(mine) == MAX_FAILURES:
        audit_service.record(user, LOCKED_ACTION, "user", user.id,
                             detail={"username": user.username, "kind": "two_factor"})
    db.session.commit()
    return max(0, left)


def two_factor_locked_message(minutes):
    return f"驗證碼錯太多次，這個帳號暫時鎖住了。請 {minutes} 分鐘後再試，或請系統管理員解除鎖定。"


# ---------- 管理員帳號管理 ----------

def locked_usernames():
    """目前被鎖住的帳號（密碼或驗證碼），給帳號管理頁顯示「解除鎖定」。"""
    rows = _recent(list(PASSWORD_ACTIONS.values()) + [TWO_FACTOR_ACTION])
    result = set()
    for name in {_username(row) for row in rows if _username(row)}:
        for action in list(PASSWORD_ACTIONS.values()) + [TWO_FACTOR_ACTION]:
            if len(_account_failures([r for r in rows if r.action == action], name)) >= MAX_FAILURES:
                result.add(name)
    return result


def unlock(actor, target):
    audit_service.record(actor, UNLOCKED_ACTION, "user", target.id, detail={"username": target.username})
