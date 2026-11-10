"""AI 統一入口：多家 AI 依管理員設定的順序自動切換，而且只送去識別化後的文字（2026-11-11 使用者決定）。

規則：
- 管理員在「AI 設定」頁選要用哪幾家、模型、先後順序；前一家額度用完或連不上，自動換下一家。
- 金鑰只放 .env（AI_API_KEY＝Gemini、OPENAI_API_KEY、ANTHROPIC_API_KEY），不存資料庫、畫面只顯示有沒有設定。
- **AI 不能讀圖片**：這裡沒有傳檔案的參數。文件一律在本機轉成文字——PDF 先抽文字層，抽不到（掃描檔）
  或本來就是圖片，就用系統後端的 OCR 辨識成文字——再經過 deidentify.redact 去識別化，才放進提示。
"""
import json
import tempfile
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path

from flask import current_app

from app.extensions import db
from app.models import SystemSetting
from app.services.deidentify import redact
from app.services.gemini_client import AIUnavailable

ORDER_KEY = "ai.order"
MODEL_KEY = "ai.model.{}"
PROVIDERS = {
    "gemini": {"label": "Google Gemini", "key_env": "AI_API_KEY", "default_model": "gemini-2.5-flash"},
    "openai": {"label": "OpenAI 或相容服務（DeepSeek、Groq 等）", "key_env": "OPENAI_API_KEY",
               "default_model": "gpt-4o-mini"},
    "anthropic": {"label": "Anthropic Claude", "key_env": "ANTHROPIC_API_KEY", "default_model": "claude-haiku-5-5"},
    "ollama": {"label": "本機 Ollama（不連外網）", "key_env": None, "default_model": "qwen2.5:7b"},
}
MIN_TEXT = 20  # PDF 文字層少於這麼多字，當成掃描檔改用 OCR
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


# ---------- 設定 ----------

def _setting(key):
    row = SystemSetting.query.filter_by(key=key).first()
    return row.value if row else None


def _set(key, value, actor):
    row = SystemSetting.query.filter_by(key=key).first()
    if row is None:
        row = SystemSetting(key=key, value=value)
        db.session.add(row)
    row.value = value
    row.updated_by_id = actor.id if actor else None


def order():
    """啟用中的 AI，依優先順序。沒設定過就沿用 .env：有開 Gemini 就用 Gemini；本機 Ollama 要管理員自己開。"""
    saved = _setting(ORDER_KEY)
    if saved is not None:
        return [name for name in saved.split(",") if name in PROVIDERS]
    config = current_app.config
    default = ["gemini"] if config.get("AI_ENABLED") and config.get("AI_PROVIDER") == "gemini" else []
    return default


def model(name):
    if name == "gemini":
        fallback = current_app.config.get("GEMINI_MODEL") or PROVIDERS[name]["default_model"]
    elif name == "ollama":
        fallback = current_app.config.get("OLLAMA_MODEL") or PROVIDERS[name]["default_model"]
    else:
        fallback = PROVIDERS[name]["default_model"]
    return _setting(MODEL_KEY.format(name)) or fallback


def has_key(name):
    env = PROVIDERS[name]["key_env"]
    return True if env is None else bool(current_app.config.get(env))


def status():
    """給管理員頁看的：每家 AI 的啟用、順序、模型、金鑰有沒有設定。"""
    enabled = order()
    rows = []
    for name in enabled + [n for n in PROVIDERS if n not in enabled]:
        rows.append({"name": name, **PROVIDERS[name], "enabled": name in enabled, "model": model(name),
                     "has_key": has_key(name)})
    return rows


def save(actor, enabled_in_order, models):
    names = [name for name in enabled_in_order if name in PROVIDERS]
    _set(ORDER_KEY, ",".join(dict.fromkeys(names)), actor)
    for name, value in models.items():
        value = (value or "").strip()[:100]
        if name in PROVIDERS and value:
            _set(MODEL_KEY.format(name), value, actor)
    from app.services import audit_service
    audit_service.record(actor, "ai.settings", detail={"order": names})
    db.session.commit()


def ready():
    """至少有一家 AI 可以試（Ollama 實際能不能用要呼叫才知道）。"""
    return any(has_key(name) for name in order())


# ---------- 文件轉文字（AI 不讀圖片） ----------

def _ocr_engine():
    engine = current_app.config.get("OCR_ENGINE")
    if engine is None or not hasattr(engine, "recognize_text"):
        raise AIUnavailable("這份文件需要先用系統 OCR 辨識成文字，但 OCR 還沒設定，請到「OCR 辨識設定」開啟。")
    return engine


def _ocr_pages(path):
    from app.services.ocr_pipeline import load_document_pages
    engine = _ocr_engine()
    texts = []
    with tempfile.TemporaryDirectory() as folder:
        for index, page in enumerate(load_document_pages(path)):
            image = Path(folder) / f"page-{index}.png"
            page.save(image)
            texts.append(engine.recognize_text(str(image)) or "")
    return "\n".join(texts)


def document_text(path):
    """文件 → 文字。PDF 有文字層就直接用，沒有（掃描檔）或是圖片就交給系統 OCR。"""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        import pypdfium2 as pdfium
        try:
            with closing(pdfium.PdfDocument(str(path))) as pdf:
                text = "\n".join(pdf[i].get_textpage().get_text_bounded() for i in range(len(pdf)))
        except Exception:
            raise RuntimeError("PDF 無法讀取，請確認檔案完整且未加密。") from None
        if len("".join(text.split())) >= MIN_TEXT:
            return text
        return _ocr_pages(path)
    if suffix in IMAGE_SUFFIXES:
        return _ocr_pages(path)
    if suffix in {".html", ".htm"}:
        from app.services.admission_agent_service import _html_to_text
        return _html_to_text(path.read_bytes())
    return path.read_text(encoding="utf-8", errors="replace")


# ---------- 各家 AI（都只收文字） ----------

def _post_json(url, payload, headers, timeout=180):
    request = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                     headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code == 429:
            raise AIUnavailable("額度用完或請求太頻繁") from None
        if error.code in (401, 403):
            raise AIUnavailable("金鑰無效或沒有權限") from None
        raise AIUnavailable(f"服務回應錯誤（{error.code}）") from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise AIUnavailable("連不上") from None


def _parse_json(text):
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):] if "{" in text else text
    start, end = text.find("{"), text.rfind("}")
    try:
        return json.loads(text[start:end + 1])
    except (ValueError, TypeError):
        raise AIUnavailable("回傳的不是 JSON") from None


def _schema_lower(value):
    if isinstance(value, dict):
        return {k: v.lower() if k == "type" and isinstance(v, str) else _schema_lower(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_schema_lower(item) for item in value]
    return value


def _json_instruction(schema):
    return ("請只回傳一個 JSON 物件，不要加說明文字或 Markdown，格式要符合這個 JSON Schema：\n"
            + json.dumps(_schema_lower(schema), ensure_ascii=False))


def _call_gemini(prompt, schema):
    from app.services import gemini_client
    # 由管理員的 AI 設定決定要不要用，所以直接帶 .env 的金鑰（不看 AI_ENABLED）
    return gemini_client.generate_json(prompt, schema, api_key=current_app.config.get("AI_API_KEY"),
                                       model=model("gemini"))


def _call_openai(prompt, schema):
    config = current_app.config
    base = (config.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    result = _post_json(f"{base}/chat/completions", {
        "model": model("openai"), "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": _json_instruction(schema)}, {"role": "user", "content": prompt}],
    }, {"Authorization": f"Bearer {config.get('OPENAI_API_KEY')}"})
    try:
        return _parse_json(result["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError):
        raise AIUnavailable("回傳格式不對") from None


def _call_anthropic(prompt, schema):
    result = _post_json("https://api.anthropic.com/v1/messages", {
        "model": model("anthropic"), "max_tokens": 8192, "system": _json_instruction(schema),
        "messages": [{"role": "user", "content": prompt}],
    }, {"x-api-key": current_app.config.get("ANTHROPIC_API_KEY") or "", "anthropic-version": "2023-06-01"})
    try:
        return _parse_json("".join(block.get("text", "") for block in result["content"]))
    except (KeyError, TypeError):
        raise AIUnavailable("回傳格式不對") from None


def _call_ollama(prompt, schema):
    url = (current_app.config.get("OLLAMA_URL") or "http://127.0.0.1:11434").rstrip("/")
    result = _post_json(f"{url}/api/chat", {
        "model": model("ollama"), "stream": False, "format": _schema_lower(schema), "options": {"temperature": 0.2},
        "messages": [{"role": "user", "content": prompt}],
    }, {}, timeout=600)
    try:
        return _parse_json(result["message"]["content"])
    except (KeyError, TypeError):
        raise AIUnavailable("回傳格式不對") from None


CALLERS = {"gemini": _call_gemini, "openai": _call_openai, "anthropic": _call_anthropic, "ollama": _call_ollama}


def generate_json(prompt, schema, documents=(), known=(), callers=None):
    """依順序試每一家 AI，回傳 (結果, 用的是哪一家)。全部失敗丟 AIUnavailable，訊息列出每家的原因。

    documents：本機檔案路徑，會轉成文字（圖片走 OCR）並去識別化後接在提示後面；known：要換成代號的個資值。
    """
    callers = callers or CALLERS
    parts = [prompt]
    for index, path in enumerate(documents, start=1):
        parts.append(f"\n\n文件 {index} 內容（已轉成文字並去識別化）：\n{document_text(path)}")
    text = redact("".join(parts), known)
    reasons = []
    for name in order():
        if not has_key(name):
            reasons.append(f"{PROVIDERS[name]['label']}：沒有金鑰")
            continue
        try:
            return callers[name](text, schema), name
        except AIUnavailable as error:
            reasons.append(f"{PROVIDERS[name]['label']}：{error}")
    raise AIUnavailable("所有 AI 都不能用：" + "；".join(reasons) if reasons else "管理員還沒有啟用任何 AI。")
