"""學生可以把成績、證照、經歷標成「不放進備審」；簡章規定必備的不能排除（導師 2026-11-12）。

以下姓名、學號、校系、成績皆僅為測試資料。
"""
from datetime import date
import io
from pathlib import Path

import pytest
from docx import Document

from app import create_app
from app.extensions import db
from app.models import (AdmissionProgram, AdmissionRequirementItem, CredentialRecord, LearningCourseRecord,
                        Portfolio, StudentProfile, StudentTarget, User)
from app.services import package_exclusion
from app.services.autobiography_service import build_facts, custom_contents, strength_inventory
from app.services.gap_service import analyze_gap
from app.services.journey_service import academic_year_of
from app.services.package_service import build_package_docx


def _program(code, items):
    program = AdmissionProgram(program_code=code, admission_year=116, school_name=f"測試科大{code}",
                               department_name="資訊管理系", status="published")
    for order, (name, weight, keys, requirement) in enumerate(items):
        program.items.append(AdmissionRequirementItem(
            source_item_name=name, weight_percent=weight, mapped_categories=keys,
            mapping_status="confirmed", requirement=requirement, sort_order=order))
    db.session.add(program)
    return program


@pytest.fixture()
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        for username in ("stu", "other"):
            user = User(username=username, display_name=f"測試生{username}", role="student")
            user.set_password("pw")
            db.session.add(user)
        db.session.flush()
        stu = User.query.filter_by(username="stu").one()
        other = User.query.filter_by(username="other").one()
        db.session.add(StudentProfile(user_id=stu.id, student_no="T-0000001", class_name="資管科五甲",
                                      admission_year=academic_year_of(date.today()) - 4))
        # A：簡章把成績列為評分項目 → 歷年成績單必備
        _program("A", [("歷年成績單", 30, "grades", None), ("證照", 30, "credential", None),
                       ("競賽成果", 40, "competition", None)])
        # B：沒有成績項目 → 成績可以不放
        _program("B", [("證照", 50, "credential", None), ("競賽成果", 50, "competition", None)])
        # C：簡章寫明證照必繳
        _program("C", [("專業證照", 60, "credential", "必繳：至少一張資訊類證照影本"), ("競賽成果", 40, "competition", None)])
        db.session.add_all([
            LearningCourseRecord(student_id=stu.id, course_name="不想放的會計學", normalized_course_name="不想放的會計學",
                                 score=55, confirmation_status="confirmed", excluded_from_package=True),
            LearningCourseRecord(student_id=stu.id, course_name="資料庫管理", normalized_course_name="資料庫管理",
                                 score=90, confirmation_status="confirmed"),
            CredentialRecord(student_id=stu.id, credential_name="不想放的丙級證照", confirmation_status="confirmed",
                             excluded_from_package=True),
            CredentialRecord(student_id=stu.id, credential_name="乙級軟體應用", confirmation_status="confirmed"),
            Portfolio(student_id=stu.id, title="不想放的校內比賽", category="competition", status="confirmed",
                      excluded_from_package=True),
            Portfolio(student_id=stu.id, title="校園黑客松", category="competition", status="confirmed"),
            CredentialRecord(student_id=other.id, credential_name="別人的證照", confirmation_status="confirmed"),
        ])
        db.session.commit()
    yield app


def _stu():
    return User.query.filter_by(username="stu").one()


def _prog(code):
    return AdmissionProgram.query.filter_by(program_code=code).one()


def _target(*codes):
    for code in codes:
        db.session.add(StudentTarget(student_id=_stu().id, rule_version_id=_prog(code).id))
    db.session.commit()


def login(app, username="stu"):
    client = app.test_client()
    client.post("/login", data={"username": username, "password": "pw"})
    return client


def _docx_text(stream):
    document = Document(io.BytesIO(stream.read()))
    cells = [cell.text for table in document.tables for row in table.rows for cell in row.cells]
    return "\n".join([p.text for p in document.paragraphs] + cells)


def test_required_keys_come_from_the_program_rules(app):
    with app.app_context():
        assert package_exclusion.required_keys(_prog("A")) == {"grades"}
        assert package_exclusion.required_keys(_prog("B")) == set()
        assert package_exclusion.required_keys(_prog("C")) == {"credential"}


def test_excluded_records_stay_out_of_autobiography_facts(app):
    with app.app_context():
        text = "\n".join(fact["text"] for fact in build_facts(_stu(), _prog("B"))["items"])

    assert "不想放的會計學" not in text
    assert "不想放的丙級證照" not in text
    assert "不想放的校內比賽" not in text
    assert "資料庫管理" in text and "乙級軟體應用" in text and "校園黑客松" in text


def test_required_category_ignores_exclusion_for_that_program(app):
    with app.app_context():
        grades_required = "\n".join(fact["text"] for fact in build_facts(_stu(), _prog("A"))["items"])
        credential_required = "\n".join(fact["text"] for fact in build_facts(_stu(), _prog("C"))["items"])

    assert "不想放的會計學" in grades_required  # 歷年成績單必備
    assert "不想放的丙級證照" not in grades_required
    assert "不想放的丙級證照" in credential_required  # 簡章寫明必繳
    assert "不想放的會計學" not in credential_required


def test_excluded_records_stay_out_of_package_word(app):
    with app.app_context():
        optional = _docx_text(build_package_docx(_stu(), _prog("B")))
        required = _docx_text(build_package_docx(_stu(), _prog("A")))

    assert "不想放的丙級證照" not in optional
    assert "不想放的校內比賽" not in optional
    assert "乙級軟體應用" in optional and "校園黑客松" in optional
    assert "不想放的會計學" in required  # A 校系成績必備，成績表完整
    assert "不想放的丙級證照" not in required


def test_excluded_records_stay_out_of_evidence_lists_and_readiness(app):
    with app.app_context():
        chapters = custom_contents(_stu(), _prog("B"))
        names = [item["name"] for chapter in chapters for item in chapter["evidence"]]
        inventory = [item["name"] for group in strength_inventory(_stu(), _prog("B")) for item in group["evidence"]]
        gap = analyze_gap(_stu(), _prog("B"))
        gap_required = analyze_gap(_stu(), _prog("C"))

    assert "不想放的丙級證照" not in names and "乙級軟體應用" in names
    assert "不想放的校內比賽" not in names and "不想放的校內比賽" not in inventory
    assert "不想放的會計學" not in inventory
    by_name = {item["name"]: item for item in gap["items"]}
    assert by_name["證照"]["counts"]["credential"] == 1  # 兩張只算沒排除的一張
    assert by_name["證照"]["percent"] == 50
    assert gap["readiness"] == 50
    assert {item["name"]: item for item in gap_required["items"]}["專業證照"]["counts"]["credential"] == 2


def test_student_marks_and_restores_a_record(app):
    client = login(app)
    with app.app_context():
        _target("B")
        credential_id = CredentialRecord.query.filter_by(credential_name="乙級軟體應用").one().id

    response = client.post("/student/package-exclusions",
                           data={"kind": "credential", "record_id": credential_id, "excluded": "1"})
    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(CredentialRecord, credential_id).excluded_from_package is True

    client.post("/student/package-exclusions", data={"kind": "credential", "record_id": credential_id, "excluded": "0"})
    with app.app_context():
        assert db.session.get(CredentialRecord, credential_id).excluded_from_package is False


def test_student_cannot_touch_other_students_record(app):
    client = login(app)
    with app.app_context():
        other_id = CredentialRecord.query.filter_by(credential_name="別人的證照").one().id

    response = client.post("/student/package-exclusions",
                           data={"kind": "credential", "record_id": other_id, "excluded": "1"})

    assert response.status_code == 404
    with app.app_context():
        assert db.session.get(CredentialRecord, other_id).excluded_from_package is False


def test_required_record_cannot_be_excluded_and_page_explains_why(app):
    client = login(app)
    with app.app_context():
        _target("A")
        course_id = LearningCourseRecord.query.filter_by(course_name="資料庫管理").one().id

    response = client.post("/student/package-exclusions",
                           data={"kind": "course", "record_id": course_id, "excluded": "1"})
    page = client.get("/student/package-exclusions").get_data(as_text=True)

    assert response.status_code == 400
    assert "簡章規定必備" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(LearningCourseRecord, course_id).excluded_from_package is False
    assert "簡章規定必備" in page and "測試科大A" in page
    assert "乙級軟體應用" in page and "校園黑客松" in page


def test_exclusion_table_turns_into_cards_on_phone(app):
    """11-12 驗收：手機寬 375px 時表格把頁面撐到 679px；改用學生端卡片表格，長句可換行。"""
    client = login(app)
    with app.app_context():
        _target("A")
    page = client.get("/student/package-exclusions").get_data(as_text=True)
    assert 'class="data-table sv2-table" data-exclusion-table' in page
    css = (Path(app.root_path) / "static" / "css" / "student-v2" / "ocr.css").read_text(encoding="utf-8")
    assert ".table-wrap .sv2-table td { min-width: 0; word-break: normal; overflow-wrap: anywhere; }" in css


def test_partly_required_record_can_be_excluded_with_a_note(app):
    client = login(app)
    with app.app_context():
        _target("A", "B")
        course_id = LearningCourseRecord.query.filter_by(course_name="資料庫管理").one().id

    response = client.post("/student/package-exclusions",
                           data={"kind": "course", "record_id": course_id, "excluded": "1"})
    page = client.get("/student/package-exclusions").get_data(as_text=True)

    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(LearningCourseRecord, course_id).excluded_from_package is True
    assert "測試科大A" in page and "仍會放進" in page


def test_gap_page_links_to_the_exclusion_page(app):
    client = login(app)
    with app.app_context():
        _target("B")
        program_id = _prog("B").id

    page = client.get(f"/student/targets/{program_id}").get_data(as_text=True)

    assert "/student/package-exclusions" in page
