"""DEMO-03 活動適合學校：每一筆活動與經歷，列出哪些校系的甄審項目會用到它的類別。

規則（寫在這裡，方便報告時說明；只用本機規則，不呼叫 AI）：
- 校系範圍：有目標校系就只看目標校系；沒有目標時，用推薦排序（matching_service.rank_programs）裡
  「可報」、學群不是「不相關」的前 10 個（排序本來就把學群相關的放在待確認前面）。
- 一個校系有好幾個項目都用到同一類別時，取占比最高的那一項。
- 同一個系可能有不同招生管道（例如二技甄選、四技申請入學），所以每個校系都標出招生管道。
- 每筆紀錄最多列 3 個校系，依占比由高到低；同占比依校系範圍原本的順序。
- 項目對應的類別來自缺件比對（gap_service.analyze_gap）的 have＋missing，兩邊一定相同。
- 總結：依「幫得上幾筆紀錄」排序，同筆數再比最高占比，列前 3 個。
"""

from app.models import StudentTarget
from app.services.admission_schedule import channel_label
from app.services.admission_service import published_programs
from app.services.gap_service import analyze_gap
from app.services.journey_service import build_journey
from app.services.matching_service import rank_programs

RECOMMEND_LIMIT = 10
PER_RECORD_LIMIT = 3
SUMMARY_LIMIT = 3
EMPTY_NOTES = {
    "target": "目前目標校系的甄審沒有列這一類",
    "recommended": "目前推薦的校系甄審沒有列這一類",
}


def _scope_programs(student, journey):
    targets = [t.program for t in StudentTarget.query.filter_by(student_id=student.id)
               .order_by(StudentTarget.selected_at)]
    if targets:
        return "target", [(program, analyze_gap(student, program, journey)) for program in targets]
    rows = [row for row in rank_programs(student, published_programs(), journey)
            if row["status"] == "eligible" and row["related"] is not False]
    return "recommended", [(row["program"], row["gap"]) for row in rows[:RECOMMEND_LIMIT]]


def _uses_by_category(scoped):
    """{類別: [{program, name, item, weight}]}，每個校系只取用到該類別、占比最高的項目。"""
    uses = {}
    for program, gap in scoped:
        best = {}
        for item in gap["items"]:
            for key in item["have"] + item["missing"]:
                if key not in best or item["weight"] > best[key]["weight"]:
                    best[key] = {"program": program, "name": f"{program.school_name} {program.department_name}",
                                 "channel": channel_label(program), "item": item["name"], "weight": item["weight"]}
        for key, entry in best.items():
            uses.setdefault(key, []).append(entry)
    for entries in uses.values():
        entries.sort(key=lambda entry: -entry["weight"])  # 穩定排序，同占比維持校系範圍的順序
    return uses


def build_activity_fit(student, records, journey=None):
    """回傳 {scope, programs, by_record, summary, summary_schools, record_count, empty_note}。"""
    journey = journey or build_journey(student)
    scope, scoped = _scope_programs(student, journey)
    uses = _uses_by_category(scoped)
    by_record = {record.id: uses.get(record.category, [])[:PER_RECORD_LIMIT] for record in records}

    tally = {}
    for entries in by_record.values():
        for entry in entries:
            row = tally.setdefault(entry["program"].id, {"program": entry["program"], "name": entry["name"],
                                                          "channel": entry["channel"], "count": 0, "weight": 0})
            row["count"] += 1
            row["weight"] = max(row["weight"], entry["weight"])
    summary = sorted(tally.values(), key=lambda row: (-row["count"], -row["weight"]))[:SUMMARY_LIMIT]

    return {
        "scope": scope,
        "programs": [program for program, _ in scoped],
        "by_record": by_record,
        "summary": summary,
        # 標題只寫學校名稱；同一間學校的兩個系只寫一次
        "summary_schools": list(dict.fromkeys(row["program"].school_name for row in summary)),
        "record_count": len(records),
        "empty_note": EMPTY_NOTES[scope],
    }
