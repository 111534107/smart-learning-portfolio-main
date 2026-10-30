"""所有測試共用的設定。"""
import pytest

from app.config import Config


@pytest.fixture(autouse=True)
def no_real_ai(monkeypatch):
    """測試一律不讀 .env 裡真的 AI 金鑰，避免連網路、花額度或洩漏金鑰。"""
    monkeypatch.setattr(Config, "AI_ENABLED", False)
    monkeypatch.setattr(Config, "AI_API_KEY", "")


@pytest.fixture(autouse=True)
def no_real_google(monkeypatch):
    """測試一律不讀 .env 裡真的 Google OAuth 設定；需要時由測試自己傳假值與替身。"""
    monkeypatch.setattr(Config, "GOOGLE_OAUTH_CLIENT_SECRET", "")
    monkeypatch.setattr(Config, "GOOGLE_OAUTH_REDIRECT_URI", "")
    monkeypatch.setattr(Config, "GOOGLE_STORAGE_REDIRECT_URI", "")
    monkeypatch.setattr(Config, "STORAGE_BACKEND", "local")


@pytest.fixture(autouse=True)
def no_real_ocr(monkeypatch):
    """測試預設用假辨識，不吃 .env 的 DOCUMENT_ANALYSIS_PROVIDER；要測真實 OCR 的測試自己在 create_app 指定。
    10-29 有人把 .env 改成 rapidocr 後，沒指定的 5 個測試拿 4 個位元組的假檔去真辨識而失敗。"""
    monkeypatch.setattr(Config, "DOCUMENT_ANALYSIS_PROVIDER", "fake")
