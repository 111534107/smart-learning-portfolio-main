"""推薦排序頁的細項：只列登入學生本人的「已符合」與「缺少」。"""
from datetime import date

import pytest

from app import create_app
from app.extensions import db
from app.models import AdmissionProgram, AdmissionRequirementItem, CredentialRecord, MatchFilterOption, StudentProfile, StudentTarget, User


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


def test_matching_tours_explain_search_and_target_selection(site):
    client = _login(site)
    listing = client.get('/student/matching').get_data(as_text=True)
    detail = client.get(f"/student/matching/{site.config['_ids']['program']}").get_data(as_text=True)
    assert 'data-tour="選二技或插大，切換招生管道。"' in listing
    assert 'data-tour="輸入學校或科系，篩選推薦清單。"' in listing
    assert 'data-tour="點校系名稱，查看資格與缺少項目。"' in listing
    assert 'data-tour="核對資格與已符合、缺少的項目。"' in detail
    assert 'data-tour="想追蹤這個校系時，設為目標。"' in detail


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


def test_target_cards_sort_by_readiness_even_when_lower_one_is_selected(site):
    with site.app_context():
        low = _program("900003", "低準備大學", "published", [("競賽成果", 100, "competition")])
        high = _program("900004", "高準備大學", "published", [("證照證明", 100, "credential")])
        _program("900005", "文件大學", "published", [("自傳", 100, "autobiography")])
        db.session.add(StudentTarget(student_id=site.config["_ids"]["mine"], rule_version_id=low.id))
        db.session.commit()

    html = _login(site).get("/student/targets").get_data(as_text=True)

    assert "全部校系依準備度由高到低排列" in html
    chart = html[html.index('<section class="target-ranking"'):html.index("</section>", html.index('<section class="target-ranking"'))]
    assert chart.index("高準備大學") < chart.index("公開大學") < chart.index("低準備大學") < chart.index("文件大學")
    assert 'aria-label="高準備大學 資管系 二技技優甄審準備度 ' in chart
    assert 'style="width: ' in chart



def test_target_ranking_is_one_list_by_readiness_with_home_tag(site):
    with site.app_context():
        other = _program("900006", "外系高分大學", "published", [("證照證明", 100, "credential")])
        home = _program("900007", "本科低分大學", "published", [("競賽成果", 100, "competition")])
        other.department_name = "資訊工程系"
        home.department_name = "資訊管理學系"
        db.session.commit()
        other_id, home_id = other.id, home.id

    html = _login(site).get("/student/targets").get_data(as_text=True)
    chart = html[html.index('<section class="target-ranking"'):html.index("</section>", html.index('<section class="target-ranking"'))]

    # 不再分組：準備度高的外系排第一，本科系只加「本科」標籤
    assert chart.index("外系高分大學") < chart.index("本科低分大學")
    assert html.index(f'id="target-program-{other_id}"') < html.index(f'id="target-program-{home_id}"')
    assert 'aria-label="外系高分大學 資訊工程系' in chart
    assert "本科</span>" in chart



def test_target_page_puts_selected_goals_first_and_collapses_exploration(site):
    with site.app_context():
        program_id = site.config["_ids"]["program"]
        db.session.add(StudentTarget(student_id=site.config["_ids"]["mine"], rule_version_id=program_id))
        db.session.commit()

    html = _login(site).get("/student/targets").get_data(as_text=True)
    assert html.index('id="my-targets"') < html.index('id="target-programs"')
    selected = html[html.index('id="my-targets"'):html.index("</section>", html.index('id="my-targets"'))]
    assert "公開大學" in selected and f'/student/targets/{program_id}' in selected
    assert '<details class="target-program"' in html
    assert '<div class="program-cards"' not in html



def test_transfer_year_disambiguates_same_school_and_department(site):
    with site.app_context():
        second = _program("TRF-CCU-IM-2", "轉學大學", "published", [])
        third = _program("TRF-CCU-IM-3", "轉學大學", "published", [])
        second.admission_category = third.admission_category = "插大（轉學考）"
        db.session.commit()

    html = _login(site).get("/student/targets?track=transfer").get_data(as_text=True)
    assert "轉學大學 資管系（插大（轉學考） · 二年級）" in html
    assert "轉學大學 資管系（插大（轉學考） · 三年級）" in html



def test_same_department_shows_admission_channel_in_ranking(site):
    with site.app_context():
        skill = _program("900009", "同校大學", "published", [("證照證明", 100, "credential")])
        day = _program("DAY-900009", "同校大學", "published", [("歷年成績", 100, "grades")])
        skill.admission_category = "管理類四"
        day.admission_category = "日間部申請入學"
        db.session.commit()

    html = _login(site).get("/student/targets").get_data(as_text=True)
    chart = html[html.index('<section class="target-ranking"'):html.index("</section>", html.index('<section class="target-ranking"'))]
    assert "同校大學 資管系" in chart
    assert "二技技優甄審" in chart
    assert "日間部申請入學" in chart



def test_target_dropdowns_filter_major_and_specific_program(site):
    with site.app_context():
        other = _program("900008", "外系大學", "published", [("證照證明", 100, "credential")])
        other.department_name = "資訊工程系"
        db.session.commit()
        other_id = other.id

    client = _login(site)
    all_html = client.get("/student/targets").get_data(as_text=True)
    assert 'name="major" value="home"' in all_html
    assert '<select name="program_id"' in all_html
    assert "全部校系" in all_html and "本科系" in all_html and "非本科系" in all_html

    other_html = client.get("/student/targets?major=other").get_data(as_text=True)
    assert "外系大學" in other_html
    assert 'id="target-program-' + str(site.config["_ids"]["program"]) + '"' not in other_html

    one_html = client.get(f"/student/targets?program_id={other_id}").get_data(as_text=True)
    assert 'id="target-program-' + str(other_id) + '"' in one_html
    assert 'id="target-program-' + str(site.config["_ids"]["program"]) + '"' not in one_html




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


def _make_programs(app, specs):
    with app.app_context():
        for code, school, department, category in specs:
            program = _program(code, school, "published", [("證照證明", 100, "credential")])
            program.department_name, program.admission_category = department, category
        db.session.commit()


def test_matching_separates_twotech_and_transfer_tabs(site):
    _make_programs(site, [("TRF-901", "轉學大學", "資訊管理學系", "插大（轉學考）")])
    client = _login(site)

    twotech = client.get("/student/matching").get_data(as_text=True)
    transfer = client.get("/student/matching?track=transfer").get_data(as_text=True)

    assert "公開大學" in twotech and "轉學大學" not in twotech
    assert "轉學大學" in transfer and "公開大學" not in transfer
    assert "二技（1）" in twotech and "插大（1）" in twotech


def test_matching_keyword_search_matches_school_or_department(site):
    _make_programs(site, [("900101", "北商大學", "企業管理系", "管理類二"),
                          ("900102", "南方科大", "資訊管理系", "管理類二")])
    client = _login(site)

    by_school = client.get("/student/matching?q=北商").get_data(as_text=True)
    by_both = client.get("/student/matching?q=南方 資訊").get_data(as_text=True)

    assert "北商大學" in by_school and "南方科大" not in by_school
    assert "南方科大" in by_both and "北商大學" not in by_both


def test_matching_lists_first_twenty_then_show_more(site):
    _make_programs(site, [(f"9002{n:02d}", f"測試{n:02d}大學", "資管系", "管理類二") for n in range(25)])
    client = _login(site)

    first = client.get("/student/matching").get_data(as_text=True)
    more = client.get("/student/matching?show=40").get_data(as_text=True)

    assert first.count('class="match-chart__item"') == 20
    assert "看更多" in first and "show=40" in first
    assert more.count('class="match-chart__item"') == 26  # 25 間＋原本的公開大學
    assert "看更多" not in more


def test_matching_detail_page_offers_reasons_schedule_and_add_target(site):
    pid = site.config["_ids"]["program"]
    html = _login(site).get(f"/student/matching/{pid}").get_data(as_text=True)

    assert "怎麼進這所學校" in html
    assert "設為目標校系" in html
    assert "看招生時程 →" in html


def test_matching_detail_shows_confirmed_qualification_with_source(site):
    from app.models import AdmissionEligibilityRule
    with site.app_context():
        program = db.session.get(AdmissionProgram, site.config["_ids"]["program"])
        program.eligibility_rules.append(AdmissionEligibilityRule(rule_group=1, condition_type="student_status", operator="in",
            value_json={"field":"class_name", "values":["資管科五甲"]}, description="僅為測試資料：學籍條件",
            source_url="https://example.edu.tw/rules.pdf", source_location="第 3 頁", mapping_status="confirmed", is_required=True))
        db.session.commit()
    html = _login(site).get(f"/student/matching/{site.config['_ids']['program']}").get_data(as_text=True)
    assert "僅為測試資料：學籍條件" in html
    assert "第 3 頁" in html and "學生資料符合此項學籍條件" in html
    assert "仍以當年度招生簡章" in html


def test_targets_separate_two_year_and_transfer_tracks(site):
    with site.app_context():
        transfer = _program("TRF-TEST-2", "僅為測試插大", "published", [])
        transfer.admission_category = "插大（轉學考）"
        db.session.add(StudentTarget(student_id=site.config["_ids"]["mine"], rule_version_id=transfer.id))
        db.session.commit()
    client = _login(site)
    twotech = client.get("/student/targets").get_data(as_text=True)
    assert "二技" in twotech and "插大" in twotech
    assert "僅為測試插大" not in twotech
    assert "公開大學" in twotech
    transfer_html = client.get("/student/targets?track=transfer").get_data(as_text=True)
    assert "僅為測試插大" in transfer_html
    assert "考試科目與資料需求請看招生簡章" in transfer_html
    assert "此校系以自傳等文件為主" not in transfer_html
    assert "公開大學" not in transfer_html
    assert 'name="track" value="transfer"' in transfer_html
    filtered = client.get("/student/targets?track=transfer&major=home").get_data(as_text=True)
    assert "僅為測試插大" in filtered



def test_target_search_filters_by_school_or_department(site):
    with site.app_context():
        other = _program("900010", "搜尋大學", "published", [("證照證明", 100, "credential")])
        other.department_name = "護理系"
        db.session.commit()

    client = _login(site)
    html = client.get("/student/targets?q=護理").get_data(as_text=True)
    assert "搜尋大學 護理系" in html
    assert "公開大學" not in html[html.index('id="target-programs"'):].split("</section>")[0]
    assert 'value="護理"' in html

    empty = client.get("/student/targets?q=不存在的科系").get_data(as_text=True)
    ranking = empty[empty.index('id="target-programs"'):]
    assert "搜尋大學" not in ranking.split("</section>")[0]
    assert 'name="q"' in empty



def test_major_switches_preserve_search_and_filter_matching(site):
    with site.app_context():
        other = _program("900701", "測試外系", "published", [("證照證明", 100, "credential")])
        other.department_name = "資訊工程系"
        _program("900705", "測試本科", "published", [("證照證明", 100, "credential")])
        db.session.commit()
    client = _login(site)
    for path in ("/student/targets", "/student/matching"):
        html = client.get(path + "?q=測試&major=other").get_data(as_text=True)
        assert 'name="major" value="home"' in html
        assert 'name="major" value="other"' in html
        assert 'value="測試"' in html
        assert "測試外系" in html
        ranking = html[html.index('id="target-programs"'):] if path.endswith("targets") else html[html.index('<ol class="match-chart'):]
        assert "測試外系" in ranking and "測試本科" not in ranking
        home_html = client.get(path + "?q=測試&major=home").get_data(as_text=True)
        ranking = home_html[home_html.index('id="target-programs"'):] if path.endswith("targets") else home_html[home_html.index('<ol class="match-chart'):]
        assert "測試本科" in ranking and "測試外系" not in ranking


def test_matching_places_only_ineligible_last_then_sorts_readiness(site, monkeypatch):
    with site.app_context():
        _program("900702", "低分可報", "published", [("競賽成果", 100, "competition")])
        _program("900703", "高分待確認", "published", [("證照證明", 100, "credential")])
        _program("900704", "高分不可報", "published", [("證照證明", 100, "credential")])
        db.session.commit()
    _force_status(monkeypatch, {"低分可報": "eligible", "高分待確認": "needs_check", "高分不可報": "ineligible", "公開大學": "eligible"})
    html = _login(site).get("/student/matching").get_data(as_text=True)
    chart = html[html.index('<ol class="match-chart'):html.index('</ol>', html.index('<ol class="match-chart'))]
    assert chart.index("高分待確認") < chart.index("低分可報") < chart.index("高分不可報")


def test_matching_shows_actual_qualification_reason(site, monkeypatch):
    from app.routes import student as student_routes
    real = student_routes.rank_programs

    def fake(*args, **kwargs):
        rows = real(*args, **kwargs)
        rows[0]["status"] = "ineligible"
        rows[0]["qualification"] = {"status": "not_eligible", "conditions": [{"status": "not_matched", "reason": "不符合學籍限制"}]}
        return rows

    monkeypatch.setattr(student_routes, "rank_programs", fake)
    html = _login(site).get("/student/matching").get_data(as_text=True)
    chart = html[html.index('<ol class="match-chart'):html.index('</ol>', html.index('<ol class="match-chart'))]
    assert "不符合學籍限制" in chart


def test_matching_shows_later_failed_condition(site, monkeypatch):
    from app.routes import student as student_routes
    real = student_routes.rank_programs

    def fake(*args, **kwargs):
        rows = real(*args, **kwargs)
        rows[0]["status"] = "ineligible"
        rows[0]["qualification"] = None
        rows[0]["reasons"] = ["符合第一條", "第二條證照期限不符"]
        return rows

    monkeypatch.setattr(student_routes, "rank_programs", fake)
    html = _login(site).get("/student/matching").get_data(as_text=True)
    chart = html[html.index('<ol class="match-chart'):html.index('</ol>', html.index('<ol class="match-chart'))]
    assert "第二條證照期限不符" in chart
