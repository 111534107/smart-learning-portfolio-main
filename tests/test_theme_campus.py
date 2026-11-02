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


def contrast_with_white(hex_colour):
    """WCAG 相對亮度：白字在這個底色上的對比值。"""
    def channel(value):
        value /= 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    luminance = 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
    return 1.05 / (luminance + 0.05)


def test_sheet_heads_become_bands_with_white_links():
    text = THEME_CSS.read_text(encoding="utf-8")

    assert '[data-theme="campus"] .sheet > .sheet__head:first-child' in text
    assert "var(--band-navy)" in text and "var(--band-caramel)" in text
    assert '[data-theme="campus"] .sheet > .sheet__head:first-child a' in text  # 標題帶裡的連結要白字


def test_band_colours_pass_contrast_with_white_text():
    for hex_colour in ("#1f3a5f", "#2c5282", "#94652a", "#9c6a2c"):
        assert contrast_with_white(hex_colour) >= 4.5, hex_colour


def test_student_pages_show_quick_dock():
    html = login(ui_app(), "ui-student").get("/student/targets").get_data(as_text=True)

    assert 'class="quick-dock"' in html
    assert 'href="/student/schedule"' in html
    assert 'href="/student/autobiography"' in html
    assert 'href="#main-content"' in html


def test_quick_dock_hidden_on_home_and_for_teachers():
    student = login(ui_app(), "ui-student")
    assert 'class="quick-dock"' not in student.get("/student/dashboard").get_data(as_text=True)
    teacher = login(ui_app(), "ui-teacher")
    assert 'class="quick-dock"' not in teacher.get("/teacher/dashboard").get_data(as_text=True)
    assert 'class="quick-dock"' not in ui_app().test_client().get("/login").get_data(as_text=True)


def test_quick_dock_is_not_printed_and_respects_small_screens():
    text = THEME_CSS.read_text(encoding="utf-8")

    assert "@media print" in text and ".quick-dock" in text
    assert "@media (max-width: 480px)" in text
