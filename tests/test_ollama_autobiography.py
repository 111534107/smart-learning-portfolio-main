import io
import json
import urllib.error

import pytest

from tests.test_autobiography import ANSWERS, app, choose_target, login, program


def test_ollama_request_uses_local_model_and_schema(app):
    from app.services import ollama_client

    seen = {}

    def opener(request, timeout):
        seen.update(json.loads(request.data))
        return io.BytesIO(json.dumps({"message": {"content": '{"paragraphs": []}'}}).encode())

    with app.app_context():
        app.config["OLLAMA_MODEL"] = "test-model"
        result = ollama_client.generate_json("測試", {"type": "OBJECT"}, opener=opener)
    assert result == {"paragraphs": []}
    assert seen["model"] == "test-model"
    assert seen["format"] == {"type": "object"}
    assert seen["stream"] is False


def test_ollama_unavailable_has_safe_error(app):
    from app.services import ollama_client
    from app.services.gemini_client import AIUnavailable

    def opener(request, timeout):
        raise urllib.error.URLError("sensitive detail")

    with app.app_context(), pytest.raises(AIUnavailable, match="Ollama") as error:
        ollama_client.generate_json("測試", {}, opener=opener)
    assert "sensitive detail" not in str(error.value)


def test_autobiography_uses_ollama_and_records_provider(app, monkeypatch):
    from app.models import LearningProfileOutput
    from app.services import ollama_client

    app.config.update(AUTOBIOGRAPHY_AI_PROVIDER="ollama", AI_ENABLED=True)
    monkeypatch.setattr(ollama_client, "generate_json", lambda prompt, schema: {
        "paragraphs": [{"title": "動機", "text": "我想讀資管。", "sources": ["F1", "F999"]}]})
    client = login(app)
    choose_target(app, client)
    assert "請 AI 寫草稿" in client.get("/student/autobiography").get_data(as_text=True)
    response = client.post("/student/autobiography/generate", data={"program_id": program(app), **ANSWERS})
    assert response.status_code == 302
    with app.app_context():
        content = LearningProfileOutput.query.filter_by(output_type="autobiography_ai").one().content_json
        assert content["provider"] == "ollama"
        assert content["paragraphs"][0]["sources"] == ["F1"]


def test_ollama_failure_does_not_save_demo_draft(app, monkeypatch):
    from app.models import LearningProfileOutput
    from app.services import ollama_client
    from app.services.gemini_client import AIUnavailable

    app.config.update(AUTOBIOGRAPHY_AI_PROVIDER="ollama", AI_ENABLED=True)
    def fail(prompt, schema):
        raise AIUnavailable("Ollama 無法產生草稿")
    monkeypatch.setattr(ollama_client, "generate_json", fail)
    client = login(app)
    choose_target(app, client)
    response = client.post("/student/autobiography/generate", data={"program_id": program(app), **ANSWERS})
    assert response.status_code == 503
    assert "Ollama 無法產生草稿" in response.get_data(as_text=True)
    with app.app_context():
        assert LearningProfileOutput.query.filter_by(output_type="autobiography_ai").count() == 0


def test_own_key_still_uses_gemini_when_ollama_selected(app, monkeypatch):
    from app.models import LearningProfileOutput
    from app.services import autobiography_service

    app.config.update(AUTOBIOGRAPHY_AI_PROVIDER="ollama", AI_ENABLED=True, LOCAL_DEMO_MODE=False)
    seen = {}
    def fake_gemini(prompt, schema, api_key=None):
        seen["key"] = api_key
        return {"paragraphs": [{"title": "動機", "text": "我想讀資管。", "sources": []}]}
    monkeypatch.setattr(autobiography_service, "generate_json", fake_gemini)
    client = login(app)
    choose_target(app, client)
    response = client.post("/student/autobiography/generate", data={"program_id": program(app), "own_api_key": "test-key", **ANSWERS})
    assert response.status_code == 302
    assert seen["key"] == "test-key"
    with app.app_context():
        assert LearningProfileOutput.query.filter_by(output_type="autobiography_ai").one().content_json["provider"] == "gemini"
