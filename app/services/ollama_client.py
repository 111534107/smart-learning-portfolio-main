"""自傳使用的本機 Ollama JSON 介面。"""
import json
import urllib.error
import urllib.request

from flask import current_app

from app.services.gemini_client import AIUnavailable


def _json_schema(value):
    if isinstance(value, dict):
        return {key: item.lower() if key == "type" and isinstance(item, str) else _json_schema(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [_json_schema(item) for item in value]
    return value


def generate_json(prompt, schema, opener=None):
    opener = opener or urllib.request.urlopen
    payload = {"model": current_app.config.get("OLLAMA_MODEL", "qwen2.5-coder:7b"),
               "messages": [{"role": "user", "content": prompt}], "stream": False,
               "format": _json_schema(schema), "options": {"temperature": 0.4}}
    request = urllib.request.Request("http://127.0.0.1:11434/api/chat",
                                     data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        with opener(request, timeout=180) as response:
            result = json.loads(response.read().decode("utf-8"))
        content = json.loads(result["message"]["content"])
        if not isinstance(content, dict) or not isinstance(content.get("paragraphs"), list):
            raise ValueError("invalid response")
        if any(not isinstance(p, dict) or not isinstance(p.get("title"), str)
               or not isinstance(p.get("text"), str) or not isinstance(p.get("sources"), list)
               or any(not isinstance(s, str) for s in p["sources"]) for p in content["paragraphs"]):
            raise ValueError("invalid paragraph")
        return content
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError, TypeError):
        raise AIUnavailable("Ollama 無法產生草稿，請確認本機服務與模型已啟動後再試。") from None
