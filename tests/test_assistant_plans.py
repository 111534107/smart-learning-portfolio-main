"""同意式 Agent 計畫與待辦（組員版 vujhdcusa/1028 移入）＋ GitHub 風格頁面。

前半段是組員版的測試（原在 tests/test_assistant.py），後半段是本次修正與新頁面的測試。
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app import create_app
from app.extensions import db
from app.models import (AdmissionProgram, AgentTask, ClassAdvisor, CredentialRecord, SourceDocument, StudentProfile,
                        StudentTarget, User)
from app.services import assistant_agent_service, assistant_service
from app.services.admission_service import import_seed_programs


@pytest.fixture()
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        import_seed_programs()
        for username, role in (("stu", "student"), ("other", "student"), ("teacher", "teacher")):
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
    seen = []

    def chat(contents, tools, instruction):
        seen.append({"contents": json.loads(json.dumps(contents, ensure_ascii=False))})
        return turns[len(seen) - 1]

    chat.seen = seen
    return chat


def text(value):
    return {"role": "model", "parts": [{"text": value}]}


def login(app, username):
    client = app.test_client()
    client.post("/login", data={"username": username, "password": "pw"})
    return client


def new_plan(app, username="stu"):
    with app.app_context():
        return assistant_service.ask(user(app, username), "幫我規劃下一步", chat=scripted(text("好")))["plan"]


# ---------- 組員版測試 ----------

def test_agent_returns_safe_navigation_links_and_waits_for_student_consent(app):
    with app.app_context():
        result = assistant_service.ask(user(app, "stu"), "幫我規劃下一步，成績 OCR 要怎麼核對？",
                                       chat=scripted(text("我會先幫你整理。")))
        plan = result["plan"]
        assert any(link["url"] == "/student/learning-profile" for link in result["links"])
        assert plan["status"] == "pending"
        task = db.session.get(AgentTask, plan["id"])
        assert task.status == "pending"
        assert "幫我規劃" not in json.dumps(task.result_json, ensure_ascii=False)


def test_student_must_approve_agent_plan_before_it_runs(app):
    plan = new_plan(app)
    response = login(app, "stu").post(f"/assistant/plans/{plan['id']}/approve")

    assert response.status_code == 200
    assert response.get_json()["status"] == "succeeded"
    with app.app_context():
        assert db.session.get(AgentTask, plan["id"]).status == "succeeded"


def test_approved_agent_plan_saves_todos_and_student_can_read_history(app):
    plan = new_plan(app)
    client = login(app, "stu")

    approved = client.post(f"/assistant/plans/{plan['id']}/approve").get_json()
    history = client.get("/assistant/plans").get_json()["plans"]

    assert approved["todos"]
    assert all(todo["url"].startswith("/student/") for todo in approved["todos"])
    assert history[0]["id"] == plan["id"]
    assert history[0]["todos"] == approved["todos"]


def test_agent_todos_are_ranked_by_selected_program_weight_and_can_be_completed(app):
    with app.app_context():
        student = user(app, "stu")
        db.session.add(StudentTarget(student_id=student.id, rule_version_id=AdmissionProgram.query.first().id))
        db.session.commit()
    plan = new_plan(app)
    client = login(app, "stu")

    approved = client.post(f"/assistant/plans/{plan['id']}/approve").get_json()
    weighted = [todo["weight"] for todo in approved["todos"] if todo.get("kind") == "target_gap"]
    assert weighted == sorted(weighted, reverse=True)
    first_open = next(index for index, todo in enumerate(approved["todos"]) if todo["status"] == "open")
    marked = client.post(f"/assistant/plans/{plan['id']}/todos/{first_open}/completed").get_json()
    reopened = client.post(f"/assistant/plans/{plan['id']}/todos/{first_open}/open").get_json()

    assert marked["status"] == "completed"
    assert reopened["status"] == "open"


def test_agent_plan_history_is_private_to_each_student(app):
    new_plan(app)

    assert login(app, "other").get("/assistant/plans").get_json()["plans"] == []


def test_expired_unapproved_agent_plan_is_cancelled_before_creating_a_new_one(app):
    with app.app_context():
        student = user(app, "stu")
        old = assistant_agent_service.propose_plan(student, "幫我規劃下一步")
        task = db.session.get(AgentTask, old["id"])
        task.created_at = datetime.now(timezone.utc) - timedelta(hours=25)
        db.session.commit()
        new = assistant_agent_service.propose_plan(student, "幫我規劃下一步")

        assert db.session.get(AgentTask, old["id"]).status == "cancelled"
        assert new["id"] != old["id"]


# ---------- 本次修正 ----------

def test_expired_plan_cannot_be_approved(app):
    plan = new_plan(app)
    with app.app_context():
        task = db.session.get(AgentTask, plan["id"])
        task.created_at = datetime.now(timezone.utc) - timedelta(hours=25)
        db.session.commit()

    result = login(app, "stu").post(f"/assistant/plans/{plan['id']}/approve").get_json()

    assert result["status"] == "cancelled" and "24 小時" in result["message"]
    with app.app_context():
        assert db.session.get(AgentTask, plan["id"]).status == "cancelled"
        assert "todos" not in db.session.get(AgentTask, plan["id"]).result_json


def test_reopen_sticks_even_when_data_already_complete(app):
    """組員版：資料已補齊的待辦按「重新開啟」仍顯示完成。改為以學生的選擇為準。"""
    with app.app_context():
        db.session.add(SourceDocument(owner_id=user(app, "stu").id, document_type="transcript", display_name="a.pdf",
                                      file_path="a.pdf", sha256="0" * 64, status="extracted"))
        db.session.commit()
    plan = new_plan(app)
    client = login(app, "stu")
    todos = client.post(f"/assistant/plans/{plan['id']}/approve").get_json()["todos"]
    ocr = next(index for index, todo in enumerate(todos) if todo["kind"] == "confirm_ocr")
    with app.app_context():
        SourceDocument.query.update({"status": "confirmed"})  # 學生核對完：條件已滿足
        db.session.commit()
    assert client.get("/assistant/plans").get_json()["plans"][0]["todos"][ocr]["status"] == "completed"

    reopened = client.post(f"/assistant/plans/{plan['id']}/todos/{ocr}/open").get_json()

    assert reopened["status"] == "open"
    assert client.get("/assistant/plans").get_json()["plans"][0]["todos"][ocr]["status"] == "open"


def test_plan_previews_todos_before_consent(app):
    plan = new_plan(app)

    titles = [todo["title"] for todo in plan["preview_todos"]]
    assert "選擇目標校系" in titles
    with app.app_context():
        assert "todos" not in db.session.get(AgentTask, plan["id"]).result_json  # 還沒建立


def test_chat_widget_history_is_per_account(app):
    html = login(app, "stu").get("/student/dashboard").get_data(as_text=True)

    with app.app_context():
        assert f'data-user="{user(app, "stu").id}"' in html


# ---------- GitHub 風格頁面 ----------

def test_pages_flow_plan_approve_close_reopen_activity(app):
    client = login(app, "stu")

    location = client.post("/student/agent/plan").headers["Location"]
    page = client.get(location).get_data(as_text=True)
    assert "同意執行" in page and "同意後會建立的待辦" in page and "選擇目標校系" in page

    response = client.post(location + "/approve")
    assert response.headers["Location"].endswith("/student/agent/issues")
    issues = client.get("/student/agent/issues").get_data(as_text=True)
    assert "選擇目標校系" in issues and "件事要做" in issues

    plan_id = int(location.rsplit("/", 1)[1])
    with app.app_context():
        todos = db.session.get(AgentTask, plan_id).result_json["todos"]
    index = next(i for i, todo in enumerate(todos) if todo["kind"] == "choose_targets")
    client.post(f"/student/agent/issues/{plan_id}/{index}/close")
    assert "選擇目標校系" in client.get("/student/agent/issues?state=closed").get_data(as_text=True)
    client.post(f"/student/agent/issues/{plan_id}/{index}/reopen")

    activity = client.get("/student/agent/activity").get_data(as_text=True)
    assert "你同意執行" in activity and "標記完成" in activity and "重新開啟" in activity


def test_reject_from_page_creates_no_todos(app):
    client = login(app, "stu")
    location = client.post("/student/agent/plan").headers["Location"]

    client.post(location + "/reject")

    assert "未執行" in client.get("/student/agent/proposals").get_data(as_text=True)
    assert "還沒有待辦" in client.get("/student/agent/issues").get_data(as_text=True)


def test_other_student_gets_404_on_pages(app):
    location = login(app, "stu").post("/student/agent/plan").headers["Location"]
    other = login(app, "other")

    assert other.get(location).status_code == 404
    assert other.post(location + "/approve").status_code == 404


def test_teacher_cannot_open_student_pages(app):
    assert login(app, "teacher").get("/student/agent/issues").status_code == 403


def test_issue_action_ignores_external_next(app):
    client = login(app, "stu")
    location = client.post("/student/agent/plan").headers["Location"]
    client.post(location + "/approve")
    plan_id = int(location.rsplit("/", 1)[1])

    response = client.post(f"/student/agent/issues/{plan_id}/0/close", data={"next": "https://evil.example/"})

    assert response.headers["Location"].endswith("/student/agent/issues")


def test_label_filter(app):
    client = login(app, "stu")
    location = client.post("/student/agent/plan").headers["Location"]
    client.post(location + "/approve")

    html = client.get("/student/agent/issues?label=target").get_data(as_text=True)

    assert "選擇目標校系" in html and "整理證照資料" not in html


def test_student_main_nav_shows_my_todos_with_count(app):
    """11-04 使用者：「我的待辦」藏在聊天視窗太不明顯，改放學生主選單並顯示未完成數。"""
    client = login(app, "stu")
    html = client.get("/student/portfolio").get_data(as_text=True)
    assert 'class="mainnav__todo" href="/student/agent/issues"' in html and "mainnav__count" not in html

    location = client.post("/student/agent/plan").headers["Location"]
    assert "有規劃提案等你同意" in client.get("/student/portfolio").get_data(as_text=True)
    client.post(location + "/approve")

    html = client.get("/student/portfolio").get_data(as_text=True)
    assert "mainnav__count" in html and "有規劃提案等你同意" not in html


def test_planning_twice_does_not_duplicate_todos(app):
    """B6（2026-11-13）：重複請小助手規劃並同意，同一個待辦只列最新那份，選單數字也不會變兩倍。"""
    client = login(app, "stu")
    first = client.post(f"/assistant/plans/{new_plan(app)['id']}/approve").get_json()
    second = client.post(f"/assistant/plans/{new_plan(app)['id']}/approve").get_json()
    assert [t["key"] for t in first["todos"]] == [t["key"] for t in second["todos"]]

    page = client.get("/student/agent/issues").get_data(as_text=True)
    for todo in second["todos"]:
        assert page.count(f"標記完成：{todo['title']}") == 1
    assert f"/student/agent/issues/{second['plan_id']}/0/close" in page  # 列的是最新那份
    with app.app_context():
        assert assistant_agent_service.open_todo_count(user(app, "stu"))["open"] == len(second["todos"])
