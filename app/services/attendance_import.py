"""Read attendance details for preview and school-term totals for confirmation."""

from contextlib import closing
from datetime import date
import re
import unicodedata

import pypdfium2 as pdfium


LABELS = ("曠課", "遲到", "事假", "病假", "生理假", "心理假", "公假", "喪假", "產假", "婚假",
          "疫苗假", "應上課 1/3 總時數", "至今缺課總時數")
ABSENCE_LABELS = LABELS[:-2]
HOURS_LABELS = LABELS[-2:]
EXCEPTION_PREFIX = "exception_"
EXCEPTION_TOTALS = "exception_totals"
EXCEPTION_HEADING = "實習、調補課及其他請假"
FORM_LABELS = (*LABELS, *(EXCEPTION_PREFIX + label for label in ABSENCE_LABELS))
MAX_BYTES = 5 * 1024 * 1024
MAX_TERMS = 20
YEAR = "school_year"
TERM = "semester"
HEADERS = {"學年度": YEAR, "學年": YEAR, "學期": TERM, "節次": "節次",
           "曠課節數": "曠課", "遲到次數": "遲到", "缺課總時數": "至今缺課總時數",
           **{label.replace(" ", ""): label for label in LABELS}}
NO_TOTALS = "請將校方起訖學年期選成同一學期，再複製畫面底部包含「項目」和「合計」的表格。"
_DAILY_DATE = re.compile(r"[0-9]{2,4}[/.-][0-9]{1,2}[/.-][0-9]{1,2}")
_PERIODS = ("朝會", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
            "十一", "十二", "十三", "十四", "十五")
_MAX_DAILY_ROWS = 500
_DAILY_LABELS = {*ABSENCE_LABELS, "朝會未到", "朝會請假"}
_UNALIGNED_ROW = "[節次位置未確認]"


class NoTotals(ValueError):
    """The source did not contain a recognizable summary."""


def looks_like_school_attendance(text):
    """Recognize school attendance by its title, summary headers or daily rows."""
    text = unicodedata.normalize("NFKC", text)
    for raw in text.splitlines():
        line = raw.strip()
        if re.sub(r"\s+", "", line) in {"缺曠記錄查詢", "缺曠紀錄查詢"}:
            return True
        cells = line.split()
        if _daily_header(cells) or (cells and cells[0] == "項目" and set(cells[1:]).intersection(ABSENCE_LABELS)):
            return True
        if cells and _DAILY_DATE.fullmatch(cells[0]) and set(cells[1:]).intersection(_DAILY_LABELS):
            return True
    return False


def pdf_text(content):
    if not content.startswith(b"%PDF-"):
        raise ValueError("請選擇有效的 PDF。")
    try:
        with closing(pdfium.PdfDocument(content)) as document:
            if not 1 <= len(document) <= 10:
                raise ValueError("請上傳 1 至 10 頁的缺曠合計 PDF。")
            parts = []
            period_columns = []
            for page in document:
                with closing(page), closing(page.get_textpage()) as text_page:
                    parts.append(_page_rows(text_page, period_columns))
            return "\n\n".join(parts)
    except pdfium.PdfiumError:
        raise ValueError("PDF 無法讀取，請確認檔案完整且未加密。") from None


def _page_rows(text_page, column_positions):
    """Recover visual rows even if the PDF stores text in column order."""
    chars = []
    if text_page.count_chars() > 25000:
        raise ValueError("PDF 單頁文字過多，請只上傳缺曠合計頁。")
    for index in range(text_page.count_chars()):
        char = chr(pdfium.raw.FPDFText_GetUnicode(text_page.raw, index))
        if char.isspace() or not char.isprintable():
            continue
        left, bottom, right, top = text_page.get_charbox(index)
        if right > left and top > bottom:
            chars.append(((bottom + top) / 2, left, right, char))
    bands = []
    for y, left, right, char in sorted(chars, reverse=True):
        if not bands or bands[-1][0] - y > 5:
            bands.append((y, []))
        bands[-1][1].append((left, right, char))
    rows = []
    for _, band in bands:
        cells = []
        previous_right = None
        for left, right, char in sorted(band):
            if previous_right is None or left - previous_right > 7:
                cells.append((left, char))
            else:
                start, value = cells[-1]
                cells[-1] = (start, value + char)
            previous_right = right
        if not cells:
            continue
        values = [value for _, value in cells]
        if _daily_header(values):
            column_positions[:] = [left for left, _ in cells]
        elif column_positions and _DAILY_DATE.fullmatch(values[0]):
            # School detail columns are left-aligned. Missing periods stay empty.
            aligned = [values[0]] + [""] * (len(column_positions) - 1)
            for left, value in cells[1:]:
                column = min(range(1, len(column_positions)), key=lambda i: abs(column_positions[i] - left))
                if abs(column_positions[column] - left) > 8 or aligned[column]:
                    aligned = [values[0], _UNALIGNED_ROW]
                    break
                aligned[column] = value
            rows.append("\t".join(aligned))
            continue
        elif values[0] == "項目":
            column_positions.clear()
        rows.append("\t".join(values))
    return "\n".join(rows)


def _daily_header(cells):
    return (len(cells) > 1 and cells[0] in {"日期", "缺曠日期"}
            and len(set(cells[1:])) == len(cells) - 1
            and all(cell in _PERIODS for cell in cells[1:]))


def _calendar_date(value):
    year, month, day = re.split(r"[/.-]", value)
    calendar_year = int(year)
    if calendar_year == 0:
        return None
    if len(year) < 4:
        calendar_year += 1911
    try:
        return date(calendar_year, int(month), int(day))
    except ValueError:
        return None


def daily_table(text):
    """Read positional cells only when the school period header is available."""
    columns = []
    active = None
    rows = []
    unaligned_dates = set()
    invalid_dates = set()
    calendar_dates = []
    has_unknown_labels = False
    for line in unicodedata.normalize("NFKC", text).splitlines():
        cells = [cell.strip() for cell in line.strip("\t ").split("\t")]
        if not cells:
            continue
        if _daily_header(cells):
            active = cells[1:]
            columns = [period for period in _PERIODS if period in {*columns, *active}]
            continue
        if cells[0] == "項目":
            active = None
        if not active or not _DAILY_DATE.fullmatch(cells[0]):
            continue
        date_text, *values = cells
        actual_date = _calendar_date(date_text)
        if actual_date is None:
            invalid_dates.add(date_text)
            marks = {}
        elif len(values) > len(active) or _UNALIGNED_ROW in values or any(len(value) > 40 for value in values):
            unaligned_dates.add(date_text)
            marks = {}
        else:
            marks = {period: value for period, value in zip(active, values) if value}
            has_unknown_labels |= any(value not in _DAILY_LABELS for value in marks.values())
        if marks or date_text in invalid_dates or date_text in unaligned_dates:
            rows.append((date_text, marks))
            if actual_date is not None:
                calendar_dates.append(actual_date)
            if len(rows) > _MAX_DAILY_ROWS:
                raise ValueError("逐日明細超過 500 筆，請縮短校方查詢範圍再匯入。")
    if not rows:
        return None
    return {
        "columns": columns,
        "rows": rows,
        "unaligned_dates": unaligned_dates,
        "invalid_dates": invalid_dates,
        # This is a conservative guard, never an attempt to infer term boundaries.
        "overlong_span": bool(calendar_dates and (max(calendar_dates) - min(calendar_dates)).days >= 365),
        "has_unknown_labels": has_unknown_labels,
    }


def source_term_range(text):
    compact = re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))
    match = re.search(r"學年期:?([0-9]{3}[12])(?![0-9])(?:(?:至|到|[-~])([0-9]{3}[12])(?![0-9]))?", compact)
    return match.groups() if match else (None, None)

def _key(cell):
    return HEADERS.get(re.sub(r"\s+", "", cell))


def _number(value, low, high):
    value = unicodedata.normalize("NFKC", value).strip()
    if re.fullmatch(r"[0-9]{1,5}", value) and low <= int(value) <= high:
        return int(value)
    raise ValueError("請檢查學年度、學期和各欄的合計數字。")


def validated_row(values):
    year = _number(values.get(YEAR, ""), 1, 999)
    term = values.get(TERM, "").strip()
    term = {"上": "1", "上學期": "1", "下": "2", "下學期": "2"}.get(term, term)
    semester = _number(term, 1, 2)
    totals = {label: _number(values[label], 0, 99999) for label in FORM_LABELS if values.get(label, "").strip()}
    if not totals:
        raise ValueError("請填寫至少一項缺曠合計。")
    return {"school_year": year, "semester": semester, **totals}


def parse_totals(text, *, allow_range_preview=False):
    """Read the school's summary first, then the existing term-based formats."""
    school_row = _school_summary(text, allow_range_preview=allow_range_preview)
    if school_row is not None:
        return [school_row]
    rows = []
    headers = []
    labelled = {}
    for line in unicodedata.normalize("NFKC", text).splitlines():
        line = line.strip(" \r")
        if not line:
            continue
        cells = re.split(r"\t| {2,}", line) if re.search(r"\t| {2,}", line) else line.split()
        keys = [_key(cell) for cell in cells]
        if YEAR in keys and TERM in keys and any(key in LABELS for key in keys):
            known = [key for key in keys if key]
            detail_columns = {"日期", "缺曠日期", "缺席日期", "課程", "課程名稱", "科目", "節次"}
            headers = keys if len(set(known)) == len(known) and not detail_columns.intersection(cells) else []
            continue
        if headers and len(headers) == len(cells):
            values = {key: cell for key, cell in zip(headers, cells) if key}
            if re.fullmatch(r"[0-9]{1,3}", values[YEAR]):
                rows.append(validated_row(values))
                continue
        match = re.fullmatch(r"(.+?)\s*:\s*(\S+)", line)
        if match and (key := _key(match[1])) in (YEAR, TERM, *LABELS):
            if key in labelled:
                if set(labelled) >= {YEAR, TERM} and any(label in labelled for label in LABELS):
                    rows.append(validated_row(labelled))
                labelled = {}
            labelled[key] = match[2]
    if set(labelled) >= {YEAR, TERM} and any(label in labelled for label in LABELS):
        rows.append(validated_row(labelled))
    if not rows:
        raise NoTotals(NO_TOTALS)
    check_terms(rows)
    return rows


def _school_summary(text, *, allow_range_preview=False):
    # Read only the labelled totals; ignore dates, personal details, and individual periods.
    text = unicodedata.normalize("NFKC", text)
    compact = re.sub(r"\s+", "", text)
    start, end = source_term_range(text)
    if start and end and start != end and not allow_range_preview:
        raise ValueError("校方查詢涵蓋多個學期。請把起訖學年期選成同一學期，再重新匯入。")
    if "項目" not in compact or "合計" not in compact:
        return None

    row = {}
    if start and (not end or start == end):
        row[YEAR], row[TERM] = int(start[:3]), int(start[3])

    for label in HOURS_LABELS:
        match = re.search(re.escape(label.replace(" ", "")) + r"(?:為|:)?([0-9]{1,5})節", compact)
        if match:
            row[label] = int(match[1])

    groups = set()
    prefix = ""
    columns = []
    for line in text.splitlines():
        if EXCEPTION_HEADING in re.sub(r"\s+", "", line):
            prefix = EXCEPTION_PREFIX
            columns = []
            continue
        line = line.strip(" \r")
        cells = re.split(r"\t| {2,}", line) if re.search(r"\t| {2,}", line) else line.split()
        cells = [cell.strip() for cell in cells]
        if cells and cells[0] == "項目":
            labels = [_key(cell) for cell in cells[1:]]
            valid = labels and all(label in ABSENCE_LABELS for label in labels)
            columns = labels if valid and len(set(labels)) == len(labels) else []
        elif cells and cells[0] == "合計" and columns:
            if prefix in groups:
                raise ValueError("同一組出現兩張合計表。請保留各組標題及一列合計。")
            if len(cells) != len(columns) + 1:
                raise ValueError("合計欄位與表頭數量不同。請重新複製完整表格，空格請保留。")
            for label, value in zip(columns, cells[1:]):
                if value:
                    row[prefix + label] = _number(value, 0, 99999)
            groups.add(prefix)
            columns = []
    return row if groups else None


def merged_totals(existing, row):
    """Keep both tables independent and preserve any section absent from this import."""
    totals = dict(existing or {})
    incoming = {label: row[label] for label in ABSENCE_LABELS if label in row}
    if incoming:
        for label in ABSENCE_LABELS:
            totals.pop(label, None)
        totals.update(incoming)
    exceptions = {label: row[EXCEPTION_PREFIX + label] for label in ABSENCE_LABELS
                  if EXCEPTION_PREFIX + label in row}
    if exceptions:
        totals[EXCEPTION_TOTALS] = exceptions
    totals.update({label: row[label] for label in HOURS_LABELS if label in row})
    return totals


def check_terms(rows):
    if not 1 <= len(rows) <= MAX_TERMS:
        raise ValueError(f"每次請匯入 1 至 {MAX_TERMS} 個學期。")
    if len({(row[YEAR], row[TERM]) for row in rows}) != len(rows):
        raise ValueError("同一批資料有重複的學期，請每學期只保留一筆合計。")
