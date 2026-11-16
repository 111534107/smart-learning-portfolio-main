"""學校名錄與目標校系地圖（2026-11-13）：學生依地區、學校找校系；管理員逐筆改、匯入匯出、檢查連結。"""
import io
from datetime import date

import pytest

from app import create_app
from app.extensions import db
from app.models import School, StudentProfile, User
from app.services import school_directory as directory
from app.services.admission_service import import_seed_programs
from app.services.journey_service import academic_year_of


@pytest.fixture()
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        import_seed_programs()
        directory.import_defaults()
        for username, role in (("stu", "student"), ("adm", "admin"), ("staff", "staff")):
            user = User(username=username, display_name=username, role=role)
            user.set_password("pw")
            db.session.add(user)
        db.session.flush()
        stu = User.query.filter_by(username="stu").one()
        db.session.add(StudentProfile(user_id=stu.id, student_no="113534999", class_name="資管科三甲",
                                      admission_year=academic_year_of(date.today()) - 2))
        db.session.commit()
    yield app


def login(app, username):
    client = app.test_client()
    path = {"adm": "/admin/login", "staff": "/staff/login"}.get(username, "/login")
    client.post(path, data={"username": username, "password": "pw"})
    return client


def test_default_data_has_regions_coordinates_and_three_links(app):
    with app.app_context():
        schools = School.query.all()
        # 2026-11-13 起含私立科大（招策會「全國技專校院」＋慈濟大學），不再只有 10 所國立
        assert len(schools) >= 60 and {s.region for s in schools} == {"北部", "中部", "南部", "東部"}
        assert any(not s.name.startswith("國立") for s in schools)
        assert all(s.website_url and s.latitude and s.city for s in schools)
        assert sum(1 for s in schools if s.admission_url) >= len(schools) - 15  # 官網找不到招生頁的留空，不自己猜
        x, y = directory.project(121.53846, 25.01682)  # 臺大在台北：地圖右上方
        assert 0 < x < directory.MAP_WIDTH and 0 < y < directory.MAP_HEIGHT * 0.15


def test_student_filters_by_region_and_sees_school_card(app):
    client = login(app, "stu")
    page = client.get("/student/targets").get_data(as_text=True)
    assert page.count('class="tw-county"') >= 19 and "school-map__pin" in page and "依地區找學校" in page

    import re
    central = client.get("/student/targets?region=中部").get_data(as_text=True)
    # 2026-11-13 起排行全部送到瀏覽器、不在本區的加 hidden（地圖不換頁切換用）：只看沒隱藏的列
    # 2026-11-16 B22 起每列多了篩選用的 data-f-* 屬性：只看有沒有 hidden
    rows = re.findall(r'<li data-region="([^"]*)" data-school="([^"]+)"([^>]*)>', central)
    shown = [(region, school) for region, school, rest in rows if not rest.endswith(" hidden")]
    hidden = [region for region, _, rest in rows if rest.endswith(" hidden")]
    assert shown and {region for region, _ in shown} == {"中部"} and hidden and "中部" not in set(hidden)

    card = client.get("/student/targets?school=國立臺中科技大學&region=中部").get_data(as_text=True)
    assert 'id="school-card"' in card
    for text in ("https://www.nutc.edu.tw/", "https://admission.nutc.edu.tw/", "在 Google 地圖開啟", "招生時程",
                 "https://im.nutc.edu.tw/"):  # 官網、招生網站、科系介紹＝至少三個網站
        assert text in card
    # 亂填地區或學校就當沒選
    assert client.get("/student/targets?region=火星&school=不存在大學").status_code == 200


def test_import_rejects_bad_rows_and_updates_existing(app):
    bad = "學校,地區,縣市,緯度,經度,官網,招生網站,確認日期\n某大學,西部,臺北市,25,121.5,https://a.edu.tw,,\n"
    with app.app_context():
        with pytest.raises(directory.ImportRejected, match="地區"):
            directory.import_schools(bad)
        db.session.rollback()
        swapped = bad.replace("西部", "北部").replace("25,121.5", "121.5,25")
        with pytest.raises(directory.ImportRejected, match="座標"):
            directory.import_schools(swapped)
        db.session.rollback()
        added, updated = directory.import_schools(
            "學校,地區,縣市,緯度,經度,官網,招生網站,確認日期\n國立臺灣大學,北部,臺北市,25.0,121.5,https://www.ntu.edu.tw/,,\n")
        assert (added, updated) == (0, 1)
        assert School.query.filter_by(name="國立臺灣大學").one().admission_url is None


def test_admin_edits_exports_imports_and_checks_links(app, monkeypatch):
    admin = login(app, "adm")
    page = admin.get("/admin/schools").get_data(as_text=True)
    assert "學校資料" in page and "匯出學校" in page and "檢查連結" in page

    with app.app_context():
        school_id = School.query.filter_by(name="國立中興大學").one().id
    admin.post(f"/admin/schools/{school_id}", data={"region": "中部", "city": "臺中市", "latitude": "24.12",
                                                   "longitude": "120.67", "website_url": "https://www.nchu.edu.tw/",
                                                   "admission_url": "https://recruit.nchu.edu.tw/", "checked_on": "2026-11-13"})
    admin.post(f"/admin/schools/{school_id}/departments", data={"department_name": "測試學系", "url": "https://test.nchu.edu.tw/"})
    with app.app_context():
        school = db.session.get(School, school_id)
        assert school.latitude == 24.12 and any(link.department_name == "測試學系" for link in school.department_links)

    exported = admin.get("/admin/schools/export/schools.csv")
    assert exported.status_code == 200 and "國立中興大學" in exported.get_data().decode("utf-8-sig")
    rows = exported.get_data().decode("utf-8-sig").replace("國立中興大學,中部,臺中市", "國立中興大學,中部,臺中市南區")
    admin.post("/admin/schools/import", data={"kind": "schools", "file": (io.BytesIO(rows.encode("utf-8-sig")), "s.csv")},
               content_type="multipart/form-data")
    with app.app_context():
        assert db.session.get(School, school_id).city == "臺中市南區"

    from app.services import form_library_service
    monkeypatch.setattr(form_library_service, "check_link",
                        lambda url, fetch=None: ("broken", "HTTP 404") if "test.nchu" in url else ("ok", "HTTP 200"))
    checked = admin.post("/admin/schools/check-links").get_data(as_text=True)
    assert "1 個要處理" in checked and "test.nchu.edu.tw" in checked


def test_only_admin_can_maintain(app):
    assert login(app, "staff").get("/admin/schools").status_code in (401, 403)
    assert login(app, "stu").post("/admin/schools/defaults").status_code in (401, 403)


def test_school_map_columns_can_shrink_so_nothing_is_cut_off():
    """2026-11-13 使用者回報手機與電腦版右邊被裁：欄位要用 minmax(0, …)、下拉選單寬度 100% 且可縮。"""
    from pathlib import Path
    css = (Path(__file__).resolve().parents[1] / "app/static/css/student-v2/shell.css").read_text(encoding="utf-8")
    assert "grid-template-columns: minmax(0, 340px) minmax(0, 1fr)" in css
    assert ".school-map__pick select { width: 100%; min-width: 0; max-width: 100%;" in css
    assert ".target-filter :is(select, input) { min-width: 0; max-width: 100%;" in css


def test_map_fits_canvas_and_region_zoom_has_reset_and_school_list(app):
    """2026-11-13：東海岸被裁（畫布太窄）；點地區要放大、有「回到全台灣」，沒選學校時右邊列學校清單。"""
    import re
    from pathlib import Path
    paths = (Path(__file__).resolve().parents[1] / "app/templates/partials/taiwan_map_paths.html").read_text(encoding="utf-8")
    xs = [float(x) for x in re.findall(r"[ML]([\d.]+),", paths)]
    assert 0 <= min(xs) and max(xs) <= directory.MAP_WIDTH  # 三貂角也在畫布內

    client = login(app, "stu")
    whole = client.get("/student/targets").get_data(as_text=True)
    assert f'viewBox="0 0 {directory.MAP_WIDTH} {directory.MAP_HEIGHT}"' in whole
    assert 'data-map-reset href="/student/targets?track=twotech&amp;major=all#target-explorer-title" hidden>' in whole
    assert 'class="school-list__item"' in whole and 'id="school-map-data"' in whole  # 腳本用的學校資料

    north = client.get("/student/targets?region=北部").get_data(as_text=True)
    assert f'viewBox="{directory.region_view_box("北部")}"' in north and "回到全台灣" in north
    assert 'data-map-reset href="/student/targets?track=twotech&amp;major=all#target-explorer-title">' in north  # 放大後顯示
    shown = re.findall(r'<li class="school-list__item" data-region="([^"]+)">', north)
    assert shown and set(shown) == {"北部"} and "<span data-list-region>北部</span>的二技學校" in north  # 只顯示北部的學校


def test_map_data_for_script_is_safe_json(app):
    """地圖腳本的資料放在 <script> 裡：要能解回 JSON，且不能出現 </ 提早結束標籤。"""
    import json
    import re
    page = login(app, "stu").get("/student/targets").get_data(as_text=True)
    raw = re.search(r'<script type="application/json" id="school-map-data">(.*?)</script>', page, re.S).group(1)
    assert "</" not in raw
    data = json.loads(raw)
    assert data["boxes"]["北部"] == directory.region_view_box("北部") and data["schools"][0]["programs"]
