"""目標校系地圖放大縮小與彈出視窗（2026-11-16 使用者要求）：工具列、視窗骨架、排行列帶給視窗用的資料。僅為測試資料。"""
import re
from datetime import date
from pathlib import Path

import pytest

from app import create_app
from app.extensions import db
from app.models import StudentProfile, User
from app.services import school_directory, target_filters
from app.services.admission_service import import_seed_programs
from app.services.journey_service import academic_year_of

CONTENT = Path(__file__).resolve().parents[1] / "app" / "content"
ROW = re.compile(r'<li data-region="([^"]*)" data-school="([^"]+)"([^>]*)>\s*<details class="target-program" id="target-program-(\d+)"')


@pytest.fixture()
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        import_seed_programs()
        import_seed_programs(CONTENT / "admission_demo_national_116.csv")
        import_seed_programs(CONTENT / "admission_demo_night_private_115.csv")  # 私立學校：國立、私立篩選要有兩種值
        school_directory.import_defaults()
        user = User(username="stu", display_name="測試學生", role="student")
        user.set_password("pw")
        db.session.add(user)
        db.session.flush()
        db.session.add(StudentProfile(user_id=user.id, student_no="113534999", class_name="資管科三甲",
                                      admission_year=academic_year_of(date.today()) - 2))
        db.session.commit()
    yield app


def page_of(app, query=""):
    client = app.test_client()
    client.post("/login", data={"username": "stu", "password": "pw"})
    return client.get("/student/targets" + query).get_data(as_text=True)


def test_map_has_zoom_tools_and_full_view_button(app):
    page = page_of(app)
    tools = re.search(r'<div class="school-map__tools"[^>]*>.*?</div>', page, re.S).group(0)
    # 沒有 JavaScript 時不顯示（縮放靠腳本），腳本會拿掉 hidden
    assert "data-map-tools hidden" in tools
    assert 'data-map-zoom="in"' in tools and 'aria-label="放大地圖"' in tools
    assert 'data-map-zoom="out"' in tools and 'aria-label="縮小地圖"' in tools
    assert "data-map-full" in tools and "完整檢視" in tools
    # 整張地圖的範圍不變：東海岸、澎湖都在畫布內
    assert 'viewBox="0 0 410 560"' in page


def test_reset_button_and_tools_share_one_row(app):
    """回到全台灣與縮放工具放在同一列，不再疊在地圖上互相蓋住；沒選地區時回到全台灣是藏起來的。"""
    page = page_of(app)
    bar = re.search(r'<div class="school-map__bar">(.*?)<svg', page, re.S).group(1)
    assert "data-map-reset" in bar and "data-map-tools" in bar
    assert re.search(r'data-map-reset href="[^"]*"\s+hidden>', bar)
    region_page = page_of(app, "?region=北部")
    region_bar = re.search(r'<div class="school-map__bar">(.*?)<svg', region_page, re.S).group(1)
    assert not re.search(r'data-map-reset href="[^"]*"\s+hidden>', region_bar)


def test_popup_dialog_skeleton(app):
    page = page_of(app)
    dialog = re.search(r'<dialog class="map-sheet"[^>]*>.*?</dialog>', page, re.S).group(0)
    assert 'aria-labelledby="map-sheet-title"' in dialog
    assert 'id="map-sheet-title"' in dialog
    assert 'data-sheet-close aria-label="關閉視窗"' in dialog
    assert "data-sheet-body" in dialog
    # 視窗放在地圖區塊外面，裡面的點擊不會被地圖的切換腳本攔走
    assert page.index("</dialog>") > page.index('data-school-map')
    section_end = page.index("</section>", page.index("data-school-map"))
    assert page.index('<dialog class="map-sheet"') > section_end


def test_ranking_rows_carry_readiness_and_gap_hints(app):
    """彈出視窗用排行每一列的 data-*（準備度、還缺什麼、先補哪一項），和篩選選單共用同一份列，條件一定同步。"""
    page = page_of(app)
    rows = ROW.findall(page)
    assert rows
    for region, school, attrs, program_id in rows:
        assert re.search(r'data-readiness="(\d*)"', attrs)
        assert 'data-missing="' in attrs and 'data-next="' in attrs and re.search(r'data-gain="\d+"', attrs)
    # 新屬性不能放在 hidden 後面：B22 的測試與驗收靠「屬性字串以 hidden 結尾」判斷是否隱藏
    hidden_page = page_of(app, "?region=東部")
    hidden_rows = [attrs for region, _, attrs, _ in ROW.findall(hidden_page) if region != "東部"]
    assert hidden_rows and all(attrs.endswith(" hidden") for attrs in hidden_rows)


def test_filter_refresh_event_for_map(app):
    """篩選選單每次重算都通知地圖：縣市深淺與開著的視窗跟著更新。"""
    page = page_of(app)
    assert 'new CustomEvent("target-filter:refresh")' in page
    assert 'addEventListener("target-filter:refresh"' in page


def test_gap_hint_summarises_missing_and_priority():
    gap = {
        "missing_keys": ["credential", "competition"],
        "priority_id": 2,
        "items": [{"id": 1, "name": "在校成績", "gain": 5}, {"id": 2, "name": "專業證照", "gain": 30}],
    }
    hint = target_filters.gap_hint(gap)
    assert hint["next"] == "專業證照" and hint["gain"] == 30
    assert hint["missing"] == "、".join([target_filters_labels()["credential"], "競賽"])


def test_gap_hint_when_nothing_missing():
    assert target_filters.gap_hint({"missing_keys": [], "priority_id": None, "items": []}) == {
        "missing": "", "next": "", "gain": 0}


def target_filters_labels():
    from app.services.gap_service import ALL_LABELS
    return ALL_LABELS


def test_county_click_zooms_to_that_county(app):
    """使用者要求：點縣市放大到那個縣市本身，不是整個地區。"""
    page = page_of(app)
    assert "function countyBox(path)" in page
    assert "animateTo(countyBox(county));" in page


def test_pin_click_zooms_to_school_county(app):
    """使用者要求：點圓點也放大到那所學校所在的縣市。"""
    page = page_of(app)
    assert "countyName(path) === s.city" in page and "animateTo(countyBox(home));" in page


def test_phone_panel_leaves_room_for_zoomed_map(app):
    """手機面板先開到 60% 高，上方看得到放大後的縣市；點或拉把手展開到 88%。"""
    page = page_of(app)
    css = (Path(__file__).resolve().parents[1] / "app" / "static" / "css" / "student-v2" / "shell.css").read_text(encoding="utf-8")
    assert "height: 60vh; max-height: 60vh" in css and ".map-sheet.is-tall { height: 88vh" in css
    assert 'sheet.classList.toggle("is-tall")' in page


def test_ownership_filter_splits_national_and_private(app):
    """使用者要求：國立、私立篩選。選項來自資料，選「私立」後沒隱藏的列都是私立學校。"""
    assert target_filters.ownership_of("國立臺中科技大學") == "國立"
    assert target_filters.ownership_of("弘光科技大學") == "私立"
    assert target_filters.ownership_of("臺北市立大學") == "公立"
    page = page_of(app, "?ownership=私立")
    menu = re.search(r'<select name="ownership"[^>]*>.*?</select>', page, re.S).group(0)
    assert "國立私立都看" in menu and 'value="國立"' in menu and 'value="私立"' in menu
    shown = [(school, attrs) for _, school, attrs, _ in ROW.findall(page) if not attrs.endswith(" hidden")]
    assert shown and all(not school.startswith("國立") and 'data-f-ownership="私立"' in attrs for school, attrs in shown)
    hidden = [school for _, school, attrs, _ in ROW.findall(page) if attrs.endswith(" hidden")]
    assert any(school.startswith("國立") for school in hidden)



def test_map_side_has_national_private_toggle(app):
    """2026-11-18 使用者要求：地圖旁的「依地區找學校」也能切國立、私立，和篩選選單同一個參數。"""
    html = page_of(app)
    group = html.split("data-own-group", 1)[1].split("</div>", 1)[0]
    assert "國立私立都看" in group and ">國立<" in group and ">私立<" in group
    assert 'data-own="國立"' in html and 'data-own="私立"' in html
    only_national = page_of(app, "?ownership=國立")
    items = re.findall(r'<li class="school-list__item"[^>]*>', only_national)
    assert items
    for item in items:
        assert ('data-own="國立"' in item) != (" hidden" in item)
    pressed = only_national.split("data-own-group", 1)[1].split("</div>", 1)[0]
    assert re.search(r'data-own-button="國立"[^>]*aria-pressed="true"', pressed)
