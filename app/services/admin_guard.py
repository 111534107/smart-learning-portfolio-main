"""管理員登入頁的保護（2026-11-10 使用者決定）。

- 密碼錯 5 次（同一個帳號或同一個 IP）鎖 15 分鐘。次數記在操作紀錄（資料庫），清掉瀏覽器 Cookie 也不會重算。
- 閒置 15 分鐘自動登出（ADMIN_IDLE_MINUTES）；其他角色不受影響。
- 「只能從學校網路登入」：管理員在首頁填學校網段才生效；沒填就不限制（目前專題沒有學校網路）。
  正式主機如果在反向代理後面，要先讓 request.remote_addr 拿到真正的來源 IP，否則會看到代理的位址。
"""
import ipaddress
import time
from datetime import datetime, timedelta, timezone

from flask import current_app, request

from app.extensions import db
from app.models import AuditLog, SystemSetting
from app.services import audit_service

NETWORK_KEY = "admin_allowed_networks"
FAILED_ACTION = "admin.login_failed"
MAX_FAILURES = 5
LOCK_MINUTES = 15
LAST_SEEN = "admin_last_seen"
LOGGED_OUT = "admin_logged_out"


# ---------- 學校網路 ----------

def parse_networks(text):
    """「163.17.0.0/16, 127.0.0.1」→ 網段清單；有看不懂的就丟 ValueError。"""
    parts = [part.strip() for part in (text or "").replace("，", ",").replace("\n", ",").split(",") if part.strip()]
    networks = []
    for part in parts:
        try:
            networks.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            raise ValueError(f"看不懂「{part}」，請寫成 163.17.0.0/16 或 127.0.0.1 這樣的格式。") from None
    return networks


def networks_text():
    setting = SystemSetting.query.filter_by(key=NETWORK_KEY).first()
    return setting.value if setting else ""


def ip_allowed(ip=None):
    networks = parse_networks(networks_text())
    if not networks:
        return True  # 沒設定就不限制
    try:
        address = ipaddress.ip_address(ip or request.remote_addr or "")
    except ValueError:
        return False
    return any(address in network for network in networks)


def save_networks(actor, text):
    """存學校網段。回傳給管理員看的訊息；不能存會把自己擋在外面的設定。"""
    networks = parse_networks(text)
    if networks:
        current = ipaddress.ip_address(request.remote_addr or "127.0.0.1")
        if not any(current in network for network in networks):
            raise ValueError(f"你現在的位置（{current}）不在這些網段裡，存了你會馬上被登出，請把它加進去。")
    value = ", ".join(str(network) for network in networks)
    setting = SystemSetting.query.filter_by(key=NETWORK_KEY).first()
    if setting is None:
        setting = SystemSetting(key=NETWORK_KEY, value=value)
        db.session.add(setting)
    setting.value = value
    setting.updated_by_id = actor.id
    audit_service.record(actor, "admin.login_security", detail={"networks": value})
    db.session.commit()
    return "已儲存：" + (f"只有 {value} 可以登入管理員。" if value else "不限制登入位置。")


# ---------- 錯誤次數 ----------
# 2026-11-12 起改由 app/services/login_guard.py 統一處理三個登入頁與雙重驗證。

def locked(username):
    from app.services import login_guard
    return login_guard.password_status("admin", username)[0]


def record_failure(username):
    from app.services import login_guard
    login_guard.record_password_failure("admin", username)


# ---------- 閒置 ----------

def session_ok(session):
    """已登入的管理員每個請求都檢查：位置不在學校網路或閒置太久就要登出。順便更新最後操作時間。"""
    now = time.time()
    idle = current_app.config.get("ADMIN_IDLE_MINUTES", 15) * 60
    last = session.get(LAST_SEEN)
    if (last is not None and now - last > idle) or not ip_allowed():
        return False
    session[LAST_SEEN] = now
    return True
