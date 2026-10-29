import re
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
    assert page.count("data-make-piece=") == 6
    assert "你在這裡" in page
    # 標題帶學生姓名，導師或組員看畫面時才知道是誰
    assert '<span class="route-map__name">stu</span>・' in page
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
    # 走過專一到專三：3 年 × 6 類 = 18 格，只有已確認的專一活動計入。
    assert view["summary"]["percent"] == round(1 / 18 * 100)
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


def _dashboard(app):
    client = app.test_client()
    client.post("/login", data={"username": "stu", "password": "pw"})
    return client.get("/student/dashboard").get_data(as_text=True)


# ---------- 五年拼圖桌（試用版）----------

def _journey_full(per_slot, grade):
    """假的 journey：五年 × 六類，每格 per_slot 筆。"""
    from app.services.journey_service import CATEGORY_KEYS, GRADE_LABELS
    years = [{"grade": g, "label": GRADE_LABELS[g], "count": 0,
              "categories": {key: [{"title": f"{g}{key}{n}"} for n in range(per_slot)] for key in CATEGORY_KEYS}}
             for g in range(1, 6)]
    return {"current_grade": grade, "years": years}


def test_every_record_in_five_years_is_one_piece(app):
    with app.test_request_context():
        user = student()
        db.session.add(Portfolio(student_id=user.id, title="迎新", category="activity", school_year=1, status="confirmed"))
        db.session.add(Portfolio(student_id=user.id, title="資訊週", category="service", school_year=3, status="confirmed"))
        db.session.add(LearningCourseRecord(student_id=user.id, school_year=3, course_name="系統分析",
                                            normalized_course_name="系統分析", score=80))
        db.session.commit()
        table = journey_home(user)["table"]
    assert table["count"] == 3
    assert [(p["key"], p["grade_label"], p["title"]) for p in table["pieces"]] == [
        ("activity", "專一", "迎新"), ("grades", "專三", "系統分析"), ("service", "專三", "資訊週")]
    assert len({p["id"] for p in table["pieces"]}) == 3


def test_unconfirmed_record_does_not_complete_a_puzzle_piece(app):
    with app.test_request_context():
        user = student()
        draft = Portfolio(student_id=user.id, title="待確認活動", category="activity", school_year=1, status="draft")
        db.session.add(draft)
        db.session.commit()
        assert journey_home(user)["table"]["count"] == 0
        assert journey_home(user)["summary"]["percent"] == 0
        assert next(m for m in journey_home(user)["makers"] if m["key"] == "activity")["complete"] is False
        draft.status = "confirmed"
        db.session.commit()
        assert journey_home(user)["table"]["count"] == 1
        assert journey_home(user)["summary"]["percent"] > 0
        assert next(m for m in journey_home(user)["makers"] if m["key"] == "activity")["complete"] is True


def test_piece_positions_are_stable_and_on_the_table_edges(app):
    with app.test_request_context():
        small = journey_home(student(), journey=_journey_full(1, 3))["table"]
        big = journey_home(student(), journey=_journey_full(2, 3))["table"]
    assert big["count"] == 60
    by_id = {p["id"]: p for p in big["pieces"]}
    for piece in small["pieces"]:  # 同一筆資料：片變多了，位置和角度也不變
        same = by_id[piece["id"]]
        assert (piece["x"], piece["y"], piece["mx"], piece["my"], piece["turn"]) == (same["x"], same["y"], same["mx"], same["my"], same["turn"])
    for piece in big["pieces"]:
        assert -40 <= piece["turn"] <= 40
        for x, y in ((piece["x"], piece["y"]), (piece["mx"], piece["my"])):
            assert 0 < x < 100 and 0 < y < 100
        # 中間留空：電腦版、手機版桌子的正中央都沒有片
        assert not (35 < piece["x"] < 65 and 35 < piece["y"] < 65)
        assert not (30 < piece["mx"] < 70 and 25 < piece["my"] < 75)


def test_assembled_pieces_make_an_exact_rectangle(app):
    """拼好時的格子剛好填滿一塊長方形：每列寬度加起來等於整張圖寬。"""
    from app.services.journey_home import _rows_for
    for count in (1, 2, 5, 7, 13, 30, 60, 61):
        rows = _rows_for(count)
        assert sum(rows) == count
    with app.test_request_context():
        table = journey_home(student(), journey=_journey_full(1, 3))["table"]
    assert table["count"] == 30
    cells = {(p["cx"], p["cy"]) for p in table["pieces"]}
    assert len(cells) == 30
    assert all(0 < p["cx"] < table["scene_w"] and 0 < p["cy"] < table["scene_h"] for p in table["pieces"])
    assert all(p["d"].startswith("M") and p["d"].endswith("Z") for p in table["pieces"])


def test_home_table_renders_pieces_buttons_and_count(app, monkeypatch):
    import re
    from app.routes import main as main_routes
    with app.app_context():  # 專五：自傳到專五才開放，按鈕才會是可按的連結
        student().student_profile.admission_year = academic_year_of(date.today()) - 4
        db.session.commit()
    monkeypatch.setattr(main_routes, "journey_home",
                        lambda user, journey=None, now=None: journey_home(user, journey=_journey_full(1, 3), now=now))
    page = _dashboard(app)
    assert page.count("data-table-piece=") == 30
    assert "已收集 <b class=\"mono\">30</b> 片" in page
    assert 'id="year-scene"' in page
    clip_ids = re.findall(r'<clipPath id="([^"]+)"', page)
    assert len(clip_ids) == len(set(clip_ids))
    assert 'href="/student/learning-profile/upload?type=transcript" data-make-piece="grades"' in page
    assert 'href="/student/learning-profile/upload?type=credential" data-make-piece="credential"' in page
    assert 'href="/student/portfolio/new?category=leadership" data-make-piece="leadership"' in page
    assert '<a class="button" href="/student/autobiography" data-assemble>' in page  # 沒有 JS 也是一般連結
    for gone in ("還差", "拼圖完成", "data-board-slot", "data-loose"):
        assert gone not in page.split('class="year-puzzle"', 1)[1].split('</section>', 1)[0]
    assert "錄取保證" not in page


def test_empty_table_invites_first_piece(app):
    page = _dashboard(app)
    assert "按上面的按鈕，做出第一片拼圖" in page
    assert re.search(r"已收集\s*<b[^>]*>0</b>\s*片", page)
    assert not re.search(r"<a\b[^>]*\bdata-assemble\b", page)  # 0 片：按鈕停用，不是連結
    assert re.search(r'<span\b[^>]*aria-disabled="true"[^>]*>請小助手拼好拼圖', page)


def test_grade_one_assemble_button_shows_open_note(app, monkeypatch):
    from app.routes import main as main_routes
    with app.app_context():
        profile = student().student_profile
        profile.admission_year = academic_year_of(date.today())  # 專一
        db.session.commit()
    monkeypatch.setattr(main_routes, "journey_home",
                        lambda user, journey=None, now=None: journey_home(user, journey=_journey_full(1, 1), now=now))
    page = _dashboard(app)
    assert "專五開放" in page
    assert not re.search(r"<a\b[^>]*\bdata-assemble\b", page)
    assert 'href="/student/autobiography"' not in page


def test_grade_three_assemble_button_is_disabled_until_grade_five(app, monkeypatch):
    from app.routes import main as main_routes
    with app.app_context():
        profile = student().student_profile
        profile.admission_year = academic_year_of(date.today()) - 2  # 專三
        db.session.commit()
    monkeypatch.setattr(main_routes, "journey_home",
                        lambda user, journey=None, now=None: journey_home(user, journey=_journey_full(1, 1), now=now))
    page = _dashboard(app)
    assert "專五開放生成自傳" in page
    assert not re.search(r"<a[^>]*data-assemble", page)


def test_renaming_a_record_keeps_its_piece_in_place(app):
    """片的 id 用資料庫編號：改標題後位置、角度、id 都不變（不會重播落下）。"""
    with app.test_request_context():
        user = student()
        record = Portfolio(student_id=user.id, title="資訊週", category="service", school_year=3, status="confirmed")
        db.session.add(record)
        db.session.commit()
        before = journey_home(user)["table"]["pieces"][0]
        record.title = "資訊週志工（改名）"
        db.session.commit()
        after = journey_home(user)["table"]["pieces"][0]
    assert before["id"] == after["id"] == f"portfolio-{record.id}"
    assert (before["x"], before["y"], before["mx"], before["my"], before["turn"]) == (after["x"], after["y"], after["mx"], after["my"], after["turn"])
    assert after["title"] == "資訊週志工（改名）"


def test_piece_titles_are_escaped(app):
    with app.test_request_context():
        user = student()
        db.session.add(Portfolio(student_id=user.id, title='<script>alert(1)</script> "引號"', category="activity", school_year=3, status="confirmed"))
        db.session.commit()
    page = _dashboard(app)
    table = page.split("data-ptable", 1)[1].split('class="ptable-actions"', 1)[0]
    assert "<script>alert(1)" not in table
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in table
    assert '"引號"' not in table and "&#34;引號&#34;" in table


def test_150_pieces_render_without_per_piece_filters(app, monkeypatch):
    """片很多（150 片）時頁面照常：每片都畫出來、clipPath 不重複；噪點濾鏡只在拼好的整張圖上用一次。"""
    from app.routes import main as main_routes
    monkeypatch.setattr(main_routes, "journey_home",
                        lambda user, journey=None, now=None: journey_home(user, journey=_journey_full(5, 3), now=now))
    page = _dashboard(app)
    assert page.count("data-table-piece=") == 150
    clip_ids = re.findall(r'<clipPath id="([^"]+)"', page)
    assert len(clip_ids) == len(set(clip_ids)) >= 150
    assert page.count('filter="url(#ts-grain)"') == 1
    scene = page.split('<g id="year-scene">', 1)[1].split("</defs>", 1)[0]
    assert "filter=" not in scene
