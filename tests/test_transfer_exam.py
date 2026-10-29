"""插大（轉學考）：示範資料匯入、推薦排序不算契合度、卡片列出考科與資格、招生連結與時程。"""
import csv
from pathlib import Path

import pytest

from app import create_app
from app.extensions import db
from app.models import AdmissionProgram, StudentProfile, StudentTarget, User
from app.services.admission_links import load_school_links
from app.services.admission_schedule import channel_label, program_channel, timeline
from app.services.matching_service import rank_programs
from app.services.transfer_exam import (TRANSFER_CATEGORY, TRANSFER_FILE, import_transfer_programs, is_transfer,
                                        load_transfer_details)

HEADER = ("志願代碼,學年度,學校,科系,招生類別,插入年級,名額,報考資格,考試科目,原始項目名稱,加權百分比,"
          "對應資料類別,對應狀態,報名費,報名日期,考試日期,招生網址,簡章網址,出處,查詢日期\n")
EXAM_ROW = ("TRF-TEST-IM-2,115,測試大學,資訊管理學系,插大（轉學考）,二年級,一般 3 名,專科畢業可報二或三年級,"
            "計算機概論×1、英文×1,,,,,\"新臺幣 1,200 元\",115/05/05～05/14,筆試 115/07/21,"
            "https://exam.test.edu.tw/,https://exam.test.edu.tw/115.pdf,測試簡章第 2 頁,2026-10-22\n")
REVIEW_ROW = ("TRF-TEST-CS-2,115,測試大學,資訊工程學系,插大（轉學考）,二年級,一般 5 名,專科畢業可報二年級,"
              "不考筆試；書面審查 100%,書面審查,100,成績與學分；自傳與讀書計畫,待確認,\"新臺幣 1,500 元\","
              "115/05/05～05/14,不考筆試,https://exam.test.edu.tw/,https://exam.test.edu.tw/115.pdf,"
              "測試簡章第 37 頁,2026-10-22\n")


@pytest.fixture()
def app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        yield app


@pytest.fixture()
def transfer_csv(tmp_path):
    path = tmp_path / "transfer.csv"
    path.write_text(HEADER + EXAM_ROW + REVIEW_ROW, encoding="utf-8-sig")
    return path


def make_student():
    student = User(username="stu", display_name="stu", role="student")
    student.set_password("pw")
    db.session.add(student)
    db.session.flush()
    db.session.add(StudentProfile(user_id=student.id, student_no="stu", class_name="資管科五甲", admission_year=111))
    db.session.flush()
    return student


# ---------- 匯入 ----------

def test_import_creates_published_transfer_programs_with_brochure_source(app, transfer_csv):
    created = import_transfer_programs(transfer_csv)

    assert created == 2
    program = AdmissionProgram.query.filter_by(program_code="TRF-TEST-IM-2").one()
    assert program.admission_category == TRANSFER_CATEGORY
    assert program.status == "published"
    assert program.source_url == "https://exam.test.edu.tw/115.pdf"
    assert program.checked_at.isoformat() == "2026-10-22"
    assert program.items == []  # 只考筆試，沒有備審加權
    assert is_transfer(program)


def test_import_keeps_written_review_weight_as_requirement_item(app, transfer_csv):
    import_transfer_programs(transfer_csv)

    program = AdmissionProgram.query.filter_by(program_code="TRF-TEST-CS-2").one()
    assert [(item.source_item_name, item.weight_percent, item.mapped_categories, item.mapping_status)
            for item in program.items] == [("書面審查", 100, "grades,autobiography", "pending")]


def test_import_skips_programs_that_already_exist(app, transfer_csv):
    import_transfer_programs(transfer_csv)

    assert import_transfer_programs(transfer_csv) == 0
    assert AdmissionProgram.query.count() == 2


def test_transfer_codes_are_not_six_digit_skill_review_codes(transfer_csv):
    codes = list(load_transfer_details(transfer_csv)) + list(load_transfer_details())

    assert codes and not any(code.isdigit() for code in codes)


def test_load_transfer_details_returns_exam_subjects_and_eligibility(transfer_csv):
    details = load_transfer_details(transfer_csv)["TRF-TEST-IM-2"]

    assert details["grade"] == "二年級"
    assert details["subjects"] == "計算機概論×1、英文×1"
    assert details["eligibility"] == "專科畢業可報二或三年級"
    assert details["fee"] == "新臺幣 1,200 元"
    assert details["brochure_url"] == "https://exam.test.edu.tw/115.pdf"
    assert details["checked_on"] == "2026-10-22"


def test_load_transfer_details_returns_empty_when_file_is_missing(tmp_path):
    assert load_transfer_details(tmp_path / "missing.csv") == {}


def test_bundled_demo_covers_north_central_and_south_with_official_sources():
    with open(TRANSFER_FILE, encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    schools = {row["學校"] for row in rows}
    assert {"國立臺灣大學", "國立中興大學", "國立中正大學"} <= schools
    for row in rows:
        assert row["招生類別"] == TRANSFER_CATEGORY
        assert row["簡章網址"].startswith("https://") and ".edu.tw/" in row["簡章網址"]
        assert row["招生網址"].startswith("https://") and ".edu.tw/" in row["招生網址"]
        assert row["查詢日期"] == "2026-10-22"
        for column in ("插入年級", "報考資格", "考試科目", "報名費", "報名日期", "出處"):
            assert row[column].strip(), (row["志願代碼"], column)


def test_every_transfer_school_has_an_official_school_link():
    with open(TRANSFER_FILE, encoding="utf-8-sig") as handle:
        schools = {row["學校"] for row in csv.DictReader(handle)}

    assert schools <= set(load_school_links())


# ---------- 推薦排序 ----------

def test_exam_only_transfer_has_no_fit_and_lists_subjects_and_eligibility(app, transfer_csv):
    student = make_student()
    import_transfer_programs(transfer_csv)
    program = AdmissionProgram.query.filter_by(program_code="TRF-TEST-IM-2").one()

    row = rank_programs(student, [program], conditions={}, transfer=load_transfer_details(transfer_csv))[0]

    assert row["fit"] is None
    assert row["fit_note"] == "依考試成績，不算契合度"
    assert row["channel_label"] == "插大（轉學考）"
    assert row["status"] == "needs_check"  # 報考資格系統無法自動判斷（D8）
    text = "".join(row["reasons"])
    assert "計算機概論×1、英文×1" in text
    assert "專科畢業可報二或三年級" in text
    assert "測試簡章第 2 頁" in text


def test_transfer_with_written_review_still_gets_fit(app, transfer_csv):
    student = make_student()
    import_transfer_programs(transfer_csv)
    program = AdmissionProgram.query.filter_by(program_code="TRF-TEST-CS-2").one()

    row = rank_programs(student, [program], conditions={}, transfer=load_transfer_details(transfer_csv))[0]

    assert row["fit"] is not None
    assert row["fit_note"] is None


def test_skill_review_cards_are_labelled_with_their_channel(app):
    student = make_student()
    program = AdmissionProgram(program_code="900001", admission_year=116, school_name="測試大學",
                               department_name="資管系", admission_category="管理類四", status="published")
    db.session.add(program)
    db.session.flush()

    row = rank_programs(student, [program], conditions={}, transfer={})[0]

    assert row["channel_label"] == "二技技優甄審"
    assert row["fit_note"] is None


def test_transfer_programs_have_no_shared_schedule_and_their_own_channel(app, transfer_csv):
    import_transfer_programs(transfer_csv)
    program = AdmissionProgram.query.filter_by(program_code="TRF-TEST-IM-2").one()

    assert program_channel(program) == "transfer"
    assert channel_label(program) == "插大（轉學考）"
    assert timeline(program) is None
    day = AdmissionProgram(program_code="DAY-NTUB-IM", admission_year=115, school_name="測試大學",
                           department_name="資管系", admission_category="日間部申請入學")
    assert channel_label(day) == "日間部申請入學"


# ---------- 頁面 ----------

@pytest.fixture()
def site(tmp_path, monkeypatch):
    from app.services import transfer_exam
    path = tmp_path / "transfer.csv"
    path.write_text(HEADER + EXAM_ROW, encoding="utf-8-sig")
    monkeypatch.setattr(transfer_exam, "TRANSFER_FILE", path)
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        student = make_student()
        import_transfer_programs(path)
        skill = AdmissionProgram(program_code="900001", admission_year=115, school_name="二技大學",
                                 department_name="資訊管理系", admission_category="管理類四", status="published")
        db.session.add(skill)
        db.session.flush()
        transfer = AdmissionProgram.query.filter_by(program_code="TRF-TEST-IM-2").one()
        db.session.add(StudentTarget(student_id=student.id, rule_version_id=transfer.id))
        db.session.commit()
    yield app


def login(app):
    client = app.test_client()
    client.post("/login", data={"username": "stu", "password": "pw"})
    return client


def test_matching_page_shows_skill_review_and_transfer_cards_side_by_side(site):
    html = login(site).get("/student/matching").get_data(as_text=True)

    assert "二技大學" in html and "測試大學" in html
    assert "二技技優甄審" in html and "插大（轉學考）" in html
    assert "依考試成績，不算契合度" in html
    assert "計算機概論×1、英文×1" in html
    assert "專科畢業可報二或三年級" in html
    assert 'href="https://exam.test.edu.tw/115.pdf"' in html
    assert 'href="https://exam.test.edu.tw/"' in html


def test_schedule_page_says_transfer_dates_follow_each_school(site):
    html = login(site).get("/student/schedule").get_data(as_text=True)

    assert "插大（轉學考）時程依各校簡章" in html
    assert "https://exam.test.edu.tw/115.pdf" in html


def test_transfer_target_gap_page_opens(site):
    with site.app_context():
        program_id = AdmissionProgram.query.filter_by(program_code="TRF-TEST-IM-2").one().id

    response = login(site).get(f"/student/targets/{program_id}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "只看筆試成績，不收備審資料" in html
    assert "/student/matching" in html


def test_demo_seed_imports_transfer_programs_alongside_skill_review(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("run_demo", Path(__file__).resolve().parents[1] / "scripts" / "run_demo.py")
    run_demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run_demo)
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        run_demo.seed()

        categories = {program.admission_category for program in AdmissionProgram.query.all()}
        assert TRANSFER_CATEGORY in categories
        assert AdmissionProgram.query.filter_by(program_code="208003").count() == 1


# ---------- 升學 Agent ----------

def test_advisor_rank_tool_tells_ai_about_transfer_programs(app, transfer_csv, monkeypatch):
    from app.services import transfer_exam
    from app.services.agent_advisor import INSTRUCTION, run_advisor
    monkeypatch.setattr(transfer_exam, "TRANSFER_FILE", transfer_csv)
    student = make_student()
    import_transfer_programs(transfer_csv)
    for code in range(900001, 900012):  # 11 個二技校系，插大排在前 10 名之外
        db.session.add(AdmissionProgram(program_code=str(code), admission_year=115, school_name=f"二技大學{code}",
                                        department_name="資訊管理系", admission_category="管理類四", status="published"))
    db.session.commit()

    result = run_advisor(student, decide=None)

    rank = next(step for step in result["steps"] if step["tool"] == "rank_programs")["result"]
    transfer = rank["transfer"]
    assert {item["department"] for item in transfer} == {"資訊管理學系", "資訊工程學系"}
    exam_only = next(item for item in transfer if item["department"] == "資訊管理學系")
    assert exam_only["subjects"] == "計算機概論×1、英文×1"
    assert exam_only["fit_note"] == "依考試成績，不算契合度"
    assert "插大" in rank["summary"]
    assert all(item["channel"] for item in rank["programs"])
    assert "插大" in INSTRUCTION
    assert "插大" in result["summary"]
