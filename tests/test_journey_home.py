from datetime import date, datetime, timedelta, timezone

import pytest

from app import create_app
from app.extensions import db
from app.models import AuditLog, LearningCourseRecord, Portfolio, StudentProfile, User
from app.services.journey_home import RETURN_DAYS, journey_home
from app.services.journey_service import academic_year_of


@pytest.fixture()
def app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        user = User(username="stu", display_name="stu", role="student")
        user.set_password("pw")
        db.session.add(user)
        db.session.flush()
        db.session.add(StudentProfile(user_id=user.id, student_no="s1",
                                      admission_year=academic_year_of(date.today()) - 2))  # 專三
        db.session.add(AuditLog(user_id=user.id, action="student.welcome_done"))
        db.session.commit()
        yield app


def student():
    return User.query.filter_by(username="stu").one()


def test_five_stops_and_current_year(app):
    with app.test_request_context():
        view = journey_home(student())
    assert [stop["state"] for stop in view["stops"]] == ["past", "past", "now", "future", "future"]
    assert view["stops"][2]["label"] == "專三"


def test_this_year_puzzle_has_six_pieces_and_blanks(app):
    with app.test_request_context():
        user = student()
        db.session.add(LearningCourseRecord(student_id=user.id, school_year=3, course_name="系統分析",
                                            normalized_course_name="系統分析", score=80))
        db.session.add(Portfolio(student_id=user.id, title="資訊週", category="service", school_year=3))
        db.session.commit()
        view = journey_home(user)
    pieces = view["pieces"]
    assert len(pieces) == 6
    assert [p["key"] for p in pieces if p["filled"]] == ["grades", "service"]
    assert view["blanks"] == 4
    assert all(p["href"] for p in pieces if not p["filled"])


def test_past_year_counts(app):
    with app.test_request_context():
        user = student()
        db.session.add(Portfolio(student_id=user.id, title="迎新", category="activity", school_year=1))
        db.session.commit()
        view = journey_home(user)
    assert view["stops"][0]["count"] == 1


def test_return_scene_only_after_long_absence(app):
    now = datetime.now(timezone.utc)
    with app.test_request_context():
        user = student()
        assert journey_home(user, now=now)["away_days"] is None  # 沒有登入紀錄
        earlier = AuditLog(user_id=user.id, action="student.login", created_at=now - timedelta(days=10))
        db.session.add(earlier)
        db.session.add(AuditLog(user_id=user.id, action="student.login", created_at=now))
        db.session.commit()
        assert journey_home(user, now=now)["away_days"] is None  # 10 天前才來過
        earlier.created_at = now - timedelta(days=327)
        db.session.commit()
        view = journey_home(user, now=now)
    assert view["away_days"] == 327 >= RETURN_DAYS


def test_login_is_recorded_and_home_renders(app):
    client = app.test_client()
    client.post("/login", data={"username": "stu", "password": "pw"})
    with app.app_context():
        assert AuditLog.query.filter_by(action="student.login").count() == 1

    page = client.get("/student/dashboard").get_data(as_text=True)
    assert page.count("data-stop=") == 5
    assert 'aria-current="step"' in page
    assert page.count("data-piece=") == 6
    assert "你在這裡" in page
    assert "data-return" not in page


def test_return_scene_shows_once_per_login(app):
    client = app.test_client()
    with app.app_context():
        user = student()
        db.session.add(AuditLog(user_id=user.id, action="student.login",
                                created_at=datetime.now(timezone.utc) - timedelta(days=200)))
        db.session.commit()
    client.post("/login", data={"username": "stu", "password": "pw"})

    page = client.get("/student/dashboard").get_data(as_text=True)
    assert 'data-return role="dialog" aria-modal="true"' in page
    assert 'id="route-title" class="route-map__title" tabindex="-1"' in page
    assert "data-return" not in client.get("/student/dashboard").get_data(as_text=True)


def test_home_has_walker_and_four_places(app):
    client = app.test_client()
    client.post("/login", data={"username": "stu", "password": "pw"})
    page = client.get("/student/dashboard").get_data(as_text=True)

    assert "data-walker" in page
    assert page.count("data-place=") == 4
    for href in ("/student/learning-profile", "/student/portfolio", "/student/targets"):
        assert f'href="{href}"' in page


def test_blank_pieces_are_draggable(app):
    client = app.test_client()
    client.post("/login", data={"username": "stu", "password": "pw"})
    page = client.get("/student/dashboard").get_data(as_text=True)

    assert page.count("data-drag-piece") == 6  # 專三沒有資料：六塊都是洞，各有一片散在旁邊可以拖
    assert page.count("data-hole=") == 6
    assert "data-board" in page


def test_jigsaw_pieces_interlock(app):
    """六片拼圖的邊要咬合：相鄰兩片共用的那條邊，一片凸出、另一片凹進去。"""
    from app.services.journey_home import jigsaw_pieces
    pieces = jigsaw_pieces()
    assert len(pieces) == 6
    assert all(piece["d"].startswith("M") and piece["d"].endswith("Z") for piece in pieces)
    # 3×2，每片 200×200
    assert [(p["x"], p["y"]) for p in pieces] == [(0, 0), (200, 0), (400, 0), (0, 200), (200, 200), (400, 200)]
    assert pieces[0]["d"] != pieces[1]["d"]


def test_filled_pieces_show_the_picture(app):
    with app.test_request_context():
        user = student()
        db.session.add(Portfolio(student_id=user.id, title="資訊週", category="service", school_year=3))
        db.session.commit()
    client = app.test_client()
    client.post("/login", data={"username": "stu", "password": "pw"})
    page = client.get("/student/dashboard").get_data(as_text=True)
    assert page.count("data-filled") == 1
    assert page.count("data-drag-piece") == 5
    assert 'id="year-scene"' in page


def test_mobile_route_list_and_place_grid(app):
    client = app.test_client()
    client.post("/login", data={"username": "stu", "password": "pw"})
    page = client.get("/student/dashboard").get_data(as_text=True)
    assert page.count("route-list__stop ") == 5
    assert page.count("place-grid__item") == 4
    assert "你在這裡</span>" in page


def test_summary_stats_and_today_tasks(app):
    """Canva 第 11 頁：今天先完成哪一步＋五年累積、待處理、最近成果。"""
    with app.test_request_context():
        user = student()
        db.session.add(Portfolio(student_id=user.id, title="迎新", category="activity", school_year=1, status="confirmed"))
        db.session.add(Portfolio(student_id=user.id, title="資訊週志工", category="service", school_year=3))  # 草稿
        db.session.commit()
        view = journey_home(user)
    # 走過專一到專三：3 年 × 6 類 = 18 格，有資料的是專一活動、專三服務 → 2/18
    assert view["summary"]["percent"] == round(2 / 18 * 100)
    assert view["summary"]["pending"] == 1
    assert view["summary"]["latest"] == "資訊週志工"

    client = app.test_client()
    client.post("/login", data={"username": "stu", "password": "pw"})
    page = client.get("/student/dashboard").get_data(as_text=True)
    assert "今天先完成哪一步" in page
    assert "五年累積" in page and "待處理" in page and "最近成果" in page
    assert "只是累積比例，不是錄取機率" in page


def test_folders_drawer_comes_before_the_puzzle(app):
    """五年資料夾往前放：在「今天先完成哪一步」之後、拼圖之前，不用捲過整個拼圖才看得到。"""
    client = app.test_client()
    client.post("/login", data={"username": "stu", "password": "pw"})
    page = client.get("/student/dashboard").get_data(as_text=True)
    assert page.index('id="today-title"') < page.index('id="folders"') < page.index('class="year-puzzle"')


def test_loose_pieces_open_the_matching_upload_page(app):
    """成績單與證照已分兩頁：成績、證照那兩片直接開對應類型的上傳頁。"""
    client = app.test_client()
    client.post("/login", data={"username": "stu", "password": "pw"})
    page = client.get("/student/dashboard").get_data(as_text=True)
    assert 'href="/student/learning-profile/upload?type=transcript" data-loose="grades"' in page
    assert 'href="/student/learning-profile/upload?type=credential" data-loose="credential"' in page


def test_loose_pieces_sit_in_a_compact_tray():
    """散落的片在旁邊是小尺寸（一列六格、手機三格），拖起來才放大到洞的大小；不再用和洞一樣大的片撐出很長的區塊。"""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "app" / "static"
    css = (root / "css" / "design-system.css").read_text(encoding="utf-8")
    js = (root / "js" / "components.js").read_text(encoding="utf-8")
    assert ".jig__tray { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr));" in css
    assert "scale(${grow})" in js
