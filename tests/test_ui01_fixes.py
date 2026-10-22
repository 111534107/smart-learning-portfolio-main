"""UI-01 審查（GPT，2026-10-10）必修 R1～R6 的回歸測試。

報告：docs/05_交接與專案管理/AI_檢查報告_UI-01_story-guide分支審查_2026-10-10.md（在 main）
"""
from datetime import date

import pytest

from app import create_app
from app.extensions import db
from app.models import (
    AdmissionProgram,
    AdmissionRequirementItem,
    AuditLog,
    Portfolio,
    StudentProfile,
    StudentTarget,
    User,
)
from app.services.focus_service import focus_view
from app.services.guide_service import guide_cards
from app.services.journey_service import academic_year_of
from app.services import student_rules


@pytest.fixture()
def app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        yield app


def make_student(grade, username="stu"):
    user = User(username=username, display_name=username, role="student")
    user.set_password("pw")
    db.session.add(user)
    db.session.flush()
    db.session.add(StudentProfile(user_id=user.id, student_no=username,
                                  admission_year=academic_year_of(date.today()) - grade + 1))
    db.session.commit()
    return user


def make_program(code, items, year=115, category="管理類四"):
    """items: [(名稱, 加權, 類別代碼字串, mapping_status)]"""
    program = AdmissionProgram(program_code=code, admission_year=year, school_name=f"國立測試大學{code}",
                               department_name="資訊管理系", admission_category=category, status="published")
    db.session.add(program)
    db.session.flush()
    for index, (name, weight, keys, status) in enumerate(items):
        program.items.append(AdmissionRequirementItem(source_item_name=name, weight_percent=weight,
                                                      mapped_categories=keys, mapping_status=status,
                                                      sort_order=index))
    db.session.commit()
    return program


def target(user, *programs):
    for program in programs:
        db.session.add(StudentTarget(student_id=user.id, rule_version_id=program.id))
    db.session.commit()


# R1：沒有推薦，不等於全部準備好了
def test_r1_empty_focus_does_not_claim_everything_is_ready(app):
    with app.test_request_context():
        user = make_student(1)
        target(user, *[make_program(f"10000{n}", [("專題成果", 100, "project", "confirmed")]) for n in range(3)])
        view = focus_view(user)
    assert view["top"] == []

    client = app.test_client()
    client.post("/login", data={"username": "stu", "password": "pw"})
    page = client.get("/student/targets").get_data(as_text=True)
    assert "準備好了" not in page and "都有了" not in page
    assert "文件清單" in page


# R2：待確認的分類要標示出來，不能說成校方確認
def test_r2_pending_mapping_is_flagged(app):
    with app.test_request_context():
        user = make_student(3)
        target(user, *[make_program(f"20000{n}", [("競賽成果", 100, "competition", "pending")]) for n in range(3)])
        view = focus_view(user)
    assert view["top"][0]["key"] == "competition"
    assert view["top"][0]["pending"] is True
    assert view["has_pending"] is True


def test_r2_page_shows_pending_label_and_no_school_claim(app):
    with app.app_context():
        user = make_student(3)
        target(user, *[make_program(f"20000{n}", [("競賽成果", 100, "competition", "pending")]) for n in range(3)])
    client = app.test_client()
    client.post("/login", data={"username": "stu", "password": "pw"})
    page = client.get("/student/targets").get_data(as_text=True)
    assert "分類待確認" in page
    assert "都看重" not in page


# R3：舊學年度的目標不參與聚焦
def test_r3_focus_ignores_old_year_targets(app):
    with app.test_request_context():
        user = make_student(3)
        old = [make_program(f"30000{n}", [("競賽", 100, "competition", "confirmed")], year=115) for n in range(3)]
        for n in range(3):
            make_program(f"30000{n}", [("證照", 100, "credential", "confirmed")], year=116)
        target(user, *old)
        assert student_rules.target_slots(user)["used"] == 0
        assert focus_view(user) is None


# R4：內部識別碼不能標成官方志願代碼；要顯示招生管道與學年度
def test_r4_internal_code_not_shown_as_official(app):
    with app.app_context():
        make_student(3)
        make_program("DAY-YT-IM", [("書審", 100, "grades", "confirmed")], category="日間部申請入學")
        make_program("208001", [("歷年成績", 100, "grades", "confirmed")])
    client = app.test_client()
    client.post("/login", data={"username": "stu", "password": "pw"})
    page = client.get("/student/targets").get_data(as_text=True)
    assert "志願代碼 DAY-" not in page
    assert "志願代碼 208001" in page
    assert "日間部申請入學" in page and "另計統測" in page
    assert "115 學年度" in page
    assert "當年度二技技優甄審簡章" not in page


# R5：升五年級後超過 5 所，要引導縮減，送審前要先收斂
def test_r5_fifth_year_over_limit_gets_trim_card_and_review_blocked(app):
    with app.test_request_context():
        user = make_student(5)
        programs = [make_program(f"50000{n}", [("歷年成績", 100, "grades", "confirmed")]) for n in range(6)]
        target(user, *programs)
        slots = student_rules.target_slots(user)
        assert slots["used"] == 6 and slots["limit"] == 5
        assert "trim-targets" in [card["id"] for card in guide_cards(user)]
        assert student_rules.over_limit_reason(user)
        program_id = programs[0].id

    client = app.test_client()
    client.post("/login", data={"username": "stu", "password": "pw"})
    page = client.get("/student/targets").get_data(as_text=True)
    assert "取消 1 所" in page
    response = client.post(f"/student/targets/{program_id}/review")
    assert "取消 1 所" in response.get_data(as_text=True)
    with app.app_context():
        assert StudentTarget.query.count() == 6  # 不自動刪


# R6：做完的卡片要消失
def test_r6_welcome_card_hidden_after_welcome_done(app):
    with app.test_request_context():
        user = make_student(1)
        assert "welcome" in [card["id"] for card in guide_cards(user)]
        db.session.add(AuditLog(user_id=user.id, action="student.welcome_done"))
        db.session.commit()
        assert "welcome" not in [card["id"] for card in guide_cards(user)]


def test_r6_each_term_card_hidden_when_this_year_has_record(app):
    with app.test_request_context():
        user = make_student(2)
        assert "each-term" in [card["id"] for card in guide_cards(user)]
        db.session.add(Portfolio(student_id=user.id, title="社團成果", category="activity", school_year=2))
        db.session.commit()
        assert "each-term" not in [card["id"] for card in guide_cards(user)]


def test_r6_fourth_year_cards_disappear_when_done(app):
    with app.test_request_context():
        user = make_student(4)
        ids = [card["id"] for card in guide_cards(user)]
        assert "internship" in ids and "see-requirements" in ids
        db.session.add(Portfolio(student_id=user.id, title="實習", category="activity", school_year=4))
        target(user, make_program("600001", [("歷年成績", 100, "grades", "confirmed")]))
        ids = [card["id"] for card in guide_cards(user)]
        assert "internship" not in ids and "see-requirements" not in ids


# 建議 5：畫面上的要求數是完整總數，不被動畫上限截掉
def test_focus_total_count_not_capped(app):
    with app.test_request_context():
        user = make_student(3)
        items = [(f"項目{i}", 5, "grades", "confirmed") for i in range(20)]
        target(user, *[make_program(f"70000{n}", items) for n in range(4)])
        view = focus_view(user)
    assert view["total"] == 80
    assert len(view["pieces"]) <= 60
