"""畢業門檻檢核（證照加學分）：只用已確認資料，屆別未核對時標待確認。（僅為測試資料）"""
from datetime import date

import pytest

from app import create_app
from app.extensions import db
from app.models import CredentialRecord, LearningCourseRecord, StudentProfile, User
from app.services import graduation_check_service as svc


@pytest.fixture()
def app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        yield app


def make_student(admission_year=113):
    student = User(username="gstu", display_name="gstu", role="student")
    student.set_password("pw")
    db.session.add(student)
    db.session.flush()
    db.session.add(StudentProfile(user_id=student.id, student_no="gstu", class_name="資管科五甲",
                                  admission_year=admission_year))
    db.session.flush()
    return student


def add_course(student, name, credits, score=80, status="confirmed"):
    db.session.add(LearningCourseRecord(student_id=student.id, course_name=name,
                                        normalized_course_name="".join(name.split()), credits=credits,
                                        score=score, confirmation_status=status))
    db.session.flush()


def add_credential(student, name, level=None, status="confirmed"):
    db.session.add(CredentialRecord(student_id=student.id, credential_name=name, level=level,
                                    issue_date=date(2025, 1, 1), confirmation_status=status))
    db.session.flush()


def test_classify_certificates_by_level_and_name():
    def rec(name, level=None):
        return CredentialRecord(credential_name=name, level=level)

    assert svc.classify_credential(rec("電腦軟體應用 丙級", "丙級")) == "丙級"
    assert svc.classify_credential(rec("會計事務－資訊項", "丙級")) == "丙級"
    assert svc.classify_credential(rec("軟體設計", "乙級")) == "乙級"
    assert svc.classify_credential(rec("中文輸入")) == "輸入"
    assert svc.classify_credential(rec("英文輸入 ")) == "輸入"
    assert svc.classify_credential(rec("普通話證照", None)) is None


def test_only_confirmed_certificates_count_and_inputs_are_capped(app):
    student = make_student()
    add_credential(student, "電腦軟體應用 丙級", "丙級")
    add_credential(student, "軟體設計 乙級", "乙級")
    add_credential(student, "中文輸入")
    add_credential(student, "英文輸入")  # 第二張輸入證照不計
    add_credential(student, "網頁設計 丙級", "丙級", status="draft")  # 草稿不計

    status = svc.certificate_status(student)

    assert status["counted_count"] == 3
    assert status["status"] == "ok"
    assert any("至多採計 1 張" in note for note in status["notes"])


def test_missing_certificates_are_reported(app):
    student = make_student()
    add_credential(student, "電腦軟體應用 丙級", "丙級")

    status = svc.certificate_status(student)

    assert status["status"] == "short"
    assert status["missing"] == 2


def test_credits_count_only_confirmed_passed_courses(app):
    student = make_student(113)
    add_course(student, "國文", 8)
    add_course(student, "國文", 8, score=40)  # 不及格不計（同名只是測試用）
    add_course(student, "會計實務", 3, status="draft")  # 草稿不計

    credits = svc.credit_status(student)

    assert credits["earned"]["required"] == 8
    assert credits["status"] == "short"
    assert credits["gaps"]["required"] == 181 - 8


def test_credits_reach_rule_for_113_cohort(app):
    student = make_student(113)
    add_course(student, "國文", 181)
    add_course(student, "會計實務", 39)

    credits = svc.credit_status(student)

    assert credits["earned"] == {"required": 181, "elective": 39, "total": 220}
    assert credits["status"] == "ok"


def test_unmatched_courses_are_listed_and_need_check(app):
    student = make_student(113)
    add_course(student, "國文", 181)
    add_course(student, "會計實務", 39)
    add_course(student, "跨科選修不存在的課", 2)

    credits = svc.credit_status(student)

    assert credits["status"] == "needs_check"
    assert credits["unmatched"] == ["跨科選修不存在的課"]


def test_cohort_without_verified_table_is_needs_check(app):
    student = make_student(115)

    credits = svc.credit_status(student)

    assert credits["status"] == "needs_check"
    assert "115" in credits["reason"]


def test_evaluate_combines_parts_and_keeps_disclaimer(app):
    student = make_student(113)
    add_credential(student, "電腦軟體應用 丙級", "丙級")

    result = svc.evaluate(student)

    assert result["status"] == "short"
    assert "僅供提醒" in result["note"]
