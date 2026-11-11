"""學生頂端列與首頁第一屏改版（2026-11-08，合成資料）。

使用者回報系統不直覺：導覽列 8 項＋通知／導覽／字體／怎麼操作／登出擠成一排，視窗不夠寬就整頁左右捲動；
首頁一打開是五年路線圖，「今天先完成哪一步」要捲到最下面才看得到。
改成：主選單 5 項（我的資料＝成績單＋證照＋活動與經歷，頁面上方有分頁標籤），其他收進帳號選單，通知留在外面；
首頁第一屏先放下一步，路線圖保留在下面。實際寬度（768／900／1280、手機）另在瀏覽器量過，見開發日誌。
"""
import re
from pathlib import Path

import pytest

from app import create_app
from app.extensions import db
from app.models import User

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app" / "static" / "css" / "design-system.css").read_text(encoding="utf-8")
JS = (ROOT / "app" / "static" / "js" / "components.js").read_text(encoding="utf-8")


@pytest.fixture()
def client(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        student = User(username="student_syn", display_name="合成學生", role="student")
        student.set_password("pw")
        db.session.add(student)
        db.session.commit()
    client = app.test_client()
    client.post("/login", data={"username": "student_syn", "password": "pw"})
    return client


def header(html):
    return re.search(r'<header class="masthead masthead--app masthead--student">.*?</header>', html, re.S).group(0)


def mainnav_labels(html):
    nav = re.search(r'<nav class="mainnav".*?</nav>', html, re.S).group(0)
    return [re.sub(r"<[^>]+>|\s+\d+$", "", label).strip() for label in re.findall(r"<a [^>]*>(.*?)</a>", nav, re.S)]


def test_main_menu_has_five_items(client):
    html = client.get("/student/dashboard").get_data(as_text=True)

    assert mainnav_labels(html) == ["我的五年", "我的資料", "畢業門檻", "目標與備審", "我的待辦"]


def test_tools_are_in_the_account_menu_and_notifications_stay_outside(client):
    top = header(client.get("/student/dashboard").get_data(as_text=True))
    nav = re.search(r'<nav class="mainnav".*?</nav>', top, re.S).group(0)
    panel = re.search(r'<div class="account-menu__panel" id="account-menu-panel" hidden>.*?</form>\s*</div>', top, re.S).group(0)

    assert 'class="account-menu__button" data-menu-toggle aria-expanded="false" aria-controls="account-menu-panel"' in top
    # 2026-11-11 學生端 v2：字體大小改成滑桿，由 js/student-v2.js 插在帳號名稱下面
    for piece in ("data-tour-start", 'href="/help"', 'action="/logout"'):
        assert piece in panel, piece
    assert "通知" not in nav
    assert 'class="snav-bell" href="/notifications"' in top


def test_mobile_menu_button_controls_the_main_menu(client):
    top = header(client.get("/student/dashboard").get_data(as_text=True))

    assert re.search(r'<button type="button" class="snav-toggle" data-menu-toggle aria-expanded="false" aria-controls="student-mainnav">', top)
    assert '<nav class="mainnav" id="student-mainnav" aria-label="主要導覽">' in top


@pytest.mark.parametrize("path, current", [
    ("/student/learning-profile", "成績單"),
    ("/student/learning-profile/credentials", "證照"),
    ("/student/portfolio", "活動與經歷"),
    ("/student/portfolio/new", "活動與經歷"),
])
def test_my_data_pages_show_tabs_with_the_current_one_marked(client, path, current):
    html = client.get(path).get_data(as_text=True)
    tabs = re.search(r'<nav class="subnav" aria-label="我的資料">.*?</nav>', html, re.S).group(0)

    assert re.findall(r'aria-current="page">([^<]+)</a>', tabs) == [current]
    for label in ("成績單", "證照", "活動與經歷"):
        assert f">{label}</a>" in tabs
    assert 'aria-current="true">我的資料</a>' in header(html)


def test_other_pages_have_no_my_data_tabs(client):
    for path in ("/student/dashboard", "/student/graduation-check"):
        assert 'class="subnav"' not in client.get(path).get_data(as_text=True), path


def test_home_puts_the_next_step_before_the_route_map(client):
    html = client.get("/student/dashboard").get_data(as_text=True)

    today = html.index('class="today"')
    assert today < html.index('id="route-title"') < html.index('id="today-title"') < html.index('class="route-map"')
    first_action = re.search(r'class="guide-card guide-card--[^"]+"|class="next-card"', html[today:])
    assert first_action and today + first_action.start() < html.index('class="route-map"')


def test_css_keeps_the_header_on_one_row_and_folds_on_phones():
    # 11-08 起老師、科辦、管理員共用同一套頂端列，class 統一為 .masthead--app
    assert ".masthead--app .masthead__inner { gap: 1rem; flex-wrap: nowrap; }" in CSS
    assert '.js .masthead--app .snav-toggle[aria-expanded="false"] + .mainnav { display: none; }' in CSS
    assert ".account-menu__panel[hidden] { display: none; }" in CSS
    # 舊規則（900px 以下主選單整排可左右捲動、520px 以下排成五格）已拿掉
    assert ".mainnav { order: 3; width: 100%; margin: 0; overflow-x: auto; }" not in CSS


def test_menu_script_handles_escape_and_outside_clicks():
    block = JS[JS.index('document.querySelectorAll("[data-menu-toggle]")'):]
    block = block[:block.index("})();")]
    assert 'toggle.setAttribute("aria-expanded", String(open))' in block
    assert 'event.key !== "Escape"' in block and "toggle.focus()" in block
    assert 'document.addEventListener("click"' in block


def test_student_pages_load_v2_shell_and_apply_theme_before_drawing(client):
    """學生端 v2（2026-11-11）：學生頁載入 student-v2 樣式，head 先套用深淺色、字體，且不留全域變數。"""
    html = client.get("/student/dashboard").get_data(as_text=True)
    head = html.split("</head>")[0]
    assert 'data-ui="student-v2"' in html.split("<head>")[0]
    for name in ("tokens.css", "shell.css", "ocr.css"):
        assert f"css/student-v2/{name}" in head
    assert 'localStorage.getItem("ui-theme")' in head
    assert "(function () {" in head.split('localStorage.getItem("ui-theme")')[0].rsplit("<script>", 1)[1]
    assert "js/student-v2.js" in html
