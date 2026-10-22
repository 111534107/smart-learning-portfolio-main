"""把科上文件（PDF／網頁）轉成 Markdown 知識庫，給「資管科小助手」查詢。

用法（需要 .env 的 Gemini 金鑰）：
    .venv\\Scripts\\python.exe scripts\\build_knowledge.py            # 只轉還沒有的檔案
    .venv\\Scripts\\python.exe scripts\\build_knowledge.py --force    # 全部重轉

產出：app/content/knowledge/*.md。檔案是一般 Markdown，規定改了可以直接手動修改。
注意：AI 轉寫可能有錯，正式使用前請對照原始文件（每個檔案開頭都有來源）。
"""

import re
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app  # noqa: E402
from app.services.gemini_client import AIUnavailable, generate_json  # noqa: E402

OUT = PROJECT_ROOT / "app" / "content" / "knowledge"
DOCS = PROJECT_ROOT / "school" / "Documents"
PUBLIC = PROJECT_ROOT / "school" / "public-sources"
INLINE_LIMIT = 14 * 1024 * 1024  # Gemini 一次最多約 20MB（含編碼），更大的檔案改用 File API 上傳

# (輸出檔名, 標題, 本機檔案, 公開網址)
SOURCES = [
    ("graduation-requirements", "113 學年度入學康寧資管科畢業門檻", DOCS / "113-康寧資管科畢業門檻.pdf", ""),
    ("two-year-admission-116", "116 二技技優甄審時程與備審加權", DOCS / "116二技技優甄審_時程與備審加權_修訂版.pdf", ""),
    ("project-review-rubric", "專題審查學習目標與評量對照表", DOCS / "專題審查學習目標與評量對照表.pdf", ""),
    ("retake-course-rules", "重補修選課原則", DOCS / "重補修選課原則簡報.pdf", ""),
    ("curriculum-planning", "資管科修業科目表（課程規劃）", PUBLIC / "im-curriculum-planning.html",
     "https://im.ukn.edu.tw/p/405-1028-609,c82-1.php"),
    ("project-submission-114", "114 學年度畢業專題書面資料繳交公告", PUBLIC / "im-project-submission-notice.html",
     "https://im.ukn.edu.tw/p/406-1028-42684,r16.php?Lang=zh-tw"),
    ("project-forms", "資管科專題相關表格", PUBLIC / "im-special-project-forms.html",
     "https://im.ukn.edu.tw/p/412-1028-1194.php?Lang=zh-tw"),
    ("transfer-department-1142", "114 學年度第 2 學期專科班校內轉科公告", PUBLIC / "ukn-transfer-department-notice.html",
     "https://www.ukn.edu.tw/p/406-1000-41802,r257.php?Lang=zh-tw"),
    ("practical-project-course", "實務專題課程大綱", PUBLIC / "ukn-course-schema-5345609.html",
     "https://ec.ukn.edu.tw/cschemaNew/CSBrowse.aspx?CSID=5345609&Annual=115"),
]

SCHEMA = {"type": "OBJECT", "properties": {"markdown": {"type": "STRING"}}, "required": ["markdown"]}
PROMPT = """請把這份康寧大學資管科的文件「完整轉寫」成繁體中文 Markdown，給學生查詢規定用。
規則：
1. 不要摘要、不要改寫、不要增加文件沒有的內容；所有數字、日期、條件、名額都要照原文。
2. 用「## 小標題」分段；表格用 Markdown 表格。
3. 網頁的選單、頁尾、版權、瀏覽人次等與內容無關的文字全部刪掉，只留正文。
4. 看不清楚的地方寫「（原文不清楚）」，不要猜。
"""


def upload_large(path):
    """超過 14MB 的 PDF 先用 Gemini File API 上傳（檔案 48 小時後會自動刪除），回傳 file_uri。"""
    import json
    import time
    import urllib.request
    from flask import current_app
    key = current_app.config["AI_API_KEY"]
    data = path.read_bytes()
    start = urllib.request.Request(
        "https://generativelanguage.googleapis.com/upload/v1beta/files",
        data=json.dumps({"file": {"display_name": path.stem}}).encode("utf-8"),
        headers={"x-goog-api-key": key, "Content-Type": "application/json",
                 "X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start",
                 "X-Goog-Upload-Header-Content-Length": str(len(data)),
                 "X-Goog-Upload-Header-Content-Type": "application/pdf"},
        method="POST")
    with urllib.request.urlopen(start, timeout=60) as response:
        upload_url = response.headers["X-Goog-Upload-URL"]
    finish = urllib.request.Request(upload_url, data=data, method="POST", headers={
        "Content-Length": str(len(data)), "X-Goog-Upload-Offset": "0", "X-Goog-Upload-Command": "upload, finalize"})
    with urllib.request.urlopen(finish, timeout=300) as response:
        info = json.loads(response.read())["file"]
    while info.get("state") == "PROCESSING":
        time.sleep(3)
        check = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/{info['name']}",
                                       headers={"x-goog-api-key": key})
        with urllib.request.urlopen(check, timeout=60) as response:
            info = json.loads(response.read())
    return info["uri"]


def page_text(path):
    text = path.read_bytes().decode("utf-8", errors="ignore")
    text = re.sub(r"(?is)<(script|style|nav|footer|header).*?</\1>", " ", text)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))[:150000]


def convert(slug, title, path, url):
    if path.suffix == ".pdf":
        if path.stat().st_size > INLINE_LIMIT:
            result = generate_json(PROMPT, SCHEMA, uploaded=[("application/pdf", upload_large(path))])
        else:
            result = generate_json(PROMPT, SCHEMA, files=[("application/pdf", path.read_bytes())])
    else:
        result = generate_json(PROMPT + "\n網頁文字：\n" + page_text(path), SCHEMA)
    header = (f"---\ntitle: {title}\nsource: {path.relative_to(PROJECT_ROOT).as_posix()}\n"
              f"url: {url}\nconverted: Gemini 自動轉寫（{date.today().isoformat()}），請對照原始文件核對\n---\n\n")
    (OUT / f"{slug}.md").write_text(header + f"# {title}\n\n" + result["markdown"].strip() + "\n", encoding="utf-8")
    return "完成"


def main():
    force = "--force" in sys.argv
    OUT.mkdir(parents=True, exist_ok=True)
    with create_app().app_context():
        for slug, title, path, url in SOURCES:
            if (OUT / f"{slug}.md").exists() and not force:
                print(f"{slug}：已存在，略過（加 --force 重轉）")
                continue
            try:
                print(f"{slug}：{convert(slug, title, path, url)}")
            except AIUnavailable as exc:
                print(f"{slug}：失敗 - {exc}")


if __name__ == "__main__":
    main()
