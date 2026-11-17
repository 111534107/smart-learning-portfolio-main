"""AI 統一入口（2026-11-11 使用者決定）：多家 AI 依管理員設定切換；AI 不讀圖片，文件先 OCR 成文字並去識別化。"""
from pathlib import Path

import pytest
from PIL import Image

from app import create_app
from app.extensions import db
from app.models import AuditLog, User
from app.services import ai_gateway
from app.services.deidentify import known_values
from app.services.gemini_client import AIUnavailable


class FakeOcr:
    def __init__(self, text):
        self.text, self.seen = text, []

    def recognize_text(self, image_path):
        self.seen.append(image_path)
        return self.text


def make_app(**config):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "WTF_CSRF_ENABLED": False, "DOCUMENT_OCR_ENGINE": "", **config})
    with app.app_context():
        db.create_all()
        admin = User(username="admin", display_name="合成管理員", role="admin")
        admin.set_password("pw")
        db.session.add(admin)
        db.session.commit()
    return app


def recorder(name, calls, fail=False):
    def call(prompt, schema):
        calls.append((name, prompt))
        if fail:
            raise AIUnavailable("額度用完或請求太頻繁")
        return {"ok": name}
    return call


def test_falls_back_to_next_provider_in_admin_order():
    app = make_app(AI_API_KEY="g", OPENAI_API_KEY="o")
    with app.app_context():
        ai_gateway.save(db.session.get(User, 1), ["gemini", "openai", "ollama"], {"openai": "gpt-test"})
        calls = []
        callers = {"gemini": recorder("gemini", calls, fail=True), "openai": recorder("openai", calls),
                   "ollama": recorder("ollama", calls)}
        result, used = ai_gateway.generate_json("題目", {}, callers=callers)
        assert used == "openai" and result == {"ok": "openai"}
        assert [name for name, _ in calls] == ["gemini", "openai"]
        assert ai_gateway.model("openai") == "gpt-test"
        assert AuditLog.query.filter_by(action="ai.settings").count() == 1


def test_provider_without_key_is_skipped_and_all_failures_are_explained():
    app = make_app(AI_API_KEY="")
    with app.app_context():
        ai_gateway.save(db.session.get(User, 1), ["gemini", "ollama"], {})
        with pytest.raises(AIUnavailable) as error:
            ai_gateway.generate_json("題目", {}, callers={"ollama": recorder("ollama", [], fail=True)})
        assert "沒有金鑰" in str(error.value) and "額度用完" in str(error.value)


def test_image_goes_through_ocr_and_personal_data_is_redacted(tmp_path):
    image = tmp_path / "獎懲.png"
    Image.new("RGB", (40, 20), "white").save(image)
    ocr = FakeOcr("合成學生 111534999 嘉獎一次 0912345678")
    app = make_app(AI_API_KEY="g", OCR_ENGINE=ocr)
    with app.app_context():
        ai_gateway.save(db.session.get(User, 1), ["gemini"], {})
        calls = []
        ai_gateway.generate_json("請讀出", {}, documents=[image],
                                 known=known_values(display_name="合成學生"),
                                 callers={"gemini": recorder("gemini", calls)})
        sent = calls[0][1]
        assert ocr.seen, "圖片要先經過系統 OCR"
        assert "嘉獎一次" in sent
        assert "合成學生" not in sent and "111534999" not in sent and "0912345678" not in sent
        assert "[姓名]" in sent


def test_image_without_ocr_is_refused_instead_of_sent(tmp_path):
    image = tmp_path / "x.jpg"
    Image.new("RGB", (10, 10), "white").save(image)
    app = make_app(AI_API_KEY="g", OCR_ENGINE=None)
    with app.app_context():
        with pytest.raises(AIUnavailable):
            ai_gateway.document_text(image)


def test_gateway_has_no_way_to_send_files():
    """AI 不能讀圖片：統一入口沒有傳檔案的參數。"""
    import inspect
    params = inspect.signature(ai_gateway.generate_json).parameters
    assert "files" not in params and "uploaded" not in params


def test_admin_page_saves_order_and_models():
    app = make_app(AI_API_KEY="g")
    client = app.test_client()
    client.post("/admin/login", data={"username": "admin", "password": "pw"})
    page = client.get("/admin/ai").get_data(as_text=True)
    assert "AI 設定" in page and "OPENAI_API_KEY" in page and "不需要" in page
    response = client.post("/admin/ai", data={"enabled_ollama": "1", "order_ollama": "1", "model_ollama": "qwen2.5:3b",
                                              "enabled_gemini": "1", "order_gemini": "2"})
    assert "已儲存" in response.get_data(as_text=True)
    with app.app_context():
        assert ai_gateway.order() == ["ollama", "gemini"] and ai_gateway.model("ollama") == "qwen2.5:3b"
    assert "/admin/ai" in client.get("/admin/dashboard").get_data(as_text=True)
