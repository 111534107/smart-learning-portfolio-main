"""把每次上傳保存的處理步驟（processing_steps）翻成中文句子，給確認頁「查看 OCR 辨識過程」用。

步驟紀錄存在 DocumentExtraction.result_json 與操作紀錄（AuditLog），這裡只負責說明，不改紀錄本身。
舊紀錄缺少新欄位時，只說明有的部分。
"""

DEVICE_LABELS = {"cpu": "CPU", "dml": "顯示卡（DirectML）"}
TIER_LABELS = {"server": "伺服器版（較準）", "mobile": "輕量版（較快）"}
ENGINE_LABELS = {"rapidocr": "RapidOCR（PP-OCRv5）", "tesseract": "Tesseract", "paddleocr": "PaddleOCR"}


def _size(width, height):
    return f"{width}×{height}" if width and height else None


def _page_ocr(item):
    parts = [f"第 {item.get('page', 1)} 頁"]
    if item.get("source") == "pdf":
        size = _size(item.get("original_width"), item.get("original_height"))
        parts.append(f"PDF 以 {item.get('dpi', 300)} DPI 轉成圖片" + (f"（{size} 像素）" if size else ""))
    elif item.get("source") == "image":
        size = _size(item.get("original_width"), item.get("original_height"))
        if size:
            parts.append(f"圖片原始大小 {size} 像素")
    if item.get("tried_rotations"):
        tried = "、".join(str(angle) for angle in item["tried_rotations"])
        parts.append(f"試過 {tried} 度四個方向，選表格最多的方向（旋轉 {item.get('rotation', 0)} 度）")
    elif item.get("rotation"):
        parts.append(f"旋轉 {item['rotation']} 度")
    if item.get("panel_count"):
        parts.append(f"找到 {item['panel_count']} 個表格；逐格辨識前先去掉框線、依墨水找出每一列，空白格與框線殘影不辨識，"
                     "每格放大後再讀")
    elif item.get("document_type") == "credential":
        parts.append("整張辨識後，依「職類」「級別」「生效日期」等標籤找同一列的內容")
    size = _size(item.get("width"), item.get("height"))
    if size:
        parts.append(f"辨識時的圖片 {size} 像素")
    engine = ENGINE_LABELS.get(item.get("engine"), item.get("engine"))
    model = []
    if engine:
        model.append(engine)
    if item.get("model_tier"):
        model.append(TIER_LABELS.get(item["model_tier"], item["model_tier"]) + "模型")
    if item.get("device"):
        model.append("用" + DEVICE_LABELS.get(item["device"], item["device"]))
    if model:
        parts.append("、".join(model))
    return "；".join(parts) + "。"


def _resolution(item):
    verdict = {"ok": "足夠", "low": "偏低，可能漏讀，已提醒逐筆核對", "too_small": "太低，未辨識"}.get(item.get("level"), "")
    return f"檢查解析度：長邊 {item.get('long_side')} 像素（{verdict}）。"


DEMO_NOTE = "（示範模式，沒有真的辨識）"


def _file_loaded(item):
    if item.get("mode") == "deterministic_demo":
        return f"讀取檔案{DEMO_NOTE}。"
    size = _size(item.get("width"), item.get("height"))
    return f"讀取檔案（{size} 像素）。" if size else "讀取檔案。"


def _text_extracted(item):
    if item.get("mode") == "deterministic_demo":
        return f"產生示範文字{DEMO_NOTE}。"
    text = f"辨識文字（旋轉 {item.get('rotation', 0)} 度）"
    # 舊紀錄沒有字數時不寫，避免顯示成「0 個字元」
    if "character_count" in item:
        text += f"，抓到 {item['character_count']} 個字元"
    return text + "。"


def _credential_fields(item):
    kind = {"taiwan_technician_certificate": "中華民國技術士證",
            "possible_taiwan_technician_certificate": "疑似中華民國技術士證（標題需核對）"}.get(
        item.get("document_kind"), item.get("document_kind"))
    review = "，有欄位需要人工核對" if item.get("needs_review") else ""
    return f"第 {item.get('page', 1)} 頁判斷為{kind}，解析出各欄位{review}。"


DESCRIBERS = {
    "page_ocr": _page_ocr,
    "resolution_checked": _resolution,
    "credential_fields_parsed": _credential_fields,
    "credential_manual_review": lambda item: "證照類型或欄位沒有可靠辨識，請對照原圖人工填寫。",
    "file_loaded": _file_loaded,
    "image_auto_aligned": lambda item: "自動校正圖片歪斜。",
    "table_lines_removed": lambda item: "去掉表格框線。",
    "transcript_panels_scanned": lambda item: f"掃描成績單的 {item.get('panel_count', '')} 個學年表格。",
    "ocr_text_extracted": _text_extracted,
    "fields_parsed": lambda item: (f"整理欄位：課程 {item.get('course_count', 0)} 門、"
                                   f"證照 {item.get('credential_count', 0)} 筆。"),
}


def describe_step(item):
    if not isinstance(item, dict):
        return str(item)
    describer = DESCRIBERS.get(item.get("step"))
    return describer(item) if describer else f"其他處理步驟（{item.get('step')}）。"
