import pytest

from app import create_app
from app.extensions import db
from app.models import AuditLog, StudentProfile, User


@pytest.fixture()
def client():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        for name, role in (("stu", "student"), ("tch", "teacher")):
            user = User(username=name, display_name=name, role=role)
            user.set_password("pw")
            db.session.add(user)
            db.session.flush()
            if role == "student":
                db.session.add(StudentProfile(user_id=user.id, student_no="s1", admission_year=115))
        db.session.commit()
    client = app.test_client()
    client.app = app
    return client


def login(client, name="stu"):
    return client.post("/login", data={"username": name, "password": "pw"})


def test_first_login_goes_to_welcome(client):
    assert login(client).headers["Location"].endswith("/student/welcome")


def test_welcome_has_five_short_steps(client):
    login(client)
    page = client.get("/student/welcome").get_data(as_text=True)

    assert page.count("data-welcome-step=") == 5
    assert "國立臺中科技大學" in page
    assert "data-welcome-skip" in page


def test_finishing_welcome_goes_home_and_is_remembered(client):
    login(client)
    response = client.post("/student/welcome/done", data={"to": "upload"})

    assert response.status_code == 302
    assert "/student/learning-profile/upload" in response.headers["Location"]
    with client.app.app_context():
        assert AuditLog.query.filter_by(action="student.welcome_done").count() == 1
    client.post("/logout")
    assert login(client).headers["Location"].endswith("/student/dashboard")


def test_unknown_destination_falls_back_to_dashboard(client):
    login(client)

    response = client.post("/student/welcome/done", data={"to": "https://evil.example"})

    assert response.headers["Location"].endswith("/student/dashboard")


def test_welcome_is_students_only(client):
    login(client, "tch")

    assert client.get("/student/welcome").status_code == 403


def test_senior_student_is_not_welcomed_as_a_freshman(client):
    """11-04 實測：專五第一次登入看到「歡迎來到資管科」。"""
    with client.app.app_context():
        StudentProfile.query.filter_by(student_no="s1").one().admission_year = 111
        db.session.commit()
    login(client)
    page = client.get("/student/welcome").get_data(as_text=True)

    assert "歡迎來到資管科" not in page
    assert "歡迎使用學習歷程系統" in page


def test_milestone_popup_is_no_longer_shown(client):
    """2026-11-21 使用者要求拿掉里程碑彈跳視窗（用處不大、蓋住畫面）：彩蛋腳本不再讀 milestones-data 來跳卡片。
    後端的里程碑資料仍保留（頁面上還有 milestones-data），要恢復只要把腳本那一行的註解拿掉。"""
    from pathlib import Path
    script = (Path(client.application.root_path) / "static" / "js" / "easter-eggs.js").read_text(encoding="utf-8")
    live = [line for line in script.splitlines() if "window.showMilestone(item)" in line and not line.lstrip().startswith("//")]
    assert live == [], "里程碑卡片不應該在載入頁面時自動跳出來"
