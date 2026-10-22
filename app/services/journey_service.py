"""把學生的六類學習資料整理成「專一到專五」的五年資料夾。

學年欄位可能填年級（1～5）或民國學年度（例如 113），兩種都接受。
"""

from datetime import date

from app.models import CredentialRecord, LearningCourseRecord, Portfolio

CATEGORY_KEYS = ["grades", "credential", "activity", "competition", "service", "leadership"]

CATEGORY_LABELS = {
    "grades": "成績與學分",
    "credential": "證照",
    "activity": "活動",
    "competition": "競賽",
    "service": "服務學習",
    "leadership": "幹部經歷",
}

# 由學生自行新增的四類經歷（成績與證照來自上傳的文件）
EXPERIENCE_CATEGORIES = ["activity", "competition", "service", "leadership"]

GRADE_LABELS = {1: "專一", 2: "專二", 3: "專三", 4: "專四", 5: "專五"}


def academic_year_of(day):
    """民國學年度：每年 8 月 1 日開始新學年。"""
    year = day.year - 1911
    return year if day.month >= 8 else year - 1


def grade_for(school_year, admission_year):
    """把年級或民國學年度換算成 1～5 年級；無法判斷時回傳 None。"""
    if school_year is None:
        return None
    if 1 <= school_year <= 5:
        return school_year
    if admission_year is None:
        return None
    grade = school_year - admission_year + 1
    return grade if 1 <= grade <= 5 else None


def current_grade(admission_year, today=None):
    if admission_year is None:
        return None
    grade = academic_year_of(today or date.today()) - admission_year + 1
    return min(max(grade, 1), 5)


def _empty_categories():
    return {key: [] for key in CATEGORY_KEYS}


def build_journey(student, today=None):
    profile = student.student_profile
    admission_year = profile.admission_year if profile else None
    folders = {grade: _empty_categories() for grade in GRADE_LABELS}
    unsorted = _empty_categories()

    def place(grade, category, item):
        (folders[grade] if grade else unsorted)[category].append(item)

    courses = LearningCourseRecord.query.filter_by(student_id=student.id).order_by(LearningCourseRecord.id).all()
    for course in courses:
        place(grade_for(course.year_for_placement, admission_year), "grades", {
            "title": course.course_name,
            "detail": " · ".join(part for part in (
                f"{course.credits} 學分" if course.credits is not None else "",
                f"{course.score} 分" if course.score is not None else (course.status_mark or ""),
            ) if part),
        })

    credentials = CredentialRecord.query.filter_by(student_id=student.id).order_by(CredentialRecord.id).all()
    for credential in credentials:
        year = academic_year_of(credential.issue_date) if credential.issue_date else None
        place(grade_for(year, admission_year), "credential", {
            "title": credential.credential_name,
            "detail": credential.level or "",
        })

    portfolios = Portfolio.query.filter_by(student_id=student.id).order_by(Portfolio.id).all()
    unsorted_count = 0
    for record in portfolios:
        if record.category not in EXPERIENCE_CATEGORIES:
            unsorted_count += 1
            continue
        place(grade_for(record.school_year, admission_year), record.category, {
            "title": record.title,
            "detail": record.description or "",
            "source": "" if record.source == "student" else record.source_label,
        })

    totals = {key: 0 for key in CATEGORY_KEYS}
    years = []
    for grade, categories in folders.items():
        count = 0
        for key, items in categories.items():
            totals[key] += len(items)
            count += len(items)
        years.append({"grade": grade, "label": GRADE_LABELS[grade], "categories": categories, "count": count})
    for key, items in unsorted.items():
        totals[key] += len(items)
        unsorted_count += len(items)

    return {
        "current_grade": current_grade(admission_year, today),
        "admission_year": admission_year,
        "years": years,
        "unsorted": unsorted,
        "unsorted_count": unsorted_count,
        "totals": totals,
        "missing_categories": [key for key in CATEGORY_KEYS if totals[key] == 0],
    }
