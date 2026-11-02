"""缺件比對：用目標校系的備審加權，對照學生已確認的六類學習資料。

規則（寫在這裡，方便報告時說明）：
- 每個簡章項目對應到幾個資料類別。六類學習資料以外的類別（自傳與讀書計畫、專題作品）
  尚無自動確認狀態，先視為待準備，不能從分母排除。
- 項目完成比例 = 已確認且有資料的類別數 ÷ 對應的全部類別數。
- 整體準備度 = Σ（項目加權 × 完成比例）÷ Σ（全部項目加權）；
  若全部都是無法由系統確認的文件類，則不顯示數字。
"""

from app.services.journey_service import CATEGORY_KEYS, CATEGORY_LABELS, build_journey

DOCUMENT_LABELS = {"autobiography": "自傳與讀書計畫", "project": "專題作品"}
ALL_LABELS = {**CATEGORY_LABELS, **DOCUMENT_LABELS}

# 備審資料目錄（依「116 二技技優甄審」簡報的建議目錄）
CHAPTERS = [
    ("01", "封面與目錄", []),
    ("02", "報名資格證明", []),
    ("03", "歷年成績單與排名", ["grades"]),
    ("04", "自傳", ["autobiography"]),
    ("05", "讀書計畫", ["autobiography"]),
    ("06", "證照證明", ["credential"]),
    ("07", "競賽成果", ["competition"]),
    ("08", "專題／作品集", ["project"]),
    ("09", "社團與幹部經歷", ["activity", "leadership"]),
    ("10", "其他有利審查資料", ["service"]),
]


def analyze_gap(student, program, journey=None):
    journey = journey or build_journey(student)
    totals = journey.get("confirmed_totals", journey["totals"])
    items = []
    weighted, total_weight = 0.0, 0
    has_record_item = False
    for item in program.items:
        total_weight += item.weight_percent
        keys = item.category_keys
        record_keys = [key for key in keys if key in CATEGORY_KEYS]
        documents = [key for key in keys if key not in CATEGORY_KEYS]
        have = [key for key in record_keys if totals.get(key, 0) > 0]
        missing = [key for key in record_keys if totals.get(key, 0) == 0]
        if not record_keys:
            status, fraction = "prepare", None
        else:
            has_record_item = True
            fraction = len(have) / (len(record_keys) + len(documents))
            status = "complete" if fraction == 1 else ("partial" if fraction > 0 else "missing")
            weighted += item.weight_percent * fraction
        items.append({
            "id": item.id,
            "name": item.source_item_name,
            "weight": item.weight_percent,
            "status": status,
            "fraction": fraction,
            "percent": None if fraction is None else round(fraction * 100),
            "have": have,
            "missing": missing,
            "documents": documents,
            "counts": {key: totals.get(key, 0) for key in record_keys},
            "mapping_pending": item.mapping_status != "confirmed",
        })
    readiness = round(weighted / total_weight * 100) if total_weight and has_record_item else None
    missing_keys = sorted({key for item in items for key in item["missing"]}, key=CATEGORY_KEYS.index)
    # 最該先補的項目：還沒滿、加權最大的那一個
    open_items = [item for item in items if item["status"] in ("missing", "partial", "prepare")]
    priority = max(open_items, key=lambda item: item["weight"], default=None)
    return {
        "program": program,
        "priority_id": priority["id"] if priority else None,
        "items": items,
        "readiness": readiness,
        "missing_keys": missing_keys,
        "documents": sorted({key for item in items for key in item["documents"]}),
    }


def chapter_order(program):
    """01、02 固定在最前面，其餘章節依對應項目的最高加權由大到小排列。"""
    def weight_of(keys):
        return max((item.weight_percent for item in program.items if set(item.category_keys) & set(keys)), default=0)

    chapters = [{"code": code, "title": title, "keys": keys, "weight": weight_of(keys)} for code, title, keys in CHAPTERS]
    fixed, rest = chapters[:2], chapters[2:]
    rest.sort(key=lambda chapter: -chapter["weight"])  # sort 是穩定排序，同加權維持原本編號順序
    return fixed + rest
