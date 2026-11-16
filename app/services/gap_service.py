"""缺件比對：用目標校系的備審加權，對照學生的學習資料與備審文件。

規則（寫在這裡，方便報告時說明；10-30 改版，原本只看「有沒有」，一筆證照就整類滿分）：
- 每個簡章項目對應到幾個資料類別，每個類別給一個 0～1 的完成度：
  - 成績：已確認科目平均 85 分以上＝1、75 以上＝0.75、60 以上＝0.5、未滿 60＝0.25；有科目但沒分數＝0.5。
  - 證照、競賽、活動、服務、幹部：1 筆＝0.5、2 筆以上＝1。
    外語類項目只採計語言檢定（規則在 app/content/readiness_rules.csv）。
  - 自傳與讀書計畫：有草稿＝0.5、學生自己改過（第 2 版以上）＝1。
  - 專題作品：標題含「專題」或「作品」的經歷，筆數算法同上。
- 項目完成比例 = 各類完成度的平均。
- 整體準備度 = Σ（項目加權 × 完成比例）÷ Σ（項目加權）。文件項目也列入，所以文件沒寫不會顯示 100%。
- 每個項目的「補滿可加」= 項目加權 ×（1 − 完成比例）÷ 總加權，給學校引導頁排先後。
"""

import csv
import re
from functools import lru_cache
from pathlib import Path

from app.models import CredentialRecord, LearningCourseRecord, Portfolio
from app.services import package_exclusion
from app.services.journey_service import CATEGORY_KEYS, CATEGORY_LABELS, EXPERIENCE_CATEGORIES, build_journey

RULES_FILE = Path(__file__).resolve().parent.parent / "content" / "readiness_rules.csv"
PROJECT_PATTERN = package_exclusion.PROJECT_PATTERN

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


@lru_cache(maxsize=1)
def _credential_rules():
    """（項目名稱規則, 認可證照規則）清單；讀 CSV，方便老師或組員直接改。"""
    with RULES_FILE.open(encoding="utf-8-sig") as handle:
        return [(re.compile(row["項目關鍵字"]), re.compile(row["認可證照關鍵字"], re.IGNORECASE))
                for row in csv.DictReader(handle)]


def _count_level(count):
    return 0.0 if count == 0 else (0.5 if count == 1 else 1.0)


def _grade_level(scores, course_count):
    if not course_count:
        return 0.0
    if not scores:
        return 0.5
    average = sum(scores) / len(scores)
    return 1.0 if average >= 85 else 0.75 if average >= 75 else 0.5 if average >= 60 else 0.25


def student_evidence(student, journey=None):
    """學生的資料一次查好；排行一次比對幾十間校系時重複使用，不要每間都查一次資料庫。"""
    # 畫面上的五年資料夾也顯示草稿，不能直接把它的 totals 用於評估。
    courses = LearningCourseRecord.query.filter_by(student_id=student.id, confirmation_status="confirmed").all()
    credentials = CredentialRecord.query.filter_by(student_id=student.id, confirmation_status="confirmed").all()
    records = (Portfolio.active().filter_by(student_id=student.id)
               .filter_by(status="confirmed").all())
    # 預設只算學生願意放進備審的資料；"full" 是全部已確認資料，給簡章規定必備的類別用。
    kept = _summarize([c for c in courses if not c.excluded_from_package],
                      [c for c in credentials if not c.excluded_from_package],
                      [r for r in records if not r.excluded_from_package])
    kept["full"] = _summarize(courses, credentials, records)
    return kept


def _summarize(courses, credentials, records):
    totals = {key: 0 for key in CATEGORY_KEYS}
    totals["grades"] = len(courses)
    totals["credential"] = len(credentials)
    for record in records:
        if record.category in EXPERIENCE_CATEGORIES:
            totals[record.category] += 1
    return {
        "totals": totals,
        "scores": [course.score for course in courses if course.score is not None],
        "course_count": len(courses),
        "credential_names": [credential.credential_name or "" for credential in credentials],
        "project_count": sum(1 for record in records if PROJECT_PATTERN.search(record.title or "")),
    }


def _for_key(evidence, key, required):
    """簡章規定必備的類別用全部已確認資料，其餘只用學生願意放進備審的。"""
    return evidence.get("full", evidence) if key in required else evidence


def _autobiography_level(student, program):
    from app.services.autobiography_service import latest_draft, version_of  # 互相引用，放函式裡
    draft = latest_draft(student, program)
    return 0.0 if not draft else (1.0 if version_of(draft) >= 2 else 0.5)


def _key_level(key, item_name, evidence, student, program, required=()):
    evidence = _for_key(evidence, key, required)
    totals = evidence["totals"]
    if key == "grades":
        return _grade_level(evidence["scores"], evidence["course_count"])
    if key == "credential":
        for item_rule, credential_rule in _credential_rules():
            if item_rule.search(item_name or ""):
                return _count_level(sum(1 for name in evidence["credential_names"] if credential_rule.search(name)))
        return _count_level(totals.get(key, 0))
    if key == "autobiography":
        return _autobiography_level(student, program)
    if key == "project":
        return _count_level(evidence["project_count"])
    return _count_level(totals.get(key, 0))


def analyze_gap(student, program, journey=None, evidence=None):
    evidence = evidence or student_evidence(student, journey)
    required = package_exclusion.required_keys(program)
    items = []
    weighted, total_weight = 0.0, 0
    for item in program.items:
        keys = item.category_keys
        record_keys = [key for key in keys if key in CATEGORY_KEYS]
        documents = [key for key in keys if key not in CATEGORY_KEYS]
        levels = {key: _key_level(key, item.source_item_name, evidence, student, program, required) for key in keys}
        have = [key for key in record_keys if levels[key] > 0]
        missing = [key for key in record_keys if levels[key] == 0]
        if not keys:
            fraction, status = None, "prepare"  # 簡章項目還沒對應到資料類別：不列入
        else:
            fraction = sum(levels.values()) / len(keys)
            total_weight += item.weight_percent
            weighted += item.weight_percent * fraction
            if fraction == 1:
                status = "complete"
            elif not record_keys:
                status = "prepare"  # 只有自傳、專題等要自己準備的文件
            else:
                status = "partial" if fraction > 0 else "missing"
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
            "levels": levels,
            # 這個項目最該先補的類別：完成度最低的那一個（全滿時為 None）
            "next_key": min((key for key in keys if levels[key] < 1), key=lambda key: levels[key], default=None),
            "counts": {key: _for_key(evidence, key, required)["totals"].get(key, 0) for key in record_keys},
            "mapping_pending": item.mapping_status != "confirmed",
            "requirement": item.requirement,
        })
    for entry in items:
        open_part = 0 if entry["fraction"] is None else 1 - entry["fraction"]
        entry["gain"] = round(entry["weight"] * open_part / total_weight * 100) if total_weight else 0
    readiness = round(weighted / total_weight * 100) if total_weight else None
    missing_keys = sorted({key for item in items for key in item["missing"]}, key=CATEGORY_KEYS.index)
    # 最該先補的項目：補滿可加最多的那一個
    open_items = [item for item in items if item["gain"] > 0]
    priority = max(open_items, key=lambda item: item["gain"], default=None)
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
