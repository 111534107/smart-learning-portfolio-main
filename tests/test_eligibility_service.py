"""A2 學生條件（T5）：從已確認的成績整理學群；資料不足時說「待確認」，不硬判。（僅為測試資料）"""
import pytest

from app import create_app
from app.extensions import db
from app.models import AdmissionProgram, LearningCourseRecord, StudentProfile, User
from app.services.eligibility_service import (department_groups, load_curriculum, normalize_course_name,
                                              summarize_student_groups)

INFO_COURSES = ["程式設計", "網頁設計", "資料結構", "計算機網路"]


@pytest.fixture()
def app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        yield app


def make_student(admission_year=111, courses=(), status="confirmed"):
    student = User(username="stu", display_name="stu", role="student")
    student.set_password("pw")
    db.session.add(student)
    db.session.flush()
    db.session.add(StudentProfile(user_id=student.id, student_no="stu", class_name="資管科五甲",
                                  admission_year=admission_year))
    add_courses(student, courses, status=status)
    return student


def add_courses(student, names, score=85, status="confirmed"):
    for name in names:
        db.session.add(LearningCourseRecord(student_id=student.id, course_name=name,
                                            normalized_course_name="".join(name.split()), credits=3, score=score,
                                            confirmation_status=status))
    db.session.flush()


def test_curriculum_table_has_both_years_and_a_source_on_every_row():
    curriculum = load_curriculum()

    assert curriculum[111]["程式設計"]["group"] == "資訊"
    assert curriculum[113]["會計學"]["group"] == "商管"
    assert curriculum[111]["國文"]["group"] == "通識"
    assert all(row["source"] for year in curriculum.values() for row in year.values())


def test_course_names_are_normalized_before_lookup():
    assert normalize_course_name("程式設計（一）") == normalize_course_name("程式設計")
    assert normalize_course_name("資料庫管理實務（SQL）") == normalize_course_name("資料庫管理實務(SQL)")
    assert normalize_course_name("python 程式語言") == normalize_course_name("PYTHON程式語言")


def test_information_courses_make_information_the_main_group(app):
    student = make_student(courses=INFO_COURSES + ["會計學", "國文"])

    summary = summarize_student_groups(student)

    assert summary["status"] == "ok"
    assert summary["main_group"] == "資訊"
    assert summary["group_counts"] == {"資訊": 4, "商管": 1}
    assert summary["professional_course_count"] == 5  # 國文是通識，不算專業科目


def test_no_confirmed_courses_needs_check_instead_of_guessing(app):
    student = make_student(courses=INFO_COURSES, status="pending_review")

    summary = summarize_student_groups(student)

    assert summary["status"] == "needs_check"
    assert summary["main_group"] is None
    assert "待確認" in summary["reason"]


def test_too_few_professional_courses_needs_check(app):
    student = make_student(courses=["程式設計", "國文"])

    summary = summarize_student_groups(student)

    assert summary["status"] == "needs_check"
    assert summary["main_group"] is None


def test_needs_check_reason_names_courses_missing_from_curriculum(app):
    student = make_student(courses=["計算機概論"])

    assert "計算機概論" in summarize_student_groups(student)["reason"]


def test_failed_courses_are_not_counted(app):
    student = make_student(courses=["程式設計", "網頁設計"])
    add_courses(student, ["資料結構", "計算機網路"], score=40)

    summary = summarize_student_groups(student)

    assert summary["group_counts"] == {"資訊": 2}
    assert summary["status"] == "needs_check"


def test_tie_between_groups_needs_check(app):
    student = make_student(courses=["程式設計", "網頁設計", "資料結構", "會計學", "經濟學", "行銷管理"])

    summary = summarize_student_groups(student)

    assert summary["status"] == "needs_check"
    assert "一樣多" in summary["reason"]


def test_unknown_and_unclear_course_names_are_listed_for_confirmation(app):
    student = make_student(courses=INFO_COURSES + ["計算機概論", "微積分"])

    summary = summarize_student_groups(student)

    assert summary["unmatched"] == ["計算機概論"]  # 課綱裡沒有，不猜
    assert summary["needs_check_courses"] == ["微積分"]  # 課綱有，但學群待確認
    assert summary["main_group"] == "資訊"


def test_year_without_curriculum_table_needs_check(app):
    student = make_student(admission_year=99, courses=INFO_COURSES)

    summary = summarize_student_groups(student)

    assert summary["status"] == "needs_check"
    assert "99" in summary["reason"]


def program(name, category):
    return AdmissionProgram(program_code="X", admission_year=116, school_name="測試大學",
                            department_name=name, admission_category=category)


def test_accounting_information_department_is_business_not_information():
    groups = department_groups(program("會計資訊系（臺北）", "管理類二"))

    assert groups["groups"] == ["商管"]
    assert "資訊" not in groups["groups"]
    assert groups["basis"]


def test_nursing_digital_learning_department_is_not_information():
    assert "資訊" not in department_groups(program("醫護教育暨數位學習系", "護理類一"))["groups"]
    assert "資訊" not in department_groups(program("醫護教育暨數位學習系", "設計類二"))["groups"]


def test_information_management_department_is_information():
    assert "資訊" in department_groups(program("資訊管理系（臺北）", "管理類四"))["groups"]


def test_department_missing_from_table_is_none():
    assert department_groups(program("太空探索系", "管理類二")) is None
    assert department_groups(program("創意科技與產品設計系（桃園）", "管理類二")) is None  # 表上標待確認
