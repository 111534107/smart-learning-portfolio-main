from datetime import date

from app import create_app
from app.extensions import db
from app.models import CredentialRecord, LearningCourseRecord, Portfolio, StudentProfile, User
from app.services.journey_service import (
    CATEGORY_KEYS,
    academic_year_of,
    build_journey,
    current_grade,
    grade_for,
)


def journey_app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
    return app


def test_six_categories_are_fixed_and_ordered():
    assert CATEGORY_KEYS == ["grades", "credential", "activity", "competition", "service", "leadership"]


def test_grade_for_accepts_grade_numbers_and_academic_years():
    assert grade_for(3, None) == 3
    assert grade_for(113, 111) == 3
    assert grade_for(111, 111) == 1
    assert grade_for(117, 111) is None
    assert grade_for(113, None) is None
    assert grade_for(None, 111) is None
    assert grade_for(0, 111) is None


def test_academic_year_starts_in_august():
    assert academic_year_of(date(2024, 8, 1)) == 113
    assert academic_year_of(date(2025, 7, 31)) == 113
    assert academic_year_of(date(2025, 8, 1)) == 114


def test_current_grade_is_clamped_between_one_and_five():
    assert current_grade(111, date(2024, 9, 1)) == 3
    assert current_grade(111, date(2030, 9, 1)) == 5
    assert current_grade(115, date(2024, 9, 1)) == 1
    assert current_grade(None, date(2024, 9, 1)) is None


def test_build_journey_puts_each_record_in_its_year_and_category():
    app = journey_app()
    with app.app_context():
        student = User(username="s1", display_name="學生", role="student")
        student.set_password("pw")
        db.session.add(student)
        db.session.flush()
        db.session.add(StudentProfile(user_id=student.id, student_no="111534199", admission_year=111))
        db.session.add(LearningCourseRecord(
            student_id=student.id, school_year=112, course_name="程式設計",
            normalized_course_name="程式設計", credits=3, score=90,
        ))
        db.session.add(CredentialRecord(
            student_id=student.id, credential_name="網頁設計丙級", issue_date=date(2024, 3, 2),
        ))
        db.session.add(Portfolio(student_id=student.id, title="迎新活動", category="activity", school_year=1))
        db.session.add(Portfolio(student_id=student.id, title="舊資料", category="其他"))
        db.session.commit()

        journey = build_journey(student, today=date(2024, 9, 1))

    assert journey["current_grade"] == 3
    years = {year["grade"]: year for year in journey["years"]}
    assert [item["title"] for item in years[2]["categories"]["grades"]] == ["程式設計"]
    assert [item["title"] for item in years[2]["categories"]["credential"]] == ["網頁設計丙級"]
    assert [item["title"] for item in years[1]["categories"]["activity"]] == ["迎新活動"]
    assert journey["unsorted_count"] == 1
    assert journey["totals"]["grades"] == 1
    assert journey["totals"]["service"] == 0
    assert journey["missing_categories"] == ["competition", "service", "leadership"]
