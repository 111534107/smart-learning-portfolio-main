"""DEMO-03 活動適合學校：每一筆活動與經歷，列出哪些校系的甄審項目會用到它的類別。"""
import pytest

from app import create_app
from app.extensions import db
from app.models import (AdmissionProgram, AdmissionRequirementItem, Portfolio, StudentProfile, StudentTarget,
                        User)
from app.services.activity_fit import build_activity_fit


@pytest.fixture()
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        yield app


def make_student():
    student = User(username="stu", display_name="stu", role="student")
    student.set_password("pw")
    db.session.add(student)
    db.session.flush()
    db.session.add(StudentProfile(user_id=student.id, student_no="111534199", class_name="資管科五甲",
                                  admission_year=111))
    db.session.flush()
    return student


def make_program(code, school, items, department="資管系"):
    program = AdmissionProgram(program_code=code, admission_year=116, school_name=school,
                               department_name=department, status="published")
    for order, (name, weight, keys) in enumerate(items):
        program.items.append(AdmissionRequirementItem(
            source_item_name=name, weight_percent=weight, mapped_categories=keys, sort_order=order,
            mapping_status="confirmed"))
    db.session.add(program)
    db.session.flush()
    return program


def add_record(student, title, category):
    record = Portfolio(student_id=student.id, title=title, category=category, status="confirmed")
    db.session.add(record)
    db.session.flush()
    return record


def names(entries):
    return [entry["program"].school_name for entry in entries]


def test_with_targets_only_target_programs_are_used(app):
    student = make_student()
    target = make_program("900001", "目標科大", [("歷年成績", 80, "grades"), ("其他", 20, "activity,service")])
    make_program("900002", "別的科大", [("社團活動", 60, "activity")])
    db.session.add(StudentTarget(student_id=student.id, rule_version_id=target.id))
    record = add_record(student, "資訊週志工", "activity")

    fit = build_activity_fit(student, [record])

    assert fit["scope"] == "target"
    entries = fit["by_record"][record.id]
    assert names(entries) == ["目標科大"]
    assert entries[0]["item"] == "其他"
    assert entries[0]["weight"] == 20


def test_without_targets_uses_top_recommended_programs_sorted_by_weight(app):
    student = make_student()
    for index, weight in enumerate([10, 40, 25, 30, 5]):
        make_program(f"90000{index}", f"推薦{index}科大", [("活動表現", weight, "activity"),
                                                          ("歷年成績", 100 - weight, "grades")])
    record = add_record(student, "系學會", "activity")

    fit = build_activity_fit(student, [record])

    assert fit["scope"] == "recommended"
    entries = fit["by_record"][record.id]
    # 每筆最多 3 間，依占比由高到低
    assert [entry["weight"] for entry in entries] == [40, 30, 25]
    assert names(entries) == ["推薦1科大", "推薦3科大", "推薦2科大"]


def test_without_targets_considers_at_most_ten_programs(app):
    student = make_student()
    for index in range(12):
        make_program(f"9100{index:02d}", f"校{index:02d}", [("活動", 10, "activity"), ("成績", 90, "grades")])

    fit = build_activity_fit(student, [])

    assert len(fit["programs"]) == 10


def test_category_not_used_by_any_program_returns_empty_list(app):
    student = make_student()
    target = make_program("900001", "目標科大", [("歷年成績", 100, "grades")])
    db.session.add(StudentTarget(student_id=student.id, rule_version_id=target.id))
    record = add_record(student, "全國技能競賽", "competition")

    fit = build_activity_fit(student, [record])

    assert fit["by_record"][record.id] == []
    assert fit["empty_note"] == "目前目標校系的甄審沒有列這一類"


def test_summary_lists_programs_that_help_most_records(app):
    student = make_student()
    wide = make_program("900001", "廣用科大", [("多元表現", 30, "activity,service,leadership")])
    narrow = make_program("900002", "單項科大", [("服務", 50, "service")])
    for program in (wide, narrow):
        db.session.add(StudentTarget(student_id=student.id, rule_version_id=program.id))
    records = [add_record(student, "社團", "activity"), add_record(student, "淨灘", "service"),
               add_record(student, "班長", "leadership")]

    fit = build_activity_fit(student, records)

    assert fit["record_count"] == 3
    assert [entry["program"].school_name for entry in fit["summary"]] == ["廣用科大", "單項科大"]
    assert fit["summary"][0]["count"] == 3
    assert fit["summary_schools"] == ["廣用科大", "單項科大"]


def login(client):
    client.post("/login", data={"username": "stu", "password": "pw"})


def test_portfolio_page_shows_program_names_and_weights(app):
    student = make_student()
    target = make_program("900001", "目標科大", [("其他", 20, "activity")], department="資訊管理系")
    db.session.add(StudentTarget(student_id=student.id, rule_version_id=target.id))
    add_record(student, "資訊週志工", "activity")
    add_record(student, "全國技能競賽", "competition")
    db.session.commit()

    client = app.test_client()
    login(client)
    html = client.get("/student/portfolio").get_data(as_text=True)

    assert "對這些學校的甄審有幫助" in html
    assert "目標科大" in html and "資訊管理系" in html
    assert "可放進「其他」（這個項目占 20%）" in html
    assert "最能用在" in html
    assert "目前目標校系的甄審沒有列這一類" in html
