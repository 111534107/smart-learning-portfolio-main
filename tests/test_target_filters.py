"""B22 目標校系篩選選單（2026-11-16）：選項來自資料、網址參數篩選、和地區學校一起用、亂填當沒選。僅為測試資料。"""
import re
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import create_app
from app.extensions import db
from app.models import AdmissionProgram, StudentProfile, User
from app.services import school_directory, target_filters
from app.services.admission_service import import_seed_programs
from app.services.journey_service import academic_year_of

CONTENT = Path(__file__).resolve().parents[1] / "app" / "content"


@pytest.fixture()
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        import_seed_programs()
        import_seed_programs(CONTENT / "admission_demo_national_116.csv")
        import_seed_programs(CONTENT / "admission_demo_night_private_115.csv")
        import_seed_programs(CONTENT / "admission_demo_dayapply_115.csv")
        school_directory.import_defaults()
        # 沒有加權資料的校系（簡章還沒整理）：用來測「有沒有加權資料」
        db.session.add(AdmissionProgram(program_code="TEST-NOWEIGHT", admission_year=115, school_name="國立臺中科技大學",
                                        department_name="測試用科系（僅為測試資料）", admission_category="日間部申請入學",
                                        status="published"))
        user = User(username="stu", display_name="測試學生", role="student")
        user.set_password("pw")
        db.session.add(user)
        db.session.flush()
        db.session.add(StudentProfile(user_id=user.id, student_no="113534999", class_name="資管科三甲",
                                      admission_year=academic_year_of(date.today()) - 2))
        db.session.commit()
    yield app


def login(app):
    client = app.test_client()
    client.post("/login", data={"username": "stu", "password": "pw"})
    return client


ROW = re.compile(r'<li data-region="[^"]*" data-school="([^"]+)"([^>]*)>\s*<details class="target-program" id="target-program-(\d+)"')


def rows(page):
    """排行每一列：(學校, 屬性字串, 是否隱藏)。"""
    return [(school, attrs, attrs.endswith(" hidden")) for school, attrs, _ in ROW.findall(page)]


def attr(attrs, name):
    match = re.search(rf'data-f-{name}="([^"]*)"', attrs)
    return match.group(1) if match else None


# ---------- 服務：選項從資料產生 ----------

def _program(category, department="資訊管理系", items=True):
    return SimpleNamespace(admission_category=category, department_name=department, items=[1] if items else [])


def test_options_come_from_data_and_single_value_menus_are_skipped():
    programs = {1: _program("管理類四"), 2: _program("電機類"), 3: _program("進修部單獨招生", items=False)}
    channels = {1: "二技技優甄審", 2: "二技技優甄審", 3: "進修部單獨招生"}
    facets = {pid: target_filters.program_facets(p, channels[pid], "") for pid, p in programs.items()}

    options = {o["name"]: o for o in target_filters.build_options(facets)}

    assert facets[3]["session"] == "進修部" and facets[1]["session"] == "日間部"
    assert facets[3]["group"] == ""  # 類別和管道同名就不算群類別
    assert [c["value"] for c in options["channel"]["choices"]] == ["二技技優甄審", "進修部單獨招生"]
    assert {c["value"]: c["count"] for c in options["group"]["choices"]} == {"管理類四": 1, "電機類": 1}
    assert {c["value"]: c["count"] for c in options["weights"]["choices"]} == {"有加權資料": 2, "還沒有加權資料": 1}
    assert "grade" not in options  # 沒有插入年級的資料，不顯示這個選單


def test_parse_ignores_values_not_in_menu():
    options = [{"name": "session", "choices": [{"value": "日間部", "count": 2}, {"value": "進修部", "count": 1}]}]

    assert target_filters.parse({"session": "進修部"}, options) == {"session": "進修部"}
    assert target_filters.parse({"session": "夜間部", "channel": "亂填"}, options) == {}


# ---------- 頁面 ----------

def test_page_shows_menus_built_from_programs(app):
    page = login(app).get("/student/targets").get_data(as_text=True)

    for name in ("region", "school", "channel", "group", "session", "weights"):
        assert f'name="{name}"' in page
    assert "進修部單獨招生" in page and "日間部申請入學" in page and "管理類四" in page
    assert 'name="grade"' not in page  # 二技分頁沒有插入年級
    assert "data-filter-shown" in page
    assert re.search(r'data-filter-clear hidden', page)  # 沒篩選時不顯示「清除篩選」


def test_session_filter_hides_day_programs_and_keeps_url_values(app):
    page = login(app).get("/student/targets?session=進修部").get_data(as_text=True)

    listed = rows(page)
    shown = [r for r in listed if not r[2]]
    assert shown and all(attr(a, "session") == "進修部" for _, a, _ in shown)
    assert any(attr(a, "session") == "日間部" and hidden and "data-filter-off" in a for _, a, hidden in listed)
    assert '<option value="進修部" data-label="進修部" selected>' in page
    assert f'data-filter-shown>{len(shown)}<' in page
    assert re.search(r'data-filter-clear>', page)  # 有篩選時出現「清除篩選」


def test_filters_combine_with_region_and_weights(app):
    client = login(app)
    page = client.get("/student/targets?region=中部&weights=還沒有加權資料").get_data(as_text=True)

    shown = [r for r in rows(page) if not r[2]]
    assert [school for school, _, _ in shown] == ["國立臺中科技大學"]
    assert "測試用科系" in page
    # 地圖的連結與學校表單保留篩選條件，切換學校時不會掉
    assert "weights=%E9%82%84" in page and '<input type="hidden" name="weights" value="還沒有加權資料">' in page


def test_channel_filter_and_unknown_values(app):
    client = login(app)
    page = client.get("/student/targets?channel=二技技優甄審").get_data(as_text=True)
    shown = [r for r in rows(page) if not r[2]]
    assert shown and all(attr(a, "channel") == "二技技優甄審" for _, a, _ in shown)

    weird = client.get("/student/targets?channel=不存在&session=夜間部&weights=x")
    assert weird.status_code == 200
    assert not any(hidden for _, _, hidden in rows(weird.get_data(as_text=True)))  # 亂填就當沒選


def test_no_match_shows_hint_to_relax(app):
    page = login(app).get("/student/targets?session=進修部&weights=還沒有加權資料").get_data(as_text=True)

    assert not [r for r in rows(page) if not r[2]]
    assert re.search(r'data-filter-empty>這些條件下沒有校系', page)
