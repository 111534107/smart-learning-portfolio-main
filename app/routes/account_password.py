"""帳號選單「修改密碼」（11-05 評審意見 1b，2026-11-10）。

輸入目前密碼與兩次新密碼 → 依 app/services/password_policy.py 檢查 → 存新密碼。
密碼雜湊一換，其他裝置 session 的指紋就對不上，下一次開頁面會被登出；這台裝置換上新指紋，繼續使用。
用學校 Google 登入建立的帳號原本就沒有人知道密碼，所以頁面只說明，不提供修改。
"""
import time

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for

from app.extensions import db
from app.models import AuditLog
from app.routes.main import get_current_user, role_required
from app.services import backup_email, password_policy

account_password_bp = Blueprint("account_password", __name__)

FAILURES = "password_change_failures"
LOCKED_UNTIL = "password_change_locked_until"
MAX_FAILURES = 5


def _render(user, status=200, **context):
    from app.services import email_notify
    return render_template("account_password.html", user=user, rules=password_policy.rules_text(),
                           google_only=bool(user.google_sub), email_saved=request.args.get("email_saved"),
                           email_global=email_notify.globally_enabled(),
                           backup_status=request.args.get("backup"),
                           # 展示站（有 Demo 快速登入的假資料站）沒有寄信帳號時，頁面直接給確認連結，不然流程走不完
                           demo_verify_path=(backup_email.verify_path(user)
                                             if (current_app.config.get("LOCAL_DEMO_MODE")
                                                 or current_app.config.get("DEMO_ACCOUNTS"))
                                             and not email_notify.smtp_ready() and user.backup_email
                                             and not user.backup_email_verified_at else None),
                           **context), status


@account_password_bp.get("/account/password")
@role_required("student", "teacher", "staff", "admin")
def password_page():
    return _render(get_current_user())


@account_password_bp.post("/account/password")
@role_required("student", "teacher", "staff", "admin")
def password_change():
    user = get_current_user()
    until = session.get(LOCKED_UNTIL)
    if until and until > time.time():
        return _render(user, 429, error="目前密碼輸入錯太多次，請 15 分鐘後再試。")
    current = request.form.get("current_password", "")
    new = request.form.get("new_password", "")
    confirm = request.form.get("confirm_password", "")
    if not user.check_password(current):
        failures = session.get(FAILURES, 0) + 1
        session[FAILURES] = failures
        if failures >= MAX_FAILURES:
            session[LOCKED_UNTIL] = time.time() + 15 * 60
            session[FAILURES] = 0
        return _render(user, 400, error="目前的密碼不正確。")
    session.pop(FAILURES, None)
    problems = password_policy.check(new, user)
    if new != confirm:
        problems.append("兩次輸入的新密碼不一樣。")
    if problems:
        return _render(user, 400, problems=problems)
    user.set_password(new)
    db.session.add(AuditLog(user_id=user.id, action="user.password_change", ip_address=request.remote_addr))
    db.session.commit()
    session[password_policy.SESSION_KEY] = password_policy.fingerprint(user)  # 這台留著，其他裝置登出
    return _render(user, done=True)


@account_password_bp.post("/account/email-notify")
@role_required("student", "teacher")
def email_notify_toggle():
    """學生、導師自己開關電子郵件通知（站內通知照常）。"""
    from app.services import audit_service
    user = get_current_user()
    user.email_notify = request.form.get("email_notify") == "on"
    audit_service.record(user, "user.email_notify", "user", user.id, {"enabled": user.email_notify})
    db.session.commit()
    return redirect(url_for("account_password.password_page", email_saved=1) + "#email-notify")


# ---------- 備用信箱（11-13）：學生綁定自己的另一個信箱，用來收備審打包 ----------

@account_password_bp.post("/account/backup-email")
@role_required("student")
def backup_email_request():
    user = get_current_user()
    try:
        status = backup_email.request_binding(user, request.form.get("backup_email"))
    except backup_email.InvalidAddress as exc:
        db.session.rollback()
        return _render(user, 400, backup_error=str(exc))
    db.session.commit()
    return redirect(url_for("account_password.password_page", backup=status) + "#backup-email")


@account_password_bp.get("/account/backup-email/verify/<token>")
@role_required("student")
def backup_email_verify(token):
    user = get_current_user()
    if not backup_email.verify(user, token):
        return _render(user, 400, backup_error="這個確認連結不能用：可能已經過期、信箱已經換過，或不是用填信箱的那個帳號登入。"
                                               "請重新填一次備用信箱。")
    db.session.commit()
    return redirect(url_for("account_password.password_page", backup="verified") + "#backup-email")


@account_password_bp.post("/account/backup-email/remove")
@role_required("student")
def backup_email_remove():
    user = get_current_user()
    backup_email.remove(user)
    db.session.commit()
    return redirect(url_for("account_password.password_page", backup="removed") + "#backup-email")
