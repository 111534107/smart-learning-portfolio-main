"""自傳引導題目依目標校系簡章的評分比重排列；學生要先用自己的話寫，AI 只整理（導師 2026-11-12）。

以下姓名、學號、校系、比重皆僅為測試資料。
"""
from datetime import date

import pytest

from app import create_app
from app.extensions import db
from app.models import (AdmissionProgram, AdmissionRequirementItem, LearningProfileOutput, StudentProfile,
                        StudentTarget, User)
from app.services import autobiography_service
from app.services.journey_service import academic_year_of
from tests.board_helpers import fill_board

BASE_KEYS = [key for key, _, _ in autobiography_service.QUESTIONS]


@pytest.fixture()
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        user = User(username="stu", display_name="測試生", role="student")
        user.set_password("pw")
        db.session.add(user)
        db.session.flush()
        db.session.add(StudentProfile(user_id=user.id, student_no="T-0000002", class_name="資管科五甲",
                                      admission_year=academic_year_of(date.today()) - 4))
        weighted = AdmissionProgram(program_code="W", admission_year=116, school_name="測試科大W",
                                    department_name="資訊管理系", status="published")
        for order, (name, weight, keys) in enumerate([
                ("證照", 20, "credential"), ("專題製作", 50, "project"), ("競賽成果", 30, "competition"),
                ("自傳", 0, "autobiography")]):
            weighted.items.append(AdmissionRequirementItem(source_item_name=name, weight_percent=weight,
                                                           mapped_categories=keys, mapping_status="confirmed",
                                                           sort_order=order))
        plain = AdmissionProgram(program_code="P", admission_year=116, school_name="測試科大P",
                                 department_name="資訊管理系", status="published")
        db.session.add_all([weighted, plain])
        db.session.flush()
        for program in (weighted, plain):
            db.session.add(StudentTarget(student_id=user.id, rule_version_id=program.id))
        db.session.commit()
        fill_board(user)
    yield app


def _prog(code):
    return AdmissionProgram.query.filter_by(program_code=code).one()


def _pid(app, code):
    with app.app_context():
        return _prog(code).id


def login(app):
    client = app.test_client()
    client.post("/login", data={"username": "stu", "password": "pw"})
    return client


def _drafts(app):
    with app.app_context():
        return LearningProfileOutput.query.filter_by(output_type=autobiography_service.OUTPUT_TYPE).count()


def test_questions_are_ordered_by_weight_and_flag_what_the_program_values(app):
    with app.app_context():
        questions = autobiography_service.guided_questions(_prog("W"))

    keys = [q["key"] for q in questions]
    assert keys == ["focus_project", "focus_competition", "focus_credential", *BASE_KEYS]
    assert [q["weight"] for q in questions[:3]] == [50, 30, 20]
    assert [q["important"] for q in questions[:3]] == [True, True, False]
    assert "專題製作" in questions[0]["text"]
    assert all(q["weight"] is None and not q["important"] for q in questions[3:])


def test_program_without_weights_keeps_current_questions(app):
    with app.app_context():
        questions = autobiography_service.guided_questions(_prog("P"))

    assert [q["key"] for q in questions] == BASE_KEYS
    assert [q["text"] for q in questions] == [text for _, text, _ in autobiography_service.QUESTIONS]
    assert not any(q["important"] for q in questions)


def test_page_shows_weighted_questions_first_with_label(app):
    page = login(app).get(f"/student/autobiography?program_id={_pid(app, 'W')}").get_data(as_text=True)

    assert page.count("這所校系很看重") >= 2
    assert page.index('name="focus_project"') < page.index('name="focus_competition"') < page.index('name="focus_credential"')
    assert page.index('name="focus_credential"') < page.index('name="motivation"')
    assert "50%" in page


def test_page_without_weights_has_no_label(app):
    page = login(app).get(f"/student/autobiography?program_id={_pid(app, 'P')}").get_data(as_text=True)

    assert "這所校系很看重" not in page
    assert 'name="motivation"' in page and 'name="focus_' not in page


def test_cannot_generate_without_own_words(app):
    client = login(app)

    response = client.post("/student/autobiography/generate", data={"program_id": _pid(app, "P")})

    assert response.status_code == 400
    assert "先用自己的話寫幾句" in response.get_data(as_text=True)
    assert _drafts(app) == 0


def test_cannot_generate_when_valued_items_are_blank(app):
    client = login(app)

    response = client.post("/student/autobiography/generate", data={
        "program_id": _pid(app, "W"), "motivation": "專二做網頁設計時發現自己喜歡把需求變成系統。",
        "focus_project": "我在專題負責資料庫設計與後端程式，完成選課系統。"})
    page = response.get_data(as_text=True)

    assert response.status_code == 400
    assert "競賽成果" in page and "先用自己的話寫幾句" in page
    assert "我在專題負責資料庫設計" in page  # 已經打的字要留著
    assert _drafts(app) == 0


def test_generates_when_valued_items_are_written_by_the_student(app):
    client = login(app)

    response = client.post("/student/autobiography/generate", data={
        "program_id": _pid(app, "W"),
        "focus_project": "我在專題負責資料庫設計與後端程式，完成選課系統。",
        "focus_competition": "我參加校內黑客松，負責簡報與測試，拿到佳作。"})

    assert response.status_code == 302
    with app.app_context():
        output = LearningProfileOutput.query.filter_by(output_type=autobiography_service.OUTPUT_TYPE).one()
        assert output.content_json["answers"]["focus_competition"].startswith("我參加校內黑客松")
        texts = "\n".join(p["text"] for p in output.content_json["paragraphs"])
        assert "我在專題負責資料庫設計" in texts  # 示範草稿用學生自己的字


def test_program_without_weights_generates_with_one_own_answer(app):
    client = login(app)

    response = client.post("/student/autobiography/generate", data={
        "program_id": _pid(app, "P"), "motivation": "專二做網頁設計時發現自己喜歡把需求變成系統。"})

    assert response.status_code == 302
    assert _drafts(app) == 1


def test_prompt_lists_weighted_answers_and_tells_ai_to_only_tidy(app):
    seen = {}

    def fake_ai(prompt, schema):
        seen["prompt"] = prompt
        return {"paragraphs": [{"title": "專題", "text": "我負責資料庫設計。", "sources": []}]}

    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        autobiography_service.generate_draft(student, _prog("W"), {
            "focus_project": "我在專題負責資料庫設計與後端程式。", "focus_competition": "我參加校內黑客松。"},
            generate=fake_ai)

    prompt = seen["prompt"]
    assert "我在專題負責資料庫設計與後端程式。" in prompt
    assert prompt.index("專題製作") < prompt.index("競賽成果")
    assert "只整理" in prompt


def test_answers_carry_over_weighted_keys_to_another_program(app):
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        autobiography_service.generate_draft(student, _prog("W"), {
            "focus_project": "我在專題負責資料庫設計與後端程式。", "focus_competition": "我參加校內黑客松。"})
        carried = autobiography_service.carried_answers(student)

    assert carried["focus_project"] == "我在專題負責資料庫設計與後端程式。"
