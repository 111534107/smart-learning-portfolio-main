"""版面背景方塊動畫（2026-11-16，合成資料）。

參考康寧大學證照系統登入區的方塊往上飄效果，自己重寫成共用元件 partials/bg_squares.html＋css/bg-squares.css。
全系統每一頁都有（使用者 2026-11-16 要求）；老師、科辦、管理員頁調得更淡。
系統設定「減少動態效果」時方塊停住不動；只用 transform 做動畫、不擋點擊、在內容後面。
"""
import re
from pathlib import Path

import pytest

from app import create_app
from app.extensions import db
from app.models import User

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app" / "static" / "css" / "bg-squares.css").read_text(encoding="utf-8")
LAYER = '<div class="bg-squares"'


@pytest.fixture()
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        for username, role in (("student_syn", "student"), ("teacher_syn", "teacher"), ("staff_syn", "staff"), ("admin_syn", "admin")):
            user = User(username=username, display_name="合成帳號", role=role)
            user.set_password("pw")
            db.session.add(user)
        db.session.commit()
    return app


def logged_in(app, username):
    client = app.test_client()
    client.post("/login", data={"username": username, "password": "pw"})
    return client


def test_student_pages_have_one_background_layer(app):
    client = logged_in(app, "student_syn")
    for path in ("/student/dashboard", "/student/targets", "/student/graduation-check", "/student/portfolio", "/student/files", "/forms"):
        html = client.get(path).get_data(as_text=True)
        assert html.count(LAYER) == 1, path
        assert "css/bg-squares.css" in html
        layer = re.search(r'<div class="bg-squares".*?</div>', html, re.S).group(0)
        assert 'aria-hidden="true"' in layer
        assert 6 <= layer.count("<span") <= 12  # 數量節制


def test_login_and_home_have_the_layer_and_login_side_has_panel_squares(app):
    client = app.test_client()
    login = client.get("/login").get_data(as_text=True)
    assert LAYER in login
    assert "bg-squares bg-squares--panel" in login  # 左側深色欄的白色方塊
    assert LAYER in client.get("/").get_data(as_text=True)
    assert "bg-squares--panel" in client.get("/staff/login").get_data(as_text=True)


def test_staff_and_admin_pages_also_have_the_layer(app):
    """使用者 2026-11-16：不只登入頁，全系統背景都要有；後台頁在樣式裡調淡。"""
    assert LAYER in app.test_client().get("/admin/login").get_data(as_text=True)
    teacher = logged_in(app, "teacher_syn")
    html = teacher.get("/teacher/dashboard", follow_redirects=True).get_data(as_text=True)
    assert 'data-staff-ui="teacher"' in html and html.count(LAYER) == 1
    staff = logged_in(app, "staff_syn")
    html = staff.get("/staff/dashboard", follow_redirects=True).get_data(as_text=True)
    assert 'data-staff-ui="staff"' in html and html.count(LAYER) == 1
    admin = logged_in(app, "admin_syn")
    html = admin.get("/admin/dashboard", follow_redirects=True).get_data(as_text=True)
    assert 'data-staff-ui="admin"' in html and html.count(LAYER) == 1
    assert "[data-staff-ui] .bg-squares" in CSS  # 後台更淡


def test_layer_stays_behind_content_and_does_not_block_clicks():
    rule = re.search(r"\.bg-squares \{(.*?)\}", CSS, re.S).group(1)
    assert "position: fixed" in rule
    assert "z-index: -1" in rule
    assert "pointer-events: none" in rule
    assert "overflow: hidden" in rule  # 手機不會被方塊撐出左右捲動


def test_animation_only_moves_transform():
    keyframes = re.search(r"@keyframes bg-square-rise \{(.*?)\n\}", CSS, re.S).group(1)
    props = set(re.findall(r"([a-z-]+)\s*:", keyframes))
    assert props == {"transform"}


def test_reduced_motion_stops_the_animation():
    """減少動態效果時方塊停住不動，但仍看得到（2026-11-17：使用者手機上完全看不到，改成停在原地）。"""
    block = re.search(r"@media \(prefers-reduced-motion: reduce\) \{(.*?)\n\}", CSS, re.S).group(1)
    assert "animation-play-state: paused" in block
    assert "display: none" not in block


def test_declining_the_tour_once_hides_it_everywhere():
    """導覽提示按一次「不用」，之後每一頁都不再出現（2026-11-17 使用者要求）。"""
    js = (ROOT / "app" / "static" / "js" / "components.js").read_text(encoding="utf-8")
    assert 'localStorage.setItem("tour-declined", "1")' in js
    assert "invite || declined()" in js
