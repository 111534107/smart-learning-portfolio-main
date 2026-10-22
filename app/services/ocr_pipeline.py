"""Local, geometry-first OCR. Raw evidence is separate from editable fields."""
from contextlib import closing
from pathlib import Path
import re
import unicodedata
from statistics import median

from PIL import Image, ImageOps

from app.services.course_name_correction import apply_name_correction
from app.services.course_review_presentation import split_makeup_marker

MAX_PAGES = 10
MAX_PAGE_PIXELS = 25_000_000
PDF_DPI = 300
FIELDS = ("course_name", "credits", "score", "semester", "grade_level")


def load_document_pages(file_path):
    """Yield independent RGB pages; bound PDF allocation before rendering."""
    path = Path(file_path)
    if path.suffix.lower() == ".pdf":
        try:
            import pypdfium2 as pdfium
        except ImportError as exc:
            raise RuntimeError("PDF 轉圖套件未安裝，請安裝 requirements.txt 後重試。") from exc
        try:
            with closing(pdfium.PdfDocument(str(path))) as document:
                if not 0 < len(document) <= MAX_PAGES:
                    raise RuntimeError(f"PDF 須為 1–{MAX_PAGES} 頁，請分批上傳。")
                for index in range(len(document)):
                    with closing(document[index]) as page:
                        width, height = page.get_size()
                        scale = PDF_DPI / 72
                        if width * height * scale ** 2 > MAX_PAGE_PIXELS:
                            raise RuntimeError("PDF 頁面過大，請縮小頁面尺寸後重試。")
                        with closing(page.render(scale=scale)) as bitmap:
                            yield bitmap.to_pil().convert("RGB").copy()
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError("PDF 無法讀取，請確認檔案完整且未加密。") from exc
    elif path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
        try:
            with Image.open(path) as image:
                if image.width * image.height > MAX_PAGE_PIXELS:
                    raise RuntimeError("圖片尺寸過大，請縮小後重試。")
                yield ImageOps.exif_transpose(image).convert("RGB").copy()
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError("圖片無法讀取，請確認檔案完整。") from exc
    else:
        raise RuntimeError("OCR 支援 PDF、JPG、JPEG、PNG。")


def _groups(values, gap=3):
    groups = []
    for value in values:
        if not groups or value - groups[-1][-1] > gap:
            groups.append([value])
        else:
            groups[-1].append(value)
    return [int(median(group)) for group in groups]


def detect_transcript_panels(image):
    """Find marker/name/credit/score/credit/score grids, not hardcoded page ratios.

    A wide subject column followed by four narrow numeric columns identifies
    this transcript template. The largest horizontal-rule gap is its body.
    Unsupported tables are left to the explicit unknown-layout fallback.
    """
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("表格辨識套件未安裝；請在啟動網站的 Python 環境安裝 requirements.txt。") from exc

    mask = np.asarray(image.convert("L")) < 175
    # Small rule thickness/skew tolerance; never erase strokes from OCR input.
    vertical = mask.copy()
    vertical[:, 1:] |= mask[:, :-1]
    vertical[:, :-1] |= mask[:, 1:]
    xs = _groups(np.flatnonzero(vertical.mean(axis=0) > .36).tolist(), gap=4)
    panels = []
    for i in range(len(xs) - 5):
        name_left, name_right = xs[i:i+2]
        name_width = name_right - name_left
        numeric_edges = xs[i+1:i+6]
        widths = [b-a for a, b in zip(numeric_edges, numeric_edges[1:])]
        if name_width < image.width * .07 or not widths:
            continue
        typical = median(widths)
        if typical <= 2 or name_width < typical * 3 or not all(.45*typical < w < 1.8*typical for w in widths):
            continue
        left = xs[i-1] if i and name_left-xs[i-1] < typical*1.5 else name_left
        right = numeric_edges[-1]
        rule_mask = mask[:, left:right]
        horizontal = rule_mask.copy()
        for shift in range(1, 4):
            horizontal[shift:] |= rule_mask[:-shift]
            horizontal[:-shift] |= rule_mask[shift:]
        ys = _groups(np.flatnonzero(horizontal.mean(axis=1) > .7).tolist(), gap=3)
        gaps = [(b-a, a, b) for a,b in zip(ys, ys[1:])]
        if not gaps:
            continue
        span, top, bottom = max(gaps)
        if span < image.height * .25:
            continue
        panels.append({"bbox": [left, 0, right, image.height],
                       "body": (top+2, bottom-2),
                       "columns": [0, *([name_left-left] if left < name_left else []),
                                   *[x-left for x in numeric_edges]],
                       "layout_verified": False})
    if len(panels) >= 2:
        common_bottom = median(p["body"][1] for p in panels)
        for panel in panels:
            top, bottom = panel["body"]
            # A faint rule in one panel can otherwise include the first summary
            # line. Neighboring panels in this form share the same baseline.
            if abs(bottom-common_bottom) < image.height*.04:
                panel["body"] = (top, min(bottom, common_bottom))
    return panels


def clean_name(text):
    # Remove a separate required/elective marker, not arbitrary leading letters.
    value = re.sub(r"^\s*(?:[必選密]\s*[|｜]|[必選]\s+)", "", text)
    value = re.sub(r"^[\s|｜>\"'“”「」:：]+", "", value).strip()
    value = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", value)
    return value


def _confidence(words):
    scores = [w.get("confidence") for w in words]
    return min(scores) if scores and all(s is not None for s in scores) else None


def _number(words, maximum):
    if len(words) != 1:
        return None, None
    raw = words[0]["text"].strip().lstrip("*＊")
    if not re.fullmatch(r"\d{1,3}", raw) or not 0 <= int(raw) <= maximum:
        return None, None
    return int(raw), _confidence(words)


def _rows(words):
    """Sort by geometry first; tolerance scales with glyph height, not pixels."""
    if not words:
        return []
    tolerance = max(1, median(w["bbox"][3]-w["bbox"][1] for w in words) * .75)
    rows = []
    for word in sorted(words, key=lambda w: (w["bbox"][1]+w["bbox"][3])/2):
        cy = (word["bbox"][1]+word["bbox"][3])/2
        if rows and abs(cy-median((w["bbox"][1]+w["bbox"][3])/2 for w in rows[-1])) <= tolerance:
            rows[-1].append(word)
        else:
            rows.append([word])
    return rows


def parse_panel_words(words, size, region_index, *, body=None, columns=None,
                      offset=0, page=1, rotation=0, layout_verified=False,
                      grade_level=None, grade_confidence=None):
    from app.services.document_analysis_service import score_band

    width, height = size
    top, bottom = body or (height*.17, height*.7)
    edges = columns or [width*v for v in (.06, .65, .735, .82, .90, 1)]
    words = [w for w in words if top < (w["bbox"][1]+w["bbox"][3])/2 < bottom]
    courses = []
    for line, row in enumerate(_rows(words), 1):
        has_makeup_column = len(edges) == 7
        cells = [[] for _ in range(6 if has_makeup_column else 5)]
        for word in row:
            x = sum(word["bbox"][::2])/2
            for index, (left, right) in enumerate(zip(edges, edges[1:])):
                if left <= x < right:
                    cells[index].append(word)
                    break
        name_index = 1 if has_makeup_column else 0
        numeric_start = name_index + 1
        name_words = sorted(cells[name_index], key=lambda w: w["bbox"][0])
        raw_name = " ".join(w["text"] for w in name_words)
        _without_marker, makeup_season = split_makeup_marker(raw_name)
        if has_makeup_column:
            marker_text = "".join(w["text"] for w in cells[0])
            if "暑" in marker_text:
                makeup_season = "summer"
            elif "寒" in marker_text:
                makeup_season = "winter"
        name, _season = split_makeup_marker(clean_name(raw_name))
        if not name and not any(cells[numeric_start:]):
            continue
        # The body is geometrically bounded; never treat a 0-credit row as noise.
        semesters = [s for s in range(2) if cells[numeric_start+s*2] or cells[numeric_start+1+s*2]] or [None]
        for semester in semesters:
            credit_words = cells[numeric_start+semester*2] if semester is not None else []
            score_words = cells[numeric_start+1+semester*2] if semester is not None else []
            credits, credit_conf = _number(credit_words, 10)
            score, score_conf = _number(score_words, 100)
            confidence = {"course_name": _confidence(name_words) if name else None,
                          "credits": credit_conf, "score": score_conf,
                          "semester": None, "grade_level": grade_confidence}
            reasons = [] if layout_verified else ["學期依表格位置推定，請核對表頭。"]
            if grade_level is None:
                reasons.append("年級表頭未辨識完整，請核對。")
            for field, label, value in (("course_name", "科目", name), ("credits", "學分", credits), ("score", "成績", score)):
                if value is None or value == "":
                    reasons.append(f"{label}未讀取完整。")
                elif confidence[field] is None or confidence[field] < .85:
                    reasons.append(f"{label}辨識信心不足，請對照原圖。")
            courses.append({"course_name": name or "課名待確認", "credits": credits,
                "score": score, "score_band": score_band(score),
                "makeup_season": makeup_season,
                "semester": ("第一學期", "第二學期")[semester] if semester is not None else None,
                "grade_level": grade_level,
                "source_page": page, "source_line": line, "source_region": region_index,
                "source_rotation": rotation,
                "source_bbox": [offset, max(0, min(w["bbox"][1] for w in row)-3),
                                offset+width, min(height, max(w["bbox"][3] for w in row)+3)],
                "field_confidence": confidence, "needs_confirmation": bool(reasons),
                "review_reasons": reasons,
                "raw_cells": [[w["text"] for w in cell] for cell in cells]})
    return [apply_name_correction(course) for course in courses]


def grade_from_header(words):
    text = unicodedata.normalize("NFKC", "".join(w["text"] for w in words))
    text = re.sub(r"\s+", "", text)
    # RapidOCR 常把「學」讀成簡體「学」或形近字「举」；只在「第N_年」這個固定格式裡放寬
    match = re.search(r"(?:第([1-5一二三四五])[學学举]年|(?<!\d)([1-5一二三四五])年[級级])", text)
    if not match:
        return None, None
    value = next(v for v in match.groups() if v)
    value = str("一二三四五".index(value)+1) if value in "一二三四五" else value
    return f"{value}年級", _confidence(words)


def parse_unknown_rows(words, *, page, size, rotation=0):
    """Retain incomplete candidate rows without guessing multi-semester columns."""
    from app.services.document_analysis_service import score_band
    courses = []
    cell = r"(?:[＊*]?\d\S*|\?+|—|待確認)"
    for line, row in enumerate(_rows(words), 1):
        raw = " ".join(w["text"] for w in sorted(row, key=lambda w:w["bbox"][0]))
        # Start at the first numeric/unknown cell, not the last valid suffix:
        # damaged scores such as 7S must never become part of the subject name.
        match = re.fullmatch(rf"(.+?)\s+({cell}(?:\s+\S+)*)", raw.strip())
        if not match:
            continue
        _without_marker, makeup_season = split_makeup_marker(match[1])
        name, _season = split_makeup_marker(clean_name(match[1]))
        values = match[2].split()
        if re.search(r"學號|姓名|總計|總修|累計|平均|列印|學年度|學分|科目|課程名稱", name):
            continue
        credits = score = None
        def number(text, limit):
            text = text.lstrip("*")
            return int(text) if text.isdigit() and int(text) <= limit else None
        if len(values) == 2:
            credits, score = number(values[0], 10), number(values[1], 100)
        # A lone 0..10 could be a score OR credits. Keep its raw cell without
        # assigning a meaning until a human verifies the original columns.
        courses.append({"course_name": name or "課名待確認", "credits": credits,
            "score": score, "score_band": score_band(score), "semester": None,
            "grade_level": None, "makeup_season": makeup_season,
            "field_confidence": {field: None for field in FIELDS},
            "needs_confirmation": True, "review_reasons": [
                "未辨識到支援的表格版型，請對照原圖核對所有欄位。",
                "同列有多組數字，未自動配對學期；請核對並補齊課程。" if len(values)>2
                else "欄位依同行文字暫存，缺漏資料需人工補齊。"],
            "source_page": page, "source_line": line, "source_rotation": rotation,
            "source_bbox": [max(0,min(w["bbox"][0] for w in row)-3),
                            max(0,min(w["bbox"][1] for w in row)-3),
                            min(size[0],max(w["bbox"][2] for w in row)+3),
                            min(size[1],max(w["bbox"][3] for w in row)+3)],
            "raw_cells": values})
    return [apply_name_correction(course) for course in courses]


def _recognize_crop(image, box, engine, *, scale=None):
    from app.services.ocr_engines import recognize
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("表格辨識套件未安裝，請使用已安裝 requirements.txt 的 Python 環境。") from exc

    crop = image.crop(tuple(int(v) for v in box)).convert("RGB")
    # Grid borders can survive a slightly tilted crop. Remove only continuous
    # vertical runs longer than a glyph, never columns selected by ink density.
    dark = np.asarray(crop.convert("L")) < 200
    run = np.zeros(crop.width, dtype=int)
    longest = run.copy()
    for scanline in dark:
        run = (run + 1) * scanline
        longest = np.maximum(longest, run)
    borders = longest > max(40, crop.height*.2)
    if borders.any():
        pixels = np.asarray(crop).copy()
        pixels[:, borders] = 255
        crop = Image.fromarray(pixels)
        dark[:, borders] = False
    if int(dark.sum()) < 10:
        return []
    if scale is None:
        scale = min(3, max(2, 1000 / max(1, crop.height)))
    elif not 1 <= scale <= 3:
        raise ValueError("OCR 影像倍率須介於 1 到 3。")
    enlarged = crop.resize((round(crop.width*scale), round(crop.height*scale)), Image.Resampling.LANCZOS)
    # White border keeps edge glyphs away from the recognition boundary.
    padded = ImageOps.expand(enlarged, border=12, fill="white")
    words = recognize(padded, engine)
    for word in words:
        x1,y1,x2,y2 = word["bbox"]
        word["bbox"] = [(x1-12)/scale+box[0], (y1-12)/scale+box[1],
                        (x2-12)/scale+box[0], (y2-12)/scale+box[1]]
    return words


def _ink_without_rules(ink):
    """移除直線框線：一整條 x 在表格本體超過一半高度都有墨水的就是框線（含掃描偏移、較粗的線）。"""
    import numpy as np

    rules = ink.mean(axis=0) > .5
    rules[1:] |= rules[:-1]
    rules[:-1] |= rules[1:]
    cleaned = ink.copy()
    cleaned[:, rules] = False
    return cleaned


def _text_row_bands(ink, columns):
    """用墨水投影找出表格內每一列文字的上下範圍；不靠文字框偵測。

    先移除直線框線，再只看各欄內部；整列幾乎塗滿的是橫線框線，不算文字。
    同一個字內的空隙（例如「二」「三」）比列與列的間距小，依文字高度合併。
    """
    import numpy as np

    ink = _ink_without_rules(ink)
    interior = np.zeros(ink.shape[0], dtype=int)
    for c_left, c_right in zip(columns, columns[1:]):
        if c_right - c_left > 10:
            interior += ink[:, c_left + 4:c_right - 4].sum(axis=1)
    interior[ink.mean(axis=1) > .6] = 0
    runs, start = [], None
    for y, value in enumerate(interior >= 2):
        if value and start is None:
            start = y
        elif not value and start is not None:
            runs.append([start, y])
            start = None
    if start is not None:
        runs.append([start, len(interior)])
    if not runs:
        return []
    typical = float(np.percentile([b - a for a, b in runs], 75))
    merged = [runs[0]]
    for a, b in runs[1:]:
        if a - merged[-1][1] < max(2, typical * .3):
            merged[-1][1] = b
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged if b - a >= max(4, typical * .35)]


def _recognize_panel_cells(image, panel):
    """RapidOCR 專用：逐列、逐格只做文字辨識，回傳與 recognize() 相同格式的文字框（原圖座標）。

    窄小的學分／成績欄用文字框偵測時，兩位數會被拆成兩個框或漏掉一位數（例如 70 只剩 0），
    伺服器版模型在又高又窄的欄位裁切上甚至偵測不到任何文字；整格直接辨識可避免這兩個問題。
    """
    import numpy as np
    from app.services.ocr_engines import recognize_rapidocr_line

    left, _, right, _ = panel["bbox"]
    top, bottom = (int(v) for v in panel["body"])
    columns = panel["columns"]
    gray = np.asarray(image.convert("L"))
    raw_ink = gray[top:bottom, int(left):int(right)] < 175
    ink = _ink_without_rules(raw_ink)
    words = []
    for y1, y2 in _text_row_bands(raw_ink, columns):
        height = y2 - y1
        for c_left, c_right in zip(columns, columns[1:]):
            x1, x2 = c_left + 4, c_right - 4
            if x2 - x1 < 4:
                continue
            cell = ink[y1:y2, x1:x2]
            if int(cell.sum()) < 8:
                continue  # 空格：不辨識，避免把空白讀成「−」之類的符號
            ink_rows = np.flatnonzero(cell.any(axis=1))
            if ink_rows[-1] - ink_rows[0] + 1 < max(6, height * .4):
                # 框線殘影、污點只有幾個像素高；真正的字（連「1」）會上下跨過一定高度。
                # 實例：表頭底線殘影落在空白成績格，被讀成「1」而多出一筆不及格的假課程。
                continue
            xs = np.flatnonzero(cell.any(axis=0))
            pad = max(4, round(height * .25))
            crop_box = (int(left) + x1 + max(0, xs[0] - pad), top + max(0, y1 - pad),
                        int(left) + x1 + min(x2 - x1, xs[-1] + 1 + pad), top + min(ink.shape[0], y2 + pad))
            crop = image.crop(crop_box).convert("RGB")
            scale = max(1.0, 40 / max(1, crop.height))
            if scale > 1:
                crop = crop.resize((round(crop.width * scale), round(crop.height * scale)), Image.Resampling.LANCZOS)
            recognized = recognize_rapidocr_line(ImageOps.expand(crop, border=8, fill="white"))
            if recognized is None:
                continue
            text, confidence = recognized
            if not any(char.isalnum() for char in text):
                continue  # 掃描污點常被讀成「.」「−」，只有標點的不算文字
            words.append({"text": text, "confidence": confidence,
                          "bbox": [float(left + c_left + 3), float(top + y1), float(left + c_right - 3), float(top + y2)]})
    return words


def analyze(document_type, file_path, engine):
    from app.services.document_analysis_service import parse_ocr_text
    from app.services.credential_analysis import (
        TECHNICIAN_REGIONS, analyze_technician_regions, recognize_credential_region,
        recognize_level_fallback, recognize_number_fallback,
    )

    courses, credentials, traces, texts, evidence = [], [], [], [], []
    warnings, unparsed_pages = [], []
    credential_analysis = None
    credential_analyses = []
    pages = load_document_pages(file_path)
    try:
        for page_number, original in enumerate(pages, 1):
            before_count = len(courses)+len(credentials)
            page_credential_analysis = None
            image, rotation, panels = original, 0, []
            if document_type == "transcript":
                # Orientation is selected by table geometry, not course count.
                candidates = []
                for angle in (0, 270, 90, 180):
                    candidate = original.rotate(angle, expand=True) if angle else original
                    detected = detect_transcript_panels(candidate)
                    if detected:
                        candidates.append((len(detected), angle, candidate, detected))
                if candidates:
                    _, rotation, image, panels = max(candidates, key=lambda item: item[0])
            # Technician credentials are read from focused regions below. A
            # full-page Paddle pass before those crops duplicated the most
            # expensive inference and was especially costly on reflective,
            # patterned cards. Keep full-page OCR for transcripts; use it as a
            # credential fallback only when the focused pass cannot classify.
            page_words = []
            if panels:
                for region, panel in enumerate(panels, 1):
                    left, _, right, _ = panel["bbox"]
                    top, bottom = panel["body"]
                    words = []
                    from app.services.ocr_engines import LINE_LEVEL_ENGINES
                    paddle = engine in LINE_LEVEL_ENGINES
                    if engine == "rapidocr":
                        # 逐格只做文字辨識；見 _recognize_panel_cells 說明
                        words = _recognize_panel_cells(image, panel)
                    else:
                        for index, (c_left, c_right) in enumerate(zip(panel["columns"], panel["columns"][1:])):
                            box = [left+c_left+2, top, left+c_right-2, bottom]
                            # Keep high-resolution subject names; raw-size numeric
                            # cells were at least as complete on the reference form.
                            words.extend(_recognize_crop(image, box, engine,
                                          scale=1 if paddle and index else None))
                    if not words:
                        # Empty future-year panels still have printed headers.
                        # There is no course to assign that year to.
                        continue
                    header_words = _recognize_crop(image, [left, max(0, top-image.height*.1), right, top], engine,
                                                   scale=1 if paddle else None)
                    grade, grade_conf = grade_from_header(header_words)
                    page_words.extend(header_words)
                    page_words.extend(words)
                    local_words = [{**w, "bbox": [w["bbox"][0]-left, w["bbox"][1], w["bbox"][2]-left, w["bbox"][3]]} for w in words]
                    courses.extend(parse_panel_words(local_words, (right-left, image.height), region,
                        body=panel["body"], columns=panel["columns"], offset=left,
                        page=page_number, rotation=rotation, grade_level=grade, grade_confidence=grade_conf))
            else:
                if document_type != "credential":
                    page_words = _recognize_crop(image, [0,0,image.width,image.height], engine)
                text_rows = _rows(page_words)
                raw = "\n".join(" ".join(w["text"] for w in sorted(row, key=lambda w:w["bbox"][0])) for row in text_rows)
                if document_type == "transcript":
                    parsed = {"courses": parse_unknown_rows(page_words, page=page_number,
                              size=image.size, rotation=rotation), "credentials": []}
                    warnings.append(f"第 {page_number} 頁版型尚未確認，可能有未配對文字；請完整核對原始頁面。")
                else:
                    if engine == "rapidocr":
                        # 整張辨識（不放大）後依標籤找欄位：學生上傳的證照邊界、比例不一，固定比例切區會錯開
                        from app.services.credential_analysis import technician_regions_from_page_words
                        from app.services.ocr_engines import recognize

                        page_words = recognize(image, engine)
                        raw = "\n".join(" ".join(w["text"] for w in sorted(row, key=lambda w: w["bbox"][0]))
                                        for row in _rows(page_words))
                        regions = technician_regions_from_page_words(page_words)
                        candidate = analyze_technician_regions(regions, page=page_number)
                    else:
                        title_ratio = TECHNICIAN_REGIONS["title"]
                        title_box = [title_ratio[0] * image.width, title_ratio[1] * image.height,
                                     title_ratio[2] * image.width, title_ratio[3] * image.height]
                        title_words = recognize_credential_region(image, title_box, engine)
                        title_words.extend(word for word in page_words if "技術士證" in word["text"])
                        regions = {"title": title_words}
                        candidate = analyze_technician_regions(regions, page=page_number)
                        if candidate is None:
                            for key in ("certificate_number", "occupation", "issue_date"):
                                ratio = TECHNICIAN_REGIONS[key]
                                box = [ratio[0] * image.width, ratio[1] * image.height,
                                       ratio[2] * image.width, ratio[3] * image.height]
                                regions[key] = recognize_credential_region(image, box, engine)
                            candidate = analyze_technician_regions(regions, page=page_number)
                    if candidate:
                        for key, ratio in TECHNICIAN_REGIONS.items():
                            if key in regions:
                                continue
                            box = [ratio[0] * image.width, ratio[1] * image.height,
                                   ratio[2] * image.width, ratio[3] * image.height]
                            regions[key] = recognize_credential_region(image, box, engine)
                        page_credential_analysis = analyze_technician_regions(regions, page=page_number)
                        if page_credential_analysis["fields"]["certificate_number"]["value"] is None:
                            number_words = recognize_number_fallback(image)
                            if number_words:
                                regions["certificate_number"] = number_words
                                page_credential_analysis = analyze_technician_regions(
                                    regions, page=page_number)
                        if page_credential_analysis["fields"]["level"]["value"] is None:
                            level_words = recognize_level_fallback(image, engine)
                            if level_words:
                                regions["level"] = level_words
                                page_credential_analysis = analyze_technician_regions(
                                    regions, page=page_number)
                        credential_analyses.append(page_credential_analysis)
                        if credential_analysis is None:
                            credential_analysis = page_credential_analysis
                        fields = page_credential_analysis["fields"]
                        if fields["occupation"]["value"]:
                            parsed = {"courses": [], "credentials": [{
                                "credential_name": fields["occupation"]["value"],
                                "level": fields["level"]["value"],
                                "issuing_organization": fields["issuer"]["value"],
                                "issue_date": fields["issue_date"]["value"],
                                "source_page": page_number,
                            }]}
                        else:
                            parsed = {"courses": [], "credentials": []}
                        if engine != "rapidocr":  # RapidOCR 的整頁文字已包含各欄位
                            page_words.extend(word for words in regions.values() for word in words)
                    else:
                        if not page_words:
                            page_words = _recognize_crop(
                                image, [0, 0, image.width, image.height], engine)
                            text_rows = _rows(page_words)
                            raw = "\n".join(
                                " ".join(w["text"] for w in sorted(row, key=lambda w: w["bbox"][0]))
                                for row in text_rows)
                        try:
                            parsed = parse_ocr_text(document_type, raw)
                        except RuntimeError:
                            parsed = {"courses": [], "credentials": []}
                for item in parsed["credentials"]:
                    item["source_page"] = page_number
                courses.extend(parsed["courses"])
                credentials.extend(parsed["credentials"])
            if len(courses)+len(credentials) == before_count and page_credential_analysis is None:
                unparsed_pages.append(page_number)
                warnings.append(f"第 {page_number} 頁未擷取到課程或證照，請核對原始頁面並補登。")
            texts.append("\n".join(w["text"] for w in page_words))
            evidence.append({"page": page_number, "rotation": rotation, "words": page_words})
            # 保存這一頁的圖片處理方式（確認頁「查看 OCR 辨識過程」用 ocr_trace 翻成中文）
            page_trace = {"step": "page_ocr", "page": page_number, "engine": engine,
                          "document_type": document_type,
                          "source": "pdf" if str(file_path).lower().endswith(".pdf") else "image",
                          "original_width": original.width, "original_height": original.height,
                          "rotation": rotation, "panel_count": len(panels),
                          "width": image.width, "height": image.height}
            if page_trace["source"] == "pdf":
                page_trace["dpi"] = PDF_DPI
            if document_type == "transcript":
                page_trace["tried_rotations"] = [0, 270, 90, 180]
            if engine == "rapidocr":
                from app.services.ocr_engines import configured_rapidocr_settings
                tier, device, _ = configured_rapidocr_settings()
                page_trace.update({"model_tier": tier, "device": device})
            traces.append(page_trace)
            if page_credential_analysis:
                traces.append({"step": "credential_fields_parsed", "page": page_number,
                               "document_kind": page_credential_analysis["document_kind"],
                               "needs_review": page_credential_analysis["needs_review"]})
    finally:
        if hasattr(pages, "close"):
            pages.close()
    if document_type == "credential" and not credentials and credential_analysis is None:
        credential_analysis = {
            "source_page": unparsed_pages[0] if unparsed_pages else None,
            "document_kind": "unrecognized_credential",
            "document_label": "證照類型未辨識",
            "needs_review": True,
            "fields": {},
            "steps": ["整頁 OCR 與證照標題區域重讀", "未取得足夠文字；請對照原圖手動填寫"],
        }
        traces.append({"step": "credential_manual_review", "needs_review": True})
        warnings.append("證照類型與欄位未能可靠辨識，請對照原圖人工填寫。")
        credential_analyses.append(credential_analysis)
    if not courses and not credentials and credential_analysis is None:
        raise RuntimeError("未辨識到可確認的資料；請提供清晰、正向的原始檔案。")
    return {"document_type": document_type, "courses": courses, "credentials": credentials,
            "credential_analysis": credential_analysis, "credential_analyses": credential_analyses,
            "academic_summary": [], "raw_text": "\n\n".join(texts), "ocr_evidence": evidence,
            "unparsed_pages": unparsed_pages,
            "warnings": ["OCR 信心分數不是正確率；請對照原圖核對，低分也不能自動改成高分。", *warnings],
            "source": {"file_name": Path(file_path).name, "engine": engine,
                       "document_type": document_type, "page_count": len(evidence)},
            "source_file_available": True, "processing_steps": traces}
