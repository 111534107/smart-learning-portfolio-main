"""獎懲記錄：學生從學校系統下載（和成績單一樣），上傳後由 AI 逐列讀出並分類。

規則（寫在這裡，方便報告時說明）：
- 只匯入「獎」（嘉獎、小功、大功）；警告、小過等懲處與已銷過的列一律略過，不存、不顯示。
- 分類先看 app/content/award_rules.json 的關鍵字規則（科上可自己改），比不到才用 AI 的建議，
  兩者都沒有就留空，請學生自己選。
- 「1141學期…」開頭的事由，讀成 114 學年度第 1 學期。
- 學生確認後才寫進「活動與經歷」，來源標示「學校獎懲記錄」，學生之後可以修改內容。
"""

import json
import re
from functools import lru_cache
from pathlib import Path

from app.services import gemini_client
from app.services.journey_service import EXPERIENCE_CATEGORIES

RULES_FILE = Path(__file__).resolve().parents[1] / "content" / "award_rules.json"
MIME_TYPES = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
BLANK_ROWS = 3  # 沒有 AI 時，確認頁先給幾列空白讓學生手動填

ROW_SCHEMA = {
    "type": "object",
    "properties": {
        "rows": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "獎懲日期，照原文，例如 2025/12/30"},
                    "name": {"type": "string", "description": "獎懲名稱，例如 嘉獎、小功、警告"},
                    "count": {"type": "integer", "description": "數量"},
                    "reason": {"type": "string", "description": "獎懲事由，完整照抄原文，不要改寫"},
                    "revoked": {"type": "string", "description": "銷過欄位的內容，沒有就空字串"},
                    "category": {"type": "string", "enum": EXPERIENCE_CATEGORIES + ["none"],
                                 "description": "activity 活動、competition 競賽、service 服務學習、leadership 幹部經歷；都不像就填 none"},
                },
                "required": ["date", "name", "count", "reason", "revoked", "category"],
            },
        },
    },
    "required": ["rows"],
}

PROMPT = """這是一位學生從學校系統下載的「獎懲記錄查詢」。請逐列讀出表格，每一列一筆，不要合併、不要漏列，
事由要完整照抄原文。看不清楚的字就照你看到的寫，不要自己編。
category 依事由判斷：參加比賽或得獎→competition；協助科上、服務、志工→service；班級幹部、小老師→leadership；
其他校內活動→activity；都不像→none。"""


@lru_cache(maxsize=1)
def _rules():
    return json.loads(RULES_FILE.read_text(encoding="utf-8"))


def classify(reason):
    """依設定檔的關鍵字分類；比不到回傳 None。"""
    for rule in _rules()["rules"]:
        if all(word in reason for word in rule["keywords"]):
            return rule["category"]
    return None


def parse_semester(reason):
    """「1141學期…」→ (114, 1)；讀不到回傳 (None, None)。"""
    match = re.match(r"\s*(\d{3})([12])", reason or "")
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def extract_rows(file_path, display_name):
    """把檔案交給 AI 逐列讀出。回傳 (rows, warnings)；沒有 AI 時 rows 是空的。"""
    if not gemini_client.ai_ready():
        return [], ["尚未接上 AI，請對照上方的原始檔，自己把要匯入的列填進下面的表格。"]
    mime_type = MIME_TYPES.get(Path(display_name).suffix.lower())
    if not mime_type:
        return [], ["這種檔案 AI 讀不了，請改傳 PDF 或照片，或自己填寫下面的表格。"]
    try:
        result = gemini_client.generate_json(PROMPT, ROW_SCHEMA, files=[(mime_type, Path(file_path).read_bytes())])
    except gemini_client.AIUnavailable as exc:
        return [], [f"AI 這次沒有讀出來：{exc} 你可以重新上傳，或自己填寫下面的表格。"]
    return result.get("rows") or [], []


def build_draft(rows, warnings=None):
    """過濾掉懲處與已銷過的列，補上建議類別與學年度，給學生確認。"""
    rewards = set(_rules()["rewards"])
    draft, skipped = [], 0
    for row in rows:
        reason = (row.get("reason") or "").strip()
        if not reason or row.get("name") not in rewards or (row.get("revoked") or "").strip():
            skipped += 1
            continue
        ai_category = row.get("category")
        category = classify(reason) or (ai_category if ai_category in EXPERIENCE_CATEGORIES else "")
        school_year, semester = parse_semester(reason)
        draft.append({
            "reason": reason,
            "category": category,
            "school_year": school_year or "",
            "semester": semester or "",
            "detail": f"{row.get('date', '')} {row.get('name', '')}{row.get('count') or 1}次".strip(),
        })
    warnings = list(warnings or [])
    if skipped:
        warnings.append(f"已略過 {skipped} 筆懲處、已銷過或沒有事由的紀錄，這些不會存進系統。")
    if draft:
        warnings.append("AI 讀的字可能有錯，請對照原始檔逐列檢查；類別是建議，可以改。")
    return {"rows": draft, "warnings": warnings}
