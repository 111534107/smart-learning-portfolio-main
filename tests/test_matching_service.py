"""A3 媒合排序：全部校系判斷可不可報、依契合度排序，每一間都寫理由。"""
from datetime import date

import pytest

from app import create_app
from app.extensions import db
from app.models import (AdmissionProgram, AdmissionRequirementItem, CredentialRecord, LearningCourseRecord, Portfolio,
                        StudentProfile, User)
from app.services.gap_service import analyze_gap
from app.services.matching_service import load_conditions, rank_programs


@pytest.fixture()
def app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        yield app


def make_student(admission_year=111):
    student = User(username="stu", display_name="stu", role="student")
    student.set_password("pw")
    db.session.add(student)
    db.session.flush()
    db.session.add(StudentProfile(user_id=student.id, student_no="stu", class_name="資管科五甲",
                                  admission_year=admission_year))
    db.session.flush()
    return student


def make_program(code, items, year=116, school="測試大學"):
    program = AdmissionProgram(program_code=code, admission_year=year, school_name=school,
                               department_name="資管系", status="published")
    for order, (name, weight, keys) in enumerate(items):
        program.items.append(AdmissionRequirementItem(
            source_item_name=name, weight_percent=weight, mapped_categories=keys, sort_order=order))
    db.session.add(program)
    db.session.flush()
    return program


FRESH_ONLY = {"type": "fresh_graduate", "text": "限應屆畢業生（測試原文）", "source": "測試簡章 p.3"}


def test_eligible_programs_are_sorted_by_fit_from_high_to_low(app):
    student = make_student()
    db.session.add(CredentialRecord(student_id=student.id, credential_name="網頁設計丙級", issue_date=date(2025, 3, 1)))
    low = make_program("900001", [("歷年成績", 100, "grades")])
    high = make_program("900002", [("證照", 100, "credential")])

    ranked = rank_programs(student, [low, high], conditions={})

    assert [row["program"].program_code for row in ranked] == ["900002", "900001"]
    assert [row["status"] for row in ranked] == ["eligible", "eligible"]


def test_fit_is_the_same_number_as_gap_readiness(app):
    student = make_student()
    db.session.add(CredentialRecord(student_id=student.id, credential_name="丙級", issue_date=date(2025, 3, 1)))
    program = make_program("900001", [("證照", 40, "credential"), ("歷年成績", 60, "grades")])

    ranked = rank_programs(student, [program], conditions={})

    assert ranked[0]["fit"] == analyze_gap(student, program)["readiness"] == 40


def test_ranking_recalculates_after_student_adds_a_confirmed_credential(app):
    student = make_student()
    grades = make_program("900010", [("歷年成績", 100, "grades")])
    credential = make_program("900011", [("證照", 100, "credential")])
    before = rank_programs(student, [grades, credential], conditions={})
    assert [row["program"].program_code for row in before] == ["900010", "900011"]
    assert [row["fit"] for row in before] == [0, 0]

    db.session.add(CredentialRecord(student_id=student.id, credential_name="測試證照",
                                    issue_date=date(2025, 3, 1), confirmation_status="confirmed"))
    db.session.flush()
    after = rank_programs(student, [grades, credential], conditions={})
    assert [row["program"].program_code for row in after] == ["900011", "900010"]
    assert [row["fit"] for row in after] == [100, 0]


def test_unconfirmed_portfolio_does_not_raise_recommendation_readiness(app):
    student = make_student()
    program = make_program("900013", [("活動經歷", 100, "activity")])
    record = Portfolio(student_id=student.id, title="待核對活動", category="activity", school_year=1, status="draft")
    db.session.add(record)
    db.session.flush()
    assert analyze_gap(student, program)["readiness"] == 0
    record.status = "confirmed"
    db.session.flush()
    assert analyze_gap(student, program)["readiness"] == 100


def test_readiness_currently_excludes_document_only_requirements(app):
    student = make_student()
    db.session.add(LearningCourseRecord(student_id=student.id, course_name="測試課程",
                                        normalized_course_name="測試課程", school_year=1,
                                        confirmation_status="confirmed"))
    program = make_program("900012", [("自傳", 60, "autobiography"), ("成績", 40, "grades")])
    result = analyze_gap(student, program)
    assert result["readiness"] == 100
    assert result["items"][0]["fraction"] is None


def test_graduate_cannot_apply_to_fresh_graduate_only_program_and_is_listed_last(app):
    student = make_student(admission_year=110)  # 推算 115 年畢業，報 116 學年度已不是應屆
    fresh_only = make_program("900001", [("證照", 100, "credential")])
    open_program = make_program("900002", [("歷年成績", 100, "grades")])

    ranked = rank_programs(student, [fresh_only, open_program], conditions={"900001": [FRESH_ONLY]})

    assert [row["program"].program_code for row in ranked] == ["900002", "900001"]
    last = ranked[-1]
    assert last["status"] == "ineligible"
    assert any("應屆" in reason and "115" in reason for reason in last["reasons"])


def test_student_graduating_in_the_admission_year_meets_fresh_graduate_rule(app):
    student = make_student(admission_year=111)  # 推算 116 年畢業
    program = make_program("900001", [("證照", 100, "credential")])

    ranked = rank_programs(student, [program], conditions={"900001": [FRESH_ONLY]})

    assert ranked[0]["status"] == "eligible"
    assert any("應屆" in reason for reason in ranked[0]["reasons"])


def test_younger_student_is_fresh_graduate_when_they_apply_later(app):
    student = make_student(admission_year=113)  # 推算 118 年畢業，到時候報考仍是應屆
    program = make_program("900001", [("證照", 100, "credential")])

    ranked = rank_programs(student, [program], conditions={"900001": [FRESH_ONLY]})

    assert ranked[0]["status"] == "eligible"


def test_missing_admission_year_needs_check_instead_of_eligible(app):
    student = make_student(admission_year=None)
    program = make_program("900001", [("證照", 100, "credential")])

    ranked = rank_programs(student, [program], conditions={"900001": [FRESH_ONLY]})

    assert ranked[0]["status"] == "needs_check"
    assert any("入學年度" in reason for reason in ranked[0]["reasons"])


def test_unknown_condition_type_needs_check_and_shows_original_text(app):
    student = make_student()
    program = make_program("900001", [("證照", 100, "credential")])
    odd = {"type": "other", "text": "須參加本校舉辦之說明會", "source": "測試簡章 p.5"}

    ranked = rank_programs(student, [program], conditions={"900001": [odd]})

    assert ranked[0]["status"] == "needs_check"
    assert any("須參加本校舉辦之說明會" in reason for reason in ranked[0]["reasons"])


def test_needs_check_is_listed_between_eligible_and_ineligible(app):
    student = make_student(admission_year=110)
    eligible = make_program("900001", [("證照", 100, "credential")])
    check = make_program("900002", [("證照", 100, "credential")])
    blocked = make_program("900003", [("證照", 100, "credential")])
    odd = {"type": "other", "text": "其他條件", "source": ""}

    ranked = rank_programs(student, [blocked, check, eligible],
                           conditions={"900002": [odd], "900003": [FRESH_ONLY]})

    assert [row["status"] for row in ranked] == ["eligible", "needs_check", "ineligible"]


def test_every_program_gets_a_reason_naming_its_heaviest_item(app):
    student = make_student()
    db.session.add(CredentialRecord(student_id=student.id, credential_name="丙級", issue_date=date(2025, 3, 1)))
    program = make_program("900001", [("歷年成績", 30, "grades"), ("證照證明", 70, "credential")])

    ranked = rank_programs(student, [program], conditions={})

    reasons = " ".join(ranked[0]["reasons"])
    assert "證照證明" in reasons and "70%" in reasons
    assert "歷年成績" in reasons  # 還缺的項目也要說


def test_program_with_only_self_prepared_items_has_no_fit_but_still_a_reason(app):
    student = make_student()
    program = make_program("900001", [("自傳", 100, "autobiography")])

    ranked = rank_programs(student, [program], conditions={})

    assert ranked[0]["fit"] is None
    assert ranked[0]["reasons"]


def add_info_courses(student, names=("程式設計", "網頁設計", "資料結構", "計算機網路", "會計學")):
    for name in names:
        db.session.add(LearningCourseRecord(student_id=student.id, course_name=name, normalized_course_name=name,
                                            credits=3, score=85, confirmation_status="confirmed"))
    db.session.flush()


def set_department(program, name, category):
    program.department_name = name
    program.admission_category = category
    return program


def test_related_departments_rank_before_unrelated_ones_with_higher_fit(app):
    student = make_student()
    add_info_courses(student)
    db.session.add(CredentialRecord(student_id=student.id, credential_name="丙級", issue_date=date(2025, 3, 1)))
    unrelated = set_department(make_program("900001", [("證照", 100, "credential")]), "模具工程系", "機械類")
    related = set_department(make_program("900002", [("證照", 50, "credential"), ("歷年成績", 50, "grades")]),
                             "資訊管理系", "管理類四")

    ranked = rank_programs(student, [unrelated, related], conditions={})

    assert [row["program"].department_name for row in ranked] == ["資訊管理系", "模具工程系"]
    assert any("資訊類專業科目 4 科" in reason and "資訊學群" in reason for reason in ranked[0]["reasons"])
    assert any("關聯較低" in reason for reason in ranked[1]["reasons"])
    assert ranked[1]["status"] == "eligible"  # 不相關不代表不能報


def test_accounting_information_is_not_ranked_as_information_group(app):
    """誤判案例：系名有「資訊」的會計資訊系，以前被關鍵字當成資管相關。"""
    student = make_student()
    add_info_courses(student)
    accounting = set_department(make_program("900001", [("證照", 100, "credential")]), "會計資訊系", "管理類二")
    nursing = set_department(make_program("900002", [("證照", 100, "credential")]), "醫護教育暨數位學習系", "護理類一")
    info = set_department(make_program("900003", [("歷年成績", 100, "grades")]), "資訊管理系", "管理類四")

    ranked = rank_programs(student, [accounting, nursing, info], conditions={})

    assert ranked[0]["program"].department_name == "資訊管理系"
    by_name = {row["program"].department_name: row for row in ranked}
    assert by_name["會計資訊系"]["related"] is False
    assert by_name["醫護教育暨數位學習系"]["related"] is False
    assert any("商管學群" in reason for reason in by_name["會計資訊系"]["reasons"])


def test_student_without_course_data_gets_needs_check_relation(app):
    student = make_student()
    info = set_department(make_program("900001", [("證照", 100, "credential")]), "資訊管理系", "管理類四")

    ranked = rank_programs(student, [info], conditions={})

    assert ranked[0]["related"] is None
    assert any("學群待確認" in reason for reason in ranked[0]["reasons"])


def test_department_missing_from_table_gets_needs_check_relation_and_sorts_in_between(app):
    student = make_student()
    add_info_courses(student)
    unknown = set_department(make_program("900001", [("證照", 100, "credential")]), "太空探索系", "管理類二")
    unrelated = set_department(make_program("900002", [("證照", 100, "credential")]), "模具工程系", "機械類")
    info = set_department(make_program("900003", [("證照", 100, "credential")]), "資訊管理系", "管理類四")

    ranked = rank_programs(student, [unrelated, unknown, info], conditions={})

    assert [row["related"] for row in ranked] == [True, None, False]
    assert any("學群待確認" in reason for reason in ranked[1]["reasons"])


def test_load_conditions_groups_rows_by_program_code(tmp_path):
    path = tmp_path / "conditions.csv"
    path.write_text("志願代碼,條件類型,條件原文,出處\n"
                    "208003,fresh_graduate,限應屆,示範\n"
                    "208003,other,須面試,示範\n"
                    "208001,fresh_graduate,限應屆,示範\n", encoding="utf-8-sig")

    conditions = load_conditions(path)

    assert [c["type"] for c in conditions["208003"]] == ["fresh_graduate", "other"]
    assert conditions["208001"][0]["text"] == "限應屆"
    assert conditions["208001"][0]["source"] == "示範"


def test_load_conditions_returns_empty_when_file_is_missing(tmp_path):
    assert load_conditions(tmp_path / "missing.csv") == {}


# ---------- 推薦排序頁 ----------

@pytest.fixture()
def site(tmp_path, monkeypatch):
    from app.services import matching_service
    conditions = tmp_path / "conditions.csv"
    conditions.write_text("志願代碼,條件類型,條件原文,出處\n900001,fresh_graduate,限應屆畢業生,測試簡章 p.3\n",
                          encoding="utf-8-sig")
    monkeypatch.setattr(matching_service, "CONDITIONS_FILE", conditions)
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        make_student(admission_year=110)
        make_program("900001", [("證照證明", 100, "credential")], school="應屆大學")
        make_program("900002", [("歷年成績", 100, "grades")], school="開放大學")
        db.session.commit()
    yield app


def login(app):
    client = app.test_client()
    client.post("/login", data={"username": "stu", "password": "pw"})
    return client


def test_matching_page_lists_every_program_with_status_and_detail_link(site):
    html = login(site).get("/student/matching").get_data(as_text=True)

    assert "開放大學" in html and "應屆大學" in html
    assert html.index("開放大學") < html.index("應屆大學")  # 不可報的排最後，但仍列出
    assert "不可報" in html and "可報" in html
    assert "查看校系細項與計算依據" in html
    assert "不是錄取機率" in html


def test_targets_page_links_to_matching_page(site):
    html = login(site).get("/student/targets").get_data(as_text=True)

    assert "/student/matching" in html


def test_matching_page_requires_student_login(site):
    response = site.test_client().get("/student/matching")

    assert response.status_code in (302, 401, 403)


# ---------- 招生連結 ----------

from app.services.admission_links import admission_links, load_school_links  # noqa: E402


def _program(code="208003", school="國立臺北商業大學", source_url=None):
    return AdmissionProgram(program_code=code, admission_year=116, school_name=school,
                            department_name="資訊管理系", source_url=source_url)


SCHOOLS = {"國立臺北商業大學": "https://admis.ntub.edu.tw/"}


def test_links_include_school_admission_site_and_joint_entry_for_skill_review_codes():
    links = admission_links(_program(), SCHOOLS)

    assert [link["url"] for link in links] == ["https://admis.ntub.edu.tw/", "https://www.jctv.ntut.edu.tw/enter/"]
    assert "國立臺北商業大學" in links[0]["label"]
    assert "技優" in links[1]["label"]


def test_school_application_programs_without_numeric_code_only_link_the_school():
    links = admission_links(_program(code="DAY-NTUB-IM"), SCHOOLS)

    assert [link["url"] for link in links] == ["https://admis.ntub.edu.tw/"]


def test_agent_source_url_is_listed_first():
    links = admission_links(_program(source_url="https://example.edu.tw/brochure.pdf"), SCHOOLS)

    assert links[0]["url"] == "https://example.edu.tw/brochure.pdf"
    assert "簡章" in links[0]["label"]


def test_unknown_school_still_gets_joint_entry_but_no_made_up_site():
    links = admission_links(_program(school="不存在大學"), SCHOOLS)

    assert [link["url"] for link in links] == ["https://www.jctv.ntut.edu.tw/enter/"]


def test_load_school_links_reads_csv(tmp_path):
    path = tmp_path / "links.csv"
    path.write_text("學校,招生網址,確認日期\n國立臺北商業大學,https://admis.ntub.edu.tw/,2026-10-22\n", encoding="utf-8-sig")

    assert load_school_links(path) == {"國立臺北商業大學": "https://admis.ntub.edu.tw/"}


def test_every_school_in_seed_data_has_an_official_link():
    import csv
    from pathlib import Path
    content = Path(__file__).resolve().parents[1] / "app" / "content"
    schools = set()
    for name in ("admission_seed_115.csv", "admission_demo_national_116.csv", "admission_demo_dayapply_115.csv"):
        with open(content / name, encoding="utf-8-sig") as handle:
            schools |= {row["學校"] for row in csv.DictReader(handle)}

    links = load_school_links()

    assert schools <= set(links)
    assert all(url.startswith("https://") and ".edu.tw" in url for url in links.values())


def test_matching_page_shows_admission_links(site):
    with site.app_context():
        program = AdmissionProgram.query.filter_by(program_code="900002").one()
        program.source_url = "https://example.edu.tw/brochure.pdf"
        db.session.commit()

    client = login(site)
    with site.app_context():
        program_id = AdmissionProgram.query.filter_by(program_code="900002").one().id
    html = client.get(f"/student/matching/{program_id}").get_data(as_text=True)

    assert "https://example.edu.tw/brochure.pdf" in html
    assert 'rel="noopener noreferrer"' in html


def test_targets_page_cards_show_admission_links(site):
    with site.app_context():
        program = AdmissionProgram.query.filter_by(program_code="900002").one()
        program.source_url = "https://example.edu.tw/targets-brochure.pdf"
        db.session.commit()

    html = login(site).get("/student/targets").get_data(as_text=True)

    assert "https://example.edu.tw/targets-brochure.pdf" in html


# ---------- C5 技優資格：證照等級與取得期限 ----------

SKILL_B = {"type": "skill_credential", "text": "須持有乙級以上技術士證，且於 115/04/13（含）前取得（測試原文）",
           "source": "測試簡章 p.5", "level": "乙級", "deadline": "115/04/13"}


def add_credential(student, name, level, issued, status="confirmed"):
    db.session.add(CredentialRecord(student_id=student.id, credential_name=name, level=level, issue_date=issued,
                                    confirmation_status=status))
    db.session.flush()


def skill_row(student):
    program = make_program("900077", [("證照", 100, "credential")])
    return rank_programs(student, [program], conditions={"900077": [SKILL_B]})[0]


def test_skill_credential_at_required_level_before_deadline_is_eligible(app):
    student = make_student()
    add_credential(student, "網頁設計乙級", "乙級", date(2025, 11, 2))

    row = skill_row(student)

    assert row["status"] == "eligible"
    assert any("網頁設計乙級" in reason and "2025-11-02" in reason for reason in row["reasons"])


def test_higher_level_also_counts(app):
    student = make_student()
    add_credential(student, "電腦硬體裝修甲級", "甲級", date(2025, 6, 1))

    assert skill_row(student)["status"] == "eligible"


def test_only_lower_level_credentials_need_checking_not_rejection(app):
    """系統裡沒有，不代表學生沒有（可能還沒上傳）；缺資料一律需確認。"""
    student = make_student()
    add_credential(student, "電腦軟體應用丙級", "丙級", date(2025, 5, 20))

    row = skill_row(student)

    assert row["status"] == "needs_check"
    assert any("乙級以上" in reason for reason in row["reasons"])


def test_credential_obtained_after_deadline_is_ineligible(app):
    student = make_student()
    add_credential(student, "網頁設計乙級", "乙級", date(2026, 5, 1))

    row = skill_row(student)

    assert row["status"] == "ineligible"
    assert any("2026-04-13" in reason for reason in row["reasons"])


def test_credential_without_date_needs_checking(app):
    student = make_student()
    add_credential(student, "網頁設計乙級", "乙級", None)

    assert skill_row(student)["status"] == "needs_check"


def test_unconfirmed_credentials_are_not_counted(app):
    student = make_student()
    add_credential(student, "網頁設計乙級", "乙級", date(2025, 11, 2), status="pending")

    assert skill_row(student)["status"] == "needs_check"


def test_load_conditions_reads_optional_level_and_deadline(tmp_path):
    path = tmp_path / "conditions.csv"
    path.write_text("志願代碼,條件類型,條件原文,出處,等級,期限\n"
                    "208001,skill_credential,乙級以上,示範,乙級,115/04/13\n"
                    "208002,fresh_graduate,限應屆,示範,,\n", encoding="utf-8-sig")

    conditions = load_conditions(path)

    assert conditions["208001"][0]["level"] == "乙級" and conditions["208001"][0]["deadline"] == "115/04/13"
    assert conditions["208002"][0]["level"] is None


def test_student_group_unknown_falls_back_to_their_department_for_ordering(app):
    """實測問題 1：林小美只有一門對不到課綱的課，模具工程系排第一。學群待確認時，暫依學生科別排序。"""
    student = make_student()  # 資管科五甲，沒有成績
    db.session.add(CredentialRecord(student_id=student.id, credential_name="丙級", issue_date=date(2025, 3, 1)))
    mold = set_department(make_program("900001", [("證照", 100, "credential")]), "模具工程系", "機械類")
    info = set_department(make_program("900002", [("證照", 50, "credential"), ("歷年成績", 50, "grades")]),
                          "資訊管理系", "管理類四")

    ranked = rank_programs(student, [mold, info], conditions={})

    assert [row["program"].department_name for row in ranked] == ["資訊管理系", "模具工程系"]
    assert all(row["related"] is None for row in ranked)  # 仍然標學群待確認，不假裝已經判斷
    assert any("暫依你的科別（資管科）" in reason for reason in ranked[0]["reasons"])
