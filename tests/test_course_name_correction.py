"""課程名稱字形校正測試；全部使用合成課名（僅為測試資料），不含真實成績單內容。"""
import pytest

from app.services.course_name_correction import apply_name_correction, correct_course_name

CATALOG = ("會計概論", "資料結構", "體育", "護理導論", "通識數學", "經濟學", "英語與溝通", "康寧服務",
           "數位化資料處理", "會計學", "JAVA程式語言", "資料庫管理實務(SQL)")


@pytest.mark.parametrize("ocr_name, expected", [
    ("数位化育料處理", "數位化資料處理"),   # 簡體字＋字形錯字
    ("合计學", "會計學"),
    ("JAVA程式语言", "JAVA程式語言"),       # 只有簡體字
    ("貢料庫管理實務(SQL）", "資料庫管理實務(SQL)"),  # 全形括號
])
def test_simplified_and_full_width_variants_are_normalized_before_matching(ocr_name, expected):
    assert correct_course_name(ocr_name, CATALOG) == (expected, ocr_name)


@pytest.mark.parametrize("ocr_name, expected", [
    ("合計概論", "會計概論"),
    ("育料結構", "資料結構"),
    ("脊料結構", "資料結構"),
    ("貢料結構", "資料結構"),
    ("體商", "體育"),
    ("獲理導論", "護理導論"),
    ("通域數學", "通識數學"),
    ("經滑學", "經濟學"),
    ("英語奧溝通", "英語與溝通"),
    ("康事服務", "康寧服務"),
])
def test_known_look_alike_errors_are_corrected(ocr_name, expected):
    assert correct_course_name(ocr_name, CATALOG) == (expected, ocr_name)


@pytest.mark.parametrize("name", [
    "會計概論",       # 已經是清單名稱
    "程式設計",       # 清單裡沒有、也沒有相近的課名
    "資料結構實習",   # 比清單名稱多字，不猜
    "英語溝通",       # 少一個字，不是字形錯誤
])
def test_names_without_a_look_alike_match_are_left_alone(name):
    assert correct_course_name(name, CATALOG) == (name, None)


def test_empty_catalog_changes_nothing():
    assert correct_course_name("合計概論", ()) == ("合計概論", None)


def test_apply_correction_marks_course_for_confirmation_and_keeps_original():
    course = {"course_name": "合計概論", "needs_confirmation": False, "review_reasons": []}
    apply_name_correction(course, CATALOG)
    assert course["course_name"] == "會計概論"
    assert course["course_name_corrected_from"] == "合計概論"
    assert course["needs_confirmation"] is True
    assert "課程名稱已依課程清單校正為『會計概論』（OCR 原文『合計概論』），請對照原圖。" in course["review_reasons"]


def test_apply_correction_does_not_touch_unchanged_course():
    course = {"course_name": "程式設計", "needs_confirmation": False, "review_reasons": []}
    apply_name_correction(course, CATALOG)
    assert course == {"course_name": "程式設計", "needs_confirmation": False, "review_reasons": []}


def test_apply_correction_ignores_pending_placeholder():
    course = {"course_name": "課名待確認", "needs_confirmation": True, "review_reasons": []}
    apply_name_correction(course, CATALOG)
    assert course["course_name"] == "課名待確認"
    assert "course_name_corrected_from" not in course
