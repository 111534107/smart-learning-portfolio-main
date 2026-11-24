"""實習履歷的缺曠記錄：從查詢截圖（圖片或 PDF）自動讀出各項時數，或用學生已確認的學期合計加總。

缺曠資料只在本機處理，不送任何外部 AI（專案規定）；圖片用本機 RapidOCR，PDF 用本機文字解析。
讀出來的只是預填，學生可以逐格修改，判斷失敗時自己填。
"""

from io import BytesIO

from app.models import AttendanceSummary
from app.services import attendance_import
from app.services.internship_resume_draft import ABSENCE_ROWS

# 履歷表格的列 → 缺曠合計裡對應的項目名稱（總計由各項加總）
_ROW_SOURCE = {"曠課": "曠課", "遲到": "遲到", "事假": "事假", "病假": "病假", "生理假": "生理假",
               "公假": "公假", "喪假": "喪假"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024
_ROW_TOLERANCE = 0.6  # 同一行的文字：垂直中心差距小於行高的這個比例


class AbsenceReadError(ValueError):
    """讀不出來；訊息直接給學生看（中文）。"""


def _image_text(content):
    from PIL import Image, ImageOps, UnidentifiedImageError
    from app.services import ocr_engines
    try:
        with Image.open(BytesIO(content)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise AbsenceReadError("看不懂這個圖片，請改傳 PNG、JPG 或 PDF，或直接在表格裡填。") from None
    try:
        tokens = ocr_engines.recognize(image, engine="rapidocr")
    except RuntimeError:
        raise AbsenceReadError("本機文字辨識目前不能用，請直接在表格裡填。") from None
    return tokens_to_text(tokens)


def tokens_to_text(tokens):
    """把辨識出的文字區塊依位置排成一行一行（左到右、上到下）。"""
    boxes = [(t["bbox"], str(t.get("text", "")).strip()) for t in tokens if str(t.get("text", "")).strip()]
    boxes.sort(key=lambda b: ((b[0][1] + b[0][3]) / 2, b[0][0]))
    lines, current, center, height = [], [], None, 1
    for bbox, text in boxes:
        middle, h = (bbox[1] + bbox[3]) / 2, max(bbox[3] - bbox[1], 1)
        if center is None or abs(middle - center) <= height * _ROW_TOLERANCE:
            current.append((bbox[0], text))
            center = middle if center is None else (center + middle) / 2
            height = max(height, h)
        else:
            lines.append(current)
            current, center, height = [(bbox[0], text)], middle, h
    if current:
        lines.append(current)
    return "\n".join("  ".join(t for _, t in sorted(line)) for line in lines)


_FIX = str.maketrans({"遅": "遲", "丧": "喪", "项": "項", "旷": "曠", "课": "課", "计": "計", "时": "時", "总": "總",
                      "节": "節", "缺": "缺", "学": "學", "间": "間", "锻": "鍛"})
_NUM = __import__("re").compile(r"^[0-9]{1,3}$")


def parse_summary_table(text):
    """從辨認出的文字找學校畫面的「項目／合計」表（第一張）；回傳 ({項目: 時數}, 累計總時數或 None, 查詢區間文字)。

    辨認常把「遲」讀成「遅」、「喪」讀成「丧」，先統一字形再找。找不到回傳 None。
    """
    import re
    clean = text.translate(_FIX)
    lines = [re.sub(r"\s+", " ", line).strip() for line in clean.splitlines()]
    for index, line in enumerate(lines):
        if line.startswith("項目") and "曠課" in line and index + 1 < len(lines):
            labels = line.split()[1:]
            nxt = lines[index + 1]
            if not nxt.startswith("合計"):
                continue
            numbers = [t for t in nxt.split()[1:] if _NUM.match(t)]
            if len(numbers) < 3:
                continue
            totals = {label: int(num) for label, num in zip(labels, numbers)}
            overall = None
            match = re.search(r"至今缺課總時數為\s*([0-9]{1,3})\s*節", clean)
            if match:
                overall = int(match.group(1))
            span = re.search(r"([0-9]{3,4})\s*[VvＶ∨]?\s*至\s*([0-9]{3,4})", clean)
            term_text = f"{span.group(1)}至{span.group(2)}" if span else ""
            return totals, overall, term_text
    return None


TOTAL_LABEL = "至今缺課總時數"  # 學校查詢畫面上的累計總時數；範例履歷的「總計」填的是這個數，不是各項相加


def rows_from_totals(totals_by_label, term_text="", overall=None):
    """把 {項目: 時數} 轉成履歷表格 8 格（照 ABSENCE_ROWS 順序，每格寫成「N節」）。

    總計：只用學校畫面的「至今缺課總時數」（跟老師給的範例一致，不是各項相加）；
    讀不到就留空，請學生對照學校畫面自己填。
    """
    values = []
    for label in ABSENCE_ROWS:
        if label == "總計":
            values.append(f"{overall}節" if overall is not None else "")
            continue
        values.append(f"{int(totals_by_label.get(_ROW_SOURCE[label], 0) or 0)}節")
    return {"rows": values, "range": term_text}


def read_file(filename, content):
    """讀取查詢截圖（圖片或 PDF），回傳 {rows, range, source}。"""
    if not content:
        raise AbsenceReadError("沒有收到檔案。")
    if len(content) > MAX_IMAGE_BYTES:
        raise AbsenceReadError("檔案太大，請縮小到 8MB 以內。")
    is_pdf = content.startswith(b"%PDF-")
    try:
        text = attendance_import.pdf_text(content) if is_pdf else _image_text(content)
    except ValueError as exc:
        raise AbsenceReadError(str(exc)) from None
    found = parse_summary_table(text)
    if found:
        totals, overall, term_text = found
        result = rows_from_totals(totals, term_text, overall)
        result["source"] = "pdf" if is_pdf else "image"
        if overall is None:
            result["note"] = "總計沒有讀到，請對照學校畫面的「至今缺課總時數」自己填。"
        return result
    try:
        parsed = attendance_import.parse_totals(text, allow_range_preview=True)
    except attendance_import.NoTotals:
        raise AbsenceReadError("讀不出缺曠合計，請直接在表格裡填，或確認截圖包含「項目」和「合計」。") from None
    except ValueError as exc:
        raise AbsenceReadError(str(exc)) from None
    totals, overall = {}, None
    for row in parsed:
        for label, amount in row.items():
            if label in _ROW_SOURCE.values() and isinstance(amount, int):
                totals[label] = totals.get(label, 0) + amount
        if isinstance(row.get(TOTAL_LABEL), int):
            overall = row[TOTAL_LABEL]  # 累計值，取最後一個學期的
    terms = sorted({(row.get("school_year"), row.get("semester")) for row in parsed if row.get("school_year")})
    term_text = "、".join(f"{year}{semester}" for year, semester in terms if semester)
    result = rows_from_totals(totals, term_text, overall)
    result["source"] = "pdf" if is_pdf else "image"
    return result


def from_saved_records(student):
    """用學生已確認的學期缺曠合計加總；沒有紀錄回傳 None。"""
    summaries = AttendanceSummary.query.filter_by(student_id=student.id).order_by(
        AttendanceSummary.school_year, AttendanceSummary.semester).all()
    if not summaries:
        return None
    totals, overall = {}, None
    for summary in summaries:
        value = (summary.totals or {}).get(TOTAL_LABEL)
        if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
            overall = int(value)  # 累計值，取最後一個學期的
        for label, amount in (summary.totals or {}).items():
            if label in _ROW_SOURCE.values():
                try:
                    totals[label] = totals.get(label, 0) + int(amount or 0)
                except (TypeError, ValueError):
                    continue
    first, last = summaries[0], summaries[-1]
    term_text = f"{first.school_year}{first.semester}至{last.school_year}{last.semester}"
    result = rows_from_totals(totals, term_text, overall)
    result["source"] = "records"
    return result
