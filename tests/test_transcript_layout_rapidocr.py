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
