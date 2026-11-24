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
    "bad_client": ("warn", storage_service.DriveCredentialError.user_message),
    "redirect_mismatch": ("warn", storage_service.DriveRedirectMismatch.user_message),
    "api_disabled": ("warn", storage_service.DriveApiDisabled.user_message),
}
_CALLBACK_STATUS = {storage_service.DriveCredentialError: "bad_client",
                    storage_service.DriveRedirectMismatch: "redirect_mismatch",
                    storage_service.DriveApiDisabled: "api_disabled"}
CONFIRM_TEXT = "確定搬移"


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
        checks=storage_service.check_settings(config),
        last_check=storage_service.last_check(current_app),
        last_error=storage_service.token_holder(current_app).last_error,
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
    except storage_service.DriveError as error:
        return redirect(url_for("storage.settings_page", status=_CALLBACK_STATUS.get(type(error), "unavailable")))
    storage_service.token_holder(current_app).set(token)
    _log("system.storage_google_connected")
    return redirect(url_for("storage.settings_page", status="connected"))


@storage_bp.post("/admin/storage/google/disconnect")
@role_required("admin")
def disconnect():
    storage_service.token_holder(current_app).clear()
    _log("system.storage_google_disconnected")
    return redirect(url_for("storage.settings_page", status="disconnected"))


@storage_bp.post("/admin/storage/google/test")
@role_required("admin")
def test_connection():
    """測試連線：只讀帳號資訊、確認系統資料夾，不上傳也不刪檔。結果留在記憶體給設定頁顯示。"""
    result = storage_service.test_connection(current_app._get_current_object())
    _log("system.storage_google_test", ok=result["ok"],
         failed_step=next((step["label"] for step in result["steps"] if not step["ok"]), None))
    return redirect(url_for("storage.settings_page") + "#connection-test")


@storage_bp.route("/admin/storage/migration", methods=["GET", "POST"])
@role_required("admin")
def migration_page():
    """舊檔搬進學生資料夾：GET 預覽、POST 試跑；兩者都不改任何資料。"""
    from app.services import storage_migration
    dry = request.method == "POST"
    result = storage_migration.dry_run() if dry else storage_migration.preview()
    if not dry:
        result["blockers"] = storage_migration.blockers()
    return render_template("admin_storage_migration.html", user=get_current_user(), result=result, dry=dry,
                           kinds=storage_migration.KIND_LABELS, statuses=storage_migration.STATUS_LABELS,
                           confirm_text=CONFIRM_TEXT, outcome=None, error=None)


@storage_bp.post("/admin/storage/migration/execute")
@role_required("admin")
def migration_execute():
    """真的搬：要輸入確認文字；本機原檔保留，只在旁邊寫 .migrated.json。"""
    from app.services import storage_migration
    error = outcome = None
    if request.form.get("confirm", "").strip() != CONFIRM_TEXT:
        error = f"請在確認欄輸入「{CONFIRM_TEXT}」才會執行。"
    else:
        try:
            outcome = storage_migration.execute(get_current_user())
        except RuntimeError as exc:
            error = f"還不能搬：{exc}"
    result = storage_migration.preview()
    result["blockers"] = storage_migration.blockers()
    return render_template("admin_storage_migration.html", user=get_current_user(), result=result, dry=False,
                           kinds=storage_migration.KIND_LABELS, statuses=storage_migration.STATUS_LABELS,
                           confirm_text=CONFIRM_TEXT, outcome=outcome, error=error), (400 if error else 200)
