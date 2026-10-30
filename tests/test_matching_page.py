"""推薦排序頁的細項：只列登入學生本人的「已符合」與「缺少」。"""
from datetime import date

import pytest

from app import create_app
from app.extensions import db
from app.models import AdmissionProgram, AdmissionRequirementItem, CredentialRecord, MatchFilterOption, StudentProfile, User


@pytest.fixture()
def site():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        mine = _student("stu")
        other = _student("other")
        # 登入的這位有證照、另一位什麼都沒有：若路由改讀別人的資料，結果會整個不同
        db.session.add(CredentialRecord(student_id=mine.id, credential_name="我的證照", issue_date=date(2025, 3, 1)))
        program = _program("900001", "公開大學", "published", [
            ("證照證明", 50, "credential"), ("競賽成果", 30, "competition"), ("綜合成果", 20, "credential,competition")])
        candidate = _program("900002", "候選大學", "candidate", [("證照證明", 100, "credential")])
        db.session.commit()
        app.config["_ids"] = {"program": program.id, "candidate": candidate.id, "other": other.id, "mine": mine.id}
    yield app


def _student(username):
    user = User(username=username, display_name=username, role="student")
    user.set_password("pw")
    db.session.add(user)
    db.session.flush()
    db.session.add(StudentProfile(user_id=user.id, student_no=username, class_name="資管科五甲", admission_year=111))
    db.session.flush()
    return user


def _program(code, school, status, items):
    program = AdmissionProgram(program_code=code, admission_year=116, school_name=school,
                               department_name="資管系", status=status)
    for order, (name, weight, keys) in enumerate(items):
        program.items.append(AdmissionRequirementItem(
            source_item_name=name, weight_percent=weight, mapped_categories=keys, sort_order=order))
    db.session.add(program)
    db.session.flush()
    return program


def _login(app, username="stu"):
    client = app.test_client()
    client.post("/login", data={"username": username, "password": "pw"})
    return client


def _columns(html):
    have = html[html.index("<h3>已符合</h3>"):html.index("<h3>缺少</h3>")]
    missing = html[html.index("<h3>缺少</h3>"):]
    return have, missing


def test_matching_detail_shows_have_and_missing(site):
    pid = site.config["_ids"]["program"]
    html = _login(site).get(f"/student/matching/{pid}").get_data(as_text=True)
    have, missing = _columns(html)

    # 10-30 新規則：證照 1 筆只算一半 → 50×0.5 + 30×0 + 20×0.25 = 30%
    assert "證照證明（部分）" in have
    assert "競賽成果" in missing and "競賽成果" not in have
    assert "準備度 30%（建議值）" in html
    assert "錄取保證" not in html


def test_matching_detail_orders_missing_items_by_gain_with_links(site):
    pid = site.config["_ids"]["program"]
    html = _login(site).get(f"/student/matching/{pid}").get_data(as_text=True)
    _, missing = _columns(html)

    # 補滿可加：競賽 30% ＞ 證照 25% ＞ 綜合 15%，第一條標「先做這個」
    assert "先做這個：</b>競賽成果" in missing
    assert missing.index("競賽成果") < missing.index("證照證明") < missing.index("綜合成果")
    assert "補滿可加 30%" in missing
    assert "去補 →" in missing and "/student/portfolio/new?category=competition" in missing


def test_matching_detail_marks_partial_items_in_have_column(site):
    pid = site.config["_ids"]["program"]
    have, missing = _columns(_login(site).get(f"/student/matching/{pid}").get_data(as_text=True))

    assert "綜合成果（部分）" in have
    assert "證照證明（部分）" in have  # 只有 1 張證照，還沒滿
    assert "綜合成果" in missing  # 還缺的競賽仍列在缺少


def test_matching_list_has_inline_detail_and_link(site):
    ids = site.config["_ids"]
    html = _login(site).get("/student/matching").get_data(as_text=True)

    assert "<details" in html and "已符合" in html and "缺少" in html
    assert f"/student/matching/{ids['program']}" in html


def test_matching_detail_owner_only(site):
    ids = site.config["_ids"]
    client = _login(site)

    # 未公開（候選）的校系沒有細項頁
    assert client.get(f"/student/matching/{ids['candidate']}").status_code == 404

    # 帶別人（什麼都沒有）的學生編號，仍只看到登入者自己的證照：證照證明在已符合、準備度 60%
    html = client.get(f"/student/matching/{ids['program']}?student_id={ids['other']}").get_data(as_text=True)
    have, missing = _columns(html)
    assert "證照證明（部分）" in have
    assert "準備度 30%（建議值）" in html
    assert "準備度 0%" not in html


def test_matching_detail_requires_student_login(site):
    response = site.test_client().get(f"/student/matching/{site.config['_ids']['program']}")

    assert response.status_code in (302, 401, 403)


# ---- C1：篩選與圖表切換 ----

def _add_extra_programs(app):
    """再加兩個公開校系：企管系（四技）與資工系（二技），用來看篩選是否只留下符合的列。"""
    with app.app_context():
        for code, school, dept, category in (("900003", "企管大學", "企管系", "四技"), ("900004", "二技大學", "資工系", "二技")):
            program = AdmissionProgram(program_code=code, admission_year=116, school_name=school,
                                       department_name=dept, admission_category=category, status="published")
            program.items.append(AdmissionRequirementItem(
                source_item_name="證照證明", weight_percent=100, mapped_categories="credential", sort_order=0))
            db.session.add(program)
        db.session.commit()


def _add_options(app, *options):
    with app.app_context():
        for category, label, value, active in options:
            db.session.add(MatchFilterOption(category=category, label=label, value=value, sort_order=1, is_active=active))
        db.session.commit()


def _force_status(monkeypatch, statuses):
    """把指定學校的狀態換掉，才能測「是否可報」篩選（真實條件來自設定檔）。"""
    from app.routes import student as student_routes
    real = student_routes.rank_programs

    def fake(user, programs, *args, **kwargs):
        rows = real(user, programs, *args, **kwargs)
        for row in rows:
            row["status"] = statuses.get(row["program"].school_name, row["status"])
            row["status_label"] = row["status"]
        return rows

    monkeypatch.setattr(student_routes, "rank_programs", fake)


def _schools(html):
    return [name for name in ("公開大學", "企管大學", "二技大學") if f"{name} " in html]


def test_matching_filter_by_eligibility(site, monkeypatch):
    _add_extra_programs(site)
    _force_status(monkeypatch, {"公開大學": "eligible", "企管大學": "ineligible", "二技大學": "needs_check"})

    html = _login(site).get("/student/matching?eligible=ineligible").get_data(as_text=True)

    assert _schools(html) == ["企管大學"]


def test_matching_filter_by_department(site):
    _add_extra_programs(site)

    html = _login(site).get("/student/matching?department=企管").get_data(as_text=True)

    assert _schools(html) == ["企管大學"]


def test_matching_filter_by_level(site):
    _add_extra_programs(site)

    html = _login(site).get("/student/matching?level=二技").get_data(as_text=True)

    assert _schools(html) == ["二技大學"]


def test_matching_no_filter_shows_all(site):
    _add_extra_programs(site)

    html = _login(site).get("/student/matching").get_data(as_text=True)

    assert set(_schools(html)) == {"公開大學", "企管大學", "二技大學"}


def test_matching_filter_without_match_shows_empty_message(site):
    html = _login(site).get("/student/matching?department=不存在的科系").get_data(as_text=True)

    assert "沒有符合的校系" in html
    assert "公開大學" not in html.split("沒有符合的校系")[0].split("<ol")[-1]


def test_matching_filter_selects_come_from_active_options(site):
    _add_options(site, ("department", "資管系", "資管", True), ("department", "停用科系", "停用科", False),
                 ("level", "四技", "四技", True))

    html = _login(site).get("/student/matching").get_data(as_text=True)

    assert 'name="department"' in html and "資管系" in html
    assert "停用科系" not in html
    assert 'name="level"' in html
    assert 'name="eligible"' not in html  # 這類沒有選項就不顯示
    assert 'name="region"' not in html  # 地區尚無資料，不顯示


def test_matching_chart_defaults_to_bars_and_toggles_to_columns(site):
    client = _login(site)

    default = client.get("/student/matching").get_data(as_text=True)
    column = client.get("/student/matching?chart=column").get_data(as_text=True)

    assert "match-chart--bar" in default and "match-chart--column" not in default
    assert "match-chart--column" in column
    assert "準備度" in default and "建議值" in default
    assert "錄取保證" not in default
