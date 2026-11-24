"""OCR 課程名稱字形校正：只把字形相近的錯字改成課程清單上唯一的課名；學生仍要確認。"""
import unicodedata

from app.services.course_review_presentation import traditionalize_course_name

# OCR 常把左邊的字讀成右邊的字：(OCR 讀到的字, 課程清單上的字)。
# 來源：docs/03_開發紀錄/OCR驗收紀錄_2026-10-20.md 的成績單課程名稱錯字。
LOOK_ALIKE_PAIRS = {
    ("合", "會"), ("育", "資"), ("脊", "資"), ("貢", "資"), ("商", "育"),
    ("獲", "護"), ("域", "識"), ("滑", "濟"), ("奧", "與"), ("事", "寧"),
}
# 本科（五專資訊管理科）課程名稱清單。來源：使用者提供的 111 學年度入學 1～3 年級成績單，
# 2026-10-21 逐筆人工對照原圖抄錄，只取課名，不含成績與個人資料。
# 只涵蓋這份成績單修過的課；其他選修課或其他入學年度的課名要再補。清單是空的時候不做任何校正。
COURSE_CATALOG = (
    # 第 1 學年
    "康寧全人教育", "一年全民國防教育", "一年康寧勞作教育", "音樂", "一年體育", "一年國文",
    "一年英文", "資訊科技", "一年數學", "管理學", "中英文輸入", "資訊科技進階", "電腦繪圖與動畫",
    "商品攝影與後製", "會計概論", "數位化資料處理", "程式設計", "硬體裝修", "創意機器人",
    # 第 2 學年
    "服務學習與實踐", "二年康寧勞作教育", "物理", "化學", "二年體育", "健康與護理", "二年國文",
    "二年英文", "歷史", "多媒體設計", "進階分類通識數學類", "會計學", "微積分", "商業套裝軟體",
    "行動網頁程式開發", "微電影製作", "網頁設計", "統計學", "行銷管理", "臨床檢查報告判讀與應用",
    # 第 3 學年
    "三年康寧勞作教育", "生涯規劃", "藝術生活", "公民與社會", "台灣手語", "體育—健康體適能",
    "創意發明實務", "多媒體製作與應用", "JAVA程式語言", "辦公室自動化", "經濟學", "作業系統",
    "資料結構", "系統分析與設計", "計算機網路", "資料庫管理實務(SQL)", "資料庫伺服器管理與實作",
    "商務網站經營", "行銷企劃書撰寫",
)
MAX_LOOK_ALIKE_CHARS = 2


def _normalize(text):
    # OCR 常把個別字讀成簡體（数、计、语）或讀出全形括號；比對前先轉繁體並統一全半形
    return unicodedata.normalize("NFKC", traditionalize_course_name(text))


def correct_course_name(name, catalog=COURSE_CATALOG):
    """Return (name, original). original is set only when exactly one catalog name matches."""
    if not name or name in catalog:
        return name, None
    read = _normalize(name)
    matches = set()
    for official in catalog:
        target = _normalize(official)
        if len(target) != len(read):
            continue
        diffs = [(a, b) for a, b in zip(read, target) if a != b]
        if len(diffs) <= MAX_LOOK_ALIKE_CHARS and all(pair in LOOK_ALIKE_PAIRS for pair in diffs):
            matches.add(official)
    if len(matches) == 1:
        return matches.pop(), name
    return name, None


def apply_name_correction(course, catalog=COURSE_CATALOG):
    corrected, original = correct_course_name(course.get("course_name"), catalog)
    if original is None:
        return course
    course["course_name"] = corrected
    course["course_name_corrected_from"] = original
    course["needs_confirmation"] = True
    course.setdefault("review_reasons", []).append(
        f"課程名稱已依課程清單校正為『{corrected}』（OCR 原文『{original}』），請對照原圖。")
    return course
