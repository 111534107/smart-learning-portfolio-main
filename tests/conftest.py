"""所有測試共用的設定。"""
import pytest

from app.config import Config


@pytest.fixture(autouse=True)
def no_real_ai(monkeypatch):
    """測試一律不讀 .env 裡真的 AI 金鑰，避免連網路、花額度或洩漏金鑰。"""
    monkeypatch.setattr(Config, "AI_ENABLED", False)
    monkeypatch.setattr(Config, "AI_API_KEY", "")
    monkeypatch.setattr(Config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(Config, "ANTHROPIC_API_KEY", "")


@pytest.fixture(autouse=True)
def no_real_google(monkeypatch):
    """測試一律不讀 .env 裡真的 Google OAuth 設定；需要時由測試自己傳假值與替身。"""
    monkeypatch.setattr(Config, "GOOGLE_DRIVE_PREVIEW_ENABLED", False)
    monkeypatch.setattr(Config, "GOOGLE_OAUTH_CLIENT_ID", "")
    monkeypatch.setattr(Config, "GOOGLE_PICKER_API_KEY", "")
    monkeypatch.setattr(Config, "GOOGLE_OAUTH_CLIENT_SECRET", "")
    monkeypatch.setattr(Config, "GOOGLE_OAUTH_REDIRECT_URI", "")
    monkeypatch.setattr(Config, "GOOGLE_STORAGE_REDIRECT_URI", "")
    monkeypatch.setattr(Config, "STORAGE_BACKEND", "local")


@pytest.fixture(autouse=True)
def no_real_ocr(monkeypatch):
    """測試預設用假辨識，不吃 .env 的 DOCUMENT_ANALYSIS_PROVIDER；要測真實 OCR 的測試自己在 create_app 指定。
    10-29 有人把 .env 改成 rapidocr 後，沒指定的 5 個測試拿 4 個位元組的假檔去真辨識而失敗。"""
    monkeypatch.setattr(Config, "DOCUMENT_ANALYSIS_PROVIDER", "fake")


@pytest.fixture(autouse=True)
def login_route_by_role(request, monkeypatch):
    """2026-11-10 登入頁分成學生 /login、老師與科辦 /staff/login、管理員 /admin/login。

    舊測試大多直接把任何角色的帳號 POST 到 /login；這裡依帳號角色改送到對應的登入頁，
    舊測試不用逐一改。直接測登入頁分流的測試加 @pytest.mark.real_login_routes 關掉這個轉送。
    """
    if request.node.get_closest_marker("real_login_routes"):
        return
    from flask.testing import FlaskClient

    original_open = FlaskClient.open

    def open_by_role(self, *args, **kwargs):
        path = args[0] if args else kwargs.get("path")
        data = kwargs.get("data")
        if path == "/login" and kwargs.get("method") == "POST" and isinstance(data, dict) and data.get("username"):
            from app.models import User
            with self.application.app_context():
                user = User.query.filter_by(username=data["username"]).first()
                role = user.role if user else None
            target = {"teacher": "/staff/login", "staff": "/staff/login", "admin": "/admin/login"}.get(role)
            if target:
                args = (target,) + tuple(args[1:]) if args else args
                if not args:
                    kwargs["path"] = target
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(FlaskClient, "open", open_by_role)
