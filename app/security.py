from pathlib import Path
import re
from secrets import compare_digest, token_urlsafe

from flask import abort, render_template, request, session


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
            submitted = request.form.get("csrf_token")
            if (not isinstance(expected, str) or not expected or not isinstance(submitted, str) or not submitted
                    or not compare_digest(expected.encode("utf-8"), submitted.encode("utf-8"))):
                if submitted and request.endpoint in {"main.login", "main.staff_login"}:
                    from app.routes.main import _render_portal
                    portal = "staff" if request.endpoint == "main.staff_login" else "student"
                    return _render_portal(portal, 400, error="登入頁已過期，請重新輸入帳號密碼。")
                if submitted and request.endpoint == "main.logout":
                    from app.routes.main import get_current_user
                    return render_template("logout_retry.html", user=get_current_user()), 400
                abort(400, description="Invalid CSRF token")
        return None
