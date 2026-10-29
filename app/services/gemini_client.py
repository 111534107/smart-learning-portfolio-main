"""呼叫 Google Gemini，要求回傳固定格式的 JSON，或進行有工具呼叫的對話。

只用 Python 內建的 urllib，不需要另外安裝套件。
設定（放在 .env，不要 commit 金鑰）：
    AI_ENABLED=true
    AI_PROVIDER=gemini
    AI_API_KEY=你的金鑰（Google AI Studio 申請）
    GEMINI_MODEL=gemini-2.5-flash   （可省略）
"""

import base64
import json
import re
import time
import urllib.error
import urllib.request

from flask import current_app

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_RETRY_WAIT = 30  # 遇到「每分鐘次數用完」最多等幾秒再試一次


class AIUnavailable(RuntimeError):
    """AI 沒有設定，或呼叫失敗。訊息是給使用者看的中文。"""


def ai_ready():
    config = current_app.config
    return bool(config.get("AI_ENABLED") and config.get("AI_PROVIDER") == "gemini" and config.get("AI_API_KEY"))


def _retry_delay(error_body):
    """從 429 回應裡讀出 Google 建議等待的秒數（例如 "17s"）。"""
    match = re.search(r'"retryDelay":\s*"(\d+)', error_body)
    return int(match.group(1)) + 1 if match else 10


def _post(body, api_key, opener, model=None):
    """送出請求並回傳 JSON。免費額度有「每分鐘次數」限制，遇到 429 會等一下再試一次。"""
    if not api_key and not ai_ready():
        raise AIUnavailable("學校的 AI 目前沒有開啟，請稍後再試或洽系統管理員。")  # 設定方式寫在 .env.example，不給學生看變數名
    request = urllib.request.Request(
        API_URL.format(model=model or current_app.config.get("GEMINI_MODEL", "gemini-2.5-flash")),
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key or current_app.config["AI_API_KEY"]},
        method="POST",
    )
    for attempt in (1, 2):
        try:
            with opener(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                wait = _retry_delay(exc.read().decode("utf-8", "ignore") if exc.fp else "")
                if attempt == 1 and wait <= MAX_RETRY_WAIT:
                    time.sleep(wait)
                    continue
                if wait > 3600:
                    raise AIUnavailable("今天的 AI 免費額度已經用完了，明天會自動恢復；急用可以改用自己的金鑰。") from None
                raise AIUnavailable("AI 額度暫時用完了（每分鐘次數有限制），請過一分鐘再試，或改用自己的金鑰。") from None
            if exc.code in (400, 401, 403):
                raise AIUnavailable(f"金鑰無效或沒有權限（HTTP {exc.code}），請確認金鑰是否正確。") from None
            raise AIUnavailable(f"Gemini 回應錯誤（HTTP {exc.code}），請稍後再試。") from None
        except (urllib.error.URLError, TimeoutError):
            # from None：不把原始錯誤（可能含請求內容）串進例外，避免金鑰出現在錯誤紀錄
            raise AIUnavailable("連不到 Gemini，請確認網路後再試一次。") from None


def generate_json(prompt, schema, files=None, api_key=None, opener=urllib.request.urlopen, uploaded=None):
    """送出提示詞（可附 PDF 或圖片），回傳 Gemini 依 schema 產生的 dict。

    files：[(MIME 類型, 檔案 bytes), ...]
    api_key：學生自己的金鑰，只用這一次；不會存檔、不寫進紀錄。沒給就用 .env 的學校金鑰。
    opener：測試時可以換成假的，不會真的連網路。
    uploaded：已用 File API 上傳的大檔案 [(MIME 類型, file_uri), ...]
    """
    parts = [{"text": prompt}]
    for mime_type, data in files or []:
        parts.append({"inline_data": {"mime_type": mime_type, "data": base64.b64encode(data).decode("ascii")}})
    for mime_type, uri in uploaded or []:
        parts.append({"file_data": {"mime_type": mime_type, "file_uri": uri}})
    payload = _post({
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": schema, "temperature": 0.4},
    }, api_key, opener)
    try:
        return json.loads(payload["candidates"][0]["content"]["parts"][0]["text"])
    except (KeyError, IndexError, json.JSONDecodeError):
        raise AIUnavailable("Gemini 回傳的格式不正確，請再試一次。") from None


def chat(contents, tools, system_instruction, api_key=None, opener=urllib.request.urlopen):
    """多輪對話＋工具呼叫（function calling），回傳模型這一輪的 content（可能是文字或工具呼叫）。

    contents：對話紀錄，格式為 [{"role": "user"/"model", "parts": [...]}]
    tools：工具說明（functionDeclarations），讓 AI 自己決定要查什麼
    """
    payload = _post({
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "contents": contents,
        "tools": [{"functionDeclarations": tools}],
        "generationConfig": {"temperature": 0.3},
    }, api_key, opener, model=current_app.config.get("ASSISTANT_MODEL"))
    try:
        return payload["candidates"][0]["content"]
    except (KeyError, IndexError):
        raise AIUnavailable("小助手這次沒有產生回答，請換個方式再問一次。") from None
