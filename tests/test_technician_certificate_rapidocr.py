"""技術士證＋RapidOCR：整張辨識後依標籤找欄位，不靠固定比例切區（全部合成資料）。

使用者上傳的證照圖片（邊界、比例與組員參考檔不同）實測發現：
1. 組員用固定比例切欄位，證號區切到出生日期、職類區切到證號，整個錯開。
2. 標題「中華民國技術士證」被讀成「中華民」「術士證」「國技」三塊，照辨識順序接起來找不到「技術士證」。
   兩張圖的「國技」被紅色印章蓋住，只剩「中華民」「術士證」。
"""
from pathlib import Path

import pytest

from app import create_app
from app.services.credential_analysis import analyze_technician_regions, technician_regions_from_page_words
from app.services.document_analysis_service import DEFAULT_OCR_MODEL_DIR, OCR_MODEL_TIERS
from synthetic_certificate import MSJH_FONT, render


def word(text, left, top, right, bottom, confidence=0.98):
    return {"text": text, "bbox": [left, top, right, bottom], "confidence": confidence}


SEPARATE_LABEL_WORDS = [  # 依實測的位置排列，職類標籤與值分開
    word("中華民", 292, 62, 582, 226), word("術士證", 738, 76, 1031, 216),
    word("出生日期", 47, 432, 266, 493), word("民國96年01月01日", 261, 426, 825, 512),
    word("技术士證", 42, 526, 268, 586), word("999-0000001", 281, 554, 638, 624), word("總编號", 41, 584, 266, 648),
    word("電腦硬體裝修", 276, 660, 687, 749), word("職類（項）", 50, 691, 263, 753),
    word("名稱", 47, 768, 241, 829), word("级別", 1041, 763, 1164, 833), word("丙級", 1216, 771, 1357, 853),
    word("生效日期", 47, 905, 262, 963), word("民國113年11月13日", 276, 907, 765, 983),
    word("製發日期", 801, 901, 1017, 963), word("民國113年11月20日", 1038, 918, 1534, 991),
    word("勞動部發", 1338, 1005, 1575, 1054),
]


def test_title_words_out_of_reading_order_are_still_recognized():
    regions = {"title": [word("中華民", 283, 75, 578, 238), word("術士證", 738, 76, 1031, 216),
                         word("國技", 562, 71, 740, 249)]}

    result = analyze_technician_regions(regions, page=1)

    assert result is not None
    assert "技術士證" in result["title_evidence"]["raw_text"].replace(" ", "")


def test_fields_are_found_by_labels_on_the_same_row():
    regions = technician_regions_from_page_words(SEPARATE_LABEL_WORDS)
    values = {key: field["value"] for key, field in analyze_technician_regions(regions, page=1)["fields"].items()}

    assert values["occupation"] == "電腦硬體裝修"
    assert values["level"] == "丙級"
    assert values["certificate_number"] == "999-0000001"
    assert values["effective_date"] == "2024-11-13"   # 不是出生日期 2007-01-01
    assert values["issue_date"] == "2024-11-20"
    assert values["issuer"] and "勞動部" in values["issuer"]


def test_occupation_merged_with_its_label_is_still_read():
    words = [w for w in SEPARATE_LABEL_WORDS if w["text"] not in {"電腦硬體裝修", "職類（項）"}]
    words.append(word("職類(項)會計事務-資訊", 42, 686, 767, 774))

    regions = technician_regions_from_page_words(words)
    result = analyze_technician_regions(regions, page=1)

    assert result["fields"]["occupation"]["value"] == "會計事務－資訊"


def test_title_covered_by_stamp_is_recognized_from_certificate_number_label():
    regions = technician_regions_from_page_words(SEPARATE_LABEL_WORDS)
    result = analyze_technician_regions(regions, page=1)

    assert result["document_kind"] in {"taiwan_technician_certificate", "possible_taiwan_technician_certificate"}
    assert "技術士證" in result["title_evidence"]["raw_text"].replace("术", "術").replace(" ", "")


def require_models():
    if not Path(MSJH_FONT).exists():
        pytest.skip("找不到 msjh.ttc 中文字型，無法產生合成證照")
    if not all((DEFAULT_OCR_MODEL_DIR / name).exists() for name in OCR_MODEL_TIERS["server"].values()):
        pytest.skip("尚未下載離線 OCR 模型；請先執行 scripts/download_ocr_models.py")


def test_rapidocr_reads_synthetic_certificate_with_unusual_margins(tmp_path):
    from app.services.ocr_pipeline import analyze

    require_models()
    image_path = tmp_path / "synthetic_certificate.png"
    expected = render(image_path)
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite://", "TESTING": True, "UPLOAD_FOLDER": str(tmp_path)})

    with app.app_context():
        result = analyze("credential", image_path, "rapidocr")

    assert len(result["credentials"]) == 1
    credential = result["credentials"][0]
    assert credential["credential_name"] == expected["occupation"]
    assert credential["level"] == expected["level"]
    assert credential["issue_date"] == "2024-11-20"
    fields = result["credential_analysis"]["fields"]
    assert fields["certificate_number"]["value"] == expected["certificate_number"]
    assert fields["effective_date"]["value"] == "2024-11-13"


def test_issuer_printed_as_issued_by_ministry_is_normalized():
    # 證照上印的是「勞動部發」（由勞動部核發），發證單位應為「勞動部」，不該標成疑似有誤
    regions = technician_regions_from_page_words(SEPARATE_LABEL_WORDS)
    issuer = analyze_technician_regions(regions, page=1)["fields"]["issuer"]

    assert issuer["value"] == "勞動部"
    assert "疑似有誤" not in (issuer["reason"] or "")


def _replace(words, old, new):
    return [word(new, *w["bbox"], w["confidence"]) if w["text"] == old else w for w in words]


def test_occupation_label_read_in_simplified_chinese_is_still_found():
    # 實測（乙級證照）：標籤被讀成簡體「職类（项）」，職類名稱讀到了卻沒有放進欄位
    words = _replace(SEPARATE_LABEL_WORDS, "職類（項）", "職类（项）")

    result = analyze_technician_regions(technician_regions_from_page_words(words), page=1)

    assert result["fields"]["occupation"]["value"] == "電腦硬體裝修"


def test_issuer_read_in_simplified_or_cut_off_is_still_found():
    # 實測：圖片下緣把「勞動部發」切掉一半，讀成「勞动音」；推定為勞動部，但要請學生核對
    words = _replace(SEPARATE_LABEL_WORDS, "勞動部發", "勞动音")

    issuer = analyze_technician_regions(technician_regions_from_page_words(words), page=1)["fields"]["issuer"]

    assert issuer["value"] == "勞動部"
    assert "請對照原圖" in issuer["reason"]
    assert issuer["raw_text"] == "勞动音"


def test_issuer_from_another_agency_is_not_forced_to_ministry_of_labor():
    words = _replace(SEPARATE_LABEL_WORDS, "勞動部發", "勞工委員會")

    issuer = analyze_technician_regions(technician_regions_from_page_words(words), page=1)["fields"]["issuer"]

    assert issuer["value"] == "勞工委員會"
