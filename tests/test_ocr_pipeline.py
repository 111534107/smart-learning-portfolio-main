"""Geometry regression tests: no private transcript is checked into the repo."""
import pytest
from PIL import Image, ImageDraw

from app.services import ocr_pipeline as pipeline


def token(text, x, y=30, confidence=.93, width=5):
    return {"text": text, "bbox": [x, y, x + width, y + 5], "confidence": confidence}


def test_both_semesters_are_separate_and_zero_score_is_not_credit():
    words = [token("必|資料庫 SQL", 10, width=40), token("0", 68),
             token("5", 77), token("3", 85), token("88", 94)]
    rows = pipeline.parse_panel_words(words, (100, 100), 2, body=(20, 70))
    assert [(r["credits"], r["score"], r["semester"]) for r in rows] == [
        (0, 5, "第一學期"), (3, 88, "第二學期")]
    assert rows[0]["course_name"] == "資料庫 SQL"


def test_missing_name_and_zero_credit_are_kept_without_guessing():
    rows = pipeline.parse_panel_words([token("0", 68)], (100, 100), 1, body=(20, 70))
    assert len(rows) == 1
    assert rows[0]["credits"] == 0
    assert rows[0]["score"] is None
    assert rows[0]["course_name"] == "課名待確認"
    assert rows[0]["field_confidence"]["course_name"] is None
    assert rows[0]["needs_confirmation"]


def test_identical_unknown_courses_at_different_rows_are_not_deduplicated():
    # Deliberately in column order: engine token order must not define row order.
    words = [token("2", 68, 30), token("2", 68, 42),
             token("84", 77, 30), token("84", 77, 42)]
    rows = pipeline.parse_panel_words(words, (100, 100), 1, body=(20, 70))
    assert len(rows) == 2
    assert rows[0]["source_line"] != rows[1]["source_line"]


def test_missing_numeric_cell_does_not_shift_other_rows_and_keeps_five_credits():
    words = [token("統計學", 10, 30), token("3", 68, 30), token("15", 77, 30),
             token("專題", 10, 42), token("5", 68, 42),
             token("程式", 10, 54), token("2", 85, 54), token("38", 94, 54)]
    rows = pipeline.parse_panel_words(words, (100, 100), 1, body=(20, 70))
    assert [(r["credits"], r["score"]) for r in rows] == [(3, 15), (5, None), (2, 38)]


def test_tall_chinese_glyphs_align_with_digits_without_merging_next_row():
    words = [token('音樂',10,30),token('2',68,29),token('88',77,29),
             token('英文',10,50),token('2',68,49),token('80',77,49)]
    for word in words:
        word['bbox'][3] = word['bbox'][1] + (16 if word['bbox'][0] == 10 else 8)
    rows = pipeline.parse_panel_words(words,(100,100),1,body=(20,70))
    assert [(r['course_name'],r['score']) for r in rows] == [('音樂',88),('英文',80)]


def test_low_confidence_and_conflicting_tokens_are_flagged_not_max_selected():
    words = [token("國文", 10), token("2", 68), token("75", 77, confidence=.3),
             token("15", 77)]
    row = pipeline.parse_panel_words(words, (100, 100), 1, body=(20, 70))[0]
    assert row["score"] is None
    assert row["needs_confirmation"]
    assert row["field_confidence"]["score"] is None


def test_name_only_row_is_kept_for_review_with_unknown_semester():
    row = pipeline.parse_panel_words([token("體育", 10)], (100, 100), 1, body=(20, 70))[0]
    assert row["course_name"] == "體育"
    assert row["semester"] is None


@pytest.mark.parametrize(("marker", "season", "name"), [
    ("[暑] JAVA程式語言", "summer", "JAVA程式語言"),
    ("[寒] 資料庫管理", "winter", "資料庫管理"),
])
def test_panel_parser_extracts_makeup_season_without_putting_marker_in_course_name(marker, season, name):
    words = [token(marker, 10), token("3", 68), token("85", 77)]
    row = pipeline.parse_panel_words(words, (100, 100), 1, body=(20, 70))[0]
    assert row["makeup_season"] == season
    assert row["course_name"] == name
    assert row["raw_cells"][0] == [marker]


@pytest.mark.parametrize(("marker", "season"), [("暑", "summer"), ("寒", "winter")])
def test_panel_parser_reads_separate_makeup_marker_column(marker, season):
    # Six-cell grid: independent makeup marker, subject, then four numeric cells.
    words = [token(marker, 5), token("JAVA程式語言", 45, width=45),
             token("3", 118), token("85", 148)]
    row = pipeline.parse_panel_words(
        words, (170, 100), 1, body=(20, 70),
        columns=[0, 10, 110, 125, 140, 155, 170],
    )[0]
    assert row["makeup_season"] == season
    assert row["course_name"] == "JAVA程式語言"
    assert row["raw_cells"][:2] == [[marker], ["JAVA程式語言"]]


def test_grid_detection_tracks_translation_and_excludes_summary():
    image = Image.new("L", (600, 400), 255)
    draw = ImageDraw.Draw(image)
    for offset in (30, 210):
        for x in (0, 10, 112, 128, 145, 160, 178):
            draw.line((offset+x, 60, offset+x, 340), fill=0, width=2)
        for y in (60, 85, 300, 340):
            draw.line((offset, y, offset+178, y), fill=0, width=2)
    panels = pipeline.detect_transcript_panels(image)
    assert len(panels) == 2
    assert abs(panels[0]["bbox"][0] - 30) <= 2
    assert len(panels[0]["columns"]) == 7  # marker、科目與四個成績欄位的邊界
    assert abs(panels[0]["body"][1] - 300) <= 2


def test_pdf_loader_renders_all_pages_and_preserves_page_order(tmp_path):
    pytest.importorskip("pypdfium2")
    path = tmp_path / "two.pdf"
    a, b = Image.new("RGB", (100, 80), "white"), Image.new("RGB", (120, 90), "gray")
    a.save(path, "PDF", save_all=True, append_images=[b])
    pages = list(pipeline.load_document_pages(path))
    assert len(pages) == 2
    assert pages[0].width < pages[1].width


def test_bad_pdf_returns_actionable_error(tmp_path):
    path = tmp_path / "bad.pdf"
    path.write_bytes(b"not a pdf")
    with pytest.raises(RuntimeError, match="PDF"):
        list(pipeline.load_document_pages(path))


def test_blank_numeric_column_with_long_border_does_not_create_fake_courses(monkeypatch):
    from app.services import ocr_engines
    image = Image.new("RGB", (50, 500), "white")
    ImageDraw.Draw(image).line((44, 0, 44, 499), fill="black", width=2)
    def unexpected(*_args):
        pytest.fail("An empty ruled column must not be sent to OCR")
    monkeypatch.setattr(ocr_engines, "recognize", unexpected)
    assert pipeline._recognize_crop(image, [0, 0, 50, 500], "tesseract") == []


def test_paddle_crop_can_use_original_scale_without_losing_coordinates(monkeypatch):
    from app.services import ocr_engines
    image = Image.new("RGB", (80, 500), "white")
    ImageDraw.Draw(image).text((10, 10), "123", fill="black")
    seen = []
    def fake_recognize(crop, engine):
        seen.append((crop.size, engine))
        return [{"text": "123", "bbox": [22, 32, 52, 52], "confidence": .9}]
    monkeypatch.setattr(ocr_engines, "recognize", fake_recognize)
    result = pipeline._recognize_crop(image, [5, 0, 75, 500], "paddleocr", scale=1)
    assert seen == [((94, 524), "paddleocr")]
    assert result[0]["bbox"] == [15, 20, 45, 40]


def test_empty_transcript_panel_skips_header_ocr(monkeypatch):
    image = Image.new("RGB", (200, 200), "white")
    monkeypatch.setattr(pipeline, "load_document_pages", lambda _: iter([image]))
    monkeypatch.setattr(pipeline, "detect_transcript_panels", lambda _: [{
        "bbox": [0, 0, 100, 200], "body": (40, 160),
        "columns": [0, 50, 60, 70, 80, 90],
    }])
    calls = []
    def empty_recognition(_image, box, _engine, **_options):
        calls.append(box)
        return []
    monkeypatch.setattr(pipeline, "_recognize_crop", empty_recognition)
    with pytest.raises(RuntimeError, match="未辨識到"):
        pipeline.analyze("transcript", "empty.jpg", "paddleocr")
    assert len(calls) == 5
    assert all(box[1] == 40 for box in calls)


def test_unknown_layout_keeps_partial_rows_and_does_not_put_numbers_in_names():
    rows = pipeline.parse_unknown_rows([
        token("Math 2 75", 10, 20, width=60),
        token("English 0", 10, 40, width=60),
        token("Biology ?? 62", 10, 60, width=60),
        token("History 2 75 3 88", 10, 80, width=75),
    ], page=2, size=(100,100))
    assert [r['course_name'] for r in rows] == ['Math', 'English', 'Biology', 'History']
    assert rows[1]['credits'] is None and rows[1]['score'] is None
    assert rows[1]['raw_cells'] == ['0']  # Keep the zero, but its column is unknown.
    assert rows[2]['credits'] is None and rows[2]['score'] == 62
    assert rows[3]['credits'] is None and rows[3]['score'] is None
    assert all(r['grade_level'] is None and r['needs_confirmation'] for r in rows)


def test_unknown_layout_does_not_turn_lone_low_score_into_credits_or_tail_into_name():
    rows = pipeline.parse_unknown_rows([token('Math 5',10,20),token('Math 2 7S 3 88',10,40)], page=1,size=(100,100))
    assert [(r['credits'],r['score']) for r in rows] == [(None,None),(None,None)]
    assert [r['course_name'] for r in rows] == ['Math','Math']
    assert rows[1]['raw_cells'] == ['2','7S','3','88']


def test_panel_position_is_not_a_grade_without_header_evidence():
    row = pipeline.parse_panel_words([token('程式',10),token('0',68)], (100,100), 1, body=(20,70))[0]
    assert row['grade_level'] is None
    assert pipeline.grade_from_header([token('第３學年',10)]) == ('3年級', .93)
    assert pipeline.grade_from_header([token('113年8月',10)]) == (None, None)


def test_unparsed_page_is_explicit_in_multpage_result(monkeypatch):
    monkeypatch.setattr(pipeline, 'load_document_pages', lambda _: iter([Image.new('RGB',(100,100)) for _ in range(2)]))
    monkeypatch.setattr(pipeline, 'detect_transcript_panels', lambda _: [])
    page_words = iter([[token('Math 2 75',10)], [token('unreadable',10)]])
    monkeypatch.setattr(pipeline, '_recognize_crop', lambda *_: next(page_words))
    result = pipeline.analyze('transcript','sample.pdf','tesseract')
    assert result['unparsed_pages'] == [2]
    assert len(result['ocr_evidence']) == 2
    assert any('2' in warning for warning in result['warnings'])
