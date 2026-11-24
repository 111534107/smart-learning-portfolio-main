"""資管科小助手在實習履歷頁：說家庭生活，整理後填進履歷（2026-11-18）。僅為測試資料。"""
import pytest

from app import create_app
from app.extensions import db
from app.models import StudentProfile, User

PAGE = "實習履歷｜資管科智慧學習歷程系統"
STORY = "我家有四個人，爸媽做小生意，我從小幫忙顧店，也照顧弟弟，所以學會負責任。"


@pytest.fixture
def client():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        for name, role in [("stu", "student"), ("t1", "teacher")]:
            user = User(username=name, display_name=name, role=role)
            user.set_password("pw")
            db.session.add(user)
        db.session.flush()
        db.session.add(StudentProfile(user_id=User.query.filter_by(username="stu").one().id, student_no="s1",
                                      class_name="甲班", admission_year=111))
        db.session.commit()
    c = app.test_client()
    c.post("/login", data={"username": "stu", "password": "pw"})
    return c


def test_story_on_resume_page_returns_fill_and_does_not_call_the_normal_assistant(client, monkeypatch):
    from app.services import assistant_service
    monkeypatch.setattr(assistant_service, "ask", lambda *a, **k: pytest.fail("不該走一般問答"))
    from app.routes import assistant as routes
    monkeypatch.setattr(routes, "ask", lambda *a, **k: pytest.fail("不該走一般問答"))
    body = client.post("/assistant/ask", data={"message": STORY, "page": PAGE}).get_json()
    assert body["fill"]["target"] == "family" and "爸媽做小生意" in body["fill"]["text"]
    assert "家庭生活" in body["answer"]


def test_short_request_gets_guidance_without_fill(client):
    for message in ("幫我寫家庭生活", "怎麼寫家庭生活？"):
        body = client.post("/assistant/ask", data={"message": message, "page": PAGE}).get_json()
        assert "fill" not in body and "說" in body["answer"]


def test_other_pages_and_other_topics_are_not_intercepted(client, monkeypatch):
    seen = []
    from app.routes import assistant as routes
    monkeypatch.setattr(routes, "ask", lambda user, message, history=None, page="": seen.append(page) or {"answer": "一般回答"})
    assert client.post("/assistant/ask", data={"message": STORY, "page": "我的五年｜資管科智慧學習歷程系統"}).get_json() == {"answer": "一般回答"}
    assert client.post("/assistant/ask", data={"message": "畢業門檻要幾張證照呢，請告訴我詳細一點的規定", "page": PAGE}).get_json() == {"answer": "一般回答"}
    assert len(seen) == 2


def test_teacher_is_not_intercepted(client, monkeypatch):
    from app.routes import assistant as routes
    monkeypatch.setattr(routes, "ask", lambda user, message, history=None, page="": {"answer": "一般回答"})
    teacher = client.application.test_client()
    teacher.post("/staff/login", data={"username": "t1", "password": "pw"})
    assert teacher.post("/assistant/ask", data={"message": STORY, "page": PAGE}).get_json() == {"answer": "一般回答"}
