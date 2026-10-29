"""A2 學生條件（T5，最小版）：從學生已確認的成績整理學群，以及校系屬於哪個學群。

規則（規格見 AI_設計規格_Agent分工規劃_2026-10-22.md 第〇節 T5、第四節 A2）：
- 只用學生已確認（confirmation_status=confirmed）而且及格的成績；草稿與不及格的科目不算。
- 科目 → 學群查 app/content/curriculum_groups.csv（資管科修業科目表，依入學年度分版）。
  只算「專業必修、專業選修」；通識、實習、微學分不算學群。
- 主要學群 = 已修專業科目最多的學群。專業科目少於 MIN_PROFESSIONAL_COURSES 科、
  兩個學群一樣多、或沒有那一屆的課綱表時，一律「待確認」，不硬判（D8）。
- 課名對不到課綱、或課綱上標「待確認」的科目，列出來讓學生或科辦確認。
- 校系 → 學群查 app/content/department_groups.csv（人工依招生類別與系名整理）；查不到或標「待確認」回傳 None。
- 這裡不呼叫外部 AI；之後要請 AI 建議課名對應時，只送課名，不送姓名、學號與缺曠資料。
"""

import csv
import re
from pathlib import Path

from app.models import LearningCourseRecord

CONTENT_DIR = Path(__file__).resolve().parents[1] / "content"
CURRICULUM_FILE = CONTENT_DIR / "curriculum_groups.csv"
DEPARTMENT_FILE = CONTENT_DIR / "department_groups.csv"

PROFESSIONAL_CATEGORIES = ("專業必修", "專業選修")
SUBJECT_GROUPS = ("資訊", "商管")  # 資管科專業科目分得出來的學群；其餘標「待確認」
NEEDS_CHECK = "待確認"
MIN_PROFESSIONAL_COURSES = 3

# 校區、組別等括號註記：「資訊管理系（臺北）」→「資訊管理系」
_CAMPUS_SUFFIX = re.compile(r"[（(][^）)]*[）)]$")
# 學期序號：「程式設計（一）」→「程式設計」
_ORDINAL_SUFFIX = re.compile(r"\((一|二|三|四|五|六|上|下|I|II|III|IV|Ⅰ|Ⅱ|Ⅲ|Ⅳ)\)$")


def normalize_course_name(name):
    text = "".join((name or "").split()).replace("（", "(").replace("）", ")").upper()
    return _ORDINAL_SUFFIX.sub("", text)


def _department_key(name):
    return _CAMPUS_SUFFIX.sub("", "".join((name or "").split()))


def load_curriculum(path=None):
    """回傳 {入學年度: {正規化課名: {name, category, group, source}}}；同名科目以專業科目那一筆為準。"""
    curriculum = {}
    with open(path or CURRICULUM_FILE, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            year = curriculum.setdefault(int(row["入學年度"]), {})
            key = normalize_course_name(row["科目名稱"])
            if key in year and year[key]["category"] in PROFESSIONAL_CATEGORIES:
                continue
            year[key] = {"name": row["科目名稱"], "category": row["科目類別"], "group": row["學群"],
                         "source": row["出處"]}
    return curriculum


def load_department_groups(path=None):
    """回傳 {(科系, 招生類別): {groups: [...], basis}}；學群標「待確認」的 groups 為空。"""
    table = {}
    with open(path or DEPARTMENT_FILE, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            groups = [group for group in row["學群"].split("；") if group and group != NEEDS_CHECK]
            table[(_department_key(row["科系"]), row["招生類別"].strip())] = {"groups": groups, "basis": row["依據"]}
    return table


def department_groups(program, table=None):
    """校系屬於哪些學群；查不到或待確認時回傳 None。"""
    table = load_department_groups() if table is None else table
    found = table.get((_department_key(program.department_name), (program.admission_category or "").strip()))
    return found if found and found["groups"] else None


def _needs_check(summary, reason):
    if summary["unmatched"]:
        reason += f"這些課名對不到課綱，請確認：{'、'.join(summary['unmatched'])}。"
    summary.update(status="needs_check", main_group=None, reason=f"學群待確認：{reason}")
    return summary


def summarize_student_groups(student, curriculum=None):
    """學生條件摘要（學群部分）：{status, main_group, group_counts, professional_course_count, ...}。"""
    profile = student.student_profile
    admission_year = profile.admission_year if profile else None
    summary = {"status": "ok", "main_group": None, "group_counts": {}, "professional_course_count": 0,
               "courses_by_group": {}, "unmatched": [], "needs_check_courses": [],
               "curriculum_year": admission_year, "reason": ""}
    curriculum = load_curriculum() if curriculum is None else curriculum
    table = curriculum.get(admission_year)
    if table is None:
        return _needs_check(summary, f"還沒有整理 {admission_year} 學年度入學的課綱對照表，請科辦補上。")

    courses = (LearningCourseRecord.query
               .filter_by(student_id=student.id, confirmation_status="confirmed")
               .order_by(LearningCourseRecord.id).all())
    for course in courses:
        if course.acquisition_status != "passed":
            continue
        entry = table.get(normalize_course_name(course.course_name))
        if entry is None:
            summary["unmatched"].append(course.course_name)
        elif entry["category"] not in PROFESSIONAL_CATEGORIES:
            continue
        elif entry["group"] not in SUBJECT_GROUPS:
            summary["needs_check_courses"].append(course.course_name)
        else:
            summary["courses_by_group"].setdefault(entry["group"], []).append(course.course_name)
    summary["group_counts"] = {group: len(names) for group, names in summary["courses_by_group"].items()}
    summary["professional_course_count"] = sum(summary["group_counts"].values())

    total = summary["professional_course_count"]
    if total < MIN_PROFESSIONAL_COURSES:
        return _needs_check(summary, f"已確認、及格且對得到課綱的專業科目只有 {total} 科"
                                     f"（至少要 {MIN_PROFESSIONAL_COURSES} 科），請先上傳並確認成績單。")
    ranked = sorted(summary["group_counts"].items(), key=lambda item: -item[1])
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return _needs_check(summary, f"{ranked[0][0]}類和{ranked[1][0]}類專業科目一樣多（各 {ranked[0][1]} 科），"
                                     "請導師協助確認。")
    summary["main_group"] = ranked[0][0]
    return summary
