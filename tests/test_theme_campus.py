"""校園招生風主題（參考臺中科大招生網站配色）：只套在首頁以外的頁面，首頁維持原樣。"""
from pathlib import Path

from app import create_app
from app.extensions import db
from app.models import User

THEME_CSS = Path(__file__).resolve().parents[1] / "app" / "static" / "css" / "theme-campus.css"


def ui_app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "WTF_CSRF_ENABLED": False})
    with app.app_context():
        db.create_all()
        for username, role in (("ui-student", "student"), ("ui-teacher", "teacher")):
            user = User(username=username, display_name=username, role=role)
            user.set_password("test-password")
            db.session.add(user)
        db.session.commit()
    return app


def login(app, username):
    client = app.test_client()
    client.post("/login", data={"username": username, "password": "test-password"})
    return client


def test_home_pages_keep_classic_look():
    html = ui_app().test_client().get("/").get_data(as_text=True)

    assert 'data-page="public-home"' in html
    assert 'data-theme="campus"' not in html


def test_student_dashboard_keeps_classic_look():
    html = login(ui_app(), "ui-student").get("/student/dashboard").get_data(as_text=True)

    assert 'data-page="student-dashboard"' in html
    assert 'data-theme="campus"' not in html


def test_other_pages_use_campus_theme_after_design_system():
    html = login(ui_app(), "ui-student").get("/student/targets").get_data(as_text=True)

    assert 'data-theme="campus"' in html
    assert html.index("css/design-system.css") < html.index("css/theme-campus.css")


def test_theme_css_has_balanced_braces_and_scoped_rules():
    text = THEME_CSS.read_text(encoding="utf-8")

    assert text.count("{") == text.count("}")
    assert '[data-theme="campus"]' in text
    assert "--paper: #fdf3e2" in text
