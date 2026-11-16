"""B22 目標校系篩選選單（2026-11-16 使用者要求）：招生管道、群類別、插入年級、日間或進修部、有沒有加權資料。

選項一律從目前分頁（二技或插大）的校系資料產生，不寫死；只有一種值的條件不顯示選單。
篩選照地區、學校的做法：伺服器先把不符合的列加上 hidden（沒有 JavaScript 也篩得對），
瀏覽器端再依每一列的 data-* 屬性即時切換，網址參數跟著更新，可以分享、上一頁能回到原篩選。
"""

# (網址參數, 選單標題, 「全部」選項文字)
FIELDS = (
    # 2026-11-16 使用者要求：國立、私立篩選（放第一個，學生最常先分公私立）
    ("ownership", "國立或私立", "國立私立都看"),
    ("channel", "招生管道", "全部管道"),
    ("group", "群類別", "全部群類別"),
    ("grade", "插入年級", "全部年級"),
    ("session", "日間或進修部", "日間與進修都看"),
    ("weights", "加權資料", "有沒有都看"),
)
FIELD_NAMES = tuple(name for name, _, _ in FIELDS)


def session_of(program, channel):
    text = f"{program.admission_category or ''}{program.department_name or ''}{channel}"
    return "進修部" if "進修" in text else "日間部"


def ownership_of(school_name):
    """依校名判斷：國立開頭是「國立」，市立、縣立是「公立」，其他是「私立」（目前資料只有國立與私立）。"""
    name = (school_name or "").strip()
    if name.startswith("國立"):
        return "國立"
    if "市立" in name or "縣立" in name:
        return "公立"
    return "私立"


def program_facets(program, channel, entry_grade):
    """一個校系在各篩選條件上的值（空字串表示這個條件不適用）。"""
    category = program.admission_category or ""
    return {
        "ownership": ownership_of(getattr(program, "school_name", "")),
        "channel": channel,
        # 群類別只在和招生管道名稱不同時才有意義（例如技優甄審的「管理類四」）
        "group": category if category and category != channel else "",
        "grade": entry_grade or "",
        "session": session_of(program, channel),
        "weights": "有加權資料" if program.items else "還沒有加權資料",
    }


def build_options(facets):
    """每個條件的選項與筆數；只有一種值（或都沒有值）的條件不列出。"""
    options = []
    for name, label, all_label in FIELDS:
        counts = {}
        for values in facets.values():
            if values[name]:
                counts[values[name]] = counts.get(values[name], 0) + 1
        if len(counts) < 2:
            continue
        options.append({"name": name, "label": label, "all_label": all_label,
                        "choices": [{"value": value, "count": counts[value]} for value in sorted(counts)]})
    return options


def parse(args, options):
    """只接受選單裡真的有的值；其他值當成沒選（避免奇怪的網址把排行清空）。"""
    chosen = {}
    for option in options:
        value = (args.get(option["name"]) or "").strip()
        if any(choice["value"] == value for choice in option["choices"]):
            chosen[option["name"]] = value
    return chosen


def matches(values, chosen):
    return all(values[name] == value for name, value in chosen.items())


def gap_hint(gap):
    """地圖彈出視窗用的「還缺什麼」摘要（2026-11-16 使用者要求點地圖看校系細項）。

    回傳 {"missing": "證照、競賽", "next": "先補的簡章項目", "gain": 補滿可加幾個百分點}；
    只用 analyze_gap 已算好的結果，不另外判斷。
    """
    from app.services.gap_service import ALL_LABELS

    missing = "、".join(ALL_LABELS.get(key, key) for key in gap.get("missing_keys", []))
    priority = next((item for item in gap.get("items", []) if item["id"] == gap.get("priority_id")), None)
    return {
        "missing": missing,
        "next": priority["name"] if priority else "",
        "gain": priority["gain"] if priority else 0,
    }
