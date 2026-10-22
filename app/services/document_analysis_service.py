"""Document-analysis providers for the learning-profile workflow."""

import re
from pathlib import Path

from app.services.course_review_presentation import split_makeup_marker

from PIL import Image, ImageFilter, ImageOps
import pytesseract
from pytesseract import Output


ALLOWED_DOCUMENT_TYPES = {"transcript", "credential"}
CANDIDATE_WARNING = "此為 OCR 候選欄位；必須由學生逐項確認後才會成為正式資料。"
DEFAULT_OCR_MODEL_DIR = Path(__file__).resolve().parents[2] / "instance" / "ocr-models"
# PP-OCRv5 中文辨識模型簡體、繁體、英文、日文共用。
# 伺服器版（預設）對模糊、歪斜照片較準，但較慢、記憶體約 2 GB；輕量版約 0.7 GB。
OCR_MODEL_TIERS = {
    "server": {
        "Det": "ch_PP-OCRv5_det_server.onnx",
        "Rec": "ch_PP-OCRv5_rec_server.onnx",
        "Cls": "ch_ppocr_mobile_v2.0_cls_mobile.onnx",
    },
    "mobile": {
        "Det": "ch_PP-OCRv5_det_mobile.onnx",
        "Rec": "ch_PP-OCRv5_rec_mobile.onnx",
        "Cls": "ch_ppocr_mobile_v2.0_cls_mobile.onnx",
    },
}
# cpu＝一般處理器（預設，任何電腦都能用）；dml＝Windows DirectML 顯示卡加速（需安裝 onnxruntime-directml）
OCR_DEVICES = ("cpu", "dml")


def _plain_dict_provider_options(method):
    """把 rapidocr 傳給 onnxruntime 的顯示卡設定轉成一般 dict。"""
    def wrapper(self):
        return dict(method(self))

    wrapper._plain_dict = True
    return wrapper


def _patch_rapidocr_directml_options():
    """rapidocr 3.10 直接把 OmegaConf 設定物件交給 onnxruntime，被拒絕後會悄悄退回 CPU；轉成 dict 才會真的用顯示卡。"""
    from rapidocr.inference_engine.onnxruntime import provider_config

    current = provider_config.ProviderConfig.dml_ep_cfg
    if not getattr(current, "_plain_dict", False):
        provider_config.ProviderConfig.dml_ep_cfg = _plain_dict_provider_options(current)


FIELD_LABELS = ("課程", "學分", "分數", "證照名稱", "等級", "發證單位", "日期")


class RapidOcrEngine:
    """離線 OCR（RapidOCR PP-OCRv5，在本機執行，圖片不離開伺服器）。

    只讀本機模型檔，不會自動下載；模型由 scripts/download_ocr_models.py 預先下載並核對雜湊。
    """

    def __init__(self, model_dir=None, tier="server", device="cpu", dml_device_id=0):
        if tier not in OCR_MODEL_TIERS:
            raise ValueError(f"unsupported OCR model tier: {tier}")
        if device not in OCR_DEVICES:
            raise ValueError(f"unsupported OCR device: {device}")
        self.model_dir = Path(model_dir) if model_dir else DEFAULT_OCR_MODEL_DIR
        self.tier = tier
        self.model_files = OCR_MODEL_TIERS[tier]
        self.device = device
        self.dml_device_id = int(dml_device_id)
        self._ocr = None

    def build_params(self):
        from rapidocr import OCRVersion

        params = {"Global.log_level": "error",
                  "Det.ocr_version": OCRVersion.PPOCRV5, "Rec.ocr_version": OCRVersion.PPOCRV5,
                  "EngineConfig.onnxruntime.use_dml": self.device == "dml"}
        params.update({f"{stage}.model_path": str(self.model_dir / name) for stage, name in self.model_files.items()})
        if self.device == "dml":
            # 筆電常有內建與獨立兩張顯示卡；DirectML 編號 0 多半是內建顯示，要用獨立顯示卡須指定編號
            params["EngineConfig.onnxruntime.dml_ep_cfg"] = {"device_id": self.dml_device_id}
        return params

    def _load(self):
        params = self.build_params()
        missing = [name for name in self.model_files.values() if not (self.model_dir / name).exists()]
        if missing:
            raise RuntimeError(
                f"離線 OCR 模型檔不存在（{', '.join(missing)}）；請先執行 scripts/download_ocr_models.py"
            )
        from rapidocr import RapidOCR

        if self.device == "dml":
            _patch_rapidocr_directml_options()
        return RapidOCR(params=params)

    def recognize_text(self, image_path):
        if self._ocr is None:
            self._ocr = self._load()
        output = self._ocr(str(image_path))
        if output.boxes is None or not output.txts:
            return ""
        result = zip(output.boxes.tolist(), output.txts)
        # 同一行的文字框 y 座標相近：先依 y 中心分行，再依 x 由左到右排序
        boxes = sorted(result, key=lambda item: (sum(p[1] for p in item[0]) / 4))
        lines, current, current_y, current_h = [], [], None, None
        for box, text in boxes:
            ys = [p[1] for p in box]
            xs = [p[0] for p in box]
            center_y, height = (min(ys) + max(ys)) / 2, max(ys) - min(ys)
            if current_y is not None and abs(center_y - current_y) > current_h / 2:
                lines.append(current)
                current = []
            current.append((min(xs), text))
            current_y, current_h = center_y, height
        if current:
            lines.append(current)
        return "\n".join("  ".join(text for _x, text in sorted(line)) for line in lines)


class NotConfiguredOcrEngine:
    """尚未選定離線 OCR 套件（RapidOCR 待使用者確認）前的預設值：一律失敗，不猜測。"""

    def recognize_text(self, image_path):
        raise RuntimeError("目前尚未設定離線 OCR 引擎")


def _field(line, label):
    # 值到空白或下一個欄位標籤為止（OCR 常把「學分：3  分數：88」黏成「學分：3分數：88」）
    next_label = "|".join(f"{other}[:：]" for other in FIELD_LABELS if other != label)
    match = re.search(rf"{label}[:：]\s*(.+?)(?=\s|{next_label}|$)", line)
    return match.group(1) if match else ""


def parse_candidates(text, document_type):
    """把 OCR 文字轉成候選欄位；查不到的欄位留空，不推測。"""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if document_type == "transcript":
        courses = [
            {
                "school_year": None,
                "semester": None,
                "course_name": _field(line, "課程"),
                "credits": _field(line, "學分"),
                "score": _field(line, "分數"),
            }
            for line in lines if _field(line, "課程")
        ]
        return {"document_type": document_type, "courses": courses, "credentials": None}

    credentials = [
        {
            "credential_name": _field(line, "證照名稱"),
            "level": _field(line, "等級"),
            "issuing_organization": _field(line, "發證單位"),
            "issue_date": _field(line, "日期"),
        }
        for line in lines if _field(line, "證照名稱")
    ]
    return {"document_type": document_type, "courses": None, "credentials": credentials}
_NUMBER = r"\d+(?:\.\d+)?"


def score_band(score):
    if score is None:
        return "未辨識／待確認"
    if score >= 95:
        return "95–100"
    if score >= 85:
        return "85–94"
    if score >= 75:
        return "75–84"
    if score >= 60:
        return "60–74"
    return "不及格"


def parse_academic_summary(raw_text, grade_level):
    """Parse bottom-of-panel statistics without treating them as courses."""
    metrics = ("學業成績總平均", "總修學分", "實得學分", "累計學分", "採行成績")
    summaries = []
    fallback_pairs = []
    for raw_line in raw_text.splitlines():
        line = _normalise_ocr_line(raw_line)
        tokens = re.findall(r"\d+(?:\.\d+)?", line)
        values = [float(value) for value in tokens]
        if len(values) < 2:
            continue
        pair = (values[-2], values[-1])
        metric = next((item for item in metrics if item in line), None)
        if metric:
            summaries.append({
                "grade_level": grade_level,
                "metric": metric,
                "semester_1": pair[0],
                "semester_2": pair[1],
            })
            continue

        # The table labels are often the least legible part of a scan.  Keep
        # decimal rows (and four-digit values such as OCR's ``8239`` for
        # ``82.39``), then map them to the fixed summary-row order below.
        if any("." in token or len(token) == 4 for token in tokens):
            repaired = tuple(value / 100 if value >= 1000 else value for value in pair)
            fallback_pairs.append(repaired)

    if summaries:
        return summaries

    return [
        {
            "grade_level": grade_level,
            "metric": metric,
            "semester_1": pair[0],
            "semester_2": pair[1],
            "needs_confirmation": True,
        }
        for metric, pair in zip(metrics, fallback_pairs[: len(metrics)])
    ]


def _normalise_ocr_line(line):
    return " ".join(line.replace("　", " ").split())


def _clean_course_name(course_name):
    """Remove the transcript's required marker from the subject."""
    value = _normalise_ocr_line(course_name).strip(" ：:|-|｜")
    value = re.sub(r"^[^\s|｜]{1,2}\s*[|｜]\s*", "", value)
    value = re.sub(r"^[|｜>\"'“”「」]+\s*", "", value)
    if not re.search(r"[A-Za-z]", value):
        value = re.sub(r"\s+", "", value)
    return value.strip(" ：:|-|｜")


def _deduplicate_course_records(courses):
    """Only collapse repeated extraction of the same source row and semester."""
    unique = []
    seen = set()
    for course in courses:
        if course.get("source_line") is None:
            unique.append(course)
            continue
        key = (course.get("source_page"), course.get("source_region"),
               course.get("source_line"), course.get("semester"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(course)
    return unique


def _is_plausible_course_name(course_name):
    """Reject transcript summary rows and obvious OCR noise."""
    value = _clean_course_name(course_name)
    if not value or re.search(r"\d", value):
        return False
    if re.search(r"[一二三四五六七八九十百千0-9]+號$", value):
        return False
    compact = re.sub(r"[^\w\u4e00-\u9fff]+", "", value)
    if any(keyword in compact for keyword in (
        "平均", "總修", "實得", "累計", "採行", "畢業", "成績", "學分",
        "計學分", "得分", "科目", "總平課",
        "待確認",
    )):
        return False
    chinese_count = len(re.findall(r"[\u4e00-\u9fff]", value))
    if chinese_count == 1 and re.search(r"[A-Za-z]", value):
        return False
    if re.search(r"[A-Za-z]", value) and re.search(r"[|*]", value):
        return False
    if chinese_count:
        return len(value) >= 2
    return any(keyword in value.upper() for keyword in ("JAVA", "SQL", "HTML", "CSS", "PYTHON", "C++"))


def _repair_ocr_course_name(course_name):
    """Clean formatting only; uncertain characters require source review."""
    return _clean_course_name(course_name)


def _align_image_for_ocr(image):
    """Center a visibly shifted document region on a white canvas.

    This is intentionally conservative: if dark pixels reach the image edges,
    the scan is treated as a full-page image and left unchanged rather than
    risking a destructive crop.  The trace is returned so callers can expose
    whether alignment actually changed the OCR input.
    """
    try:
        image = ImageOps.exif_transpose(image)
        grayscale = image.convert("L")
        mask = grayscale.point(lambda value: 255 if value < 245 else 0)
        bbox = mask.getbbox()
        width, height = image.size
        if not bbox:
            return image, {
                "step": "image_auto_aligned",
                "translation_applied": False,
                "reason": "no_content_detected",
            }

        left, top, right, bottom = bbox
        content_width = right - left
        content_height = bottom - top
        touches_edges = left <= 1 or top <= 1 or right >= width - 1 or bottom >= height - 1
        nearly_full_page = content_width >= width * 0.96 and content_height >= height * 0.96
        if touches_edges or nearly_full_page:
            return image, {
                "step": "image_auto_aligned",
                "translation_applied": False,
                "reason": "content_already_fills_frame",
            }

        margin_x = max(4, int(content_width * 0.08))
        margin_y = max(4, int(content_height * 0.08))
        crop_box = (
            max(0, left - margin_x),
            max(0, top - margin_y),
            min(width, right + margin_x),
            min(height, bottom + margin_y),
        )
        cropped = image.crop(crop_box)
        background = (255, 255, 255) if image.mode in {"RGB", "RGBA"} else 255
        aligned = Image.new(image.mode, image.size, background)
        paste_left = (width - cropped.width) // 2
        paste_top = (height - cropped.height) // 2
        aligned.paste(cropped, (paste_left, paste_top))
        return aligned, {
            "step": "image_auto_aligned",
            "translation_applied": True,
            "source_bbox": [left, top, right, bottom],
            "crop_box": list(crop_box),
            "translation": [paste_left - crop_box[0], paste_top - crop_box[1]],
        }
    except (AttributeError, TypeError, ValueError):
        return image, {
            "step": "image_auto_aligned",
            "translation_applied": False,
            "reason": "image_alignment_unavailable",
        }


def _remove_table_lines(image):
    """Remove long table rules while preserving compact text strokes."""
    try:
        grayscale = image.convert("L")
        width, height = grayscale.size
        pixels = grayscale.load()
        threshold = 180
        horizontal_rows = [
            y for y in range(height)
            if sum(pixels[x, y] < threshold for x in range(width)) >= width * 0.55
        ]
        vertical_columns = [
            x for x in range(width)
            if sum(pixels[x, y] < threshold for y in range(height)) >= height * 0.55
        ]
        cleaned = grayscale.copy()
        cleaned_pixels = cleaned.load()
        for y in horizontal_rows:
            for x in range(width):
                vertical_density = sum(
                    pixels[x, probe_y] < threshold
                    for probe_y in range(max(0, y - 3), min(height, y + 4))
                )
                if vertical_density <= 3:
                    for probe_y in range(max(0, y - 1), min(height, y + 2)):
                        cleaned_pixels[x, probe_y] = 255
        for x in vertical_columns:
            for y in range(height):
                horizontal_density = sum(
                    pixels[probe_x, y] < threshold
                    for probe_x in range(max(0, x - 3), min(width, x + 4))
                )
                if horizontal_density <= 3:
                    for probe_x in range(max(0, x - 1), min(width, x + 2)):
                        cleaned_pixels[probe_x, y] = 255
        return cleaned, {
            "step": "table_lines_removed",
            "horizontal_lines_removed": len(horizontal_rows),
            "vertical_lines_removed": len(vertical_columns),
        }
    except (AttributeError, TypeError, ValueError):
        return image, {
            "step": "table_lines_removed",
            "horizontal_lines_removed": 0,
            "vertical_lines_removed": 0,
        }


def _prepare_ocr_image(image):
    """Create a larger, higher-contrast copy for background OCR processing."""
    try:
        prepared = image.convert("L")
        prepared = prepared.resize(
            (prepared.width * 2, prepared.height * 2),
            Image.Resampling.LANCZOS,
        )
        prepared = ImageOps.autocontrast(prepared)
        prepared, _ = _remove_table_lines(prepared)
        return prepared.filter(ImageFilter.SHARPEN)
    except (AttributeError, TypeError):
        # Keep compatibility with lightweight provider doubles and unusual
        # image objects; the original image remains a valid OCR input.
        return image


def _parse_transcript_text(raw_text):
    courses = []
    for line_number, raw_line in enumerate(raw_text.splitlines(), start=1):
        line = _normalise_ocr_line(raw_line)
        match = re.match(rf"^(?P<course>.+?)\s+(?P<credits>{_NUMBER})\s+(?P<score>{_NUMBER})$", line)
        if not match:
            continue
        _without_marker, makeup_season = split_makeup_marker(match.group("course"))
        course_name = _repair_ocr_course_name(match.group("course"))
        course_name, _season = split_makeup_marker(course_name)
        credits = float(match.group("credits"))
        score = float(match.group("score"))
        if credits < 0 or credits > 10 or score < 0 or score > 100:
            continue
        courses.append({
            "course_name": course_name,
            "credits": int(credits) if credits.is_integer() else credits,
            "score": int(score) if score.is_integer() else score,
            "score_band": score_band(score),
            "makeup_season": makeup_season,
            "source_page": 1,
            "source_line": line_number,
        })
    return _deduplicate_course_records(courses)


def _parse_transcript_table_text(raw_text, region_index):
    """Parse rows from one rotated transcript panel.

    The target transcript layout prints a course row as course/credits/score,
    but includes status marks and vertical table separators between fields.
    """
    courses = []
    for line_number, raw_line in enumerate(raw_text.splitlines(), start=1):
        line = _normalise_ocr_line(raw_line)
        match = re.search(
            r"(?P<course>.+?)\s+(?P<credits>\d)\s*[|｜]?\s*(?P<score>\d{2,3}|0)$",
            line,
        )
        if not match:
            continue
        _without_marker, makeup_season = split_makeup_marker(match.group("course"))
        course_name = _repair_ocr_course_name(match.group("course"))
        if "|" in course_name or "｜" in course_name:
            course_name = _clean_course_name(re.split(r"[|｜]", course_name)[-1])
        course_name, _season = split_makeup_marker(course_name)
        if not _is_plausible_course_name(course_name):
            continue
        if course_name.isascii() and not re.search(r"JAVA|SQL|C\+\+", course_name.upper()):
            continue
        score = int(match.group("score"))
        credits = int(match.group("credits"))
        if score > 100 or credits > 6:
            continue
        courses.append({
            "course_name": course_name,
            "credits": credits,
            "score": score,
            "score_band": score_band(score),
            "makeup_season": makeup_season,
            "grade_level": f"{region_index}年級",
            "source_page": 1,
            "source_line": line_number,
            "source_region": region_index,
        })
    return courses


def parse_transcript_columns(course_text, credits_text, score_text, region_index):
    """Recombine OCR output captured from the three transcript columns."""
    course_lines = [
        _repair_ocr_course_name(line)
        for line in course_text.splitlines()
        if _repair_ocr_course_name(line)
    ]
    course_lines = [
        line for line in course_lines
        if _is_plausible_course_name(line)
    ]

    def numeric_lines(raw_text, upper_bound):
        values = []
        for raw_line in raw_text.splitlines():
            line = _normalise_ocr_line(raw_line)
            numbers = re.findall(r"\d+(?:\.\d+)?", line)
            if not numbers:
                continue
            value = float(numbers[-1])
            if value.is_integer() and 0 <= value <= upper_bound:
                values.append(int(value))
        return values

    credits = numeric_lines(credits_text, 10)
    scores = numeric_lines(score_text, 100)
    row_count = min(len(course_lines), len(credits), len(scores))
    return [
        {
            "course_name": course_lines[index],
            "credits": credits[index],
            "score": scores[index],
            "score_band": score_band(scores[index]),
            "grade_level": f"{region_index}年級",
            "source_page": 1,
            "source_line": index + 1,
            "source_region": region_index,
        }
        for index in range(row_count)
    ]


def _parse_transcript_panel_cells(panel, region_index):
    """Read one academic panel by locating rows and OCRing each cell."""
    try:
        data = pytesseract.image_to_data(
            panel, lang="chi_tra+eng", config="--psm 6", output_type=Output.DICT
        )
    except Exception:
        return []

    words = []
    for index, raw_text in enumerate(data.get("text", [])):
        text = _normalise_ocr_line(raw_text)
        if not text:
            continue
        left = int(data["left"][index])
        top = int(data["top"][index])
        width = int(data["width"][index])
        height = int(data["height"][index])
        words.append((text, left, top, width, height))
    if not words:
        return []

    panel_width, panel_height = panel.size
    course_right = int(panel_width * 0.68)
    row_centers = []
    for text, left, top, width, height in words:
        center_y = top + height // 2
        # Use every table column as a row anchor.  A blurry course-name cell
        # may have no usable OCR token, while its credit/score cells remain
        # readable; anchoring only on the course column silently drops it.
        if panel_height * 0.12 < center_y < panel_height * 0.62:
            if not row_centers or abs(center_y - row_centers[-1]) > 9:
                row_centers.append(center_y)
            else:
                row_centers[-1] = int((row_centers[-1] + center_y) / 2)

    courses = []
    for row_index, center_y in enumerate(row_centers, start=1):
        row_words = [
            word for word in words
            if abs((word[2] + word[4] // 2) - center_y) <= 10
        ]
        course_name = _repair_ocr_course_name(_clean_course_name(" ".join(
            word[0] for word in sorted(row_words, key=lambda word: word[1])
            if int(panel_width * 0.06) <= word[1] < course_right
        )).strip(" ：:|-|"))
        course_name_needs_confirmation = False
        if not _is_plausible_course_name(course_name):
            course_name = _read_course_name_from_row(panel, center_y, course_right)
            if not course_name:
                course_name = "課名待確認"
                course_name_needs_confirmation = True

        numeric_values = []
        score_positions = []
        for text, left, _top, _width, _height in row_words:
            if left < course_right:
                continue
            for value_text in re.findall(r"\d{1,3}", text):
                value = int(value_text)
                numeric_values.append(value)
                if 10 <= value <= 100:
                    score_positions.append((value, left + _width // 2))
        score_values = [value for value in numeric_values if 10 <= value <= 100]
        credit_values = [value for value in numeric_values if 0 <= value <= 10]
        score = max(score_values) if score_values else None
        credits = credit_values[0] if credit_values else None
        if score is None and (credits is None or credits >= 5):
            # A course row needs a plausible numeric anchor.  A lone large
            # credit value without a score is usually a summary-row fragment,
            # not a real course in this transcript layout.
            continue
        if credits == 0 and (course_name_needs_confirmation or re.search(r"[A-Za-z»><=,]", course_name)):
            # A zero-credit row containing symbols/Latin fragments is a
            # common OCR artefact from the transcript summary table.
            continue
        score_x = next((x for value, x in score_positions if value == score), None)
        semester = None
        if score_x is not None:
            semester = "第一學期" if score_x < panel_width * 0.84 else "第二學期"
        courses.append({
            "course_name": course_name,
            "credits": credits,
            "score": score,
            "score_band": score_band(score),
            "grade_level": f"{region_index}年級",
            "semester": semester,
            "source_page": 1,
            "source_line": row_index,
            "source_region": region_index,
        })
    return courses


def _read_course_name_from_row(panel, center_y, course_right):
    """Retry a blurry course-name cell using a tight, enlarged row crop."""
    top = max(0, int(center_y - 16))
    bottom = min(panel.height, int(center_y + 16))
    crop = panel.crop((int(panel.width * 0.03), top, min(panel.width, int(course_right * 1.04)), bottom))
    try:
        prepared = crop.convert("L")
        prepared = prepared.resize(
            (prepared.width * 6, prepared.height * 6),
            Image.Resampling.LANCZOS,
        )
        variants = [prepared]
        try:
            variants.append(ImageOps.autocontrast(prepared))
        except (AttributeError, TypeError):
            pass
    except (AttributeError, TypeError):
        variants = [crop]

    for psm in (7, 11):
        for variant in variants:
            try:
                text = pytesseract.image_to_string(
                    variant,
                    lang="chi_tra+eng",
                    config=f"--psm {psm}",
                )
            except Exception:
                continue
            for raw_line in text.splitlines():
                candidate = _repair_ocr_course_name(
                    _clean_course_name(raw_line).strip(" ：:|-|_—")
                )
                if _is_plausible_course_name(candidate):
                    return candidate
    return None


def _extract_transcript_panels(image):
    """OCR each academic panel separately for the known transcript layout."""
    width, height = image.size
    boundaries = [0.014, 0.203, 0.397, 0.592, 0.786, 0.977]
    courses = []
    for region_index in range(len(boundaries) - 1):
        left = int(width * boundaries[region_index])
        right = int(width * boundaries[region_index + 1])
        panel = image.crop((left, 0, right, height))
        cell_courses = _parse_transcript_panel_cells(panel, region_index + 1)
        if cell_courses:
            courses.extend(cell_courses)
            continue
        panel_width = panel.width
        column_crops = [
            panel.crop((0, 0, int(panel_width * 0.68), height)),
            panel.crop((int(panel_width * 0.68), 0, int(panel_width * 0.84), height)),
            panel.crop((int(panel_width * 0.84), 0, panel_width, height)),
        ]
        column_text = [
            pytesseract.image_to_string(column, lang="chi_tra+eng", config="--psm 6")
            for column in column_crops
        ]
        column_courses = parse_transcript_columns(*column_text, region_index=region_index + 1)
        if column_courses:
            courses.extend(column_courses)
            continue
        text = pytesseract.image_to_string(
            panel, lang="chi_tra", config="--psm 4"
        )
        courses.extend(_parse_transcript_table_text(text, region_index + 1))
    return _deduplicate_course_records(courses)


def _extract_transcript_summary(image):
    width, height = image.size
    boundaries = [0.014, 0.203, 0.397, 0.592, 0.786, 0.977]
    summaries = []
    for region_index in range(len(boundaries) - 1):
        left = int(width * boundaries[region_index])
        right = int(width * boundaries[region_index + 1])
        panel = image.crop((left, 0, right, height))
        summary_region = panel.crop((0, int(height * 0.62), panel.width, int(height * 0.82)))
        text = pytesseract.image_to_string(summary_region, lang="chi_tra+eng", config="--psm 6")
        summaries.extend(parse_academic_summary(text, f"{region_index + 1}年級"))
    return summaries


def _parse_credential_text(raw_text):
    credentials = []
    level_pattern = re.compile(r"(?P<level>[甲乙丙丁A-D]\s*級?)")
    for line_number, raw_line in enumerate(raw_text.splitlines(), start=1):
        line = _normalise_ocr_line(raw_line)
        if not line or any(keyword in line for keyword in ("證照名稱", "證書名稱", "發證單位")):
            continue
        match = level_pattern.search(line)
        if not match or "證" not in line:
            continue
        credential_name = line[: match.start()].strip(" ：:|-")
        if not credential_name:
            continue
        level = match.group("level").replace(" ", "")
        if not level.endswith("級"):
            level += "級"
        credentials.append({
            "credential_name": credential_name,
            "level": level,
            "issuing_organization": None,
            "source_page": 1,
            "source_line": line_number,
        })
    if not credentials:
        # Taiwan technician certificates often place the certificate title,
        # skill name, and level in separate visual regions.  Keep the skill
        # name when OCR can read it even if the level still needs confirmation.
        for line_number, raw_line in enumerate(raw_text.splitlines(), start=1):
            line = _normalise_ocr_line(raw_line)
            match = re.search(r"(電腦[^\s]{2,12}|[\u4e00-\u9fff]{2,12}軟體[\u4e00-\u9fff]{0,8})", line)
            if match:
                credentials.append({
                    "credential_name": match.group(1),
                    "level": None,
                    "issuing_organization": None,
                    "source_page": 1,
                    "source_line": line_number,
                })
                break
    return credentials


def _ocr_quality(document_type, raw_text):
    if document_type == "transcript":
        return len(_parse_transcript_text(raw_text))
    return sum("證" in line and re.search(r"[甲乙丙丁A-D]\s*級?", line) is not None for line in raw_text.splitlines())


def parse_ocr_text(document_type, raw_text):
    if document_type == "transcript":
        courses = _parse_transcript_text(raw_text)
        if not courses:
            raise RuntimeError("OCR 未辨識到可確認的課程資料，請改用清晰的匿名成績單或手動校正")
        return {"courses": _deduplicate_course_records(courses), "credentials": []}
    if document_type == "credential":
        credentials = _parse_credential_text(raw_text)
        if not credentials:
            raise RuntimeError("OCR 未辨識到可確認的證照資料，請改用清晰的匿名證照或手動校正")
        return {"courses": [], "credentials": credentials}
    raise ValueError("unsupported document type")


def _analyze_image_with_ocr(document_type, file_path):
    suffix = Path(file_path).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png"}:
        raise RuntimeError("OCR 目前只支援 JPG、JPEG、PNG；PDF 尚未設定影像轉換")
    try:
        with Image.open(file_path) as image:
            image, alignment_trace = _align_image_for_ocr(image)
            processing_steps = [
                {"step": "file_loaded", "width": image.width, "height": image.height},
                alignment_trace,
            ]
            panel_candidates = []
            candidates = []
            if document_type == "transcript":
                rotations = (270,) if image.height > image.width else (0,)
            else:
                rotations = (0,)
            for rotation in rotations:
                rotated = image.rotate(rotation, expand=True) if rotation else image
                ocr_variants = (
                    (rotated, _prepare_ocr_image(rotated))
                    if document_type == "transcript"
                    else (rotated,)
                )
                for variant_index, ocr_input in enumerate(ocr_variants):
                    if document_type == "transcript":
                        panel_courses = _extract_transcript_panels(ocr_input)
                        panel_candidates.append((len(panel_courses), rotation, panel_courses, variant_index))
                    ocr_image = ocr_input.resize((ocr_input.width * 3, ocr_input.height * 3)) if document_type == "credential" else ocr_input
                    text = pytesseract.image_to_string(
                        ocr_image,
                        lang="chi_tra+eng",
                        config="--psm 3" if document_type == "credential" else "--psm 6",
                    )
                    candidates.append((
                        _ocr_quality(document_type, text),
                        rotation,
                        text,
                        variant_index,
                    ))
            if document_type == "transcript" and panel_candidates:
                processing_steps.append({"step": "transcript_panels_scanned", "panel_count": 5})
                panel_quality, rotation, panel_courses, panel_variant = max(
                    panel_candidates, key=lambda item: item[0]
                )
            else:
                panel_quality, panel_courses = 0, []
            quality, text_rotation, raw_text, text_variant = max(candidates, key=lambda item: item[0])
            processing_steps.append({"step": "ocr_text_extracted", "rotation": text_rotation, "character_count": len(raw_text)})
            academic_summary = _extract_transcript_summary(rotated) if document_type == "transcript" else []
            if document_type == "credential":
                parsed = None
                for candidate_image in (rotated, ocr_image):
                    for psm in (3, 6, 11, 12):
                        candidate_text = pytesseract.image_to_string(
                            candidate_image, lang="chi_tra+eng", config=f"--psm {psm}"
                        )
                        try:
                            parsed = parse_ocr_text(document_type, candidate_text)
                        except RuntimeError:
                            continue
                        raw_text = candidate_text
                        quality = 1
                        break
                    if parsed is not None:
                        break
                if parsed is None:
                    raise RuntimeError("OCR 未辨識到可確認的證照資料，請改用清晰的匿名證照或手動校正")
                rotation = text_rotation
            elif panel_quality > quality:
                quality, rotation = panel_quality, rotation
                parsed = {"courses": panel_courses, "credentials": []}
            else:
                rotation = text_rotation
                parsed = parse_ocr_text(document_type, raw_text)
                if parsed.get("courses") or parsed.get("credentials"):
                    quality = max(quality, 1)
    except Exception as exc:
        raise RuntimeError(f"OCR 讀取檔案失敗：{exc}") from exc
    if quality <= 0:
        raise RuntimeError("OCR 未辨識到可確認的課程資料，請使用正向且清晰的匿名成績單或手動校正")
    parsed.update({
        "document_type": document_type,
        "academic_summary": academic_summary if document_type == "transcript" else [],
        "warnings": ["此資料由本機 OCR 產生，請學生逐項核對原始檔案後再確認。"],
        "source": {
            "file_name": Path(file_path).name,
            "document_type": document_type,
            "page": 1,
                "engine": "tesseract",
                "language": "chi_tra+eng",
                "rotation": rotation,
            },
        "source_file_available": True,
        "raw_text": raw_text,
        "processing_steps": processing_steps + [{
            "step": "fields_parsed",
            "course_count": len(parsed.get("courses", [])),
            "credential_count": len(parsed.get("credentials", [])),
        }],
    })
    return parsed


def analyze_document(document_type, file_path, provider_name="fake", ocr_engine=None):
    if document_type not in ALLOWED_DOCUMENT_TYPES:
        raise ValueError("unsupported document type")
    if provider_name == "offline_ocr":
        engine = ocr_engine or NotConfiguredOcrEngine()
        text = engine.recognize_text(file_path)
        result = parse_candidates(text, document_type)
        result["warnings"] = [CANDIDATE_WARNING]
        result["source_file_available"] = bool(file_path)
        result["simulation"] = False
        return result
    if provider_name == "demo":
        warning = "本機模擬 OCR：這些是假辨識資料，請先修正欄位；不會連接外部服務。"
        if document_type == "transcript":
            return {
                "document_type": document_type,
                "courses": [{"school_year": 3, "semester": "上", "course_name": "模擬辨識課程",
                             "credits": 3, "score": 88}],
                "credentials": None,
                "warnings": [warning],
                "source_file_available": bool(file_path),
                "simulation": True,
            }
        return {
            "document_type": document_type,
            "courses": None,
            "credentials": [{"credential_name": "模擬辨識證照", "level": "丙級",
                             "issuing_organization": "模擬發證單位", "issue_date": ""}],
            "warnings": [warning],
            "source_file_available": bool(file_path),
            "simulation": True,
        }
    if provider_name in {"ocr", "tesseract", "paddleocr", "rapidocr"}:
        from app.services.ocr_pipeline import analyze
        return analyze(document_type, file_path, "tesseract" if provider_name == "ocr" else provider_name)
    if provider_name != "fake":
        raise RuntimeError("目前尚未設定可用的文件分析服務")

    file_name = Path(file_path).name if file_path else None
    return {
        "document_type": document_type,
        "courses": (
            [
                {
                    "school_year": 115,
                    "semester": "一",
                    "course_name": "程式設計",
                    "credits": 3,
                    "score": 92,
                    "score_band": score_band(92),
                    "source_page": 1,
                }
            ]
            if document_type == "transcript"
            else []
        ),
        "credentials": (
            [
                {
                    "credential_name": "資訊技術類測試證照",
                    "level": "丙級",
                    "issuing_organization": "匿名測試機構",
                    "source_page": 1,
                }
            ]
            if document_type == "credential"
            else []
        ),
        "warnings": [
            "此為匿名測試用的待確認擷取草稿；請學生核對內容後再儲存。"
        ],
        "raw_text": "程式設計 3 92" if document_type == "transcript" else "資訊技術類測試證照 丙級",
        "processing_steps": [
            {"step": "file_loaded", "mode": "deterministic_demo"},
            {"step": "ocr_text_extracted", "mode": "deterministic_demo"},
            {"step": "fields_parsed", "course_count": 1 if document_type == "transcript" else 0, "credential_count": 1 if document_type == "credential" else 0},
        ],
        "source": {
            "file_name": file_name,
            "document_type": document_type,
            "page": 1,
            "mode": "deterministic_demo",
        },
        "source_file_available": bool(file_path),
    }
