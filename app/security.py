from pathlib import Path
import re
from secrets import token_urlsafe

from flask import abort, request, session


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
        if request.method == "POST" and request.form.get("csrf_token") != session.get("csrf_token"):
            abort(400, description="Invalid CSRF token")
        return None
