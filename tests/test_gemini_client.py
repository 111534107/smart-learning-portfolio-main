"""Gemini 連線：送出的格式正確、回傳的 JSON 能解析、錯誤變成中文訊息（不連網路）。"""
import io
import json
import urllib.error

import pytest

from app import create_app
from app.services.gemini_client import AIUnavailable, generate_json


def make_app(**config):
    return create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, **config})


READY = {"AI_ENABLED": True, "AI_PROVIDER": "gemini", "AI_API_KEY": "test-key", "GEMINI_MODEL": "gemini-test"}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_request_has_key_schema_and_pdf():
    sent = {}

    def opener(request, timeout):
        sent["url"], sent["key"] = request.full_url, request.get_header("X-goog-api-key")
        sent["body"] = json.loads(request.data)
        reply = {"candidates": [{"content": {"parts": [{"text": json.dumps({"ok": True})}]}}]}
        return FakeResponse(json.dumps(reply).encode())

    with make_app(**READY).app_context():
        result = generate_json("請擷取", {"type": "OBJECT"}, files=[("application/pdf", b"%PDF")], opener=opener)

    assert result == {"ok": True}
    assert "gemini-test:generateContent" in sent["url"]
    assert sent["key"] == "test-key"
    assert sent["body"]["generationConfig"]["responseMimeType"] == "application/json"
    assert sent["body"]["contents"][0]["parts"][1]["inline_data"]["mime_type"] == "application/pdf"


def test_missing_key_raises_chinese_message():
    with make_app(AI_ENABLED=False).app_context():
        with pytest.raises(AIUnavailable, match="沒有開啟"):
            generate_json("x", {})


def test_http_error_becomes_chinese_message():
    def opener(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)

    with make_app(**READY).app_context():
        with pytest.raises(AIUnavailable, match="HTTP 403"):
            generate_json("x", {}, opener=opener)


def test_env_example_never_contains_a_real_key():
    """.env.example 會被 commit，金鑰只能放在 .env（已在 .gitignore）。"""
    from pathlib import Path
    example = Path(__file__).resolve().parents[1] / ".env.example"
    lines = [line for line in example.read_text(encoding="utf-8").splitlines() if line.startswith("AI_API_KEY=")]

    assert lines == ["AI_API_KEY="], "請把金鑰從 .env.example 移到 .env"


def test_rate_limit_waits_and_retries_once(monkeypatch):
    calls = []
    monkeypatch.setattr("app.services.gemini_client.time.sleep", lambda seconds: calls.append(("sleep", seconds)))

    def opener(request, timeout):
        calls.append("call")
        if len(calls) == 1:
            body = io.BytesIO(b'{"error": {"details": [{"retryDelay": "3s"}]}}')
            raise urllib.error.HTTPError(request.full_url, 429, "Too Many", {}, body)
        reply = {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}
        return FakeResponse(json.dumps(reply).encode())

    with make_app(**READY).app_context():
        assert generate_json("x", {}, opener=opener) == {}

    assert calls == ["call", ("sleep", 4), "call"]


# ---- 2026-11-04 實測：上傳獎懲記錄時 Gemini 回 503（伺服器忙），原本直接放棄 ----

def _ok():
    reply = {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}
    return FakeResponse(json.dumps(reply).encode())


def test_server_busy_retries_then_succeeds(monkeypatch):
    calls = []
    monkeypatch.setattr("app.services.gemini_client.time.sleep", lambda seconds: calls.append(("sleep", seconds)))

    def opener(request, timeout):
        calls.append("call")
        if calls.count("call") == 1:
            raise urllib.error.HTTPError(request.full_url, 503, "Unavailable", {}, None)
        return _ok()

    with make_app(**READY).app_context():
        assert generate_json("x", {}, opener=opener) == {}

    assert calls[0] == "call" and calls[1][0] == "sleep" and calls[2] == "call"


def test_server_busy_switches_to_backup_model(monkeypatch):
    monkeypatch.setattr("app.services.gemini_client.time.sleep", lambda seconds: None)
    urls = []

    def opener(request, timeout):
        urls.append(request.full_url)
        if "gemini-test:" in request.full_url:
            raise urllib.error.HTTPError(request.full_url, 503, "Unavailable", {}, None)
        return _ok()

    with make_app(**READY, GEMINI_FALLBACK_MODEL="gemini-backup").app_context():
        assert generate_json("x", {}, opener=opener) == {}

    assert sum("gemini-test:" in url for url in urls) == 3  # 主要模型試 3 次
    assert "gemini-backup:" in urls[-1]


def test_server_busy_everywhere_gives_clear_message(monkeypatch):
    monkeypatch.setattr("app.services.gemini_client.time.sleep", lambda seconds: None)

    def opener(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 503, "Unavailable", {}, None)

    with make_app(**READY, GEMINI_FALLBACK_MODEL="gemini-backup").app_context():
        with pytest.raises(AIUnavailable, match="太忙"):
            generate_json("x", {}, opener=opener)
