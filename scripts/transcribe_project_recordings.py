"""Transcribe project meeting recordings with Gemini File API.

This script reads recordings from the project backup folder, sends them to
Gemini temporarily with explicit user consent, and writes a transcript plus
meeting record for each file under docs/06_會議錄音與逐字稿/.
"""

import json
import os
import re
import time
import urllib.request
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
AUDIO_DIR = ROOT.parent / "backup" / "專題素材" / "錄音"
OUT = ROOT / "docs" / "06_會議錄音與逐字稿"
MODEL = "gemini-flash-lite-latest"


def safe_name(name: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", name).strip("_")


def upload_audio(api_key: str, audio: Path) -> str:
    data = audio.read_bytes()
    start = urllib.request.Request(
        "https://generativelanguage.googleapis.com/upload/v1beta/files",
        data=json.dumps({"file": {"display_name": audio.stem}}).encode("utf-8"),
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


def transcribe(api_key: str, file_uri: str, filename: str) -> dict[str, str]:
    prompt = f"""請處理這段繁體中文專題開發討論錄音，輸出 JSON。

錄音檔名：{filename}

要求：
1. transcript：盡可能完整的逐字稿，依說話者或話題分段；無法辨認時寫【聽不清楚】，不要猜測。
2. meeting_record：繁體中文會議紀錄，包含「討論主題、討論重點、已確認事項、待確認事項、後續工作」。
3. timeline_facts：只列出錄音中明確提到、可放進專題開發時間線的事實與決策，每項一行；若沒有就寫「無」。
4. 這是真實討論，請保留原意，不要把推測內容寫成決議。
5. 不要加入錄音中沒有提到的人名、日期、決策或技術細節。
6. 角色與專有名詞請依錄音內容辨識，例如指導老師、科助、學生、導師、科辦、AI Agent、學習歷程。
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
                    "timeline_facts": {"type": "STRING"},
                },
                "required": ["transcript", "meeting_record", "timeline_facts"],
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
    with urllib.request.urlopen(request, timeout=900) as response:
        body = json.loads(response.read())
    text = body["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


def main() -> None:
    load_dotenv(ROOT / ".env")
    api_key = os.getenv("AI_API_KEY", "")
    if not api_key:
        raise SystemExit(".env 沒有設定 AI_API_KEY。")
    if not AUDIO_DIR.exists():
        raise SystemExit(f"找不到錄音資料夾：{AUDIO_DIR}")

    OUT.mkdir(parents=True, exist_ok=True)
    audios = sorted(AUDIO_DIR.glob("*.m4a"), key=lambda p: p.name)
    if not audios:
        raise SystemExit("找不到 .m4a 錄音檔。")

    for index, audio in enumerate(audios, start=1):
        stem = safe_name(audio.stem)
        transcript_path = OUT / f"AI_逐字稿_{stem}.txt"
        record_path = OUT / f"AI_會議紀錄_{stem}.md"
        if transcript_path.exists() and record_path.exists():
            print(f"跳過已完成：{audio.name}", flush=True)
            continue
        print(f"[{index}/{len(audios)}] 上傳：{audio.name}", flush=True)
        uri = upload_audio(api_key, audio)
        print(f"[{index}/{len(audios)}] 整理：{audio.name}", flush=True)
        result = transcribe(api_key, uri, audio.name)
        transcript_path.write_text(result["transcript"].strip() + "\n", encoding="utf-8")
        record = (
            f"# 專題討論會議紀錄：{audio.stem}\n\n"
            f"- 錄音檔：`{audio.name}`\n"
            f"- 錄音日期：`{audio.name[:10]}`\n"
            f"- 處理方式：Gemini 暫時轉錄；原始錄音未複製到專案\n"
            f"- 注意：逐字稿與整理內容仍需由組員對照錄音確認；標示【聽不清楚】處不得直接當作決議。\n\n"
            f"{result['meeting_record'].strip()}\n\n"
            f"## 可放入開發時間線的錄音事實\n\n"
            f"{result['timeline_facts'].strip()}\n"
        )
        record_path.write_text(record, encoding="utf-8")
        print(f"[{index}/{len(audios)}] 完成：{record_path.name}", flush=True)


if __name__ == "__main__":
    main()
