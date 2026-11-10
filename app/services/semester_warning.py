"""各學期預警（只提醒，不判定畢業或學業退學）。

每個已結束的學期看已確認的成績：
- 還沒補及格的不及格科目（標出必修，必修一定要重修）。
- 不及格學分占該學期修習學分的比例：達三分之一「要注意」、達一半「請找導師討論」。
  比例門檻是 Claude 的提議（2026-11-10），還沒和學校學則核對，畫面一律寫「僅供提醒」。
- 已結束但沒有已確認成績的學期，提醒先上傳並確認成績單。
目前這個學期還沒結束，不列入。
"""

from app.services import graduation_check_service as check
from app.services.eligibility_service import load_curriculum, normalize_course_name

WATCH_RATIO = 1 / 3
HIGH_RATIO = 1 / 2
LEVEL_LABELS = {
    "high": ("請找導師討論", "tag--danger"),
    "watch": ("要注意", "tag--warn"),
    "no_data": ("成績還沒確認", "tag--info"),
    "ok": ("沒有不及格", "tag--ok"),
}
NOTE = "僅供提醒：比例是系統先幫你算的，是否需要補救、重修，以學校規定和導師說明為準。"


def _term_label(grade, semester):
    return f"專{grade}{semester}"


def _term(grade, semester, courses, passed_names, table):
    if not courses:
        return {"label": _term_label(grade, semester), "level": "no_data", "attempted": 0, "failed_credits": 0,
                "still_failed": [], "recovered": [],
                "message": "這學期還沒有已確認的成績，請先上傳並確認成績單。"}
    attempted = failed_credits = 0
    still_failed, recovered = [], []
    for course in courses:
        if course.score is None:  # 抵、免、補或沒有分數：不算修習學分
            continue
        credits = course.credits or 0
        attempted += credits
        if course.acquisition_status != "not_passed":
            continue
        failed_credits += credits
        key = normalize_course_name(course.course_name)
        entry = table.get(key)
        required = bool(entry and entry["category"] in check.REQUIRED_CATEGORIES)
        record = {"name": course.course_name, "credits": credits, "score": course.score, "required": required}
        (recovered if key in passed_names else still_failed).append(record)
    ratio = failed_credits / attempted if attempted else 0
    failed_required = [c["name"] for c in still_failed if c["required"]]
    if attempted and ratio >= HIGH_RATIO:
        level = "high"
        message = f"不及格 {failed_credits} 學分，達這學期修習 {attempted} 學分的一半，請盡快找導師討論。"
    elif (attempted and ratio >= WATCH_RATIO) or failed_required:
        level = "watch"
        message = f"不及格 {failed_credits} 學分（這學期修習 {attempted} 學分）。"
        if failed_required:
            message += f"必修 {'、'.join(failed_required)} 還沒補及格，之後一定要重修。"
    elif still_failed:
        level = "watch"
        message = f"有 {len(still_failed)} 門課不及格，還沒補及格。"
    else:
        level = "ok"
        message = "這學期沒有不及格。" if not recovered else "不及格的課之後都已補及格。"
    return {"label": _term_label(grade, semester), "level": level, "attempted": attempted,
            "failed_credits": failed_credits, "still_failed": still_failed, "recovered": recovered,
            "message": message}


def build(student, today=None, curriculum=None):
    """回傳 {terms（新到舊）, counts, stage, reason}。不寫資料庫。"""
    profile = student.student_profile
    admission = profile.admission_year if profile else None
    today = check.check_today() if today is None else today
    stage = check.student_stage(admission, today)
    counts = {"high": 0, "watch": 0, "no_data": 0, "ok": 0}
    if admission is None:
        return {"terms": [], "counts": counts, "stage": stage, "reason": "還沒有入學年度，無法分學期整理。"}
    curriculum = load_curriculum() if curriculum is None else curriculum
    table = curriculum.get(admission) or {}
    courses, _ = check._confirmed_courses(student)
    passed_names = {normalize_course_name(c.course_name) for c in courses if c.acquisition_status == "passed"}
    by_term = {}
    no_semester = set()  # 有年級、沒標上下學期的成績（例如舊資料或辨識漏掉）
    for course in courses:
        key = check.course_term_key(course, admission)
        if key is not None:
            by_term.setdefault((key[0], key[1]), []).append(course)
            continue
        year = course.year_for_placement
        if year is not None and year > 5:
            year = year - admission + 1
        if year is not None:
            no_semester.add(year)
    terms = []
    for year, semester in reversed(stage["ended_terms"]):
        grade = year - admission + 1
        term = _term(grade, semester, by_term.get((grade, semester), []), passed_names, table)
        if term["level"] == "no_data" and grade in no_semester:
            term["message"] = "這一年有成績，但沒有標上下學期，請到成績確認頁補上學期，才能分學期提醒。"
        counts[term["level"]] += 1
        terms.append(term)
    reason = "" if terms else "還沒有已結束的學期。"
    return {"terms": terms, "counts": counts, "stage": stage, "reason": reason}
