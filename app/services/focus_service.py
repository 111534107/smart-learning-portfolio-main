"""選了很多目標校系時的「聚焦」：資料很多，先做最重要的 3 件。

畫面先把所有校系的備審項目堆滿（pieces），再框出最重要的 3 類資料（top）。
「重要」的算法（寫在這裡，報告時可以說明）：
- 只看學生還沒有的資料類別（gap_service 的 missing）。
- 每個簡章項目的加權平均分給它對應的學習資料類別，同一類在所有目標校系的分數加總。
  例：某系「證照/競賽 40%」，兩類各得 20 分；三個系都要證照，就是三個系的分數加起來。
- 「自傳與讀書計畫」不是學習資料，但很多系佔分不低：還沒替該系寫自傳時也列入，
  分數一樣用該項目加權平分（要到可以寫自傳的年級才列）。
- 分數最高的 3 類就是先做的事；同分時，需要它的校系多的排前面。
- 分數是系統把加權「平分」後的估算，不是校方公布的細項配分，也不是錄取機率。
- 只算現行目標（最新學年度的校系，和選校名額同一套）；舊學年度的目標不參與。
- 簡章項目對應哪一類若還是「待確認」（關鍵字推測），結果會標 pending，畫面要寫「分類待確認」。
- 專題作品等要自己準備的文件不在推薦範圍內；沒有推薦時不能說「都準備好了」。
"""

from flask import url_for

from app.services import student_rules
from app.services.autobiography_service import latest_draft
from app.services.gap_service import ALL_LABELS, analyze_gap
from app.services.journey_service import build_journey

FOCUS_MIN_TARGETS = 3
MAX_TOP = 3
MAX_PIECES = 60


def _add_link(category):
    if category in ("grades", "credential"):
        return url_for("student.learning_profile_upload_page",
                       type="transcript" if category == "grades" else "credential")
    return url_for("student.portfolio_new", category=category)


def _short_school(name):
    return name.replace("國立", "").replace("科技大學", "科大").replace("大學", "大")


def focus_view(user, journey=None):
    targets = student_rules.target_slots(user)["current"]
    if len(targets) < FOCUS_MIN_TARGETS:
        return None
    journey = journey or build_journey(user)

    can_write_bio = student_rules.review_block_reason(user) is None
    pieces, scores, schools, links, pending = [], {}, {}, {}, set()
    for target in targets:
        program = target.program
        gap = analyze_gap(user, program, journey)
        needs_bio = can_write_bio and latest_draft(user, program) is None
        for item in gap["items"]:
            pieces.append({"school": _short_school(program.school_name), "name": item["name"], "weight": item["weight"]})
            missing = list(item["missing"])
            if needs_bio and "autobiography" in item["documents"]:
                missing.append("autobiography")
                links.setdefault("autobiography", url_for("student.autobiography", program_id=program.id))
            share = len(item["have"]) + len(item["missing"]) + len(item["documents"])
            for key in missing:
                scores[key] = scores.get(key, 0) + item["weight"] / share
                schools.setdefault(key, set()).add(program.id)
                if item["mapping_pending"]:
                    pending.add(key)

    ranked = sorted(scores, key=lambda key: (-scores[key], -len(schools[key])))
    top = [{
        "key": key,
        "label": ALL_LABELS[key],
        "verb": "寫" if key == "autobiography" else "補上",
        "score": round(scores[key], 1),
        "schools": len(schools[key]),
        "href": links.get(key) or _add_link(key),
        "pending": key in pending,
    } for key in ranked[:MAX_TOP]]
    return {
        "targets": len(targets),
        "total": len(pieces),
        "pieces": pieces[:MAX_PIECES],
        "top": top,
        "has_pending": any(item["pending"] for item in top),
    }
