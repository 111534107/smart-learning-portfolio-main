import io
from pathlib import Path

import pytest
from PIL import Image

from app import create_app
from app.extensions import db
from app.models import AuditLog, DocumentExtraction, SourceDocument, User
from app.services import document_analysis_service
from app.services.document_analysis_service import (
    _extract_transcript_panels,
    _parse_transcript_panel_cells,
    _read_course_name_from_row,
    _repair_ocr_course_name,
    _prepare_ocr_image,
    _remove_table_lines,
    _deduplicate_course_records,
    _align_image_for_ocr,
    _is_plausible_course_name,
    analyze_document,
    parse_ocr_text,
    parse_academic_summary,
    score_band,
    parse_transcript_columns,
)


def test_align_image_for_ocr_recenters_shifted_content():
    image = Image.new("L", (200, 120), 255)
    for x in range(20, 80):
        for y in range(35, 85):
            image.putpixel((x, y), 0)

    aligned, trace = _align_image_for_ocr(image)
    dark = aligned.point(lambda value: 0 if value < 128 else 255).getbbox()

    assert dark is not None
    assert abs(((dark[0] + dark[2]) / 2) - 100) < 8
    assert abs(((dark[1] + dark[3]) / 2) - 60) < 8
    assert trace["step"] == "image_auto_aligned"
    assert trace["translation_applied"] is True


def learning_profile_app(tmp_path):
    app = create_app({
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "TESTING": True,
        "UPLOAD_FOLDER": str(tmp_path),
        "DOCUMENT_ANALYSIS_PROVIDER": "fake",
    })
    with app.app_context():
        db.create_all()
        student = User(username="student_demo", display_name="測試學生甲", role="student")
        student.set_password("pw")
        db.session.add(student)
        db.session.commit()
    return app


def login(client):
    client.post("/login", data={"username": "student_demo", "password": "pw"})


def test_student_upload_creates_private_source_document_and_extraction(tmp_path):
    app = learning_profile_app(tmp_path)
    client = app.test_client()
    login(client)

    response = client.post(
        "/student/learning-profile/documents",
        data={
            "document_type": "transcript",
            "file": (io.BytesIO(b"demo transcript"), "transcript.pdf"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 302
    with app.app_context():
        document = SourceDocument.query.one()
        extraction = DocumentExtraction.query.one()
        assert document.owner.username == "student_demo"
        assert document.document_type == "transcript"
        assert document.status == "extracted"
        assert document.file_path != "transcript.pdf"
        assert extraction.source_document_id == document.id
        assert extraction.provider == "fake"
        assert extraction.status == "extracted"
        assert extraction.result_json["document_type"] == "transcript"


def test_student_upload_records_ocr_processing_trace(tmp_path):
    app = learning_profile_app(tmp_path)
    client = app.test_client()
    login(client)

    response = client.post(
        "/student/learning-profile/documents",
        data={
            "document_type": "transcript",
            "file": (io.BytesIO(b"demo transcript"), "transcript.pdf"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 302
    with app.app_context():
        log = AuditLog.query.filter_by(action="learning_profile.ocr_completed").one()
        assert log.target_type == "source_document"
        assert log.detail_json["document_type"] == "transcript"
        assert log.detail_json["parsed_count"] == 1
        assert log.detail_json["processing_steps"]


def test_learning_profile_rejects_unapproved_document_type(tmp_path):
    app = learning_profile_app(tmp_path)
    client = app.test_client()
    login(client)

    response = client.post(
        "/student/learning-profile/documents",
        data={
            "document_type": "identity_card",
            "file": (io.BytesIO(b"private"), "card.png"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    with app.app_context():
        assert SourceDocument.query.count() == 0


def test_learning_profile_forms_render_current_csrf_token():
    app = learning_profile_app("instance/test-learning-profile")
    client = app.test_client()
    login(client)
    with client.session_transaction() as session:
        session["csrf_token"] = "known-token"

    response = client.get("/student/learning-profile")

    assert b'value="known-token"' in response.data


@pytest.mark.skip(reason="組員的學習歷程頁改版（含上傳前預覽旋轉）本次未搬，保留本分支頁面；之後若要採用再移除此行")
def test_learning_profile_upload_has_scan_preview_controls():
    app = learning_profile_app("instance/test-learning-profile-scan")
    client = app.test_client()
    login(client)

    response = client.get("/student/learning-profile")

    assert b"scan-preview" in response.data
    assert b"rotate-scan" in response.data
    assert "掃描預覽".encode() in response.data
    assert b"learning-profile-hero" in response.data
    assert b"source-list" in response.data
    assert "已生成草稿".encode() in response.data


def test_fake_transcript_extraction_returns_non_empty_traceable_courses():
    result = analyze_document("transcript", Path("anonymous-transcript.pdf"), "fake")

    assert result["courses"]
    assert result["courses"][0]["course_name"] == "程式設計"
    assert result["source"]["file_name"] == "anonymous-transcript.pdf"


def test_fake_credential_extraction_returns_non_empty_traceable_credential():
    result = analyze_document("credential", Path("anonymous-credential.jpg"), "fake")

    assert result["credentials"]
    assert result["credentials"][0]["credential_name"] == "資訊技術類測試證照"
    assert result["source"]["file_name"] == "anonymous-credential.jpg"


def test_ocr_transcript_parser_extracts_non_empty_traceable_courses():
    result = parse_ocr_text(
        "transcript",
        "課程名稱 學分 成績\n程式設計 3 92\n資料庫管理 3 85",
    )

    assert result["courses"] == [
        {
            "course_name": "程式設計",
            "credits": 3,
            "score": 92,
            "score_band": "85–94",
            "makeup_season": None,
            "source_page": 1,
            "source_line": 2,
        },
        {
            "course_name": "資料庫管理",
            "credits": 3,
            "score": 85,
            "score_band": "85–94",
            "makeup_season": None,
            "source_page": 1,
            "source_line": 3,
        },
    ]


def test_ocr_transcript_parser_removes_required_course_prefix():
    result = parse_ocr_text("transcript", "必|商業套裝軟體 2 85")

    assert result["courses"][0]["course_name"] == "商業套裝軟體"


def test_ocr_text_parser_keeps_summer_and_winter_makeup_categories_separate_from_course_names():
    result = parse_ocr_text(
        "transcript", "[暑] 程式設計 3 85\n[寒] 資料庫管理 2 78"
    )
    assert [(course["course_name"], course["makeup_season"]) for course in result["courses"]] == [
        ("程式設計", "summer"), ("資料庫管理", "winter"),
    ]


def test_ocr_transcript_parser_normalises_spaced_and_noisy_course_names():
    result = parse_ocr_text(
        "transcript",
        "必|一年聽育 ie 1 84\n必|統 計 學 3 15\n密|三年康寧 2 77",
    )

    assert [course["course_name"] for course in result["courses"]] == [
        "一年聽育 ie",
        "統計學",
        "三年康寧",
    ]


def test_course_name_cleaning_removes_ocr_punctuation_prefixes():
    result = parse_ocr_text("transcript", ">|數位化資料處理 2 81")

    assert result["courses"][0]["course_name"] == "數位化資料處理"


def test_unknown_courses_are_not_collapsed_without_source_identity():
    courses = [
        {"course_name": "課名待確認", "credits": 2, "score": 84, "semester": "第一學期", "grade_level": "1年級"},
        {"course_name": "課名待確認", "credits": 2, "score": 84, "semester": "第一學期", "grade_level": "1年級"},
    ]

    assert _deduplicate_course_records(courses) == courses


def test_transcript_columns_are_recombined_into_course_records():
    result = parse_transcript_columns(
        "程式設計\n資料庫管理",
        "3\n3",
        "92\n85",
        region_index=2,
    )

    assert result == [
        {
            "course_name": "程式設計",
            "credits": 3,
            "score": 92,
            "score_band": "85–94",
            "grade_level": "2年級",
            "source_page": 1,
            "source_line": 1,
            "source_region": 2,
        },
        {
            "course_name": "資料庫管理",
            "credits": 3,
            "score": 85,
            "score_band": "85–94",
            "grade_level": "2年級",
            "source_page": 1,
            "source_line": 2,
            "source_region": 2,
        },
    ]


def test_transcript_panel_extractor_scans_the_fifth_year_column(monkeypatch):
    crop_boxes = []

    class FakeImage:
        size = (1000, 100)
        width = 1000
        height = 100

        def crop(self, box):
            crop_boxes.append(box)
            return self

    monkeypatch.setattr(
        document_analysis_service.pytesseract,
        "image_to_string",
        lambda *_args, **_kwargs: "",
    )

    _extract_transcript_panels(FakeImage())

    assert (786, 0, 977, 100) in crop_boxes


def test_ocr_preparation_upscales_and_improves_contrast():
    prepared = _prepare_ocr_image(Image.new("RGB", (100, 50), "white"))

    assert prepared.size == (200, 100)


def test_table_line_removal_keeps_text_like_marks_but_clears_long_lines():
    image = Image.new("L", (120, 80), 255)
    for x in range(120):
        image.putpixel((x, 40), 0)
    for y in range(35, 46):
        for x in range(55, 65):
            image.putpixel((x, y), 0)

    cleaned, trace = _remove_table_lines(image)

    assert cleaned.getpixel((10, 40)) == 255
    assert cleaned.getpixel((60, 40)) == 0
    assert trace["horizontal_lines_removed"] >= 1


def test_transcript_filter_rejects_summary_rows_and_ocr_gibberish():
    assert not _is_plausible_course_name("fF 成 & 90.00)")
    assert not _is_plausible_course_name("RRERE")
    assert not _is_plausible_course_name("得 FF")
    assert not _is_plausible_course_name("計學 分")
    assert not _is_plausible_course_name("BH 科目")
    assert not _is_plausible_course_name("Lex * 總 平 課")
    assert not _is_plausible_course_name("Lex * 總 平 課|")
    assert not _is_plausible_course_name("六號")
    assert _is_plausible_course_name("資料庫管理")
    assert _is_plausible_course_name("JAVA程式語言")


def test_transcript_keeps_course_when_score_is_missing(monkeypatch):
    class FakePanel:
        size = (100, 100)
        width = 100
        height = 100

    data = {
        "text": ["體育", "2"],
        "left": [10, 75],
        "top": [20, 20],
        "width": [20, 8],
        "height": [10, 10],
    }
    monkeypatch.setattr(document_analysis_service.pytesseract, "image_to_data", lambda *_args, **_kwargs: data)
    result = _parse_transcript_panel_cells(FakePanel(), region_index=1)

    assert result[0]["course_name"] == "體育"
    assert result[0]["credits"] == 2
    assert result[0]["score"] is None


def test_transcript_drops_unanchored_noise_without_score_or_credits(monkeypatch):
    class FakePanel:
        size = (100, 100)
        width = 100
        height = 100

    data = {
        "text": ["二年體育"],
        "left": [10],
        "top": [20],
        "width": [30],
        "height": [10],
    }
    monkeypatch.setattr(document_analysis_service.pytesseract, "image_to_data", lambda *_args, **_kwargs: data)

    assert _parse_transcript_panel_cells(FakePanel(), region_index=2) == []


def test_transcript_keeps_zero_credit_courses_without_a_score(monkeypatch):
    class FakePanel:
        size = (100, 100)
        width = 100
        height = 100

    data = {
        "text": ["三年康寧", "0"],
        "left": [10, 75],
        "top": [20, 20],
        "width": [30, 8],
        "height": [10, 10],
    }
    monkeypatch.setattr(document_analysis_service.pytesseract, "image_to_data", lambda *_args, **_kwargs: data)

    result = _parse_transcript_panel_cells(FakePanel(), region_index=3)

    assert len(result) == 1
    assert result[0]["course_name"] == "三年康寧"
    assert result[0]["credits"] == 0
    assert result[0]["score"] is None


def test_transcript_drops_summary_noise_that_only_looks_like_five_credits(monkeypatch):
    class FakePanel:
        size = (100, 100)
        width = 100
        height = 100

    data = {
        "text": ["行銷管理", "5"],
        "left": [10, 75],
        "top": [20, 20],
        "width": [30, 8],
        "height": [10, 10],
    }
    monkeypatch.setattr(document_analysis_service.pytesseract, "image_to_data", lambda *_args, **_kwargs: data)

    assert _parse_transcript_panel_cells(FakePanel(), region_index=2) == []


def test_transcript_drops_zero_credit_symbol_noise_with_a_score(monkeypatch):
    class FakePanel:
        size = (100, 100)
        width = 100
        height = 100

    data = {
        "text": ["» i 和年 =>,", "0", "29"],
        "left": [10, 75, 90],
        "top": [20, 20, 20],
        "width": [35, 8, 8],
        "height": [10, 10, 10],
    }
    monkeypatch.setattr(document_analysis_service.pytesseract, "image_to_data", lambda *_args, **_kwargs: data)

    assert _parse_transcript_panel_cells(FakePanel(), region_index=2) == []


def test_course_name_row_ocr_retries_with_an_upscaled_crop(monkeypatch):
    class FakeCrop:
        width = 60
        height = 20

        def convert(self, _mode):
            return self

        def resize(self, _size, _resample):
            return self

        def filter(self, _filter):
            return self

    class FakePanel:
        width = 100
        height = 100

        def crop(self, _box):
            return FakeCrop()

    monkeypatch.setattr(
        document_analysis_service.pytesseract,
        "image_to_string",
        lambda *_args, **_kwargs: "一年體育",
    )

    assert _read_course_name_from_row(FakePanel(), 40, 68) == "一年體育"


def test_course_name_row_ocr_tries_additional_layout_modes(monkeypatch):
    class FakeCrop:
        width = 60
        height = 20

        def convert(self, _mode):
            return self

        def resize(self, _size, _resample):
            return self

        def point(self, _function):
            return self

    class FakePanel:
        width = 100
        height = 100

        def crop(self, _box):
            return FakeCrop()

    def fake_ocr(_image, *, config, **_kwargs):
        return "123" if config == "--psm 7" else "資料庫管理"

    monkeypatch.setattr(document_analysis_service.pytesseract, "image_to_string", fake_ocr)

    assert _read_course_name_from_row(FakePanel(), 40, 68) == "資料庫管理"


def test_ocr_course_name_does_not_guess_uncertain_characters():
    assert _repair_ocr_course_name("一年聽育") == "一年聽育"
    assert _repair_ocr_course_name("一年族文") == "一年族文"


def test_academic_summary_is_parsed_separately_from_courses():
    result = parse_academic_summary(
        "學業成績總平均 84.83 82.39\n"
        "總修學分 29.0 28.0\n"
        "實得學分 29.0 28.0\n"
        "累計學分 29.0 57.0\n"
        "採行成績 90.00 97.00",
        grade_level="一年級",
    )

    assert result == [
        {"grade_level": "一年級", "metric": "學業成績總平均", "semester_1": 84.83, "semester_2": 82.39},
        {"grade_level": "一年級", "metric": "總修學分", "semester_1": 29.0, "semester_2": 28.0},
        {"grade_level": "一年級", "metric": "實得學分", "semester_1": 29.0, "semester_2": 28.0},
        {"grade_level": "一年級", "metric": "累計學分", "semester_1": 29.0, "semester_2": 57.0},
        {"grade_level": "一年級", "metric": "採行成績", "semester_1": 90.0, "semester_2": 97.0},
    ]


def test_academic_summary_uses_row_order_when_labels_are_garbled():
    result = parse_academic_summary(
        "xx 84.83 8239\n"
        "xx 29.0 28.0\n"
        "xx 29.0 57.0\n"
        "xx 90.00 97.00",
        grade_level="一年級",
    )

    assert [item["metric"] for item in result] == [
        "學業成績總平均",
        "總修學分",
        "實得學分",
        "累計學分",
    ]
    assert result[0]["semester_2"] == 82.39


def test_ocr_credential_parser_extracts_non_empty_traceable_credential():
    result = parse_ocr_text(
        "credential",
        "證照名稱 等級\n資訊技術類測試證照 丙級\n發證單位 匿名測試機構",
    )

    assert result["credentials"] == [
        {
            "credential_name": "資訊技術類測試證照",
            "level": "丙級",
            "issuing_organization": None,
            "source_page": 1,
            "source_line": 2,
        }
    ]


def test_ocr_technician_certificate_parser_keeps_skill_name_for_confirmation():
    result = parse_ocr_text("credential", "中華民國技術士證\n電腦軟體應用\n級別")

    assert result["credentials"][0]["credential_name"] == "電腦軟體應用"
    assert result["credentials"][0]["level"] is None


def test_ocr_provider_calls_tesseract_and_returns_traceable_result(monkeypatch):
    from app.services import ocr_pipeline, ocr_engines
    from PIL import ImageDraw
    image = Image.new("RGB", (100, 100), "white")
    ImageDraw.Draw(image).text((5, 10), "Test 3 92", fill="black")
    monkeypatch.setattr(ocr_pipeline, "load_document_pages", lambda _path: iter([image.copy()]))
    monkeypatch.setattr(ocr_engines, "recognize", lambda *_args: [
        {"text": "程式設計", "bbox": [20, 30, 100, 45], "confidence": .9},
        {"text": "3", "bbox": [120, 30, 140, 45], "confidence": .9},
        {"text": "92", "bbox": [170, 30, 200, 45], "confidence": .9},
    ])

    result = analyze_document("transcript", "anonymous-transcript.png", "ocr")

    assert result["courses"][0]["course_name"] == "程式設計"
    assert result["source"]["engine"] == "tesseract"
    assert result["source"]["file_name"] == "anonymous-transcript.png"


def test_score_bands_mark_failing_scores():
    assert score_band(100) == "95–100"
    assert score_band(94) == "85–94"
    assert score_band(84) == "75–84"
    assert score_band(74) == "60–74"
    assert score_band(59) == "不及格"
