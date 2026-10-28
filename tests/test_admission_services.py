from datetime import date
import json

import pytest

from app import create_app
from app.extensions import db
from app.models import (
    AdmissionEligibilityRule,
    AdmissionProgram,
    AdmissionRequirementItem,
    AuditLog,
    ClassAdvisor,
    CredentialRecord,
    LearningCourseRecord,
    Portfolio,
    StudentProfile,
    User,
)
from app.services.admission_service import import_seed_programs
from app.services.gap_service import analyze_gap, chapter_order
from app.services.teacher_scope import can_view_student, students_for_teacher


@pytest.fixture()
def app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        yield app


def make_student(username="stu", class_name="資管科三甲"):
    student = User(username=username, display_name=username, role="student")
    student.set_password("pw")
    db.session.add(student)
    db.session.flush()
    db.session.add(StudentProfile(user_id=student.id, student_no=username, class_name=class_name, admission_year=113))
    db.session.flush()
    return student


def make_admin():
    admin = User(username="admin", display_name="管理者", role="admin")
    admin.set_password("pw")
    db.session.add(admin)
    db.session.flush()
    return admin


def make_program(items):
    program = AdmissionProgram(program_code="999001", admission_year=115, school_name="測試大學",
                               department_name="資管系", status="published")
    for order, (name, weight, keys) in enumerate(items):
        program.items.append(AdmissionRequirementItem(
            source_item_name=name, weight_percent=weight, mapped_categories=keys, sort_order=order))
    db.session.add(program)
    db.session.flush()
    return program


def test_seed_import_creates_published_programs_once(app):
    created = import_seed_programs()
    again = import_seed_programs()

    assert created == 4
    assert again == 0
    program = AdmissionProgram.query.filter_by(program_code="208003").one()
    assert program.status == "published"
    assert program.data_origin == "manual"
    assert program.total_weight == 100
    certificate = next(item for item in program.items if item.source_item_name == "證照證明")
    assert certificate.category_keys == ["credential"]
    assert certificate.mapping_status == "confirmed"


def test_admin_can_confirm_a_valid_eligibility_rule_with_source(app):
    admin = make_admin()
    program = make_program([])
    rule = AdmissionEligibilityRule(
        rule_version_id=program.id, rule_group=1, condition_type="unresolved", operator="unresolved",
        value_json=None, description="請核對簡章資格", source_url=program.source_url,
        mapping_status="pending", source_location="待填",
    )
    db.session.add(rule)
    db.session.commit()
    client = app.test_client()
    client.post("/login", data={"username": admin.username, "password": "pw"})

    response = client.post(f"/admin/eligibility-rules/{rule.id}", data={
        "rule_group": "2", "condition_type": "credential", "operator": "has_credential",
        "value_json": json.dumps({"name": "電腦軟體應用", "min_level": "乙級"}, ensure_ascii=False),
        "description": "取得電腦軟體應用乙級以上技術士證", "source_url": "https://example.edu.tw/rules.pdf",
        "source_location": "第 3 頁、報名資格", "mapping_status": "confirmed", "is_required": "on",
    })

    assert response.status_code == 302
    assert rule.mapping_status == "confirmed"
    assert rule.rule_group == 2
    assert rule.condition_type == "credential"
    assert rule.value_json == {"name": "電腦軟體應用", "min_level": "乙級"}
    assert rule.source_url == "https://example.edu.tw/rules.pdf"
    assert AuditLog.query.filter_by(action="admission.eligibility_rule_updated", target_id=rule.id).count() == 1


def test_admin_cannot_confirm_invalid_or_untraceable_eligibility_rule(app):
    admin = make_admin()
    program = make_program([])
    rule = AdmissionEligibilityRule(
        rule_version_id=program.id, rule_group=1, condition_type="unresolved", operator="unresolved",
        value_json=None, description="請核對簡章資格", mapping_status="pending",
    )
    db.session.add(rule)
    db.session.commit()
    client = app.test_client()
    client.post("/login", data={"username": admin.username, "password": "pw"})

    response = client.post(f"/admin/eligibility-rules/{rule.id}", data={
        "rule_group": "1", "condition_type": "credential", "operator": "has_credential",
        "value_json": json.dumps({"name": "電腦軟體應用", "min_level": "未知級別"}, ensure_ascii=False),
        "description": "資格條件", "source_url": "https://example.edu.tw/rules.pdf",
        "source_location": "第 3 頁", "mapping_status": "confirmed",
    })

    assert response.status_code == 400
    assert rule.mapping_status == "pending"


def test_students_cannot_update_eligibility_rules(app):
    student = make_student()
    program = make_program([])
    rule = AdmissionEligibilityRule(
        rule_version_id=program.id, rule_group=1, condition_type="unresolved", operator="unresolved",
        description="資格", mapping_status="pending",
    )
    db.session.add(rule)
    db.session.commit()
    client = app.test_client()
    client.post("/login", data={"username": student.username, "password": "pw"})

    response = client.post(f"/admin/eligibility-rules/{rule.id}", data={"mapping_status": "confirmed"})

    assert response.status_code in (302, 403)
    assert rule.mapping_status == "pending"


def test_admin_programs_page_renders_eligibility_review_form(app):
    admin = make_admin()
    program = make_program([])
    db.session.add(AdmissionEligibilityRule(
        rule_version_id=program.id, rule_group=1, condition_type="unresolved", operator="unresolved",
        description="請管理者核對簡章資格", source_url=program.source_url,
        mapping_status="pending", source_location="第 3 頁",
    ))
    db.session.commit()
    client = app.test_client()
    client.post("/login", data={"username": admin.username, "password": "pw"})

    response = client.get("/admin/programs")

    assert response.status_code == 200
    assert "報名資格條件" in response.get_data(as_text=True)
    assert "請管理者核對簡章資格" in response.get_data(as_text=True)


def test_gap_marks_complete_partial_missing_and_documents(app):
    student = make_student()
    db.session.add(LearningCourseRecord(student_id=student.id, school_year=1, course_name="程式設計",
                                        normalized_course_name="程式設計", score=90))
    db.session.add(CredentialRecord(student_id=student.id, credential_name="丙級", issue_date=date(2025, 3, 1)))
    program = make_program([
        ("歷年成績", 30, "grades"),
        ("專業技能", 50, "credential,competition,autobiography"),
        ("其他", 20, "activity,service,leadership"),
    ])

    gap = analyze_gap(student, program)

    statuses = {item["name"]: item["status"] for item in gap["items"]}
    assert statuses == {"歷年成績": "complete", "專業技能": "partial", "其他": "missing"}
    skill = next(item for item in gap["items"] if item["name"] == "專業技能")
    assert skill["missing"] == ["competition"]
    assert skill["documents"] == ["autobiography"]
    # 30×1 + 50×(1/2) + 20×0 = 55
    assert gap["readiness"] == 55
    assert gap["priority_id"] == skill["id"]


def test_gap_item_with_only_documents_needs_preparation(app):
    student = make_student()
    program = make_program([("自傳", 100, "autobiography")])

    gap = analyze_gap(student, program)

    assert gap["items"][0]["status"] == "prepare"
    assert gap["readiness"] is None


def test_chapter_order_puts_heaviest_items_first_after_fixed_chapters(app):
    program = make_program([
        ("證照證明", 40, "credential"),
        ("學習能力", 30, "grades"),
        ("其他", 10, "activity,service,leadership"),
    ])

    codes = [chapter["code"] for chapter in chapter_order(program)]

    assert codes[:2] == ["01", "02"]
    assert codes[2:4] == ["06", "03"]
    assert sorted(codes) == ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10"]


def test_teacher_only_sees_students_in_assigned_classes(app):
    mine = make_student("mine", "資管科三甲")
    other = make_student("other", "資管科三乙")
    teacher = User(username="t", display_name="t", role="teacher")
    teacher.set_password("pw")
    db.session.add(teacher)
    db.session.flush()
    db.session.add(ClassAdvisor(teacher_id=teacher.id, class_name="資管科三甲", school_year=115))
    db.session.flush()

    assert can_view_student(teacher, mine) is True
    assert can_view_student(teacher, other) is False
    assert [s.username for s in students_for_teacher(teacher)] == ["mine"]

