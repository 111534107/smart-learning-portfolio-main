"""雙重驗證的頁面（2026-11-09）。

登入流程：帳號密碼或學校 Google 驗證成功 → main._finish_login 交給 start()，這時還沒寫入 session["user_id"]
→ 已開啟的人到「輸入驗證碼」，還沒開啟且規定要開的人到「設定」→ 成功後才由 main._complete_login 真正登入。
所以既有頁面的權限檢查都不用改。
"""
from flask import Blueprint, abort, redirect, render_template, request, session, url_for

from app.extensions import db
from app.models import User
from app.routes.main import get_current_user, role_required
from app.services import two_factor

two_factor_bp = Blueprint("two_factor", __name__)

PENDING = "two_factor_user"
NEXT = "two_factor_next"
SETUP_SECRET = "two_factor_setup_secret"
ACCOUNT_SECRET = "two_factor_account_secret"


def start(user, next_path):
    """密碼或 Google 驗證成功後呼叫：記下「等待第二步」的帳號，轉到驗證或設定頁。"""
    session.clear()
    session[PENDING] = user.id
    session[NEXT] = next_path
    endpoint = "two_factor.verify_page" if user.two_factor_enabled else "two_factor.setup_page"
    return redirect(url_for(endpoint))


def needs_second_step(user):
    if two_factor.demo_site():
        return False
    return user.two_factor_enabled or two_factor.required_for(user)


def _pending_user():
    user_id = session.get(PENDING)
    user = db.session.get(User, user_id) if user_id else None
    return user if user and user.is_active else None


def _complete(user):
    from app.routes.main import _complete_login
    return _complete_login(user, session.get(NEXT))


def _locked_message(user):
    """錯誤次數記在資料庫（操作紀錄），清掉 Cookie 重新登入也算同一個帳號。"""
    from app.services import login_guard
    is_locked, minutes = login_guard.two_factor_status(user)
    return login_guard.two_factor_locked_message(minutes) if is_locked else None


@two_factor_bp.route("/login/two-factor", methods=["GET", "POST"])
def verify_page():
    user = _pending_user()
    if user is None or not user.two_factor_enabled:
        return redirect(url_for("main.login"))
    locked = _locked_message(user)
    if locked:
        return render_template("two_factor_verify.html", user=user, error=locked), 429
    if request.method == "GET":
        return render_template("two_factor_verify.html", user=user)
    if two_factor.verify(user, request.form.get("code", "")) is None:
        from app.services import login_guard
        left = login_guard.record_two_factor_failure(user)
        if left <= 0:
            return render_template("two_factor_verify.html", user=user, error=_locked_message(user)), 429
        return render_template("two_factor_verify.html", user=user,
                               error=f"驗證碼不正確，請看手機上最新的六位數再試一次（還可以試 {left} 次）。"), 400
    db.session.commit()
    return _complete(user)


def _setup_context(user, secret):
    uri = two_factor.provisioning_uri(user, secret)
    return {"qr_svg": two_factor.qr_svg(uri), "secret_text": two_factor.format_secret(secret)}


@two_factor_bp.route("/login/two-factor/setup", methods=["GET", "POST"])
def setup_page():
    user = _pending_user()
    if user is None:
        return redirect(url_for("main.login"))
    if user.two_factor_enabled:
        return redirect(url_for("two_factor.verify_page"))
    secret = session.get(SETUP_SECRET) or two_factor.new_secret()
    session[SETUP_SECRET] = secret
    context = _setup_context(user, secret)
    if request.method == "GET":
        return render_template("two_factor_setup.html", user=user, during_login=True, **context)
    codes = two_factor.enable(user, secret, request.form.get("code", ""))
    if codes is None:
        return render_template("two_factor_setup.html", user=user, during_login=True,
                               error="驗證碼不正確。請確認已掃描這個 QR code，再輸入手機上最新的六位數。", **context), 400
    db.session.commit()
    response = _complete(user)  # 真正登入（清掉等待中的狀態）
    return render_template("two_factor_backup_codes.html", user=user, codes=codes,
                           continue_url=response.location)


# ---- 登入後自己管理（帳號選單「雙重驗證」）----

@two_factor_bp.get("/account/two-factor")
@role_required("student", "teacher", "staff", "admin")
def account_page():
    user = get_current_user()
    context = {}
    if not user.two_factor_enabled:
        secret = session.get(ACCOUNT_SECRET) or two_factor.new_secret()
        session[ACCOUNT_SECRET] = secret
        context = _setup_context(user, secret)
    return render_template("two_factor_account.html", user=user, required=two_factor.required_for(user),
                           remaining=two_factor.remaining_backup_codes(user) if user.two_factor_enabled else 0,
                           error=request.args.get("error"), **context)


@two_factor_bp.post("/account/two-factor/enable")
@role_required("student", "teacher", "staff", "admin")
def account_enable():
    user = get_current_user()
    secret = session.get(ACCOUNT_SECRET)
    if user.two_factor_enabled or not secret:
        return redirect(url_for("two_factor.account_page"))
    codes = two_factor.enable(user, secret, request.form.get("code", ""))
    if codes is None:
        return redirect(url_for("two_factor.account_page", error="驗證碼不正確，請掃描後輸入手機上最新的六位數。"))
    session.pop(ACCOUNT_SECRET, None)
    db.session.commit()
    return render_template("two_factor_backup_codes.html", user=user, codes=codes,
                           continue_url=url_for("two_factor.account_page"))


@two_factor_bp.post("/account/two-factor/backup-codes")
@role_required("student", "teacher", "staff", "admin")
def account_backup_codes():
    user = get_current_user()
    if not user.two_factor_enabled:
        abort(400)
    codes = two_factor.regenerate_backup_codes(user)
    db.session.commit()
    return render_template("two_factor_backup_codes.html", user=user, codes=codes,
                           continue_url=url_for("two_factor.account_page"))


@two_factor_bp.post("/account/two-factor/disable")
@role_required("student", "teacher", "staff", "admin")
def account_disable():
    user = get_current_user()
    if two_factor.required_for(user):
        abort(403)  # 規定要開時不能自己關
    two_factor.reset(user, user, reason="self")
    db.session.commit()
    return redirect(url_for("two_factor.account_page"))
