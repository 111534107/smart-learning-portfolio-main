"""將會議錄音送至 Gemini，輸出逐字稿與整理版會議紀錄。

用法：
    .venv\\Scripts\\python.exe scripts\\transcribe_meeting_audio.py

錄音檔不會複製進專案；Gemini File API 的暫存檔由 Google 自動清理。
輸出集中在 docs/06_會議錄音與逐字稿/。
"""

import json
import time
import urllib.request
from datetime import date
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
AUDIO = Path(r"C:\Users\lisa2\Downloads\專題討論-開發科助使用者端和小助手.m4a")
OUT = ROOT / "docs" / "06_會議錄音與逐字稿"
MODEL = "gemini-flash-lite-latest"


def upload_audio(api_key):
    data = AUDIO.read_bytes()
    start = urllib.request.Request(
        "https://generativelanguage.googleapis.com/upload/v1beta/files",
        data=json.dumps({"file": {"display_name": AUDIO.stem}}).encode("utf-8"),
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(len(data)),
            "X-Goog-Upload-Header-Content-Type": "audio/mp4",
        },
        method="POST",
    )
    with urllib.request.urlopen(start, timeout=60) as response:
        upload_url = response.headers["X-Goog-Upload-URL"]

    finish = urllib.request.Request(
        upload_url,
        data=data,
        headers={
            "Content-Length": str(len(data)),
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize",
        },
        method="POST",
    )
    with urllib.request.urlopen(finish, timeout=300) as response:
        info = json.loads(response.read())["file"]

    while info.get("state") == "PROCESSING":
        time.sleep(3)
        check = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/{info['name']}",
            headers={"x-goog-api-key": api_key},
        )
        with urllib.request.urlopen(check, timeout=60) as response:
            info = json.loads(response.read())["file"]
    if info.get("state") == "FAILED":
        raise RuntimeError("Gemini 無法處理這個錄音檔。")
    return info["uri"]


def transcribe(api_key, file_uri):
    prompt = """請處理這段繁體中文專題討論錄音，輸出 JSON。

要求：
1. transcript：盡可能完整的逐字稿，依說話者分段；無法辨認時寫【聽不清楚】，不要猜測。
2. meeting_record：整理成繁體中文會議紀錄，包含「討論主題、討論重點、已確認事項、待確認事項、後續工作」。
3. 這是一段真實討論，請保留原意，不要把推測內容寫成決議。
4. 專有名詞請盡量依上下文保留，例如「科助使用者端」、「資管科小助手」、「AI Agent」、「導師」、「系統管理員」。
5. 不要加入錄音中沒有提到的人名、日期、決策或技術細節。
"""
    payload = {
        "contents": [{"role": "user", "parts": [
            {"text": prompt},
            {"file_data": {"mime_type": "audio/mp4", "file_uri": file_uri}},
        ]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "transcript": {"type": "STRING"},
                    "meeting_record": {"type": "STRING"},
                },
                "required": ["transcript", "meeting_record"],
            },
            "temperature": 0.1,
            "maxOutputTokens": 32768,
        },
    }
    request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        body = json.loads(response.read())
    text = body["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


def main():
    if not AUDIO.exists():
        raise SystemExit(f"找不到錄音檔：{AUDIO}")
    load_dotenv(ROOT / ".env")
    import os
    api_key = os.getenv("AI_API_KEY", "")
    if not api_key:
        raise SystemExit(".env 沒有設定 AI_API_KEY。")

    OUT.mkdir(parents=True, exist_ok=True)
    print("正在上傳錄音供 Gemini 暫時處理……")
    uri = upload_audio(api_key)
    print("正在轉錄與整理，請稍候……")
    result = transcribe(api_key, uri)
    stamp = date.today().isoformat()
    transcript_path = OUT / f"AI_逐字稿_科助使用者端與小助手_{stamp}.txt"
    record_path = OUT / f"AI_會議紀錄_科助使用者端與小助手_{stamp}.md"
    transcript_path.write_text(result["transcript"].strip() + "\n", encoding="utf-8")
    record = (
        f"# 專題討論會議紀錄：科助使用者端與小助手\n\n"
        f"- 錄音檔：`{AUDIO.name}`\n"
        f"- 整理日期：{stamp}\n"
        f"- 處理方式：Gemini 暫時轉錄；原始錄音未複製到專案\n"
        f"- 注意：逐字稿與整理內容仍需由組員對照錄音確認，標示【聽不清楚】處不得直接當作決議。\n\n"
        f"{result['meeting_record'].strip()}\n"
    )
    record_path.write_text(record, encoding="utf-8")
    print(transcript_path)
    print(record_path)


if __name__ == "__main__":
    main()
