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
