"""學生首頁「我的五年路線」要用的資料。規格：docs/02_需求與設計/02_設計規格/AI_設計規格_我的五年路線首頁_2026-10-10.md

- stops：專一到專五五個節點；走過的是 past、今年是 now、之後是 future，count 是那一年留下幾筆。
- pieces：今年的六塊拼圖（六類學習資料），沒有資料的是空白，點了去補。
- away_days：上次登入在 RETURN_DAYS 天以前才有值，用來播「好久不見」那一幕。
  登入紀錄存在操作紀錄（action="student.login"），最新一筆就是這次登入。
"""

from datetime import datetime, timezone

from flask import url_for

from app.content.five_year_plan import FIVE_YEAR_PLAN
from app.models import AuditLog, Portfolio, SourceDocument
from app.services.journey_service import CATEGORY_KEYS, CATEGORY_LABELS, GRADE_LABELS, build_journey

RETURN_DAYS = 60
# 今年的拼圖：一張插畫切成 3×2 六片，每片對應一類資料（順序同 CATEGORY_KEYS）
PUZZLE_COLS, PUZZLE_ROWS, PIECE = 3, 2, 200
# 共用邊的凸出方向（固定，讓每個學生看到同一套形狀）：橫邊 +1＝往下凸，直邊 +1＝往右凸
H_TABS = {(1, 0): 1, (1, 1): -1, (1, 2): 1}              # (第幾條橫邊, 欄)
V_TABS = {(0, 1): 1, (0, 2): -1, (1, 1): -1, (1, 2): 1}  # (列, 第幾條直邊)
PIECE_LABELS = {"grades": "成績", "credential": "證照", "activity": "活動", "competition": "競賽", "service": "服務", "leadership": "幹部"}


def _edge(p, q, normal):
    """從 p 走到 q 的一條邊；normal 是凸出的方向（(0,0) 代表外框直線）。"""
    if normal == (0, 0):
        return f"L{q[0]:g} {q[1]:g}"
    dx, dy = q[0] - p[0], q[1] - p[1]
    a = (p[0] + dx * 0.36, p[1] + dy * 0.36)
    b = (p[0] + dx * 0.64, p[1] + dy * 0.64)
    h = PIECE * 0.22
    c1 = (a[0] + normal[0] * h - dx * 0.12, a[1] + normal[1] * h - dy * 0.12)
    c2 = (b[0] + normal[0] * h + dx * 0.12, b[1] + normal[1] * h + dy * 0.12)
    return (f"L{a[0]:g} {a[1]:g} C{c1[0]:g} {c1[1]:g} {c2[0]:g} {c2[1]:g} {b[0]:g} {b[1]:g} "
            f"L{q[0]:g} {q[1]:g}")


def jigsaw_pieces():
    """六片拼圖的外框路徑（座標在 600×400 的整張圖上），相鄰兩片共用同一條凹凸邊。"""
    pieces = []
    for row in range(PUZZLE_ROWS):
        for col in range(PUZZLE_COLS):
            x, y = col * PIECE, row * PIECE
            tl, tr, br, bl = (x, y), (x + PIECE, y), (x + PIECE, y + PIECE), (x, y + PIECE)
            top = (0, H_TABS.get((row, col), 0))
            bottom = (0, H_TABS.get((row + 1, col), 0))
            left = (V_TABS.get((row, col), 0), 0)
            right = (V_TABS.get((row, col + 1), 0), 0)
            d = (f"M{x} {y} " + _edge(tl, tr, top) + " " + _edge(tr, br, right) + " "
                 + _edge(br, bl, bottom) + " " + _edge(bl, tl, left) + " Z")
            pieces.append({"x": x, "y": y, "d": d})
    return pieces


def _add_link(category):
    if category in ("grades", "credential"):
        # 成績單與證照分兩頁：直接開對應類型的上傳頁
        return url_for("student.learning_profile_upload_page",
                       type="transcript" if category == "grades" else "credential")
    return url_for("student.portfolio_new", category=category)


def _aware(moment):
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def away_days(user, now=None):
    logins = (AuditLog.query.filter_by(user_id=user.id, action="student.login")
              .order_by(AuditLog.created_at.desc()).limit(2).all())
    if len(logins) < 2:
        return None
    days = (_aware(logins[0].created_at) - _aware(logins[1].created_at)).days
    return days if days >= RETURN_DAYS else None


def journey_home(user, journey=None, now=None):
    journey = journey or build_journey(user)
    grade = journey["current_grade"] or 1
    words = {stop["grade"]: stop["title"].split("・")[-1] for stop in FIVE_YEAR_PLAN}

    stops = [{
        "grade": year["grade"],
        "label": GRADE_LABELS[year["grade"]],
        "word": words.get(year["grade"], ""),
        "count": year["count"],
        "state": "past" if year["grade"] < grade else ("now" if year["grade"] == grade else "future"),
    } for year in journey["years"]]

    this_year = next(year for year in journey["years"] if year["grade"] == grade)
    shapes = jigsaw_pieces()
    pieces = [{
        "key": key,
        "label": PIECE_LABELS[key],
        "full_label": CATEGORY_LABELS[key],
        "filled": len(this_year["categories"][key]) > 0,
        "href": _add_link(key),
        **shapes[index],
    } for index, key in enumerate(CATEGORY_KEYS)]

    previous = next((year for year in journey["years"] if year["grade"] == grade - 1), None)

    # 五年累積（Canva 第 11 頁）：走過的每一年 6 類，有資料的格數比例；不是錄取機率
    walked = [year for year in journey["years"] if year["grade"] <= grade]
    filled_cells = sum(1 for year in walked for key in CATEGORY_KEYS if year["categories"][key])
    pending = (SourceDocument.query.filter(SourceDocument.owner_id == user.id, SourceDocument.status != "confirmed").count()
               + Portfolio.query.filter_by(student_id=user.id, status="draft").count())
    latest = Portfolio.query.filter_by(student_id=user.id).order_by(Portfolio.created_at.desc(), Portfolio.id.desc()).first()
    summary = {
        "percent": round(filled_cells / (len(walked) * len(CATEGORY_KEYS)) * 100) if walked else 0,
        "pending": pending,
        "latest": latest.title if latest else None,
    }
    return {
        "summary": summary,
        "grade": grade,
        "grade_label": GRADE_LABELS[grade],
        "stops": stops,
        "pieces": pieces,
        "blanks": sum(1 for piece in pieces if not piece["filled"]),
        "away_days": away_days(user, now),
        "previous": {"label": previous["label"], "count": previous["count"]} if previous else None,
    }
