"""招生時程：依招生管道列出重要日程，標出已過、進行中、下一步。"""
from datetime import datetime

import pytest

from app import create_app
from app.extensions import db
from app.models import AdmissionProgram, AdmissionRequirementItem, StudentProfile, StudentTarget, User
from app.services.admission_schedule import load_schedule, program_channel, timeline

CSV = ("管道,學年度,項目,開始,結束,說明,出處\n"
       "skill_review,115,簡章網路下載,2025-11-20 00:00,,,https://example.edu.tw/date.pdf\n"
       "skill_review,115,網路報名,2026-04-20 10:00,2026-04-23 17:00,最後一天只到 17:00,https://example.edu.tw/date.pdf\n"
       "skill_review,115,報到截止,2026-06-02 17:00,,,https://example.edu.tw/date.pdf\n")


@pytest.fixture()
def schedule(tmp_path):
    path = tmp_path / "schedule.csv"
    path.write_text(CSV, encoding="utf-8-sig")
    return load_schedule(path)


def _program(code="208003", year=115):
    return AdmissionProgram(program_code=code, admission_year=year, school_name="測試大學", department_name="資管系")


def test_load_schedule_groups_events_by_channel_and_year_in_date_order(schedule):
    events = schedule[("skill_review", 115)]

    assert [event["name"] for event in events] == ["簡章網路下載", "網路報名", "報到截止"]
    assert events[1]["start"] == datetime(2026, 4, 20, 10, 0)
    assert events[1]["end"] == datetime(2026, 4, 23, 17, 0)
    assert events[0]["end"] is None


def test_same_day_events_keep_the_official_table_order(tmp_path):
    path = tmp_path / "schedule.csv"
    path.write_text("管道,學年度,項目,開始,結束,說明,出處\n"
                    "skill_review,115,資格審查結果查詢,2026-04-20 10:00,,,x\n"
                    "skill_review,115,寄送備審資料,2026-04-20 00:00,2026-04-24 23:59,,x\n", encoding="utf-8-sig")

    events = load_schedule(path)[("skill_review", 115)]

    assert [event["name"] for event in events] == ["資格審查結果查詢", "寄送備審資料"]


def test_six_digit_codes_are_skill_review_and_school_applications_have_no_joint_schedule():
    assert program_channel(_program("208003")) == "skill_review"
    assert program_channel(_program("DAY-NTUB-IM")) is None


def test_events_are_marked_past_current_and_upcoming_with_next_step(schedule):
    result = timeline(_program(), schedule, now=datetime(2026, 4, 21, 9, 0))

    states = {event["name"]: event["state"] for event in result["events"]}
    assert states == {"簡章網路下載": "past", "網路報名": "current", "報到截止": "upcoming"}
    assert result["next"]["name"] == "網路報名"
    assert result["finished"] is False


def test_single_day_event_counts_as_current_on_that_day(schedule):
    result = timeline(_program(), schedule, now=datetime(2026, 6, 2, 9, 0))

    assert result["next"]["name"] == "報到截止"


def test_finished_year_has_no_next_step(schedule):
    result = timeline(_program(), schedule, now=datetime(2026, 10, 22, 9, 0))

    assert result["finished"] is True
    assert result["next"] is None
    assert result["reference"] is False


def test_newer_program_without_published_schedule_uses_last_year_as_reference(schedule):
    result = timeline(_program(year=116), schedule, now=datetime(2026, 10, 22, 9, 0))

    assert result["year"] == 115
    assert result["reference"] is True


def test_school_application_program_has_no_timeline(schedule):
    assert timeline(_program("DAY-NTUB-IM"), schedule, now=datetime(2026, 4, 21)) is None


def test_bundled_schedule_file_has_official_115_skill_review_dates():
    events = load_schedule()[("skill_review", 115)]

    names = [event["name"] for event in events]
    assert "網路報名" in names and "登記就讀志願序" in names and "報到截止" in names
    assert all(event["source"].startswith("https://www.jctv.ntut.edu.tw/") for event in events)


# ---------- 頁面 ----------

@pytest.fixture()
def site():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        student = User(username="stu", display_name="stu", role="student")
        student.set_password("pw")
        db.session.add(student)
        db.session.flush()
        db.session.add(StudentProfile(user_id=student.id, student_no="stu", admission_year=111))
        for code in ("208003", "DAY-NTUB-IM"):
            program = AdmissionProgram(program_code=code, admission_year=115, school_name="國立臺北商業大學",
                                       department_name=f"資訊管理系{code}", status="published")
            program.items.append(AdmissionRequirementItem(source_item_name="證照", weight_percent=100,
                                                          mapped_categories="credential"))
            db.session.add(program)
            db.session.flush()
            db.session.add(StudentTarget(student_id=student.id, rule_version_id=program.id))
        db.session.commit()
    yield app


def login(app):
    client = app.test_client()
    client.post("/login", data={"username": "stu", "password": "pw"})
    return client


def test_schedule_page_lists_official_dates_and_says_next_year_is_not_out(site):
    html = login(site).get("/student/schedule").get_data(as_text=True)

    assert "網路報名" in html and "登記就讀志願序" in html
    assert "https://www.jctv.ntut.edu.tw/downloads/115/enter/115enterdate.pdf" in html
    assert "116" in html and "尚未公告" in html


def test_schedule_page_tells_school_application_targets_to_check_the_school(site):
    html = login(site).get("/student/schedule").get_data(as_text=True)

    assert "資訊管理系DAY-NTUB-IM" in html
    assert "依各校簡章" in html


def test_matching_page_cards_show_a_schedule_line(site):
    html = login(site).get("/student/matching").get_data(as_text=True)

    assert "/student/schedule" in html
    assert "依各校簡章" in html


def test_targets_page_links_to_schedule(site):
    html = login(site).get("/student/targets").get_data(as_text=True)

    assert "/student/schedule" in html
