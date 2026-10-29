"""T2 擷取招生日程：Agent 從官方日程表擷取候選日程 → 管理員核准後才取代招生時程頁的日程。"""
from datetime import datetime

import pytest

from app import create_app
from app.extensions import db
from app.models import AdmissionScheduleEvent, AuditLog, PublicSourceChange, User
from app.services import admission_agent_service as agent
from app.services.admission_schedule import load_schedule, schedule_groups
from app.services.agent_patrol import run_patrol

SCHEDULE = {"channel": "skill_review", "admission_year": 116, "events": [
    {"name": "網路報名", "start": "2027-04-19 10:00", "end": "2027-04-22 17:00", "note": "最後一天只到 17:00"},
    {"name": "報到截止", "start": "2027-06-01 17:00", "end": "", "note": ""},
    {"name": "日期寫錯", "start": "2027-13-40 10:00", "end": "", "note": ""},
    {"name": "結束比開始早", "start": "2027-05-02 10:00", "end": "2027-05-01 10:00", "note": ""},
]}


@pytest.fixture()
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "UPLOAD_FOLDER": str(tmp_path), "AGENT_SOURCE_FOLDER": str(tmp_path / "agent")})
    with app.app_context():
        db.create_all()
        for username, role in (("admin", "admin"), ("stu", "student")):
            user = User(username=username, display_name=username, role=role)
            user.set_password("pw")
            db.session.add(user)
        db.session.commit()
        yield app


def admin():
    return User.query.filter_by(username="admin").one()


def new_change(content=b"%PDF schedule"):
    source = agent.add_source("技專校院招生委員會聯合會", url="https://example.edu.tw/116enterdate.pdf")
    agent.check_source(source, admin(), fetch=lambda url: (content, "application/pdf"))
    return PublicSourceChange.query.order_by(PublicSourceChange.id.desc()).first()


def extract(change, schedule=SCHEDULE):
    return agent.extract_programs(change, admin(), generate=lambda prompt, schema, files: {"programs": [], "schedule": schedule})


def test_extraction_creates_candidate_schedule_events_and_skips_bad_rows(app):
    task = extract(new_change())

    events = AdmissionScheduleEvent.query.order_by(AdmissionScheduleEvent.start_at).all()
    assert [e.name for e in events] == ["網路報名", "報到截止"]
    assert events[0].start_at == datetime(2027, 4, 19, 10, 0) and events[0].end_at == datetime(2027, 4, 22, 17, 0)
    assert all(e.status == "candidate" and e.channel == "skill_review" and e.admission_year == 116 for e in events)
    assert events[0].source_url == "https://example.edu.tw/116enterdate.pdf"
    assert task.result_json["schedule_created"] == 2 and task.result_json["schedule_skipped"] == 2


def test_other_channels_are_not_stored(app):
    extract(new_change(), schedule={**SCHEDULE, "channel": "other"})

    assert AdmissionScheduleEvent.query.count() == 0


def test_same_candidates_are_not_created_twice(app):
    change = new_change()
    extract(change)
    change.status = "candidate"
    extract(change)

    assert AdmissionScheduleEvent.query.count() == 2


def test_prompt_asks_for_the_schedule_table():
    prompt = agent._extract_prompt(["資訊管理"])

    assert "日程" in prompt and "民國" in prompt and "skill_review" in prompt


def test_candidates_do_not_change_the_schedule_until_approved(app):
    extract(new_change())

    assert ("skill_review", 116) not in load_schedule()


def approve(client, year=116):
    return client.post(f"/admin/agent/schedule/skill_review/{year}/approve")


def login(app, username):
    client = app.test_client()
    client.post("/login", data={"username": username, "password": "pw"})
    return client


def test_admin_approval_publishes_the_group_and_overrides_the_file(app):
    extract(new_change())

    response = approve(login(app, "admin"))

    assert response.status_code == 302
    events = load_schedule()[("skill_review", 116)]
    assert [e["name"] for e in events] == ["網路報名", "報到截止"]
    assert events[0]["source"] == "https://example.edu.tw/116enterdate.pdf"
    assert AuditLog.query.filter_by(action="admission_schedule.approve").count() == 1


def test_approving_a_new_version_retires_the_old_published_events(app):
    extract(new_change())
    client = login(app, "admin")
    approve(client)
    newer = {**SCHEDULE, "events": [{"name": "網路報名", "start": "2027-04-20 10:00", "end": "2027-04-23 17:00", "note": ""}]}
    extract(new_change(b"%PDF newer"), schedule=newer)

    approve(client)

    events = load_schedule()[("skill_review", 116)]
    assert [(e["name"], e["start"]) for e in events] == [("網路報名", datetime(2027, 4, 20, 10, 0))]
    assert AdmissionScheduleEvent.query.filter_by(status="retired").count() == 2


def test_admin_can_reject_candidates(app):
    extract(new_change())

    login(app, "admin").post("/admin/agent/schedule/skill_review/116/reject")

    assert AdmissionScheduleEvent.query.filter_by(status="rejected").count() == 2
    assert AuditLog.query.filter_by(action="admission_schedule.reject").count() == 1


def test_students_cannot_approve(app):
    extract(new_change())

    response = approve(login(app, "stu"))

    assert response.status_code in (302, 403)
    assert AdmissionScheduleEvent.query.filter_by(status="published").count() == 0


def test_candidate_groups_compare_with_the_current_schedule(app):
    # 115 學年度已有檔案裡的官方日程；擷取一份 115 的候選，網路報名日期相同、報到截止日期不同、多一項新的
    same_and_changed = {"channel": "skill_review", "admission_year": 115, "events": [
        {"name": "網路報名", "start": "2026-04-20 10:00", "end": "2026-04-23 17:00", "note": ""},
        {"name": "報到截止", "start": "2026-06-03 17:00", "end": "", "note": ""},
        {"name": "新的項目", "start": "2026-05-01 10:00", "end": "", "note": ""},
    ]}
    extract(new_change(), schedule=same_and_changed)

    group = schedule_groups()[0]

    marks = {row["event"].name: row["mark"] for row in group["rows"]}
    assert marks == {"網路報名": "相同", "報到截止": "日期不同", "新的項目": "新增"}
    assert group["missing"]  # 目前日程有、候選沒有的項目也要列出來


def test_admin_agent_page_lists_candidate_schedule(app):
    extract(new_change())

    html = login(app, "admin").get("/admin/agent").get_data(as_text=True)

    assert "候選招生日程" in html and "網路報名" in html and "核准這一組" in html


def test_patrol_summary_mentions_candidate_schedule(app):
    agent.add_source("技專校院招生委員會聯合會", url="https://example.edu.tw/116enterdate.pdf")

    result = run_patrol(admin(), fetch=lambda url: (b"%PDF x", "application/pdf"),
                        generate=lambda prompt, schema, files: {"programs": [], "schedule": SCHEDULE}, decide=None)

    assert "候選日程" in result["summary"]


def test_candidates_match_current_events_by_date_or_similar_name(app):
    # 115 學年度檔案裡有「網路報名」（4/20 10:00～4/23 17:00）與「登記就讀志願序」（5/15 10:00～5/19 17:00）
    wordy = {"channel": "skill_review", "admission_year": 115, "events": [
        {"name": "網路報名（當日只到 17:00）", "start": "2026-04-20 10:00", "end": "2026-04-23 17:00", "note": ""},
        {"name": "錄取生登記志願序", "start": "2026-05-15 10:00", "end": "2026-05-19 17:00", "note": ""},
    ]}
    extract(new_change(), schedule=wordy)

    group = schedule_groups()[0]

    assert [row["mark"] for row in group["rows"]] == ["相同", "相同"]
    assert "網路報名" not in group["missing"] and "登記就讀志願序" not in group["missing"]


def test_prompt_excludes_items_only_for_skill_admission_and_keeps_names_short():
    prompt = agent._extract_prompt(["資訊管理"])

    assert "只出現在【技優保送】欄" in prompt and "20 個字" in prompt
