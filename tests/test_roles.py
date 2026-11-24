from app import create_app
from app.extensions import db
from app.models import User


def role_app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        for username, role in (("student", "student"), ("teacher", "teacher"), ("staff", "staff"), ("admin", "admin"), ("reviewer", "reviewer")):
            user = User(username=username, role=role, display_name=username)
            user.set_password("pw")
            db.session.add(user)
        db.session.commit()
    return app


def test_staff_can_open_staff_dashboard():
    client = role_app().test_client()
    response = client.post("/login", data={"username": "staff", "password": "pw"})

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/staff/dashboard")
    assert client.get("/staff/dashboard").status_code == 200


def test_reviewer_is_not_a_supported_login_role():
    client = role_app().test_client()
    response = client.post("/login", data={"username": "reviewer", "password": "pw"})

    assert response.status_code == 403
    assert "尚未設定可用角色".encode("utf-8") in response.data


def test_reviewer_cannot_open_teacher_dashboard():
    app = role_app()
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 5

    assert client.get("/teacher/dashboard").status_code == 403
