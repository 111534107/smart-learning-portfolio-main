"""系統手冊（❓ 怎麼操作）與每頁網頁導覽。規格：引導卡片規格 1.5、Canva 第 21 頁、會議室 20261010-224756 #11 清單第 1 項。"""
import json
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

from app import create_app
from app.extensions import db
from app.models import AuditLog, StudentProfile, User
from app.services.journey_service import academic_year_of


COMPONENTS_JS = Path(__file__).resolve().parents[1] / "app" / "static" / "js" / "components.js"
DESIGN_SYSTEM = Path(__file__).resolve().parents[1] / "app" / "static" / "css" / "design-system.css"


def run_components_scenario(scenario):
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node 執行前端行為測試")
    harness = r"""
const scenario = process.argv[1];
const script = process.argv[2];
const documentListeners = new Map();
const timers = [];
const dispatched = [];
const classes = new Set();
let removed = false;
let tourQueries = 0;
let prevented = false;

global.setTimeout = (fn, delay) => { const timer = { fn, delay, cleared: false }; timers.push(timer); return timer; };
global.clearTimeout = (timer) => { if (timer) timer.cleared = true; };
global.performance = { now: () => 0 };
global.requestAnimationFrame = () => {};
global.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
global.sessionStorage = { getItem: () => null, setItem: () => {} };
global.CustomEvent = class { constructor(type) { this.type = type; } };
global.window = {
  matchMedia: () => ({ matches: true }),
  addEventListener: () => {},
  removeEventListener: () => {},
  location: { href: "" },
};

const closeListeners = new Map();
const closeButton = {
  hidden: false,
  disabled: false,
  focus() { document.activeElement = this; },
  addEventListener(type, fn) { closeListeners.set(type, fn); },
};
const number = { dataset: { countTo: "200" }, textContent: "200" };
const title = { focus() { document.activeElement = this; } };
const returnRoot = {
  classList: { add(name) { classes.add(name); } },
  querySelector(selector) { return selector === "[data-count-to]" ? number : closeButton; },
  querySelectorAll: () => [closeButton],
  contains(node) { return node === closeButton; },
  remove() { removed = true; },
};
const hiddenWalker = {
  ownerSVGElement: { getBoundingClientRect: () => ({ width: 0 }) },
};

global.document = {
  body: { dataset: { page: scenario.startsWith("tour-") ? "student-dashboard" : "other" } },
  documentElement: { dataset: {}, hasAttribute: () => false },
  activeElement: null,
  querySelectorAll(selector) {
    if (selector === "[data-return]") return scenario.startsWith("return-") ? [returnRoot] : [];
    if (selector === "[data-walker]") return scenario === "tour-early" ? [hiddenWalker] : [];
    if (selector === "[data-tour]") { tourQueries += 1; return []; }
    return [];
  },
  querySelector(selector) {
    if (selector === "[data-return]") return scenario.startsWith("return-") && !removed ? returnRoot : null;
    return null;
  },
  getElementById(id) { return id === "route-title" ? title : null; },
  addEventListener(type, fn) {
    const handlers = documentListeners.get(type) || [];
    handlers.push(fn);
    documentListeners.set(type, handlers);
  },
  removeEventListener(type, fn) {
    documentListeners.set(type, (documentListeners.get(type) || []).filter((handler) => handler !== fn));
  },
  dispatchEvent(event) {
    dispatched.push(event.type);
    [...(documentListeners.get(event.type) || [])].forEach((fn) => fn(event));
  },
};

require(script);

if (scenario.startsWith("return-")) {
  const initialFocus = document.activeElement === closeButton;
  const auto = timers.find((timer) => timer.delay === 4500);
  auto.fn();
  const stayedOpenWithFocus = !classes.has("is-leaving") && timers.filter((timer) => timer.delay === 4500).length === 2;
  document.dispatchEvent({ type: "keydown", key: "Tab", shiftKey: false, preventDefault() { prevented = true; } });
  const tabStayedInside = prevented && document.activeElement === closeButton;
  prevented = false;
  document.dispatchEvent({ type: "keydown", key: "Tab", shiftKey: true, preventDefault() { prevented = true; } });
  const shiftTabStayedInside = prevented && document.activeElement === closeButton;
  if (scenario === "return-escape") {
    document.dispatchEvent({ type: "keydown", key: "Escape", preventDefault() {} });
  } else {
    closeListeners.get("click")();
  }
  prevented = false;
  document.activeElement = closeButton;
  document.dispatchEvent({ type: "keydown", key: "Tab", shiftKey: false, preventDefault() { prevented = true; } });
  const fadeStillTrapsFocus = prevented && document.activeElement === closeButton;
  timers.filter((timer) => timer.delay === 600 && !timer.cleared).forEach((timer) => timer.fn());
  console.log(JSON.stringify({ initialFocus, stayedOpenWithFocus, tabStayedInside, shiftTabStayedInside, fadeStillTrapsFocus, removed, titleFocused: document.activeElement === title }));
} else if (scenario === "tour-early") {
  console.log(JSON.stringify({ walkedState: document.documentElement.dataset.journeyWalked, dispatched, tourQueries, fallbackCount: timers.filter((timer) => timer.delay === 6000).length }));
} else {
  const fallback = timers.find((timer) => timer.delay === 6000);
  if (scenario === "tour-delayed") document.dispatchEvent(new CustomEvent("journey:walked"));
  fallback.fn();
  console.log(JSON.stringify({ tourQueries, fallbackCleared: fallback.cleared }));
}
"""
    result = subprocess.run(
        [node, "-e", harness, scenario, str(COMPONENTS_JS)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


@pytest.fixture()
def client():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        user = User(username="stu", display_name="stu", role="student")
        user.set_password("pw")
        db.session.add(user)
        db.session.flush()
        db.session.add(StudentProfile(user_id=user.id, student_no="s1", admission_year=academic_year_of(date.today()) - 2))
        db.session.add(AuditLog(user_id=user.id, action="student.welcome_done"))
        db.session.commit()
    client = app.test_client()
    client.post("/login", data={"username": "stu", "password": "pw"})
    return client


def test_help_page_answers_common_questions_briefly(client):
    page = client.get("/help").get_data(as_text=True)
    questions = re.findall(r"<summary[^>]*>(.*?)</summary>", page, re.S)
    assert len(questions) >= 8
    assert any("證照" in q for q in questions)
    assert any("誰看得到" in q for q in questions)
    # 每個答案都短：一兩句話
    for answer in re.findall(r'<p class="help__answer">(.*?)</p>', page, re.S):
        assert len(re.sub(r"<[^>]+>", "", answer).strip()) <= 70, answer


def test_help_requires_login():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
    assert app.test_client().get("/help").status_code in (302, 401)


def test_masthead_links_to_help_and_tour(client):
    page = client.get("/student/dashboard").get_data(as_text=True)
    assert 'href="/help"' in page
    assert "data-tour-start" in page


@pytest.mark.parametrize("role, dashboard, page_name", [
    ("student", "/student/dashboard", "student-dashboard"),
    ("teacher", "/teacher/dashboard", "work-dashboard"),
    ("staff", "/staff/dashboard", "work-dashboard"),
    ("admin", "/admin/dashboard", "admin-dashboard"),
])
def test_help_replays_the_current_role_tour(role, dashboard, page_name):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        user = User(username=f"{role}_user", display_name=role, role=role)
        user.set_password("pw")
        db.session.add(user)
        db.session.commit()
    client = app.test_client()
    client.post("/login", data={"username": f"{role}_user", "password": "pw"})

    help_page = client.get("/help").get_data(as_text=True)
    tour_target = re.search(r'data-tour-replay-url="([^"]+)"', help_page)

    assert tour_target is not None
    assert tour_target.group(1) == f"{dashboard}?tour=1"
    destination = client.get(tour_target.group(1)).get_data(as_text=True)
    assert f'data-page="{page_name}"' in destination
    if role in {"teacher", "staff"}:
        assert f'data-work-role="{role}"' in destination
    assert len(re.findall(r'data-tour="([^" ]*[^\"]*)"', destination)) > 0


@pytest.mark.parametrize("close_action", ["escape", "button"])
def test_return_scene_keyboard_and_focus_contract(close_action):
    result = run_components_scenario(f"return-{close_action}")

    assert result == {
        "initialFocus": True,
        "stayedOpenWithFocus": True,
        "tabStayedInside": True,
        "shiftTabStayedInside": True,
        "fadeStillTrapsFocus": True,
        "removed": True,
        "titleFocused": True,
    }


def test_return_initial_focus_is_visible_without_animation_delay():
    css = DESIGN_SYSTEM.read_text(encoding="utf-8")

    assert re.search(r"\.return__go:focus\s*\{[^}]*animation:\s*none", css, re.S)
    assert re.search(r"\.return__go:focus\s*\{[^}]*opacity:\s*1", css, re.S)


def test_first_home_tour_waits_for_walker_with_six_second_fallback():
    early = run_components_scenario("tour-early")
    delayed = run_components_scenario("tour-delayed")
    fallback = run_components_scenario("tour-fallback")

    assert early == {
        "walkedState": "true",
        "dispatched": ["journey:walked"],
        "tourQueries": 1,
        "fallbackCount": 0,
    }
    assert delayed == {"tourQueries": 1, "fallbackCleared": True}
    assert fallback == {"tourQueries": 1, "fallbackCleared": True}


def test_student_visible_copy_uses_preparing_application_materials(monkeypatch):
    from app.content.help import HELP
    help_text = repr(HELP["student"])
    assert "做備審" not in help_text
    assert "準備備審資料" in help_text


@pytest.mark.parametrize("url, minimum", [
    ("/student/dashboard", 4),
    ("/student/learning-profile", 2),
    ("/student/portfolio", 2),
    ("/student/targets", 1),
])
def test_pages_have_short_tour_steps(client, url, minimum):
    page = client.get(url).get_data(as_text=True)
    steps = re.findall(r'data-tour="([^"]+)"', page)
    assert len(steps) >= minimum, url
    for text in steps:
        assert len(text) <= 30, text

def test_upload_page_guides_file_selection_and_submission(client):
    page = client.get('/student/learning-profile/upload').get_data(as_text=True)
    assert 'data-tour="選擇要上傳的成績單或證照檔案。"' in page
    assert 'data-tour="選好檔案後按上傳，再核對辨識結果。"' in page

def test_help_page_guides_search_and_questions(client):
    page = client.get('/help').get_data(as_text=True)
    assert 'data-tour="輸入關鍵字，搜尋想了解的操作。"' in page
    assert 'data-tour="點問題展開答案，再前往操作頁面。"' in page

def test_help_shows_transcript_animation_with_accessible_description(client):
    page = client.get('/help').get_data(as_text=True)
    assert '/static/img/howto/student-upload-transcript-labelled.gif' in page
    assert 'alt="上傳成績單、核對辨識結果並確認儲存的操作動畫"' in page

def test_help_animation_files_exist_and_fit_size_limit():
    from app.content.help import HELP
    static_dir = Path(__file__).resolve().parents[1] / 'app' / 'static' / 'img' / 'howto'
    gifs = [item['gif'] for sections in HELP.values() for section in sections
            for item in section['items'] if item.get('gif')]
    assert gifs
    for name in gifs:
        path = static_dir / name
        assert path.is_file(), name
        assert path.stat().st_size < 3 * 1024 * 1024, name

def test_student_files_and_activity_form_have_specific_tours(client):
    files = client.get('/student/files').get_data(as_text=True)
    assert 'data-tour="在這裡開啟上傳過的成績單與證照。"' in files
    assert 'data-tour="在這裡查看活動與經歷的佐證。"' in files
    form = client.get('/student/portfolio/new').get_data(as_text=True)
    assert 'data-tour="填寫這筆活動的類型、時間與內容。"' in form
    assert 'data-tour="資料核對無誤後，確認並儲存。"' in form
    assert 'data-tour="還沒寫完時，先存成草稿。"' in form


def test_attendance_page_guides_import_and_saved_totals(client):
    page = client.get('/student/attendance-records').get_data(as_text=True)
    assert 'data-tour="貼上單學期缺曠表格，再預覽核對。"' in page
    assert 'data-tour="或選擇校方列印的 PDF 讀取。"' in page
    assert 'data-tour="在這裡查看已確認儲存的學期合計。"' in page
