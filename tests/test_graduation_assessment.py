"""畢業門檻判斷（階段、資料是否足夠、5.2 規則）。（僅為測試資料）"""
from datetime import date

import pytest

from app import create_app
from app.extensions import db
from app.models import (CredentialRecord, LearningCourseRecord, SourceDocument, StudentProfile,
                        SystemSetting, TransferCreditRecord, User)
from app.services import graduation_check_service as svc

CREDIT_ITEMS = ("required_credits", "elective_credits", "total_credits")


@pytest.fixture()
def app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        yield app


def make_student(admission_year=111, with_profile=True):
    student = User(username="gastu", display_name="gastu", role="student")
    student.set_password("pw")
    db.session.add(student)
    db.session.flush()
    if with_profile:
        db.session.add(StudentProfile(user_id=student.id, student_no="gastu", class_name="資管科五甲",
                                      admission_year=admission_year))
        db.session.flush()
    return student


def add_course(student, name, credits, score=80, status="confirmed", school_year=None, semester=None):
    db.session.add(LearningCourseRecord(student_id=student.id, course_name=name,
                                        normalized_course_name="".join(name.split()), credits=credits,
                                        score=score, confirmation_status=status,
                                        school_year=school_year, semester=semester))
    db.session.flush()


def add_credential(student, name, level=None, status="confirmed"):
    db.session.add(CredentialRecord(student_id=student.id, credential_name=name, level=level,
                                    issue_date=date(2025, 1, 1), confirmation_status=status))
    db.session.flush()


def fill_ended_terms(student, admission_year, today, use_grade=False):
    """每個已結束學期放一筆 0 學分的已確認課程，讓「該學期有資料」成立。"""
    for year, semester in svc.student_stage(admission_year, today)["ended_terms"]:
        add_course(student, "會計實務", 0, school_year=(year - admission_year + 1) if use_grade else year,
                   semester=semester)


def test_academic_term_boundaries():
    assert svc.academic_term(date(2026, 8, 1)) == (115, "上")
    assert svc.academic_term(date(2027, 1, 31)) == (115, "上")
    assert svc.academic_term(date(2027, 2, 1)) == (115, "下")


def test_stage_formal_from_grade4_second_term():
    assert svc.student_stage(111, date(2026, 3, 1))["formal"] is True    # 114 下＝專四下
    assert svc.student_stage(111, date(2025, 10, 1))["formal"] is False  # 114 上＝專四上
    stage = svc.student_stage(111, date(2026, 10, 1))                     # 115 上＝專五上
    assert stage["grade"] == 5 and stage["remaining_terms"] == 2


def test_grade1_short_of_220_is_progress_not_gap(app):
    student = make_student(113)
    result = svc.assess(student, today=date(2024, 10, 1))
    assert result["stage"]["grade"] == 1
    assert {name: item["result"] for name, item in result["items"].items()} == {
        "certificates": "progress", "required_credits": "progress",
        "elective_credits": "progress", "total_credits": "progress"}


def test_grade4_first_term_without_certificates_is_progress(app):
    student = make_student(111)
    result = svc.assess(student, today=date(2025, 10, 1))
    assert result["items"]["certificates"]["result"] == "progress"


def test_grade4_second_term_one_certificate_is_gap(app):
    student = make_student(111)
    add_credential(student, "電腦軟體應用 丙級", "丙級")
    item = svc.assess(student, today=date(2026, 3, 1))["items"]["certificates"]
    assert item["result"] == "gap" and item["amount"] == 2
    assert item["unit"] == "張"


def test_three_certificates_is_met(app):
    student = make_student(111)
    for name in ("電腦軟體應用 丙級", "網頁設計 丙級", "軟體設計 乙級"):
        add_credential(student, name, name[-2:])
    assert svc.assess(student, today=date(2026, 3, 1))["items"]["certificates"]["result"] == "met"


def test_no_transcript_is_insufficient_data(app):
    student = make_student(111)
    result = svc.assess(student, today=date(2026, 3, 1))
    for name in CREDIT_ITEMS:
        assert result["items"][name]["result"] == "insufficient_data"
    assert result["items"]["required_credits"]["missing_terms"][0] == (111, "上")


def test_transfer_pending_marks_credits(app):
    student = make_student(111)
    fill_ended_terms(student, 111, date(2026, 3, 1))
    db.session.add(TransferCreditRecord(student_id=student.id, status="submitted"))
    db.session.flush()
    result = svc.assess(student, today=date(2026, 3, 1))
    for name in CREDIT_ITEMS:
        assert result["items"][name]["result"] == "transfer_pending"


def test_completed_transfer_does_not_block(app):
    student = make_student(111)
    fill_ended_terms(student, 111, date(2026, 3, 1))
    db.session.add(TransferCreditRecord(student_id=student.id, status="completed"))
    db.session.flush()
    result = svc.assess(student, today=date(2026, 3, 1))
    assert result["items"]["total_credits"]["result"] == "gap"  # 差 220 > 3×28


def test_failed_required_without_retake_is_gap(app):
    student = make_student(111)
    today = date(2026, 3, 1)
    fill_ended_terms(student, 111, today)
    add_course(student, "國文", 2, score=40, school_year=111, semester="上")
    add_course(student, "英文", 150, school_year=111, semester="下")  # 差 31 學分，在 3×28 之內
    item = svc.assess(student, today=today)["items"]["required_credits"]
    assert item["result"] == "gap"
    assert item["failed_required"] == ["國文"]


def test_failed_required_then_passed_is_not_gap(app):
    student = make_student(111)
    today = date(2026, 3, 1)
    fill_ended_terms(student, 111, today)
    add_course(student, "國文", 2, score=40, school_year=111, semester="上")
    add_course(student, "國文", 150, score=80, school_year=112, semester="上")
    item = svc.assess(student, today=today)["items"]["required_credits"]
    assert item["result"] == "progress"
    assert item["failed_required"] == []


def test_credit_gap_beyond_remaining_capacity_is_gap(app):
    student = make_student(111)
    today = date(2027, 3, 1)  # 專五下，剩 1 學期
    assert svc.student_stage(111, today)["remaining_terms"] == 1
    fill_ended_terms(student, 111, today)
    add_course(student, "國文", 151, school_year=111, semester="上")  # 必修差 30 > 28
    item = svc.assess(student, today=today)["items"]["required_credits"]
    assert item["result"] == "gap" and item["amount"] == 30


def test_credit_gap_within_capacity_is_progress(app):
    student = make_student(111)
    today = date(2026, 10, 1)  # 專五上，剩 2 學期
    fill_ended_terms(student, 111, today)
    add_course(student, "國文", 131, school_year=111, semester="上")  # 必修差 50 <= 56
    item = svc.assess(student, today=today)["items"]["required_credits"]
    assert item["result"] == "progress" and item["amount"] == 50


def test_unconfirmed_credential_document_is_insufficient(app):
    student = make_student(111)
    db.session.add(SourceDocument(owner_id=student.id, document_type="credential", display_name="證照.jpg",
                                  file_path="x", sha256="0" * 64, status="uploaded"))
    db.session.flush()
    item = svc.assess(student, today=date(2026, 3, 1))["items"]["certificates"]
    assert item["result"] == "insufficient_data"


def test_failed_credential_document_does_not_block(app):
    student = make_student(111)
    for name in ("電腦軟體應用 丙級", "網頁設計 丙級", "軟體設計 乙級"):
        add_credential(student, name, name[-2:])
    db.session.add(SourceDocument(owner_id=student.id, document_type="credential", display_name="壞檔.jpg",
                                  file_path="x", sha256="1" * 64, status="analysis_failed"))
    db.session.flush()
    item = svc.assess(student, today=date(2026, 3, 1))["items"]["certificates"]
    assert item["result"] == "met"


def test_pending_credential_document_states_are_insufficient(app):
    student = make_student(111)
    for index, status in enumerate(("queued", "processing", "extracted")):
        db.session.add(SourceDocument(owner_id=student.id, document_type="credential",
                                      display_name=f"{status}.jpg", file_path="x",
                                      sha256=str(index) * 64, status=status))
        db.session.flush()
        item = svc.assess(student, today=date(2026, 3, 1))["items"]["certificates"]
        assert item["result"] == "insufficient_data", status
        SourceDocument.query.filter_by(status=status).one().status = "confirmed"
        db.session.flush()


def test_unmatched_course_names_make_credits_rule_unverified(app):
    student = make_student(111)
    today = date(2027, 3, 1)  # 專五下，剩 1 學期：不比對的話必修會被算成缺口
    fill_ended_terms(student, 111, today)
    add_course(student, "火星探索實務", 3, school_year=111, semester="上")
    result = svc.assess(student, today=today)
    for name in CREDIT_ITEMS:
        assert result["items"][name]["result"] == "rule_unverified"
        assert "火星探索實務" in result["items"][name]["detail"]


def test_ended_term_matches_grade_number_school_year(app):
    student = make_student(111)
    today = date(2026, 3, 1)
    fill_ended_terms(student, 111, today, use_grade=True)  # school_year 記成年級 1~4
    item = svc.assess(student, today=today)["items"]["total_credits"]
    assert item["result"] != "insufficient_data"
    assert item["missing_terms"] == []


def test_missing_profile_is_rule_unverified(app):
    student = make_student(with_profile=False)
    result = svc.assess(student, today=date(2026, 3, 1))
    for name in CREDIT_ITEMS:
        assert result["items"][name]["result"] == "rule_unverified"


def test_unverified_cohort_is_rule_unverified(app):
    student = make_student(115)
    result = svc.assess(student, today=date(2026, 10, 1))
    assert result["items"]["total_credits"]["result"] == "rule_unverified"


def test_check_today_uses_setting_override(app):
    assert svc.check_today() == date.today()
    db.session.add(SystemSetting(key=svc.TODAY_SETTING_KEY, value="2027-03-01"))
    db.session.flush()
    assert svc.check_today() == date(2027, 3, 1)


def test_course_missing_from_every_curriculum_asks_advisor_and_staff(app):
    """11-09 使用者決定：任何一年的科目表都沒有的課，提醒「請詢問班導與科辦」，不推算替代課程。"""
    student = make_student(111)
    today = date(2027, 3, 1)
    fill_ended_terms(student, 111, today)
    add_course(student, "火星探索實務", 3, school_year=111, semester="上")
    add_course(student, "UI/UX設計基礎與應用", 3, school_year=111, semester="上")  # 只有 113 學年度入學的科目表有
    detail = svc.assess(student, today=today)["items"]["required_credits"]["detail"]
    assert "這門課在系統中找不到對應科目，請詢問班導與科辦：火星探索實務" in detail
    assert "其他入學年度的修業科目表，請科辦確認：UI/UX設計基礎與應用" in detail
    assert "替代" not in detail


def test_unknown_course_is_recorded_once(app):
    from app.models import AuditLog
    from app.services import graduation_case_service
    student = make_student(111)
    today = date(2027, 3, 1)
    fill_ended_terms(student, 111, today)
    add_course(student, "火星探索實務", 3, school_year=111, semester="上")
    graduation_case_service.sync_student(student, today=today)
    graduation_case_service.sync_student(student, today=today)  # 同一批課名不重複記
    rows = AuditLog.query.filter_by(action="graduation.course_unknown").all()
    assert len(rows) == 1 and rows[0].target_id == student.id
    assert rows[0].detail_json == {"courses": ["火星探索實務"]}
