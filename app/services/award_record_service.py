"""獎懲記錄：學生從學校系統下載（和成績單一樣），上傳後由 AI 逐列讀出並分類。

規則（寫在這裡，方便報告時說明）：
- 獎勵（嘉獎、小功、大功）：學生確認後才寫進「活動與經歷」，來源標示「學校獎懲記錄」。
- 懲處（警告、小過、大過等）：一律保存在 school_award_records，供備審資料使用，但不進「活動與經歷」。
  懲處不預設勾選，也不會自動放進學生的經歷列表；銷過的懲處照實保存並標示銷過欄原文。
- 已銷過的獎勵：略過，不存（銷過就不算成果）。
- 出席表現（全勤等，app/content/award_rules.json 的 default_off）：預設不勾選，學生想保留才勾。
- 分類先看 app/content/award_rules.json 的關鍵字規則（科上可自己改），比不到才用 AI 的建議，
  兩者都沒有就留空，請學生自己選。
- 「1141學期…」開頭的事由，讀成 114 學年度第 1 學期。
"""

import csv
import io
import json
import re
from functools import lru_cache
from hashlib import sha256
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


def is_default_off(reason):
    """出席表現類（例如全勤）：匯入時預設不勾選。"""
    return any(all(word in reason for word in rule["keywords"]) for rule in _rules().get("default_off", []))


def parse_semester(reason):
    """「1141學期…」「111(1)…」「111（1）…」「111-1…」→ (114, 1)；讀不到回傳 (None, None)。"""
    match = re.match(r"\s*(\d{3})([12])", reason or "")  # 1141學期…
    if not match:
        match = re.match(r"\s*(\d{3})\s*[(（\-－]\s*([12])\s*[)）]?", reason or "")  # 111(1)、111-1
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def record_key(*parts):
    """同一列獎懲記錄的指紋，用來防止重複匯入（不看學生之後怎麼改事由）。"""
    return sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()


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
    """整理成確認頁要用的資料：獎勵給學生勾選，懲處另外保存，已銷過的獎勵略過。"""
    rewards = set(_rules()["rewards"])
    draft, punishments = [], []
    skipped_revoked = skipped_empty = 0
    for row in rows:
        reason = (row.get("reason") or "").strip()
        name = (row.get("name") or "").strip()
        revoked = (row.get("revoked") or "").strip()
        if not reason or not name:
            skipped_empty += 1
            continue
        date = (row.get("date") or "").strip()
        count = row.get("count") or 1
        school_year, semester = parse_semester(reason)

        if name not in rewards:
            # 懲處：照實保存（含銷過欄原文），不進活動與經歷
            punishments.append({
                "key": record_key("punishment", date, name, count, reason),
                "date": date, "name": name, "count": count, "reason": reason, "revoked": revoked,
                "school_year": school_year, "semester": semester,
            })
            continue
        if revoked:
            skipped_revoked += 1
            continue

        ai_category = row.get("category")
        category = classify(reason) or (ai_category if ai_category in EXPERIENCE_CATEGORIES else "")
        draft.append({
            "key": record_key("reward", date, name, count, reason),
            "reason": reason,
            "category": category,
            "school_year": school_year or "",
            "semester": semester or "",
            "detail": f"{date} {name}{count}次".strip(),
            "include": not is_default_off(reason),
        })

    warnings = list(warnings or [])
    if skipped_revoked:
        warnings.append(f"已略過 {skipped_revoked} 筆已銷過的獎勵，這些不會存進系統。")
    if skipped_empty:
        warnings.append(f"已略過 {skipped_empty} 筆沒有事由或名稱的列。")
    if punishments:
        warnings.append(f"有 {len(punishments)} 筆懲處紀錄會保存供備審資料使用，但不會放進「活動與經歷」。")
    if any(not row["include"] for row in draft):
        warnings.append("出席表現（例如全勤）預設不勾選；如果想保留，請自己勾選。")
    if draft or punishments:
        warnings.append("AI 讀的字可能有錯，請對照原始檔逐列檢查；類別是建議，可以改。")
    return {"rows": draft, "punishments": punishments, "warnings": warnings}


PASTE_HEADER = ["學號", "姓名", "獎懲日期", "獎懲名稱", "數量", "獎懲事由", "銷過"]


def parse_pasted_table(text, student_no):
    """讀取從學校網頁「查歷年獎懲」複製貼上的表格（Tab 分隔、含表頭）；不送 AI，全部在本機處理。

    取自組員 111534107/smart-learning-portfolio-main 7282998。學號要和目前帳號相同，避免貼到別人的資料。
    """
    if not text or len(text) > 200000:
        raise ValueError("請貼上獎懲表格，內容不可超過 20 萬字。")
    try:
        table = list(csv.reader(io.StringIO(text, newline=""), delimiter="\t"))
    except csv.Error as exc:
        raise ValueError("表格格式無法辨識，請連同標題重新複製貼上。") from exc
    table = [row for row in table if any(cell.strip() for cell in row)]
    if not table or len(table) > 1001:
        raise ValueError("請貼上完整表格，每次最多 1000 筆。")
    header = [re.sub(r"\s+", "", cell) for cell in table[0]]
    if header[:len(PASTE_HEADER)] != PASTE_HEADER:
        raise ValueError("無法辨識表格欄位，請從學校系統連同表頭（學號、姓名、獎懲日期…）一起複製。")
    rows = []
    for index, cells in enumerate(table[1:], start=2):
        if len(cells) == 6:
            cells.append("")  # 複製時可能省略最後空白的「銷過」欄
        if len(cells) < len(PASTE_HEADER):
            raise ValueError(f"第 {index} 列欄位不完整，請重新複製整列。")
        number, _, date, name, count, reason, revoked = [cell.strip() for cell in cells[:len(PASTE_HEADER)]]
        if not student_no or number != student_no:
            raise ValueError(f"第 {index} 列學號與目前帳號不一致，請確認複製的是自己的資料。")
        if not date or not name or not reason or (count and not count.isdigit()):
            raise ValueError(f"第 {index} 列內容不完整，請檢查日期、獎懲名稱、數量及事由。")
        rows.append({"date": date, "name": name, "count": int(count) if count else 1,
                     "reason": " ".join(reason.split()), "revoked": revoked})
    if not rows:
        raise ValueError("沒有找到資料列，請連同表頭及獎懲紀錄一起複製。")
    return rows
