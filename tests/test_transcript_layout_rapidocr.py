"""學校成績單版型＋RapidOCR：年級表頭與逐格辨識（全部合成資料）。

真實成績單實測（不入庫）發現兩個原因：
1. RapidOCR 把「學年」辨識成簡體「学年」或形近字「举年」，年級規則只認「學年」，年級全部讀不到。
2. 窄小的數字欄用文字框偵測時，兩位數成績被拆成兩個框或漏掉（例如 70 只剩 0），造成整欄漏讀甚至讀錯。
"""
from pathlib import Path

import pytest

from app import create_app
from app.services.document_analysis_service import DEFAULT_OCR_MODEL_DIR, OCR_MODEL_TIERS
from app.services.ocr_pipeline import grade_from_header
from synthetic_transcript import MSJH_FONT, render


@pytest.mark.parametrize("text, expected", [
    ("第1學年", "1年級"),
    ("第2学年", "2年級"),   # 簡體「学」
    ("第1举年", "1年級"),   # 形近字「举」
    ("第 3 學 年", "3年級"),
])
def test_grade_from_header_accepts_simplified_and_lookalike_xue(text, expected):
    grade, _confidence = grade_from_header([{"text": text, "bbox": [0, 0, 10, 10], "confidence": 0.9}])

    assert grade == expected


def test_grade_from_header_does_not_guess_from_unrelated_text():
    grade, _confidence = grade_from_header([{"text": "四年忠班", "bbox": [0, 0, 10, 10], "confidence": 0.9}])

    assert grade is None


def require_models(tier):
    if not Path(MSJH_FONT).exists():
        pytest.skip("找不到 msjh.ttc 中文字型，無法產生合成成績單")
    if not all((DEFAULT_OCR_MODEL_DIR / name).exists() for name in OCR_MODEL_TIERS[tier].values()):
        pytest.skip("尚未下載離線 OCR 模型；請先執行 scripts/download_ocr_models.py")


@pytest.mark.parametrize("tier", ["server", "mobile"])
def test_rapidocr_reads_every_cell_of_synthetic_school_transcript(tmp_path, tier):
    from app.services.ocr_pipeline import analyze

    require_models(tier)
    image_path = tmp_path / "synthetic_transcript.png"
    expected = render(image_path)
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite://", "TESTING": True,
                      "UPLOAD_FOLDER": str(tmp_path), "OCR_MODEL_TIER": tier})

    with app.app_context():
        result = analyze("transcript", image_path, "rapidocr")

    got = sorted((c["grade_level"], c["semester"], c["course_name"], c["credits"], c["score"])
                 for c in result["courses"])
    want = sorted((e["grade_level"], e["semester"], e["course_name"], e["credits"], e["score"])
                  for e in expected)
    assert got == want


def test_row_bands_ignore_offset_thick_border_inside_column_margin():
    # 真實掃描檔的左框線落在偵測到的欄線右側幾個像素（x=1～5），會把每一列連成一大塊
    import numpy as np

    from app.services.ocr_pipeline import _text_row_bands

    ink = np.zeros((300, 120), dtype=bool)
    ink[:, 1:6] = True                      # 偏移、較粗的左框線
    ink[:, 59:62] = True                    # 欄與欄之間的直線
    for row in range(6):                    # 六列文字，每列 20 像素高、間距 12 像素
        y = 10 + row * 32
        ink[y:y + 20, 12:40] = True
        ink[y:y + 20, 70:100] = True

    bands = _text_row_bands(ink, [0, 60, 120])

    assert len(bands) == 6
    assert all(15 <= b - a <= 25 for a, b in bands)


def test_panel_cells_skip_punctuation_only_specks(tmp_path, monkeypatch):
    # 掃描檔上的小污點會被辨識成「.」「−」，不應變成一列課程或一個數值
    from PIL import Image

    from app.services import ocr_engines, ocr_pipeline

    image_path = tmp_path / "synthetic_transcript.png"
    render(image_path)
    image = Image.open(image_path).convert("RGB")
    panel = ocr_pipeline.detect_transcript_panels(image)[0]
    monkeypatch.setattr(ocr_engines, "recognize_rapidocr_line", lambda crop: (".", 0.4))

    assert ocr_pipeline._recognize_panel_cells(image, panel) == []


def test_rule_remnant_in_empty_cell_is_not_read_as_a_number(tmp_path, monkeypatch):
    # 真實掃描檔：表頭底線的淡灰殘影落在第一列空白的第二學期格子裡，被讀成成績「1」（信心 27%），
    # 多出一筆不及格的假課程。殘影只有 1～3 像素高，真正的字（連「1」）都會上下跨過一定高度。
    from PIL import Image, ImageDraw

    from app.services import ocr_engines, ocr_pipeline

    image_path = tmp_path / "synthetic_transcript.png"
    render(image_path)
    image = Image.open(image_path).convert("RGB")
    panel = ocr_pipeline.detect_transcript_panels(image)[0]
    left = panel["bbox"][0]
    top = panel["body"][0]
    columns = panel["columns"]
    # 第一年第四門「模擬音樂」只有第一學期；在它第二學期成績格畫一條 2 像素高的殘影
    row_y = top + 14 + 3 * 46 - 2
    ImageDraw.Draw(image).rectangle([left + columns[5] + 8, row_y, left + columns[6] - 8, row_y + 1], fill=(120, 120, 120))
    monkeypatch.setattr(ocr_engines, "recognize_rapidocr_line", lambda crop: ("1", 0.27))

    words = ocr_pipeline._recognize_panel_cells(image, panel)

    second_score_column = [w for w in words if left + columns[5] <= (w["bbox"][0] + w["bbox"][2]) / 2 < left + columns[6]]
    assert len(second_score_column) == 3   # 只有三門課真的有第二學期成績


def test_grade_header_crop_starts_at_table_top_rule_not_page_header(tmp_path, monkeypatch):
    # 真實成績單縮成長邊 1400～2400 像素時，三年級表頭裁切範圍包進了頁首「學號」那行，
    # 文字偵測把「第3學年」漏掉，整個三年級 24 門課的年級變成空白。表頭只該從表格最上緣的橫線讀起。
    from synthetic_transcript import TOP_RULE

    from app.services import ocr_pipeline

    image_path = tmp_path / "synthetic_transcript.png"
    render(image_path, student_line=True)
    header_boxes = []

    def fake_crop(image, box, engine, **_kwargs):
        if box[3] <= TOP_RULE + 300:  # 表頭裁切的下緣在表身上方
            header_boxes.append(box)
            return [{"text": "第1學年", "bbox": box, "confidence": 0.9}]
        return []

    monkeypatch.setattr(ocr_pipeline, "_recognize_crop", fake_crop)
    monkeypatch.setattr(ocr_pipeline, "_recognize_panel_cells",
                        lambda image, panel: [{"text": "模擬課程", "bbox": [panel["bbox"][0] + 60, panel["body"][0] + 10,
                                               panel["bbox"][0] + 200, panel["body"][0] + 40], "confidence": 0.9}])

    ocr_pipeline.analyze("transcript", image_path, "rapidocr")

    assert len(header_boxes) == 5
    assert all(TOP_RULE - 6 <= box[1] <= TOP_RULE + 6 for box in header_boxes)


def _header(text):
    return [{"text": text, "bbox": [0, 0, 10, 10], "confidence": 0.9}]


def test_missing_grade_header_is_inferred_from_school_year_range():
    # 真實成績單：「第 3 學年」緊貼表格上緣橫線，縮小後整行被漏掉，只剩「113年8月至114年6月」
    from app.services.ocr_pipeline import resolve_panel_grades

    grades = resolve_panel_grades([
        _header("第1学年111年8月至112年6月選课别"),
        _header("第2学年112年8月至113年6月選课别"),
        _header("113年8月至114年6月選课别第一学期"),
    ])

    assert [g for g, _conf, _note in grades] == ["1年級", "2年級", "3年級"]
    assert grades[2][1] is None                       # 推算的年級沒有辨識信心
    assert "起訖年月" in grades[2][2]
    assert grades[0][2] is None


def test_missing_grade_falls_back_to_panel_order_without_year_range():
    from app.services.ocr_pipeline import resolve_panel_grades

    grades = resolve_panel_grades([_header("第1學年"), _header("選課別"), _header("第3學年")])

    assert grades[1][0] == "2年級"
    assert "欄位順序" in grades[1][2]


def test_grade_is_left_blank_when_headers_disagree_or_nothing_is_known():
    from app.services.ocr_pipeline import resolve_panel_grades

    # 已讀到的兩欄互相矛盾（1、1），不替中間那欄猜
    assert resolve_panel_grades([_header("第1學年"), _header("選課別"), _header("第1學年")])[1][0] is None
    assert resolve_panel_grades([_header("選課別"), _header("113年8月至114年6月")]) == [(None, None, None)] * 2


def test_analyze_fills_grade_from_year_range_and_asks_student_to_check(tmp_path, monkeypatch):
    from PIL import Image
    from synthetic_transcript import TOP_RULE

    from app.services import ocr_pipeline

    image_path = tmp_path / "synthetic_transcript.png"
    render(image_path, student_line=True)
    panels = ocr_pipeline.detect_transcript_panels(Image.open(image_path))
    headers = {panels[0]["bbox"][0]: "第1學年111年8月至112年6月",
               panels[1]["bbox"][0]: "第2學年112年8月至113年6月",
               panels[2]["bbox"][0]: "113年8月至114年6月"}

    def fake_crop(image, box, engine, **_kwargs):
        if box[3] <= TOP_RULE + 300 and box[0] in headers:
            return [{"text": headers[box[0]], "bbox": box, "confidence": 0.9}]
        return []

    def fake_cells(image, panel):
        if panel["bbox"][0] not in headers:
            return []
        y = panel["body"][0] + 10
        return [{"text": "模擬課程", "bbox": [panel["bbox"][0] + 60, y, panel["bbox"][0] + 200, y + 30], "confidence": 0.9},
                {"text": "3", "bbox": [panel["bbox"][0] + 390, y, panel["bbox"][0] + 430, y + 30], "confidence": 0.9}]

    monkeypatch.setattr(ocr_pipeline, "_recognize_crop", fake_crop)
    monkeypatch.setattr(ocr_pipeline, "_recognize_panel_cells", fake_cells)

    courses = ocr_pipeline.analyze("transcript", image_path, "rapidocr")["courses"]

    assert [c["grade_level"] for c in courses] == ["1年級", "2年級", "3年級"]
    assert any("起訖年月" in reason for reason in courses[2]["review_reasons"])
    assert not any("起訖年月" in reason for reason in courses[0]["review_reasons"])


def test_dense_title_above_one_panel_does_not_move_its_header_top(tmp_path):
    # 真實成績單縮到 1400～1600 像素時，第二學年欄正上方的頁首大標題字很密，被當成一條橫線，
    # 那一欄的表頭又包進學號列。各學年欄的表格上緣在同一高度。
    from PIL import Image, ImageDraw
    from synthetic_transcript import TOP_RULE

    from app.services import ocr_pipeline

    image_path = tmp_path / "synthetic_transcript.png"
    render(image_path, student_line=True)
    image = Image.open(image_path).convert("RGB")
    second = ocr_pipeline.detect_transcript_panels(image)[1]["bbox"]
    ImageDraw.Draw(image).rectangle([second[0], TOP_RULE - 20, second[2], TOP_RULE - 16], fill="black")

    panels = ocr_pipeline.detect_transcript_panels(image)

    assert [p["header_top"] for p in panels] == [TOP_RULE] * 5


def test_panel_order_fallback_counts_empty_panels_between_read_ones():
    from app.services.ocr_pipeline import resolve_panel_grades

    # 第二欄沒有課（表頭也沒讀），第三欄讀不到年級也沒有年份 → 依欄位順序應是 3 年級
    grades = resolve_panel_grades([_header("第1學年"), [], _header("選課別")])

    assert grades[2][0] == "3年級"
