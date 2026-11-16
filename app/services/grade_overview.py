"""年級總覽（11-05 評審意見 5b；使用者 11-09 決定給科辦與管理員看）。

以年級為單位統計專一到專五：人數、平均成績、及格學分、證照、獎項（競賽）、其他經歷、上傳檔案。
只算學生已確認的資料（草稿、未確認的不算）。年級由入學學年度換算；沒填入學學年度的學生另外列人數。
"""
from collections import defaultdict

from app.models import CredentialRecord, LearningCourseRecord, Portfolio, SourceDocument, StudentProfile, User
from app.services.journey_service import EXPERIENCE_CATEGORIES, GRADE_LABELS, current_grade


def _empty():
    return {"students": 0, "course_count": 0, "score_sum": 0, "scored": 0, "credits": 0,
            "credentials": 0, "awards": 0, "experiences": 0, "uploads": 0}


def build(today=None):
    students = (User.query.join(StudentProfile, StudentProfile.user_id == User.id)
                .filter(User.role == "student", User.is_active.is_(True)).all())
    grade_of = {}
    unknown = 0
    for student in students:
        grade = current_grade(student.student_profile.admission_year, today)
        if grade is None:
            unknown += 1
        else:
            grade_of[student.id] = grade
    rows = defaultdict(_empty)
    for grade in grade_of.values():
        rows[grade]["students"] += 1
    ids = list(grade_of)
    if ids:
        for course in LearningCourseRecord.query.filter(LearningCourseRecord.student_id.in_(ids),
                                                        LearningCourseRecord.confirmation_status == "confirmed"):
            row = rows[grade_of[course.student_id]]
            row["course_count"] += 1
            if course.score is not None:
                row["score_sum"] += course.score
                row["scored"] += 1
            if course.acquisition_status == "passed":
                row["credits"] += course.credits or 0
        for record in CredentialRecord.query.filter(CredentialRecord.student_id.in_(ids),
                                                    CredentialRecord.confirmation_status == "confirmed"):
            rows[grade_of[record.student_id]]["credentials"] += 1
        for item in Portfolio.query.filter(Portfolio.student_id.in_(ids), Portfolio.status == "confirmed"):
            if item.category == "competition":
                rows[grade_of[item.student_id]]["awards"] += 1
            elif item.category in EXPERIENCE_CATEGORIES:
                rows[grade_of[item.student_id]]["experiences"] += 1
        for document in SourceDocument.query.filter(SourceDocument.owner_id.in_(ids),
                                                    SourceDocument.status == "confirmed"):
            rows[grade_of[document.owner_id]]["uploads"] += 1
    result = []
    for grade in range(1, 6):
        row = rows[grade]
        count = row["students"]
        result.append({
            "grade": grade, "label": GRADE_LABELS[grade], "students": count,
            "average_score": round(row["score_sum"] / row["scored"], 1) if row["scored"] else None,
            "average_credits": round(row["credits"] / count, 1) if count else None,
            "credentials": row["credentials"], "credentials_per_student": round(row["credentials"] / count, 1) if count else None,
            "awards": row["awards"], "experiences": row["experiences"], "uploads": row["uploads"],
        })
    return {"rows": result, "unknown_grade": unknown, "total": len(students)}
