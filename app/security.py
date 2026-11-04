from pathlib import Path
import re
from hmac import compare_digest
from secrets import token_urlsafe

from flask import abort, current_app, render_template, request, session


def validate_upload_filename(filename, allowed_extensions):
    if not filename or "/" in filename or "\\" in filename:
        raise ValueError("unsafe filename")
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    safe_name = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", f"{stem}{suffix}", flags=re.UNICODE).strip("._")
    if not safe_name:
        raise ValueError("invalid filename")
    extension = Path(safe_name).suffix.lower().lstrip(".")
    if extension not in {value.lower().lstrip(".") for value in allowed_extensions}:
        raise ValueError("file type is not allowed")
    return safe_name


def csrf_token():
    session.setdefault("csrf_token", token_urlsafe(32))
    return session["csrf_token"]


def init_security(app):
    app.context_processor(lambda: {"csrf_token": csrf_token})

    @app.before_request
    def validate_csrf_request():
        if not app.config.get("CSRF_ENABLED", True) or app.testing:
            return None
        if request.method == "POST":
            expected = session.get("csrf_token")
            supplied = request.form.get("csrf_token")
            if not expected or not supplied or not compare_digest(str(expected), str(supplied)):
                if request.endpoint == "main.login":
                    from app.services.flow import safe_next
                    from app.services.school_google_login import configured
                    return render_template("login.html", error="登入頁已過期，請重新輸入帳號密碼或再次選擇 Google 登入。",
                                           next_path=safe_next(request.form.get("next")),
                                           google_login_enabled=configured(current_app.config)), 400
                if request.endpoint == "main.logout":
                    from app.routes.main import get_current_user
                    return render_template("logout_retry.html", user=get_current_user()), 400
                abort(400, description="Invalid CSRF token")
        return None
