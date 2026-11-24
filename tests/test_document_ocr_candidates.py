"""M3／M4：上傳證明 → 離線 OCR 候選欄位（合成資料，不連外部服務）。

全部測試使用合成圖片與測試替身 OCR 引擎；尚未選定正式 OCR 套件（RapidOCR 待使用者確認），
因此這裡只驗證介面、候選解析與「未確認前不寫入正式資料」的規則。
"""
import io
from pathlib import Path

import pytest
from PIL import Image

from app import create_app
from app.extensions import db
from app.models import CredentialRecord, DocumentExtraction, LearningCourseRecord, SourceDocument, User
from app.services.document_analysis_service import analyze_document, parse_candidates


SYNTHETIC_TRANSCRIPT_TEXT = "課程：模擬資料結構 學分：3 分數：88\n課程：模擬網頁設計 學分：2 分數：91"
SYNTHETIC_CREDENTIAL_TEXT = "證照名稱：模擬電腦技能丙級 發證單位：模擬發證單位 日期：2026-09-01"


class FakeOcrEngine:
    """測試替身：不讀像素，只回傳與合成圖片對應的固定文字。"""

    def __init__(self, text):
        self.text = text
        self.seen_paths = []

    def recognize_text(self, image_path):
        self.seen_paths.append(image_path)
        return self.text


def synthetic_png_bytes(size=(800, 200)):
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_offline_ocr_text_becomes_course_candidates_with_names_and_scores(tmp_path):
    image_path = tmp_path / "synthetic_transcript.png"
    image_path.write_bytes(synthetic_png_bytes())
    engine = FakeOcrEngine(SYNTHETIC_TRANSCRIPT_TEXT)

    result = analyze_document("transcript", image_path, "offline_ocr", ocr_engine=engine)

    assert engine.seen_paths == [image_path]
    assert result["simulation"] is False
    assert result["courses"] == [
        {"school_year": None, "semester": None, "course_name": "模擬資料結構", "credits": "3", "score": "88"},
        {"school_year": None, "semester": None, "course_name": "模擬網頁設計", "credits": "2", "score": "91"},
    ]
    assert any("候選" in warning and "確認" in warning for warning in result["warnings"])


def test_offline_ocr_text_becomes_credential_candidate_with_issuer_and_date(tmp_path):
    image_path = tmp_path / "synthetic_credential.png"
    image_path.write_bytes(synthetic_png_bytes())

    result = analyze_document(
        "credential", image_path, "offline_ocr", ocr_engine=FakeOcrEngine(SYNTHETIC_CREDENTIAL_TEXT)
    )

    assert result["credentials"] == [{
        "credential_name": "模擬電腦技能丙級",
        "level": "",
        "issuing_organization": "模擬發證單位",
        "issue_date": "2026-09-01",
    }]


def test_offline_ocr_without_configured_engine_fails_instead_of_guessing(tmp_path):
    image_path = tmp_path / "synthetic.png"
    image_path.write_bytes(synthetic_png_bytes())

    try:
        analyze_document("transcript", image_path, "offline_ocr")
    except RuntimeError as exc:
        assert "離線 OCR" in str(exc)
    else:
        raise AssertionError("未設定 OCR 引擎時不應回傳任何猜測結果")


def test_parse_candidates_leaves_missing_fields_empty_instead_of_inventing_them():
    result = parse_candidates("課程：模擬微積分", "transcript")

    assert result["courses"] == [
        {"school_year": None, "semester": None, "course_name": "模擬微積分", "credits": "", "score": ""}
    ]


def test_parse_candidates_splits_labels_that_ocr_merged_without_spaces():
    # 實測 PP-OCRv5 會把「學分：3  分數：88」辨識成沒有空白的「學分：3分數：88」
    result = parse_candidates("課程：模擬資料結構  學分：3分數：88", "transcript")

    assert result["courses"] == [
        {"school_year": None, "semester": None, "course_name": "模擬資料結構", "credits": "3", "score": "88"}
    ]


def test_upload_with_offline_ocr_stores_candidates_only_until_student_confirms(tmp_path):
    engine = FakeOcrEngine(SYNTHETIC_TRANSCRIPT_TEXT)
    app = create_app({
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "TESTING": True,
        "UPLOAD_FOLDER": str(tmp_path),
        "DOCUMENT_ANALYSIS_PROVIDER": "offline_ocr",
        "OCR_ENGINE": engine,
    })
    with app.app_context():
        db.create_all()
        student = User(username="student_demo", display_name="合成學生", role="student")
        student.set_password("pw")
        db.session.add(student)
        db.session.commit()
    client = app.test_client()
    client.post("/login", data={"username": "student_demo", "password": "pw"})

    response = client.post("/student/learning-profile/documents", data={
        "document_type": "transcript",
        "file": (io.BytesIO(synthetic_png_bytes((3200, 800))), "synthetic_transcript.png"),  # 長邊須達上傳門檻
    }, content_type="multipart/form-data")

    assert response.status_code == 302
    with app.app_context():
        source = SourceDocument.query.one()
        extraction = DocumentExtraction.query.one()
        assert source.status == "extracted"
        assert extraction.status == "extracted"
        assert extraction.result_json["courses"][0]["course_name"] == "模擬資料結構"
        # 候選尚未經學生確認，正式課程資料必須是空的。
        assert LearningCourseRecord.query.count() == 0
        source_id = source.id
        # 組員的確認流程要求送回草稿版本，避免舊分頁覆蓋較新的修正
        draft_revision = extraction.result_json["draft_revision"]

    review_page = client.get(f"/student/learning-profile/documents/{source_id}/review")
    assert review_page.status_code == 200

    response = client.post(f"/student/learning-profile/documents/{source_id}/review/confirm", data={
        "draft_revision": draft_revision,
        "courses_json": '[{"school_year": "3", "semester": "上", "course_name": "模擬資料結構", '
                        '"credits": "3", "score": "88"}]',
        "credentials_json": "[]",
    })
    assert response.status_code == 302
    with app.app_context():
        assert LearningCourseRecord.query.count() == 1
        assert CredentialRecord.query.count() == 0


def test_upload_with_offline_ocr_but_no_engine_marks_analysis_failed(tmp_path):
    app = create_app({
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "TESTING": True,
        "UPLOAD_FOLDER": str(tmp_path),
        "DOCUMENT_ANALYSIS_PROVIDER": "offline_ocr",
    })
    with app.app_context():
        db.create_all()
        student = User(username="student_demo", display_name="合成學生", role="student")
        student.set_password("pw")
        db.session.add(student)
        db.session.commit()
    client = app.test_client()
    client.post("/login", data={"username": "student_demo", "password": "pw"})

    client.post("/student/learning-profile/documents", data={
        "document_type": "transcript",
        "file": (io.BytesIO(synthetic_png_bytes((3200, 800))), "synthetic_transcript.png"),  # 長邊須達上傳門檻
    }, content_type="multipart/form-data")

    with app.app_context():
        assert SourceDocument.query.one().status == "analysis_failed"
        assert DocumentExtraction.query.one().status == "failed"
        assert LearningCourseRecord.query.count() == 0


MSJH_FONT = "C:/Windows/Fonts/msjh.ttc"


def render_synthetic_transcript_png(path):
    """用系統中文字型畫一張合成成績單圖片（內容全部是假資料）。"""
    from PIL import ImageDraw, ImageFont

    font = ImageFont.truetype(MSJH_FONT, 40)
    image = Image.new("RGB", (1000, 260), "white")
    draw = ImageDraw.Draw(image)
    draw.text((30, 40), "課程：模擬資料結構  學分：3  分數：88", fill="black", font=font)
    draw.text((30, 150), "課程：模擬網頁設計  學分：2  分數：91", fill="black", font=font)
    image.save(path, format="PNG")
    return path


def require_real_ocr():
    from app.services.document_analysis_service import DEFAULT_OCR_MODEL_DIR, OCR_MODEL_TIERS

    if not Path(MSJH_FONT).exists():
        pytest.skip("找不到 msjh.ttc 中文字型，無法產生合成圖片")
    if not all((DEFAULT_OCR_MODEL_DIR / name).exists() for name in OCR_MODEL_TIERS["server"].values()):
        pytest.skip("尚未下載離線 OCR 模型；請先執行 scripts/download_ocr_models.py")


def test_rapidocr_engine_reads_synthetic_transcript_numbers(tmp_path):
    from app.services.document_analysis_service import RapidOcrEngine

    require_real_ocr()
    image_path = render_synthetic_transcript_png(tmp_path / "synthetic_transcript.png")

    text = RapidOcrEngine().recognize_text(image_path)

    assert "學分" in text
    assert "88" in text
    assert "91" in text


def test_rapidocr_engine_reads_synthetic_chinese_transcript_names(tmp_path):
    from app.services.document_analysis_service import RapidOcrEngine

    require_real_ocr()
    image_path = render_synthetic_transcript_png(tmp_path / "synthetic_transcript.png")

    text = RapidOcrEngine().recognize_text(image_path)

    assert "模擬資料結構" in text


def test_rapidocr_transcript_image_yields_candidates_through_analyze_document(tmp_path):
    from app.services.document_analysis_service import RapidOcrEngine

    require_real_ocr()
    image_path = render_synthetic_transcript_png(tmp_path / "synthetic_transcript.png")

    result = analyze_document("transcript", image_path, "offline_ocr", ocr_engine=RapidOcrEngine())

    assert [(c["course_name"], c["credits"], c["score"]) for c in result["courses"]] == [
        ("模擬資料結構", "3", "88"),
        ("模擬網頁設計", "2", "91"),
    ]
    assert result["simulation"] is False


def test_rapidocr_engine_without_model_files_fails_instead_of_downloading(tmp_path):
    from app.services.document_analysis_service import RapidOcrEngine

    image_path = tmp_path / "synthetic.png"
    image_path.write_bytes(synthetic_png_bytes())

    with pytest.raises(RuntimeError, match="download_ocr_models"):
        RapidOcrEngine(model_dir=tmp_path / "no-models").recognize_text(image_path)


def test_create_app_wires_rapidocr_only_when_explicitly_enabled(tmp_path):
    from app.services.document_analysis_service import RapidOcrEngine

    default_app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                              "UPLOAD_FOLDER": str(tmp_path)})
    enabled_app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                              "UPLOAD_FOLDER": str(tmp_path), "DOCUMENT_OCR_ENGINE": "rapidocr"})

    assert default_app.config.get("OCR_ENGINE") is None
    assert isinstance(enabled_app.config["OCR_ENGINE"], RapidOcrEngine)
    assert enabled_app.config["OCR_ENGINE"].tier == "server"


def test_rapidocr_engine_defaults_to_server_models():
    from app.services.document_analysis_service import RapidOcrEngine

    engine = RapidOcrEngine()

    assert engine.tier == "server"
    assert engine.model_files["Det"] == "ch_PP-OCRv5_det_server.onnx"
    assert engine.model_files["Rec"] == "ch_PP-OCRv5_rec_server.onnx"


def test_rapidocr_engine_can_fall_back_to_mobile_models():
    from app.services.document_analysis_service import RapidOcrEngine

    engine = RapidOcrEngine(tier="mobile")

    assert engine.model_files["Rec"] == "ch_PP-OCRv5_rec_mobile.onnx"


def test_rapidocr_engine_rejects_unknown_model_tier():
    from app.services.document_analysis_service import RapidOcrEngine

    with pytest.raises(ValueError):
        RapidOcrEngine(tier="huge")


def test_create_app_passes_configured_model_tier(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "UPLOAD_FOLDER": str(tmp_path), "DOCUMENT_OCR_ENGINE": "rapidocr",
                      "OCR_MODEL_TIER": "mobile"})

    assert app.config["OCR_ENGINE"].tier == "mobile"
