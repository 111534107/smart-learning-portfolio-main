from datetime import date

import pytest

from app import create_app
from app.extensions import db
from app.models import (
    AdmissionEligibilityRule,
    AdmissionProgram,
    CredentialRecord,
    Portfolio,
    StudentProfile,
    User,
)
from app.services.admission_eligibility_service import evaluate_program, validate_eligibility_condition


@pytest.fixture()
def app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        yield app


def make_student(username="stu", with_profile=True):
    student = User(username=username, display_name=username, role="student")
    student.set_password("pw")
    db.session.add(student)
    db.session.flush()
    if with_profile:
        db.session.add(StudentProfile(
            user_id=student.id, student_no=username, class_name="資管科三甲", admission_year=113,
        ))
        db.session.flush()
    return student


def make_program(rules, code="999001"):
    program = AdmissionProgram(
        program_code=code, admission_year=116, school_name="測試科技大學",
        department_name="資訊管理系", admission_category="技優甄審", status="published",
        source_url="https://example.edu.tw/admission/116.pdf",
    )
    for order, rule in enumerate(rules):
        program.eligibility_rules.append(AdmissionEligibilityRule(
            rule_group=rule.get("group", 1),
            condition_type=rule.get("type", "student_status"),
            operator=rule.get("operator", "in"),
            value_json=rule.get("value"),
            description=rule.get("description", "招生資格條件"),
            source_url=rule.get("source_url", program.source_url),
            source_location=rule.get("location", "簡章第 3 頁"),
            mapping_status=rule.get("mapping_status", "confirmed"),
            is_required=rule.get("required", True),
            sort_order=order,
        ))
    db.session.add(program)
    db.session.flush()
    return program


def test_evaluate_program_matches_confirmed_certificate_and_returns_source(app):
    student = make_student()
    db.session.add(CredentialRecord(
        student_id=student.id, credential_name="電腦軟體應用", level="乙級",
        issuing_organization="勞動部", issue_date=date(2025, 5, 1),
        confirmation_status="confirmed",
    ))
    program = make_program([{
        "type": "credential", "operator": "has_credential",
        "value": {"name": "電腦軟體應用", "min_level": "乙級", "issuer": "勞動部"},
    }])

    result = evaluate_program(student, program)

    assert result["status"] == "eligible"
    assert result["conditions"][0]["status"] == "matched"
    assert result["sources"] == [{
        "url": "https://example.edu.tw/admission/116.pdf", "location": "簡章第 3 頁",
    }]


def test_evaluate_program_pending_rule_needs_review(app):
    student = make_student()
    program = make_program([{
        "value": {"field": "class_name", "values": ["資管科三甲"]},
        "mapping_status": "pending",
    }])

    result = evaluate_program(student, program)

    assert result["status"] == "needs_review"
    assert result["conditions"][0]["status"] == "needs_review"


def test_evaluate_program_missing_profile_data_is_insufficient(app):
    student = make_student(with_profile=False)
    program = make_program([{
        "value": {"field": "class_name", "values": ["資管科三甲"]},
    }])

    result = evaluate_program(student, program)

    assert result["status"] == "insufficient_data"
    assert result["conditions"][0]["status"] == "insufficient_data"


def test_evaluate_program_allows_alternative_eligibility_groups(app):
    student = make_student()
    db.session.add(CredentialRecord(
        student_id=student.id, credential_name="網頁設計", level="丙級", confirmation_status="confirmed",
    ))
    program = make_program([
        {"group": 1, "type": "credential", "operator": "has_credential",
         "value": {"name": "電腦軟體應用", "min_level": "乙級"}},
        {"group": 2, "value": {"field": "class_name", "values": ["資管科三甲"]}},
    ])

    result = evaluate_program(student, program)

    assert result["status"] == "eligible"
    assert result["matched_groups"] == [2]


def test_evaluate_program_requires_all_rules_in_the_same_group(app):
    student = make_student()
    db.session.add(CredentialRecord(
        student_id=student.id, credential_name="電腦軟體應用", level="乙級", confirmation_status="confirmed",
    ))
    program = make_program([
        {"group": 1, "type": "credential", "operator": "has_credential",
         "value": {"name": "電腦軟體應用", "min_level": "乙級"}},
        {"group": 1, "value": {"field": "class_name", "values": ["非資管科"]}},
    ])

    result = evaluate_program(student, program)

    assert result["status"] == "not_eligible"
    assert result["conditions"][1]["status"] == "not_matched"


def test_evaluate_program_ignores_unconfirmed_credentials(app):
    student = make_student()
    db.session.add(CredentialRecord(
        student_id=student.id, credential_name="電腦軟體應用", level="乙級", confirmation_status="pending",
    ))
    program = make_program([{
        "type": "credential", "operator": "has_credential",
        "value": {"name": "電腦軟體應用", "min_level": "乙級"},
    }])

    result = evaluate_program(student, program)

    assert result["status"] == "insufficient_data"
    assert result["conditions"][0]["status"] == "insufficient_data"


def test_evaluate_program_only_uses_confirmed_competitions_of_that_student(app):
    student = make_student()
    other = make_student("other")
    db.session.add_all([
        Portfolio(student_id=student.id, title="未確認競賽", category="competition", status="draft"),
        Portfolio(student_id=other.id, title="已確認競賽", category="competition", status="confirmed"),
    ])
    program = make_program([{
        "type": "competition", "operator": "has_competition",
        "value": {"category": "competition"},
    }])

    result = evaluate_program(student, program)

    assert result["status"] == "insufficient_data"
    assert result["conditions"][0]["status"] == "insufficient_data"


def test_evaluate_program_with_no_rules_needs_review(app):
    student = make_student()
    program = make_program([])

    result = evaluate_program(student, program)

    assert result["status"] == "needs_review"
    assert result["conditions"] == []


def test_evaluate_program_does_not_guess_unknown_certificate_level(app):
    student = make_student()
    db.session.add(CredentialRecord(
        student_id=student.id, credential_name="資訊類證照", level="初階", confirmation_status="confirmed",
    ))
    program = make_program([{
        "type": "credential", "operator": "has_credential",
        "value": {"min_level": "乙級"},
    }])

    result = evaluate_program(student, program)

    assert result["status"] == "needs_review"
    assert result["conditions"][0]["status"] == "needs_review"


def test_evaluate_program_reports_missing_certificate_date_as_insufficient(app):
    student = make_student()
    db.session.add(CredentialRecord(
        student_id=student.id, credential_name="電腦軟體應用", level="乙級",
        confirmation_status="confirmed",
    ))
    program = make_program([{
        "type": "credential", "operator": "has_credential",
        "value": {"name": "電腦軟體應用", "min_level": "乙級", "issue_date_from": "2025-01-01"},
    }])

    result = evaluate_program(student, program)

    assert result["status"] == "insufficient_data"
    assert result["conditions"][0]["status"] == "insufficient_data"


def test_evaluate_program_requires_source_location_to_mark_rule_matched(app):
    student = make_student()
    program = make_program([{
        "value": {"field": "class_name", "values": ["資管科三甲"]}, "location": None,
    }])

    result = evaluate_program(student, program)

    assert result["status"] == "needs_review"
    assert result["conditions"][0]["status"] == "needs_review"


def test_evaluate_program_does_not_infer_competition_rank_from_text(app):
    student = make_student()
    db.session.add(Portfolio(
        student_id=student.id, title="全國競賽第一名", description="第一名", category="competition",
        status="confirmed",
    ))
    program = make_program([{
        "type": "competition", "operator": "has_competition",
        "value": {"category": "competition", "min_rank": 1},
    }])

    result = evaluate_program(student, program)

    assert result["status"] == "needs_review"
    assert result["conditions"][0]["status"] == "needs_review"


@pytest.mark.parametrize(("condition_type", "operator", "value"), [
    ("student_status", "in", {"field": [], "values": ["資管科三甲"]}),
    ("credential", "has_credential", {"min_level": []}),
    ("credential", "has_credential", {"issue_date_from": []}),
])
def test_validate_eligibility_condition_rejects_malformed_json_types(condition_type, operator, value):
    assert validate_eligibility_condition(condition_type, operator, value) is not None
