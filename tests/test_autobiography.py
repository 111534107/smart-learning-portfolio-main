"""AI 自傳小幫手：先回答問題，AI 只能用學生的資料與回答寫草稿。"""
from datetime import date
import io

import pytest
from docx import Document

from app import create_app
from app.extensions import db
from app.models import (AdmissionProgram, CredentialRecord, LearningCourseRecord, LearningProfileOutput,
                        Portfolio, StudentProfile, StudentTarget, User)
from app.services.admission_service import import_seed_programs
from app.services.autobiography_service import build_facts, generate_draft
from app.services.journey_service import academic_year_of
from tests.board_helpers import fill_board

ANSWERS = {
    "motivation": "專二做網頁設計時發現自己喜歡把需求變成系統。",
    "proud": "黑客松時負責後端 API。",
    "challenge": "",
    "future": "想學資料分析。",
}


@pytest.fixture()
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        import_seed_programs()
        for username in ("stu", "other"):
            user = User(username=username, display_name=username, role="student")
            user.set_password("pw")
            db.session.add(user)
        db.session.flush()
        stu = User.query.filter_by(username="stu").one()
        db.session.add(StudentProfile(user_id=stu.id, student_no="111534100", class_name="資管科三甲", admission_year=academic_year_of(date.today()) - 4))  # 專五
        db.session.add(Portfolio(student_id=stu.id, title="校園黑客松", category="competition", school_year=3, status="confirmed",
                                 description="三人一組完成報名網站"))
        db.session.commit()
        fill_board(stu)  # 補滿五年資料（拼圖閘門已拿掉，這裡只是讓資料齊全）
    yield app


def login(app, username="stu"):
    client = app.test_client()
    client.post("/login", data={"username": username, "password": "pw"})
    return client


def program(app):
    with app.app_context():
        return AdmissionProgram.query.filter_by(program_code="208003").one().id


def choose_target(app, client):
    client.post("/student/targets", data={"program_id": program(app)})


def test_facts_are_numbered_and_include_program_weights(app):
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        facts = build_facts(student, AdmissionProgram.query.filter_by(program_code="208003").one())

    assert facts["items"][0]["id"] == "F1"
    assert any("校園黑客松" in fact["text"] for fact in facts["items"])
    assert facts["weights"]


def test_facts_keep_stable_evidence_ids_for_confirmed_sources(app):
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        program = AdmissionProgram.query.filter_by(program_code="208003").one()
        course = LearningCourseRecord(student_id=student.id, course_name="資料庫管理", normalized_course_name="資料庫管理",
                                      score=91, confirmation_status="confirmed")
        unconfirmed = LearningCourseRecord(student_id=student.id, course_name="待確認課程", normalized_course_name="待確認課程",
                                           score=99, confirmation_status="draft")
        credential = CredentialRecord(student_id=student.id, credential_name="測試證照", confirmation_status="confirmed")
        db.session.add_all([course, unconfirmed, credential])
        db.session.commit()

        facts = build_facts(student, program)["items"]

    course_fact = next(fact for fact in facts if "資料庫管理" in fact["text"])
    credential_fact = next(fact for fact in facts if "測試證照" in fact["text"])
    assert course_fact["evidence_id"] == f"course:{course.id}"
    assert credential_fact["evidence_id"] == f"credential:{credential.id}"
    assert all("待確認課程" not in fact["text"] for fact in facts)


def test_teacher_submission_snapshot_preserves_evidence_ids(app):
    from app.services.review_snapshot_service import build_snapshot

    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        program = AdmissionProgram.query.filter_by(program_code="208003").one()
        db.session.add(LearningCourseRecord(student_id=student.id, course_name="網頁設計", normalized_course_name="網頁設計",
                                            score=90, confirmation_status="confirmed"))
        db.session.commit()

        snapshot = build_snapshot(student, program)

    assert snapshot["facts"][0]["evidence_id"].startswith("course:")


def test_generate_keeps_only_known_fact_ids(app):
    def fake_ai(prompt, schema):
        assert "專二做網頁設計" in prompt
        assert "不得編造" in prompt
        return {"paragraphs": [{"title": "動機", "text": "我想讀資管。", "sources": ["F1", "F99"]}]}

    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        prog = AdmissionProgram.query.filter_by(program_code="208003").one()
        output = generate_draft(student, prog, ANSWERS, generate=fake_ai)

        assert output.output_type == "autobiography_ai"
        assert output.content_json["paragraphs"][0]["sources"] == ["F1"]
        assert output.content_json["provider"] == "gemini"
        assert any(item["evidence_id"].startswith("portfolio:") for item in output.source_snapshot_json["evidence_package"]["items"])


def test_without_api_key_uses_labelled_demo_draft(app):
    client = login(app)
    choose_target(app, client)

    response = client.post("/student/autobiography/generate", data={"program_id": program(app), **ANSWERS})

    assert response.status_code == 302
    html = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "尚未接上 AI" in html
    assert "專二做網頁設計" in html


def test_page_asks_to_choose_target_first(app):
    html = login(app).get("/student/autobiography").get_data(as_text=True)

    assert "/student/targets" in html
    assert 'name="motivation"' not in html


def test_page_shows_questions_after_target_chosen(app):
    client = login(app)
    choose_target(app, client)

    html = client.get("/student/autobiography").get_data(as_text=True)

    assert 'name="motivation"' in html


def test_student_edits_are_saved_and_go_into_word(app):
    client = login(app)
    choose_target(app, client)
    client.post("/student/autobiography/generate", data={"program_id": program(app), **ANSWERS})
    with app.app_context():
        output = LearningProfileOutput.query.filter_by(output_type="autobiography_ai").one()
        count = len(output.content_json["paragraphs"])

    response = client.post(f"/student/autobiography/{output.id}/save",
                           data={f"paragraph_{i}": f"我修改過的第{i + 1}段" for i in range(count)})
    docx = client.get(f"/student/targets/{program(app)}/package.docx")

    assert response.status_code == 302
    text = "\n".join(p.text for p in Document(io.BytesIO(docx.data)).paragraphs)
    assert "我修改過的第1段" in text


def test_other_student_cannot_save_my_draft(app):
    client = login(app)
    choose_target(app, client)
    client.post("/student/autobiography/generate", data={"program_id": program(app), **ANSWERS})
    with app.app_context():
        output_id = LearningProfileOutput.query.filter_by(output_type="autobiography_ai").one().id

    response = login(app, "other").post(f"/student/autobiography/{output_id}/save", data={"paragraph_0": "x"})

    assert response.status_code in (403, 404)


def test_own_api_key_is_used_once_and_never_stored(app, monkeypatch):
    import json
    from app.services import gemini_client
    secret = "AQ.student-own-secret-key-123"
    seen = {}

    def fake_generate(prompt, schema, files=None, api_key=None, opener=None):
        seen["key"] = api_key
        return {"paragraphs": [{"title": "動機", "text": "我想讀資管。", "sources": []}]}

    monkeypatch.setattr(gemini_client, "generate_json", fake_generate)
    monkeypatch.setattr("app.services.autobiography_service.generate_json", fake_generate)
    client = login(app)
    choose_target(app, client)

    response = client.post("/student/autobiography/generate",
                           data={"program_id": program(app), "own_api_key": secret, **ANSWERS})
    page = client.get(response.headers["Location"]).get_data(as_text=True)

    assert seen["key"] == secret
    assert secret not in response.headers["Location"]
    assert secret not in page
    assert "記得" in page and "刪除" in page
    with app.app_context():
        stored = LearningProfileOutput.query.filter_by(output_type="autobiography_ai").one()
        assert stored.content_json["provider"] == "gemini"
        assert secret not in json.dumps(stored.content_json, ensure_ascii=False)
        assert secret not in json.dumps(stored.source_snapshot_json, ensure_ascii=False)
    with client.session_transaction() as session:
        assert secret not in json.dumps(dict(session))


def test_form_offers_own_key_field_without_autocomplete(app):
    client = login(app)
    choose_target(app, client)

    html = client.get("/student/autobiography").get_data(as_text=True)

    assert 'name="own_api_key"' in html
    assert 'type="password"' in html
    assert 'autocomplete="off"' in html


def test_draft_page_shows_review_evidence_and_ai_limits(app):
    client = login(app)
    choose_target(app, client)
    client.post("/student/autobiography/generate", data={"program_id": program(app), **ANSWERS})

    html = client.get("/student/autobiography").get_data(as_text=True)

    assert "主張" in html
    assert "證據" in html
    assert "競賽：校園黑客松" in html
    assert "三人一組完成報名網站" in html
    assert "這題還沒回答" in html
    assert "AI 不能做的事" in html
    assert "給分" in html and "退件" in html and "核定資格" in html and "發布招生規則" in html
    assert "送出前要你自己確認" in html


def _count_generate(monkeypatch):
    calls = []

    def fake(prompt, schema, files=None, api_key=None, opener=None):
        calls.append(1)
        return {"paragraphs": [{"title": "動機", "text": "我想讀資管。", "sources": []}]}

    monkeypatch.setattr("app.services.autobiography_service.generate_json", fake)
    return calls


def test_autobiography_no_longer_waits_for_the_puzzle(app, monkeypatch):
    """試用版拿掉拼圖閘門：少了一類資料（服務學習）照樣可以生成自傳。"""
    calls = _count_generate(monkeypatch)
    with app.app_context():
        Portfolio.query.filter_by(category="service").delete()
        db.session.commit()
    client = login(app)
    choose_target(app, client)

    page = client.get("/student/autobiography").get_data(as_text=True)
    response = client.post("/student/autobiography/generate",
                           data={"program_id": program(app), "own_api_key": "test-key", **ANSWERS})

    assert "拼圖還差" not in page
    assert response.status_code == 302
    assert len(calls) == 1


def test_grade_one_autobiography_page_disables_generate_up_front(app):
    with app.app_context():
        stu = User.query.filter_by(username="stu").one()
        stu.student_profile.admission_year = academic_year_of(date.today())  # 專一
        db.session.commit()
    client = login(app)
    choose_target(app, client)

    page = client.get("/student/autobiography").get_data(as_text=True)

    assert "專五開放生成自傳" in page
    submit = page.split("data-step-submit", 1)[1].split(">", 1)[0]
    assert "disabled" in submit


def _set_grade(app, grade):
    with app.app_context():
        stu = User.query.filter_by(username="stu").one()
        stu.student_profile.admission_year = academic_year_of(date.today()) - (grade - 1)
        db.session.commit()


def test_grade_three_cannot_generate_autobiography(app, monkeypatch):
    calls = _count_generate(monkeypatch)
    _set_grade(app, 3)
    client = login(app)
    choose_target(app, client)

    response = client.post("/student/autobiography/generate",
                           data={"program_id": program(app), "own_api_key": "test-key", **ANSWERS})
    page = client.get("/student/autobiography").get_data(as_text=True)

    assert calls == []
    assert "專五才開放" in response.get_data(as_text=True)
    assert "專五開放生成自傳" in page


def test_grade_five_can_generate_autobiography(app, monkeypatch):
    calls = _count_generate(monkeypatch)
    _set_grade(app, 5)
    client = login(app)
    choose_target(app, client)

    response = client.post("/student/autobiography/generate",
                           data={"program_id": program(app), "own_api_key": "test-key", **ANSWERS})

    assert response.status_code == 302
    assert len(calls) == 1


def test_grade_three_can_still_submit_for_review(app):
    """送審維持專二規則：專三不受自傳專五限制影響。"""
    from app.services import student_rules
    _set_grade(app, 3)
    with app.app_context():
        stu = User.query.filter_by(username="stu").one()
        assert student_rules.review_block_reason(stu) is None
        assert "專五" in student_rules.autobiography_block_reason(stu)



def test_grade_one_is_told_autobiography_opens_at_grade_five(app):
    """專一的說明要講自傳專五才開放，不能沿用送審那句「專二」。"""
    from app.services import student_rules
    _set_grade(app, 1)
    with app.app_context():
        stu = User.query.filter_by(username="stu").one()
        reason = student_rules.autobiography_block_reason(stu)
        assert "專五" in reason and "專二" not in reason
        assert student_rules.review_open_note(stu) == "專五開放生成自傳"
