"""學生首頁「我的五年路線」要用的資料。規格：docs/02_需求與設計/02_設計規格/AI_設計規格_我的五年路線首頁_2026-10-10.md

- stops：專一到專五五個節點；走過的是 past、今年是 now、之後是 future，count 是那一年留下幾筆。
- table：五年桌板，一筆資料一片拼圖，散在桌子四邊（table_pieces）。
- makers：六個「做拼圖」按鈕（六類學習資料的新增頁）。
- away_days：上次登入在 RETURN_DAYS 天以前才有值，用來播「好久不見」那一幕。
  登入紀錄存在操作紀錄（action="student.login"），最新一筆就是這次登入。
"""

import hashlib
import zlib
from datetime import datetime, timezone

from flask import url_for

from app.content.five_year_plan import FIVE_YEAR_PLAN
from app.models import AuditLog, Portfolio, SourceDocument
from app.services.journey_service import CATEGORY_KEYS, CATEGORY_LABELS, GRADE_LABELS, build_journey

RETURN_DAYS = 60
PIECE_LABELS = {"grades": "成績", "credential": "證照", "activity": "活動", "competition": "競賽", "service": "服務", "leadership": "幹部"}

# 五年桌板：一筆資料＝一片拼圖，散在桌子四邊；拼起來是同一張圖（學期照片或預設風景）。
# 片的格子是 100×100（最後一列可能較寬），外框留 MARGIN 給凸耳。
CELL, MARGIN = 100, 30
# 凸耳的形狀（沿邊比例, 往外比例），對 0.5 左右對稱，所以從哪一端畫過來都一樣，兩片才咬得合
KNOB = [((0.40, 0.00), (0.40, 0.08), (0.37, 0.12)),
        ((0.32, 0.20), (0.40, 0.27), (0.50, 0.27)),
        ((0.60, 0.27), (0.68, 0.20), (0.63, 0.12)),
        ((0.60, 0.08), (0.60, 0.00), (0.65, 0.00))]
# 桌子的長寬（電腦版約 16:9、手機直向 3:4）與片的寬度（佔桌寬的比例），散落位置依這兩種桌子各算一次
TABLES = {"desk": (16, 9, 0.085), "phone": (3, 4, 0.15)}


def _edge(p, q, normal):
    """從 p 畫到 q 的一條邊；normal 是凸耳往哪個方向凸（(0,0)＝直線）。"""
    if normal == (0, 0):
        return f"L{q[0]:g} {q[1]:g}"
    length = abs(q[0] - p[0]) + abs(q[1] - p[1])
    ux, uy = (q[0] - p[0]) / length, (q[1] - p[1]) / length
    mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2

    def at(s, t):  # 凸耳固定大小（以 100 為準），放在邊的正中間
        return (f"{mx + ux * (s - 0.5) * CELL + normal[0] * t * CELL:.1f} "
                f"{my + uy * (s - 0.5) * CELL + normal[1] * t * CELL:.1f}")

    out = [f"L{at(0.35, 0)}"]
    out += ["C" + " ".join(at(*point) for point in curve) for curve in KNOB]
    out.append(f"L{q[0]:g} {q[1]:g}")
    return " ".join(out)


def piece_path(x, y, w, h, top=0, right=0, bottom=0, left=0):
    """一片拼圖的外框；四個邊的值 +1／-1 是凸耳往下（右）或往上（左），0 是直邊。"""
    return (f"M{x:g} {y:g} " + _edge((x, y), (x + w, y), (0, top)) + " "
            + _edge((x + w, y), (x + w, y + h), (right, 0)) + " "
            + _edge((x + w, y + h), (x, y + h), (0, bottom)) + " "
            + _edge((x, y + h), (x, y), (left, 0)) + " Z")


# 「做拼圖」按鈕飛出來的那片：四邊都有凹凸的一片
SAMPLE_PIECE = piece_path(0, 0, CELL, CELL, top=-1, right=1, bottom=1, left=-1)


def _hash(text):
    """穩定的雜湊：同一筆資料每次重新整理都得到同樣的四個 0～1 數字。"""
    digest = hashlib.md5(text.encode("utf-8")).digest()
    return [int.from_bytes(digest[i:i + 4], "big") / 2 ** 32 for i in (0, 4, 8, 12)]


def _scatter(edge_pick, depth, width, height, size):
    """依雜湊把片放在桌子四邊的帶狀區（中間留空）；回傳中心點的 (left%, top%)。"""
    piece = size * width                 # 片的寬度（和桌子同單位）
    near, band = piece * 0.55, piece * 0.9  # 離桌邊的距離、帶子的寬度
    inner = near + band
    side_len = max(height - 2 * inner, 0.01)
    top_len = width - 2 * near
    spot = edge_pick * (2 * top_len + 2 * side_len)
    if spot < 2 * top_len:               # 上邊或下邊
        x = near + (spot % top_len)
        y = near + depth * band if spot < top_len else height - near - depth * band
    else:                                # 左邊或右邊
        spot -= 2 * top_len
        y = inner + (spot % side_len)
        x = near + depth * band if spot < side_len else width - near - depth * band
    return round(x / width * 100, 2), round(y / height * 100, 2)


def _rows_for(count):
    """拼好時的排法：每列幾片。盡量接近 3:2 的長方形；除不盡時最後一列片比較寬，整塊仍是長方形。"""
    if count <= 0:
        return []
    best = None
    for cols in range(1, count + 1):
        rows = -(-count // cols)
        last = count - cols * (rows - 1)
        score = abs(cols / rows - 1.5) + (0 if last == cols else 0.6 + (cols - last) / cols)
        if best is None or score < best[0]:
            best = (score, cols, rows, last)
    _, cols, rows, last = best
    return [cols] * (rows - 1) + [last]


def _bump(row, col, kind):
    """格子之間凸耳的方向：依列、欄、邊的種類混出 +1／-1（固定規則），同一列的片形狀才不會都一樣。"""
    return 1 if (row * 7 + col * 5 + row * col * 3 + kind * 11) % 3 else -1


def table_pieces(journey):
    """五年全部資料，一筆一片：位置、角度依資料的穩定 id 雜湊決定；形狀依拼好時的格子決定，相鄰片咬合。"""
    items = []
    for year in journey["years"]:
        for key in CATEGORY_KEYS:
            seen = {}
            for item in year["categories"][key]:
                if item.get("confirmed") is False:
                    continue
                title = item.get("title") or ""
                # 片的 id＝資料來源＋資料庫編號（改標題、換年級都不變）；沒有編號的假資料才退回用標題
                if item.get("id"):
                    piece_id = item["id"]
                else:
                    seen[title] = seen.get(title, 0) + 1
                    piece_id = f"{year['grade']}-{key}-{zlib.crc32(title.encode('utf-8')):08x}-{seen[title]}"
                items.append({
                    "id": piece_id,
                    "key": key,
                    "label": PIECE_LABELS[key],
                    "grade_label": GRADE_LABELS[year["grade"]],
                    "title": title,
                })

    rows = _rows_for(len(items))
    cols = rows[0] if rows else 0
    scene_w, scene_h = cols * CELL, len(rows) * CELL
    index = 0
    for r, count in enumerate(rows):
        w = scene_w / count
        for c in range(count):
            item = items[index]
            x, y = c * w, r * CELL
            top = _bump(r, c, 1) if r > 0 and rows[r - 1] == count else 0
            bottom = _bump(r + 1, c, 1) if r + 1 < len(rows) and rows[r + 1] == count else 0
            left = _bump(r, c, 2) if c > 0 else 0
            right = _bump(r, c + 1, 2) if c + 1 < count else 0
            t, d, _, turn = _hash(item["id"])
            spots = {name: _scatter(t, d, *size) for name, size in TABLES.items()}
            item.update({
                "d": piece_path(x, y, w, CELL, top, right, bottom, left),
                "box": f"{x - MARGIN:g} {y - MARGIN:g} {w + 2 * MARGIN:g} {CELL + 2 * MARGIN}",
                "box_w": round(w + 2 * MARGIN, 2),
                "cx": round(x + w / 2, 2), "cy": y + CELL / 2,
                "x": spots["desk"][0], "y": spots["desk"][1],
                "mx": spots["phone"][0], "my": spots["phone"][1],
                "turn": round(-40 + 80 * turn, 1),
            })
            index += 1
    return {"pieces": items, "count": len(items), "scene_w": scene_w or 300, "scene_h": scene_h or 200}


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


def board_progress(journey):
    """走過的每一年 × 六類，回傳（總格數, 已有資料格數）；首頁「五年累積」的比例用。"""
    grade = journey["current_grade"] or 1
    walked = [year for year in journey["years"] if year["grade"] <= grade]
    total = len(walked) * len(CATEGORY_KEYS)
    filled = sum(1 for year in walked for key in CATEGORY_KEYS
                 if any(item.get("confirmed", True) for item in year["categories"][key]))
    return total, filled


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

    previous = next((year for year in journey["years"] if year["grade"] == grade - 1), None)
    board_total, board_filled = board_progress(journey)
    table = table_pieces(journey)
    completed_keys = {piece["key"] for piece in table["pieces"]}
    totals = journey.get("totals", {})
    confirmed_totals = journey.get("confirmed_totals", totals)
    pending = (SourceDocument.query.filter(SourceDocument.owner_id == user.id, SourceDocument.status != "confirmed").count()
               + Portfolio.active().filter_by(student_id=user.id, status="draft").count())
    latest = Portfolio.active().filter_by(student_id=user.id).order_by(Portfolio.created_at.desc(), Portfolio.id.desc()).first()
    summary = {
        "percent": round(board_filled / board_total * 100) if board_total else 0,
        "pending": pending,
        "latest": latest.title if latest else None,
    }
    return {
        "summary": summary,
        "grade": grade,
        "grade_label": GRADE_LABELS[grade],
        "stops": stops,
        "table": table,
        "sample_piece": SAMPLE_PIECE,
        "makers": [{"key": key, "label": PIECE_LABELS[key], "href": _add_link(key),
                    "complete": key in completed_keys,
                    "pending": totals.get(key, 0) > confirmed_totals.get(key, 0)}
                   for key in CATEGORY_KEYS],
        "away_days": away_days(user, now),
        "previous": {"label": previous["label"], "count": previous["count"]} if previous else None,
    }
