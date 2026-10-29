"""管理員的「檔案存放設定」：看新上傳的檔案存在哪裡、連上或中斷 Google 雲端硬碟。

規則見 app/services/storage_service.py；設定步驟見 docs/03_開發紀錄/01_參考與環境設定/Google雲端硬碟存放_設定步驟.md。
"""
from flask import Blueprint, abort, current_app, redirect, render_template, request, session, url_for

from app.extensions import db
from app.models import AuditLog
from app.routes.main import get_current_user, role_required
from app.services import storage_service

storage_bp = Blueprint("storage", __name__)

STATE = "google_storage_state"
MESSAGES = {
    "unconfigured": ("warn", "Google 尚未設定（.env 的 OAuth 欄位沒填齊），新上傳的檔案繼續存本機。"),
    "connected": ("ok", "已連上 Google 雲端硬碟（只授權本系統建立的檔案）。"),
    "denied": ("warn", "沒有完成 Google 授權，新上傳的檔案繼續存本機。"),
    "unavailable": ("warn", "Google 暫時無法使用，新上傳的檔案繼續存本機，稍後再試。"),
    "disconnected": ("ok", "已中斷 Google 雲端硬碟，新上傳的檔案改存本機；已經存在雲端的檔案要重新連線才讀得到（本機快取仍可用）。"),
}


def _log(action, **detail):
    db.session.add(AuditLog(user_id=get_current_user().id, action=action, target_type="system_setting",
                            detail_json=detail))
    db.session.commit()


@storage_bp.get("/admin/storage")
@role_required("admin")
def settings_page():
    config = current_app.config
    return render_template(
        "admin_storage.html",
        user=get_current_user(),
        active=storage_service.active_backend_name(),
        wants_drive=storage_service.wants_drive(config),
        configured=storage_service.configured(config),
        connected=storage_service.token_holder(current_app).connected,
        message=MESSAGES.get(request.args.get("status", "")),
        folder_name=storage_service.FOLDER_NAME,
    )


@storage_bp.post("/admin/storage/google/connect")
@role_required("admin")
def connect():
    if not storage_service.configured(current_app.config):
        return redirect(url_for("storage.settings_page", status="unconfigured"))
    session[STATE] = storage_service.new_state()
    return redirect(storage_service.authorization_url(current_app.config, session[STATE]))


@storage_bp.get("/admin/storage/google/callback")
@role_required("admin")
def callback():
    expected = session.pop(STATE, None)
    if not expected or request.args.get("state") != expected:
        abort(400, description="Google 授權狀態不符，請回到檔案存放設定重新連線。")
    code = request.args.get("code")
    if request.args.get("error") or not code:
        return redirect(url_for("storage.settings_page", status="denied"))
    try:
        token = storage_service.client_for(current_app).exchange_code(code)
    except storage_service.DriveAuthExpired:
        return redirect(url_for("storage.settings_page", status="denied"))
    except storage_service.DriveError:
        return redirect(url_for("storage.settings_page", status="unavailable"))
    storage_service.token_holder(current_app).set(token)
    _log("system.storage_google_connected")
    return redirect(url_for("storage.settings_page", status="connected"))


@storage_bp.post("/admin/storage/google/disconnect")
@role_required("admin")
def disconnect():
    storage_service.token_holder(current_app).clear()
    _log("system.storage_google_disconnected")
    return redirect(url_for("storage.settings_page", status="disconnected"))
