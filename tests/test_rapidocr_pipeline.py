"""把本機 RapidOCR（PP-OCRv5）接成組員 OCR 流程的一個引擎（合成資料，不連外部服務）。"""
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from app import create_app
from app.services.document_analysis_service import DEFAULT_OCR_MODEL_DIR, OCR_MODEL_TIERS, analyze_document

MSJH_FONT = "C:/Windows/Fonts/msjh.ttc"


def require_real_ocr():
    if not Path(MSJH_FONT).exists():
        pytest.skip("找不到 msjh.ttc 中文字型，無法產生合成圖片")
    if not all((DEFAULT_OCR_MODEL_DIR / name).exists() for name in OCR_MODEL_TIERS["server"].values()):
        pytest.skip("尚未下載離線 OCR 模型；請先執行 scripts/download_ocr_models.py")


def synthetic_text_image():
    font = ImageFont.truetype(MSJH_FONT, 40)
    image = Image.new("RGB", (900, 140), "white")
    ImageDraw.Draw(image).text((30, 40), "模擬資料結構 3 88", fill="black", font=font)
    return image


def test_recognize_supports_rapidocr_engine_with_teammate_token_format():
    from app.services.ocr_engines import recognize

    require_real_ocr()
    tokens = recognize(synthetic_text_image(), "rapidocr")

    assert any("模擬資料結構" in token["text"] for token in tokens)
    for token in tokens:
        left, top, right, bottom = token["bbox"]
        assert all(isinstance(value, float) for value in token["bbox"])
        assert left <= right and top <= bottom
        assert token["confidence"] is None or 0 <= token["confidence"] <= 1


def test_rapidocr_provider_runs_teammate_pipeline_with_rapidocr_engine(tmp_path, monkeypatch):
    import app.services.ocr_pipeline as ocr_pipeline

    calls = []
    monkeypatch.setattr(ocr_pipeline, "analyze", lambda *args: calls.append(args) or {"courses": []})
    image_path = tmp_path / "synthetic.png"
    Image.new("RGB", (10, 10), "white").save(image_path)

    analyze_document("transcript", image_path, "rapidocr")

    assert calls == [("transcript", image_path, "rapidocr")]


def test_rapidocr_counts_as_line_level_engine_like_paddleocr():
    from app.services.ocr_engines import LINE_LEVEL_ENGINES

    assert {"paddleocr", "paddle", "rapidocr"} <= LINE_LEVEL_ENGINES
    assert "tesseract" not in LINE_LEVEL_ENGINES


def test_rapidocr_engine_follows_configured_model_tier(tmp_path):
    from app.services.ocr_engines import configured_rapidocr_tier

    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "UPLOAD_FOLDER": str(tmp_path), "OCR_MODEL_TIER": "mobile"})
    with app.app_context():
        assert configured_rapidocr_tier() == "mobile"
    assert configured_rapidocr_tier() == "server"
