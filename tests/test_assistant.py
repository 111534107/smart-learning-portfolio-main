"""資管科小助手（AI Agent）：會呼叫工具查資料、守權限、不保存對話內容。"""
import json

import pytest

from app import create_app
from app.extensions import db
from app.models import AgentTask, ClassAdvisor, CredentialRecord, StudentProfile, User
from app.services import assistant_service
from app.services.admission_service import import_seed_programs
from app.services.knowledge_service import search


@pytest.fixture()
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        import_seed_programs()
        for username, role in (("stu", "student"), ("other", "student"), ("teacher", "teacher"), ("admin", "admin")):
            user = User(username=username, display_name=username, role=role)
            user.set_password("pw")
            db.session.add(user)
        db.session.flush()
        stu = User.query.filter_by(username="stu").one()
        other = User.query.filter_by(username="other").one()
        db.session.add(StudentProfile(user_id=stu.id, student_no="111534100", class_name="資管科三甲", admission_year=113))
        db.session.add(StudentProfile(user_id=other.id, student_no="111534200", class_name="資管科三乙", admission_year=113))
        db.session.add(CredentialRecord(student_id=stu.id, credential_name="網頁設計丙級", level="丙級"))
        teacher = User.query.filter_by(username="teacher").one()
        db.session.add(ClassAdvisor(teacher_id=teacher.id, class_name="資管科三甲", school_year=115))
        db.session.commit()
    yield app


def user(app, username):
    return User.query.filter_by(username=username).one()


def scripted(*turns):
    """假的 Gemini：依序回傳設定好的回合（工具呼叫或文字），並記錄收到的內容。"""
    seen = []

    def chat(contents, tools, instruction):
        seen.append({"contents": json.loads(json.dumps(contents, ensure_ascii=False)), "tools": tools,
                     "instruction": instruction})
        return turns[len(seen) - 1]

    chat.seen = seen
    return chat


def call(name, **args):
    return {"role": "model", "parts": [{"functionCall": {"name": name, "args": args}}]}


def text(value):
    return {"role": "model", "parts": [{"text": value}]}


def test_knowledge_search_finds_graduation_rule():
    results = search("畢業門檻要幾張證照")

    assert results and "畢業門檻" in results[0]["title"]
    assert "三張" in results[0]["text"] or any("三張" in r["text"] for r in results)


def test_student_agent_calls_tools_then_answers(app):
    chat = scripted(call("search_department_rules", query="畢業門檻 證照"), call("get_my_overview"),
                    text("畢業門檻要三張證照，你目前有 1 張（網頁設計丙級），還差 2 張。"))
    with app.app_context():
        result = assistant_service.ask(user(app, "stu"), "我還差幾張證照才能畢業？", chat=chat)

    assert "還差 2 張" in result["answer"]
    assert result["steps"] == ["查科上規定", "查你的資料"]
    assert any("畢業門檻" in s["title"] for s in result["sources"])
    tool_reply = chat.seen[2]["contents"][-1]["parts"][0]["functionResponse"]
    assert tool_reply["name"] == "get_my_overview"
    assert "網頁設計丙級" in json.dumps(tool_reply, ensure_ascii=False)


def test_student_tools_do_not_include_teacher_tools(app):
    chat = scripted(text("好"))
    with app.app_context():
        assistant_service.ask(user(app, "stu"), "嗨", chat=chat)

    names = {tool["name"] for tool in chat.seen[0]["tools"]}
    assert "list_my_class_students" not in names and "get_student_overview" not in names
    assert "get_my_overview" in names


def test_teacher_cannot_query_student_from_other_class(app):
    chat = scripted(call("get_student_overview", student_no="111534200"), text("無法查詢"))
    with app.app_context():
        assistant_service.ask(user(app, "teacher"), "查 111534200", chat=chat)

    reply = chat.seen[1]["contents"][-1]["parts"][0]["functionResponse"]["response"]["result"]
    assert "不是你負責班級" in reply["error"]
    assert "other" not in json.dumps(reply, ensure_ascii=False)


def test_teacher_lists_only_own_class(app):
    chat = scripted(call("list_my_class_students"), text("本班 1 人"))
    with app.app_context():
        assistant_service.ask(user(app, "teacher"), "本班有誰？", chat=chat)

    students = chat.seen[1]["contents"][-1]["parts"][0]["functionResponse"]["response"]["result"]["students"]
    assert [s["student_no"] for s in students] == ["111534100"]


def test_conversation_text_is_not_stored(app):
    chat = scripted(call("get_my_overview"), text("這是回答"))
    with app.app_context():
        assistant_service.ask(user(app, "stu"), "我的祕密問題", chat=chat)
        task = AgentTask.query.filter_by(task_type="assistant_chat").one()

        stored = json.dumps(task.result_json, ensure_ascii=False)
        assert task.status == "succeeded"
        assert "我的祕密問題" not in stored and "這是回答" not in stored
        assert "查你的資料" in stored


def test_loop_stops_after_max_steps(app):
    chat = scripted(*[call("get_my_overview")] * assistant_service.MAX_STEPS)
    with app.app_context():
        result = assistant_service.ask(user(app, "stu"), "一直查", chat=chat)

    assert "換個問法" in result["answer"]
    assert len(chat.seen) == assistant_service.MAX_STEPS


def test_without_api_key_route_gives_friendly_message(app):
    client = app.test_client()
    client.post("/login", data={"username": "stu", "password": "pw"})

    response = client.post("/assistant/ask", data={"message": "畢業門檻？", "history": "[]"})

    assert response.status_code == 200
    assert "沒有開啟" in response.get_json()["answer"]


def test_admin_cannot_use_assistant_route(app):
    client = app.test_client()
    client.post("/login", data={"username": "admin", "password": "pw"})

    assert client.post("/assistant/ask", data={"message": "x"}).status_code == 403


def test_widget_shows_on_student_and_teacher_pages_only(app):
    student = app.test_client()
    student.post("/login", data={"username": "stu", "password": "pw"})
    teacher = app.test_client()
    teacher.post("/login", data={"username": "teacher", "password": "pw"})

    assert "data-assistant" in student.get("/student/dashboard").get_data(as_text=True)
    assert "data-assistant" in teacher.get("/teacher/dashboard").get_data(as_text=True)
    assert "data-assistant" not in app.test_client().get("/login").get_data(as_text=True)
