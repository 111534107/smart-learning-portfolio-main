"""備審 A4 頁面（參考學長姐的備審作品）：封面、客製目錄、簡歷表、自傳、求學歷程（代表課程 → 課程延伸成果）、
企業實習、社團、作品集、報考動機與未來規劃。資料只用學生已確認的，順序依校系簡章加權。"""

import math
import re

from app.services import package_exclusion
from app.services.gap_service import chapter_order
from app.services.journey_service import build_journey
from app.services.package_service import _draft_parts

CHARS_PER_PAGE = 700  # 自傳一頁約放這麼多字（用來估目錄頁碼）
TOP_COURSES = 5
OUTCOME_KEYS = ("credential", "competition", "leadership", "activity", "service")
_SCORE = re.compile(r"(\d{1,3}) 分")


def _confirmed(items):
    return [item for item in items if item.get("confirmation_status") == "confirmed"]


def _score(item):
    match = _SCORE.search(item.get("detail") or "")
    return int(match.group(1)) if match else None


GRADE_SUBTITLES = {1: "打好專業基礎", 2: "從基礎走向應用", 3: "建立程式與系統能力", 4: "從課堂走向實作", 5: "銜接升學與職涯"}


def study_years(journey):
    """求學歷程：每個年級的代表課程（成績最高的 5 門）與同年度的課程延伸成果（證照、競賽、幹部、活動、服務）。"""
    years = []
    for year in journey["years"]:
        categories = year["categories"]
        courses = [dict(name=item["title"], score=_score(item)) for item in _confirmed(categories.get("grades", []))
                   if _score(item) is not None]
        courses.sort(key=lambda c: -c["score"])
        outcomes = []
        for key in OUTCOME_KEYS:
            for item in _confirmed(categories.get(key, [])):
                outcomes.append({"kind": key, "title": item["title"], "detail": item.get("detail") or ""})
        if courses or outcomes:
            years.append({"grade": year["grade"], "label": year["label"], "subtitle": GRADE_SUBTITLES.get(year["grade"], ""),
                          "courses": courses[:TOP_COURSES],
                          "outcomes": outcomes})
    return years


def build(student, program):
    """回傳備審 A4 頁面要用的所有資料。"""
    journey = build_journey(student)
    profile = student.student_profile
    years = study_years(journey)
    bio, plan, heading = _draft_parts(student, program)
    everything = {key: [] for key in OUTCOME_KEYS}
    projects = []
    for year in journey["years"]:
        for key in OUTCOME_KEYS:
            everything[key] += [{"title": i["title"], "detail": i.get("detail") or "", "label": year["label"]}
                                for i in _confirmed(year["categories"].get(key, []))]
        for item in _confirmed(year["categories"].get("activity", [])):
            if (item.get("detail") or "").startswith("專題與作品集"):
                projects.append({"title": item["title"], "detail": item["detail"].replace("專題與作品集 · ", "")})
    resume = {
        "name": student.display_name, "class_name": profile.class_name if profile else "",
        "student_no": profile.student_no if profile else "",
        "competitions": everything["competition"], "credentials": everything["credential"],
        "leaderships": everything["leadership"], "projects": projects,
    }
    bio_paragraphs = [{"title": heading(p), "text": p["text"]} for p in bio]
    plan_paragraphs = [{"title": heading(p), "text": p["text"]} for p in plan]
    chapters = [c for c in chapter_order(program) if c["code"] != "01"]
    page = 3  # 1 封面、2 目錄
    toc = []
    for position, chapter in enumerate(chapters, start=1):
        pages = 1
        if chapter["code"] == "04":
            pages = max(1, math.ceil(sum(len(p["text"]) for p in bio_paragraphs) / CHARS_PER_PAGE))
        elif chapter["code"] == "03":
            pages = max(1, len(years))
        toc.append({"no": f"{position:02d}", "code": chapter["code"], "title": chapter["title"],
                    "weight": chapter["weight"], "page": page, "pages": pages})
        page += pages
    return {
        "cover": {"year": program.admission_year, "school": program.school_name,
                  "department": program.department_name, "applicant": student.display_name},
        "toc": toc, "resume": resume, "bio": bio_paragraphs, "plan": plan_paragraphs, "years": years,
        "has_draft": bool(bio_paragraphs or plan_paragraphs),
        "excluded_note": bool(package_exclusion.required_keys(program) is not None),
    }
