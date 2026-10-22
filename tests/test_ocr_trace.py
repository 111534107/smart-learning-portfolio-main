"""每次上傳都保存圖片的處理方式，並在確認頁用中文說明（合成資料）。"""
from pathlib import Path

from app.services.ocr_trace import describe_step


def test_pdf_transcript_page_explains_every_image_step():
    text = describe_step({"step": "page_ocr", "page": 1, "engine": "rapidocr", "source": "pdf", "dpi": 300,
                          "original_width": 2481, "original_height": 3507, "tried_rotations": [0, 270, 90, 180],
                          "rotation": 270, "panel_count": 5, "width": 3507, "height": 2481,
                          "model_tier": "server", "device": "dml", "document_type": "transcript"})

    assert "page_ocr" not in text
    assert "PDF" in text and "300 DPI" in text and "2481×3507" in text
    assert "旋轉 270 度" in text and "0、270、90、180" in text
    assert "5 個表格" in text
    assert "伺服器版" in text and "顯示卡" in text
    assert "框線" in text  # 逐格辨識前會先去掉框線


def test_image_credential_page_explains_label_matching():
    text = describe_step({"step": "page_ocr", "page": 1, "engine": "rapidocr", "source": "image",
                          "original_width": 1005, "original_height": 646, "rotation": 0, "panel_count": 0,
                          "width": 1005, "height": 646, "model_tier": "server", "device": "cpu",
                          "document_type": "credential"})

    assert "圖片原始大小 1005×646" in text
    assert "CPU" in text
    assert "標籤" in text


def test_other_steps_are_chinese_and_unknown_steps_are_marked():
    assert "長邊 2400 像素" in describe_step({"step": "resolution_checked", "long_side": 2400, "level": "low"})
    assert "偏低" in describe_step({"step": "resolution_checked", "long_side": 2400, "level": "low"})
    assert "需要人工" in describe_step({"step": "credential_fields_parsed", "page": 1,
                                        "document_kind": "taiwan_technician_certificate", "needs_review": True})
    assert "人工填寫" in describe_step({"step": "credential_manual_review", "needs_review": True})
    assert "something_new" in describe_step({"step": "something_new"})  # 沒翻譯的步驟照原名顯示，不會消失


def test_older_records_without_new_fields_still_describe():
    text = describe_step({"step": "page_ocr", "page": 2, "engine": "rapidocr", "rotation": 0,
                          "panel_count": 0, "width": 800, "height": 600})
    assert "第 2 頁" in text and "800×600" in text


def test_review_page_uses_the_chinese_description():
    review = (Path(__file__).resolve().parents[1] / "app" / "templates" / "learning_profile_review.html").read_text(encoding="utf-8")
    assert "{{ item|ocr_step }}" in review
    assert "<strong>{{ item.step }}</strong>" not in review


def test_pipeline_records_source_resolution_model_and_device():
    pipeline = (Path(__file__).resolve().parents[1] / "app" / "services" / "ocr_pipeline.py").read_text(encoding="utf-8")
    for key in ('"source"', '"dpi"', '"original_width"', '"tried_rotations"', '"model_tier"', '"device"', '"document_type"'):
        assert key in pipeline
