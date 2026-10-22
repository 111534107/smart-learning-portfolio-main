"""Technician certificate OCR uses synthetic tokens, never a personal image fixture."""

from PIL import Image
import pytest

from app.services import credential_analysis, ocr_pipeline
from app.services.credential_analysis import analyze_technician_regions, recognize_credential_region


def word(text, box, confidence=.96):
    return {"text": text, "bbox": box, "confidence": confidence}


def test_technician_regions_extract_fields_and_separate_dates():
    regions = {
        "title": [word("中華民國技術士證", [10, 10, 200, 40])],
        "occupation": [word("電腦軟體應用", [30, 200, 180, 235])],
        "level": [word("乙級", [220, 250, 270, 285])],
        "certificate_number": [word("118-0186204", [30, 130, 160, 155])],
        "effective_date": [word("生效日期 民國115年08月21日", [20, 320, 210, 350])],
        "issue_date": [word("製發日期 民國115年08月21日", [220, 320, 430, 350])],
        "issuer": [word("勞動部", [400, 360, 460, 380])],
    }
    result = analyze_technician_regions(regions, page=1)
    assert result["document_kind"] == "taiwan_technician_certificate"
    assert result["fields"]["occupation"]["value"] == "電腦軟體應用"
    assert result["fields"]["level"]["value"] == "乙級"
    assert result["fields"]["certificate_number"]["value"] == "118-0186204"
    assert result["fields"]["issue_date"]["value"] == "2026-08-21"
    assert result["fields"]["effective_date"]["value"] == "2026-08-21"
    assert result["fields"]["issuer"]["value"] == "勞動部"
    assert result["fields"]["occupation"]["bbox"] == [30, 200, 180, 235]
    assert result["fields"]["occupation"]["confidence"] == .96
    assert result["needs_review"] is False


def test_occupation_strips_trailing_name_label_even_when_ocr_attaches_it():
    result = analyze_technician_regions({
        "title": [word("中華民國技術士證", [0, 0, 100, 20])],
        "occupation": [word("電腦軟體應用稱", [90, 190, 240, 242], .31)],
    }, page=1)
    assert result["fields"]["occupation"]["value"] == "電腦軟體應用"


def test_existing_draft_removes_trailing_occupation_label_for_review():
    draft = {
        "credentials": [{"credential_name": "電腦軟體應用稱", "level": "丙級"}],
        "credential_analysis": {"fields": {
            "occupation": {"value": "電腦軟體應用稱", "raw_text": "電腦軟體應用稱"},
        }},
    }
    review = credential_analysis.prepare_credential_review_result(draft)
    assert review["credential_analysis"]["fields"]["occupation"]["value"] == "電腦軟體應用"
    assert review["credentials"][0]["credential_name"] == "電腦軟體應用"
    assert draft["credentials"][0]["credential_name"] == "電腦軟體應用稱"


def test_missing_and_invalid_fields_are_not_guessed():
    regions = {
        "title": [word("中華民國技術士證", [0, 0, 50, 10])],
        "occupation": [],
        "level": [word("乙級", [0, 0, 10, 10], confidence=.5)],
        "issue_date": [word("製發日期 民國115年13月40日", [0, 0, 80, 10])],
    }
    result = analyze_technician_regions(regions, page=2)
    assert result["needs_review"] is True
    assert result["fields"]["occupation"]["value"] is None
    assert result["fields"]["occupation"]["reason"]
    assert result["fields"]["level"]["reason"]
    assert result["fields"]["issue_date"]["value"] is None
    assert result["fields"]["issue_date"]["reason"]
    assert result["fields"]["issue_date"]["raw_text"] == "製發日期 民國115年13月40日"
    assert result["fields"]["occupation"]["page"] == 2


@pytest.mark.parametrize("raw_date", [
    "製發日期 民國115年08月211日", "製發日期 民國115年08月21 1日",
])
def test_roc_date_with_extra_digits_is_invalid(raw_date):
    regions = {
        "title": [word("中華民國技術士證", [0, 0, 60, 20])],
        "issue_date": [word(raw_date, [0, 40, 200, 65])],
    }
    result = analyze_technician_regions(regions, page=1)
    assert result["fields"]["issue_date"]["value"] is None
    assert result["fields"]["issue_date"]["reason"]


def test_low_confidence_title_requires_review_even_with_complete_fields():
    regions = {
        "title": [word("中華民國技術士證", [0, 0, 100, 20], confidence=.21)],
        "occupation": [word("電腦軟體應用", [0, 40, 100, 60])],
        "level": [word("乙級", [120, 40, 160, 60])],
        "certificate_number": [word("118-0186204", [0, 80, 100, 100])],
        "effective_date": [word("民國115年08月21日", [0, 120, 150, 140])],
        "issue_date": [word("民國115年08月21日", [160, 120, 310, 140])],
        "issuer": [word("勞動部", [300, 160, 360, 180])],
    }
    result = analyze_technician_regions(regions, page=1)
    assert result["needs_review"] is True
    assert result["document_kind"] == "possible_taiwan_technician_certificate"
    assert "信心" in result["classification_reason"]


def test_credential_pipeline_keeps_review_draft_when_occupation_is_missing(monkeypatch):
    image = Image.new("RGB", (600, 400), "white")
    monkeypatch.setattr(ocr_pipeline, "load_document_pages", lambda _path: iter([image]))
    monkeypatch.setattr(ocr_pipeline, "_recognize_crop", lambda _image, box, _engine, **_kwargs:
                        [word("中華民國技術士證", [10, 10, 100, 30])] if box[1] < 100 else [])
    monkeypatch.setattr(credential_analysis, "recognize_credential_region", lambda _image, box, _engine:
                        [word("中華民國技術士證", [10, 10, 100, 30])] if box[1] < 100 else [])
    result = ocr_pipeline.analyze("credential", "anonymous.png", "tesseract")
    assert result["credential_analysis"]["document_kind"] == "taiwan_technician_certificate"
    assert result["credential_analysis"]["needs_review"] is True
    assert result["credentials"] == []
    assert result["processing_steps"][-1]["step"] == "credential_fields_parsed"
    assert result["source"]["page_count"] == 1


def test_unreadable_credential_image_is_manual_review_draft(monkeypatch):
    image = Image.new("RGB", (600, 400), "white")
    monkeypatch.setattr(ocr_pipeline, "load_document_pages", lambda _path: iter([image]))
    monkeypatch.setattr(ocr_pipeline, "_recognize_crop", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(credential_analysis, "recognize_credential_region", lambda *_args, **_kwargs: [])
    result = ocr_pipeline.analyze("credential", "anonymous.png", "tesseract")
    assert result["credential_analysis"]["document_kind"] == "unrecognized_credential"
    assert result["credential_analysis"]["needs_review"] is True
    assert result["credentials"] == []
    assert result["unparsed_pages"] == [1]
    assert any("人工" in warning for warning in result["warnings"])


def test_credential_region_uses_raw_crop_and_maps_evidence_to_source(monkeypatch):
    from app.services import ocr_engines

    seen = []
    def recognize(image, engine):
        seen.append((image.size, engine))
        return [word("電腦軟體應用", [5, 7, 105, 37])]
    monkeypatch.setattr(ocr_engines, "recognize", recognize)
    image = Image.new("RGB", (600, 400), "white")
    result = recognize_credential_region(image, [100, 120, 300, 220], "tesseract")
    assert seen == [((200, 100), "tesseract")]
    assert result[0]["bbox"] == [105, 127, 205, 157]


def test_empty_credential_crop_is_reported_as_unreadable(monkeypatch):
    from app.services import ocr_engines

    monkeypatch.setattr(ocr_engines, "recognize", lambda *_args: (_ for _ in ()).throw(AssertionError("OCR called")))
    assert recognize_credential_region(Image.new("RGB", (1, 1), "white"),
                                       [0, 0, 0, 0], "tesseract") == []


def test_unreadable_raw_credential_crop_is_reread_at_double_size(monkeypatch):
    from app.services import ocr_engines

    sizes = []
    def recognize(image, _engine):
        sizes.append(image.size)
        return [] if image.size == (200, 100) else [word("乙級", [10, 14, 110, 74])]
    monkeypatch.setattr(ocr_engines, "recognize", recognize)
    image = Image.new("RGB", (600, 400), "white")
    result = recognize_credential_region(image, [100, 120, 300, 220], "tesseract")
    assert sizes == [(200, 100), (400, 200)]
    assert result[0]["bbox"] == [105, 127, 155, 157]


def test_low_confidence_paddle_credential_region_is_not_repeated_at_double_size(monkeypatch):
    from app.services import ocr_engines

    sizes = []
    def recognize(image, _engine):
        sizes.append(image.size)
        return [word("勞助部發", [5, 7, 105, 37], confidence=.42)]
    monkeypatch.setattr(ocr_engines, "recognize", recognize)
    image = Image.new("RGB", (600, 400), "white")

    result = recognize_credential_region(image, [100, 120, 300, 220], "paddleocr")

    assert sizes == [(200, 100)]
    assert result[0]["text"] == "勞助部發"
    assert result[0]["confidence"] == .42


def test_recognized_technician_title_skips_full_page_ocr_pass(monkeypatch):
    image = Image.new("RGB", (600, 400), "white")
    monkeypatch.setattr(ocr_pipeline, "load_document_pages", lambda _path: iter([image]))
    full_page_calls = []
    monkeypatch.setattr(ocr_pipeline, "_recognize_crop", lambda _image, box, _engine, **_kwargs:
                        full_page_calls.append(box) or [])

    def region(_image, box, _engine):
        if box[1] < 100:
            return [word("中華民國技術士證", [100, 20, 300, 50])]
        return []
    monkeypatch.setattr(credential_analysis, "recognize_credential_region", region)
    monkeypatch.setattr(credential_analysis, "recognize_number_fallback", lambda *_args: [])
    monkeypatch.setattr(credential_analysis, "recognize_level_fallback", lambda *_args: [])

    result = ocr_pipeline.analyze("credential", "anonymous.png", "paddleocr")

    assert full_page_calls == []
    assert result["credential_analysis"]["document_kind"] == "taiwan_technician_certificate"


def test_missing_title_with_three_independent_field_signals_is_only_possible():
    regions = {
        "title": [],
        "occupation": [word("電腦軟體應用", [30, 200, 180, 235])],
        "certificate_number": [word("118-0186204", [30, 130, 160, 155])],
        "issue_date": [word("民國115年08月21日", [220, 320, 430, 350])],
    }
    result = analyze_technician_regions(regions, page=1)
    assert result["document_kind"] == "possible_taiwan_technician_certificate"
    assert result["needs_review"] is True
    assert "標題" in result["classification_reason"]
    assert result["fields"]["occupation"]["value"] == "電腦軟體應用"
    assert analyze_technician_regions({"occupation": regions["occupation"],
                                       "issue_date": regions["issue_date"]}, page=1) is None


def test_fragmented_chinese_occupation_is_joined_without_guessing_characters():
    regions = {
        "title": [word("中華民國技術士證", [0, 0, 60, 20])],
        "occupation": [word("電", [0, 40, 10, 60]), word("腦", [11, 40, 21, 60]),
                       word("軟體", [22, 40, 42, 60]), word("應", [43, 40, 53, 60]),
                       word("用", [54, 40, 64, 60])],
    }
    result = analyze_technician_regions(regions, page=1)
    assert result["fields"]["occupation"]["value"] == "電腦軟體應用"


def test_occupation_keeps_hyphenated_specialty_from_ocr_text():
    regions = {
        "title": [word("中華民國技術士證", [0, 0, 100, 20])],
        "occupation": [word("49-0685006 會計事務-資訊", [20, 40, 300, 70])],
    }

    result = analyze_technician_regions(regions, page=1)

    assert result["fields"]["occupation"]["value"] == "會計事務－資訊"


def test_pipeline_reads_card_regions_even_when_title_ocr_misses(monkeypatch):
    image = Image.new("RGB", (600, 400), "white")
    monkeypatch.setattr(ocr_pipeline, "load_document_pages", lambda _path: iter([image]))
    monkeypatch.setattr(ocr_pipeline, "_recognize_crop", lambda *_args, **_kwargs: [])
    def region(_image, box, _engine):
        top = box[1]
        left = box[0]
        if 160 < top < 190:
            return [word("118-0186204", [100, 180, 200, 200])]
        if 210 < top < 250:
            return [word("電腦軟體應用", [100, 240, 200, 260])]
        if top > 300 and left > 350:
            return [word("民國115年08月21日", [400, 330, 550, 350])]
        return []
    monkeypatch.setattr(credential_analysis, "recognize_credential_region", region)
    result = ocr_pipeline.analyze("credential", "anonymous.png", "tesseract")
    assert result["credential_analysis"]["document_kind"] == "possible_taiwan_technician_certificate"
    assert result["credentials"][0]["credential_name"] == "電腦軟體應用"


def test_two_page_credential_keeps_page_specific_analysis(monkeypatch):
    images = [Image.new("RGB", (600, 400), color) for color in ("white", "black")]
    monkeypatch.setattr(ocr_pipeline, "load_document_pages", lambda _path: iter(images))
    monkeypatch.setattr(ocr_pipeline, "_recognize_crop", lambda *_args, **_kwargs: [])
    def region(image, box, _engine):
        second = image.getpixel((0, 0)) == (0, 0, 0)
        if box[1] < 100:
            return [word("中華民國技術士證", [10, 10, 100, 30])]
        if 210 < box[1] < 250:
            return [word("電腦硬體裝修" if second else "電腦軟體應用", [100, 240, 200, 260])]
        return []
    monkeypatch.setattr(credential_analysis, "recognize_credential_region", region)
    result = ocr_pipeline.analyze("credential", "anonymous.pdf", "tesseract")
    assert [item["credential_name"] for item in result["credentials"]] == ["電腦軟體應用", "電腦硬體裝修"]
    assert [(item["source_page"], item["fields"]["occupation"]["value"])
            for item in result["credential_analyses"]] == [(1, "電腦軟體應用"), (2, "電腦硬體裝修")]
    assert result["credential_analysis"]["source_page"] == 1


def test_level_and_issuer_crops_include_bottom_edge_print(monkeypatch):
    """A reduced card still includes the complete printed values at its bottom."""
    image = Image.new("RGB", (1005, 646), "white")
    monkeypatch.setattr(ocr_pipeline, "load_document_pages", lambda _path: iter([image]))
    monkeypatch.setattr(ocr_pipeline, "_recognize_crop", lambda *_args, **_kwargs: [])

    def region(_image, box, _engine):
        left, top, right, bottom = box
        if top < 100:
            return [word("中華民國技術士證", [220, 50, 640, 150])]
        if left <= 760 and top <= 485 and right >= 840 and bottom >= 523:
            return [word("乙級", [760, 485, 840, 523])]
        if left <= 820 and top <= 616 and right >= 950 and bottom >= 644:
            return [word("勞動部", [820, 616, 950, 644])]
        return []

    monkeypatch.setattr(credential_analysis, "recognize_credential_region", region)
    result = ocr_pipeline.analyze("credential", "anonymous.png", "tesseract")
    fields = result["credential_analysis"]["fields"]
    assert fields["level"]["value"] == "乙級"
    assert fields["issuer"]["value"] == "勞動部"


def test_level_fallback_accepts_only_ocr_read_grade_and_keeps_raw_evidence(monkeypatch):
    from app.services import ocr_engines

    seen = []
    def read_line(crop):
        seen.append(crop.size)
        if len(seen) == 1:
            return [word("乙", [0, 13, 81, 55], .83),
                    word("级", [58, 9, 83, 58], .88)]
        return [word("妥", [0, 13, 81, 55], .91),
                word("级", [58, 9, 83, 58], .92)]
    monkeypatch.setattr(ocr_engines, "recognize_tesseract_level", read_line, raising=False)
    words = credential_analysis.recognize_level_fallback(
        Image.new("RGB", (1005, 646), "white"), "tesseract")
    assert len(seen) == 3
    assert [item["text"] for item in words] == ["乙", "级"]
    assert words[0]["bbox"][0] >= 750
    analysis = analyze_technician_regions({
        "title": [word("中華民國技術士證", [0, 0, 100, 20])],
        "level": words,
    }, page=1)
    assert analysis["fields"]["level"]["value"] == "乙級"
    assert analysis["fields"]["level"]["raw_text"] == "乙 级"
    assert analysis["fields"]["level"]["confidence"] == .83


def test_inset_card_level_fallback_reads_paddleocr_draft_layout(monkeypatch):
    from app.services import ocr_engines

    seen = []
    def read_level(crop):
        seen.append(crop.size)
        if len(seen) == 3:
            return [word("丙", [5, 4, 25, 27], .27),
                    word("级", [26, 3, 48, 28], .83)]
        return []
    monkeypatch.setattr(ocr_engines, "recognize_tesseract_level", read_level)
    words = credential_analysis.recognize_level_fallback(
        Image.new("RGB", (500, 331), "white"), "paddleocr")
    assert len(seen) == 3
    assert [item["text"] for item in words] == ["丙", "级"]
    assert 210 <= words[0]["bbox"][1] <= 220
    analysis = analyze_technician_regions({
        "title": [word("中華民國技術士證", [0, 0, 100, 20])],
        "level": words,
    }, page=1)
    assert analysis["fields"]["level"]["value"] == "丙級"
    assert analysis["fields"]["level"]["reason"]


def test_level_fallback_rejects_similar_but_unreadable_characters(monkeypatch):
    from app.services import ocr_engines

    monkeypatch.setattr(ocr_engines, "recognize_tesseract_level",
                        lambda _crop: [word("妥", [0, 0, 20, 20], .9),
                                       word("级", [20, 0, 40, 20], .9)], raising=False)
    assert credential_analysis.recognize_level_fallback(
        Image.new("RGB", (1005, 646), "white"), "tesseract") == []


def test_level_fallback_confidence_excludes_unrelated_crop_noise(monkeypatch):
    from app.services import ocr_engines

    monkeypatch.setattr(ocr_engines, "recognize_tesseract_level",
                        lambda _crop: [word("-", [0, 0, 10, 10], 0.0),
                                       word("乙", [10, 0, 30, 20], .29),
                                       word("级", [30, 0, 50, 20], .92)])
    words = credential_analysis.recognize_level_fallback(
        Image.new("RGB", (1005, 646), "white"), "tesseract")
    assert [item["text"] for item in words] == ["乙", "级"]
    analysis = analyze_technician_regions({
        "title": [word("中華民國技術士證", [0, 0, 100, 20])], "level": words,
    }, page=1)
    assert analysis["fields"]["level"]["confidence"] == .29
    assert analysis["fields"]["level"]["reason"]


def test_pipeline_uses_level_fallback_only_after_primary_ocr_misses(monkeypatch):
    image = Image.new("RGB", (1005, 646), "white")
    monkeypatch.setattr(ocr_pipeline, "load_document_pages", lambda _path: iter([image]))
    monkeypatch.setattr(ocr_pipeline, "_recognize_crop", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(credential_analysis, "recognize_credential_region",
                        lambda _image, box, _engine:
                        [word("中華民國技術士證", [220, 50, 640, 150])] if box[1] < 100 else [])
    monkeypatch.setattr(credential_analysis, "recognize_level_fallback",
                        lambda _image, _engine: [word("乙", [755, 485, 810, 520], .83),
                                                 word("级", [810, 485, 840, 520], .88)])
    result = ocr_pipeline.analyze("credential", "anonymous.png", "tesseract")
    assert result["credential_analysis"]["fields"]["level"]["value"] == "乙級"
    assert result["credential_analysis"]["fields"]["level"]["raw_text"] == "乙 级"


def test_number_fallback_reads_complete_identifier_from_small_card(monkeypatch):
    from app.services import ocr_engines

    seen = []
    def read_number(crop):
        seen.append(crop.size)
        return [word("120-0298233", [5, 13, 110, 35], .83)] if len(seen) == 1 else []
    monkeypatch.setattr(ocr_engines, "recognize_tesseract_number", read_number, raising=False)
    words = credential_analysis.recognize_number_fallback(
        Image.new("RGB", (500, 348), "white"))
    assert [item["text"] for item in words] == ["120-0298233"]
    assert words[0]["bbox"][0] >= 95
    assert len(seen) == 2


def test_user_confirmed_issuer_ocr_pattern_is_corrected_but_raw_evidence_is_kept():
    regions = {
        "title": [word("中華民國技術士證", [0, 0, 100, 20])],
        "issuer": [word("劳助部發", [200, 200, 280, 220], .75)],
    }
    result = analyze_technician_regions(regions, page=1)
    assert result["fields"]["issuer"]["value"] == "勞動部"
    assert result["fields"]["issuer"]["raw_text"] == "劳助部發"
    assert "人工核對" in result["fields"]["issuer"]["reason"]


def test_simplified_ocr_script_is_normalized_only_for_exact_issuer():
    regions = {
        "title": [word("中華民國技術士證", [0, 0, 100, 20])],
        "issuer": [word("劳动部", [200, 200, 280, 220], .95)],
    }
    result = analyze_technician_regions(regions, page=1)
    assert result["fields"]["issuer"]["value"] == "勞動部"
    assert result["fields"]["issuer"]["raw_text"] == "劳动部"


def test_pipeline_retries_partial_number_without_completing_it_by_guess(monkeypatch):
    image = Image.new("RGB", (500, 348), "white")
    monkeypatch.setattr(ocr_pipeline, "load_document_pages", lambda _path: iter([image]))
    monkeypatch.setattr(ocr_pipeline, "_recognize_crop", lambda *_args, **_kwargs: [])
    def region(_image, box, _engine):
        if box[1] < 100:
            return [word("中華民國技術士證", [100, 20, 300, 80])]
        if 140 < box[1] < 170:
            return [word("-0298233", [128, 187, 207, 201])]
        return []
    monkeypatch.setattr(credential_analysis, "recognize_credential_region", region)
    monkeypatch.setattr(credential_analysis, "recognize_number_fallback",
                        lambda _image: [word("120-0298233", [100, 187, 207, 201], .83)],
                        raising=False)
    monkeypatch.setattr(credential_analysis, "recognize_level_fallback", lambda *_args: [])
    result = ocr_pipeline.analyze("credential", "anonymous.jpg", "paddleocr")
    assert result["credential_analysis"]["fields"]["certificate_number"]["value"] == "120-0298233"


def test_existing_draft_shows_traditional_issuer_without_changing_saved_evidence():
    draft = {
        "credentials": [{"credential_name": "電腦硬體裝修", "level": "丙级",
                         "issuing_organization": "劳助部"}],
        "credential_analysis": {"fields": {
            "issuer": {"value": "劳助部", "raw_text": "劳助部發", "reason": "OCR 信心偏低，請核對"},
            "level": {"value": "丙级", "raw_text": "丙级", "reason": None},
        }},
    }
    review = credential_analysis.prepare_credential_review_result(draft)
    assert draft["credentials"][0]["issuing_organization"] == "劳助部"
    assert review["credential_analysis"]["fields"]["issuer"]["value"] == "勞動部"
    assert review["credentials"][0]["issuing_organization"] == "勞動部"
    assert "人工核對" in review["credential_analysis"]["fields"]["issuer"]["reason"]
    assert review["credentials"][0]["level"] == "丙級"
    assert review["credential_analysis"]["fields"]["issuer"]["raw_text"] == "劳助部發"


def test_confirmed_human_issuer_is_preserved_while_old_ocr_error_is_flagged():
    draft = {
        "credentials": [{"credential_name": "電腦硬體裝修", "level": "丙級",
                         "issuing_organization": "勞動部"}],
        "credential_analysis": {"fields": {
            "issuer": {"value": "劳助部", "raw_text": "劳助部發", "reason": "OCR 信心偏低"},
        }},
    }
    review = credential_analysis.prepare_credential_review_result(
        draft, preserve_confirmed_credentials=True)
    assert review["credential_analysis"]["fields"]["issuer"]["value"] == "勞動部"
    assert review["credentials"][0]["issuing_organization"] == "勞動部"

