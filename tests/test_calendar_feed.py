"""備審時間線行事曆訂閱（.ics）。（僅為測試資料）"""
from datetime import datetime

import pytest

from app import create_app
from app.extensions import db
from app.models import AuditLog, StudentProfile, SystemSetting, User
from app.services import calendar_feed, check_dates


@pytest.fixture()
def app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "WTF_CSRF_ENABLED": False, "TWO_FACTOR_REQUIRED": False})
    with app.app_context():
        db.create_all()
        yield app


def make_student(username="cal1"):
    user = User(username=username, display_name="合成學生", role="student")
    user.set_password("pw-123456789")
    db.session.add(user)
    db.session.flush()
    db.session.add(StudentProfile(user_id=user.id, student_no=username, class_name="資五甲", admission_year=111))
    db.session.commit()
    return user


def test_build_ics_is_valid_and_has_events(app):
    student = make_student()
    events = [
        {"uid": "a", "name": "報名,截止;測試", "start": datetime(2026, 3, 2, 9, 0), "end": None,
         "all_day": False, "description": "", "url": "https://example.edu.tw"},
        {"uid": "b", "name": "畢業檢核", "start": datetime(2026, 5, 1), "end": None, "all_day": True,
         "description": "很長的說明" * 30, "url": ""},
    ]
    text = calendar_feed.build_ics(student, events)
    assert text.startswith("BEGIN:VCALENDAR\r\n") and text.endswith("END:VCALENDAR\r\n")
    assert "DTSTART:20260302T010000Z" in text  # 台灣 09:00 = UTC 01:00
    assert "DTSTART;VALUE=DATE:20260501" in text and "DTEND;VALUE=DATE:20260502" in text
    assert "SUMMARY:報名\\,截止\\;測試" in text
    assert all(len(line.encode("utf-8")) <= 75 for line in text.split("\r\n"))


def test_collect_includes_skill_review_and_check_dates(app):
    student = make_student()
    db.session.add(SystemSetting(key=check_dates.FIRST_KEY, value="2026-05-01"))
    db.session.commit()
    names = [e["name"] for e in calendar_feed.collect_events(student)]
    assert any(n.startswith("二技技優甄審：") for n in names)
    assert any(n.startswith("畢業檢核：") for n in names)


def login(client, username):
    client.post("/login", data={"username": username, "password": "pw-123456789"})


def test_schedule_page_shows_private_url_and_feed_works_without_login(app):
    student = make_student()
    client = app.test_client()
    login(client, "cal1")
    page = client.get("/student/schedule").get_data(as_text=True)
    token = db.session.get(User, student.id).calendar_token
    assert token and f"/calendar/{token}.ics" in page
    resp = app.test_client().get(f"/calendar/{token}.ics")
    assert resp.status_code == 200 and resp.mimetype == "text/calendar"
    assert b"BEGIN:VCALENDAR" in resp.data
    assert app.test_client().get("/calendar/wrong-token.ics").status_code == 404


def test_reset_invalidates_old_url(app):
    student = make_student()
    client = app.test_client()
    login(client, "cal1")
    client.get("/student/schedule")
    old = db.session.get(User, student.id).calendar_token
    client.post("/student/calendar/reset")
    db.session.expire_all()
    new = db.session.get(User, student.id).calendar_token
    assert new and new != old
    assert app.test_client().get(f"/calendar/{old}.ics").status_code == 404
    assert app.test_client().get(f"/calendar/{new}.ics").status_code == 200
    assert AuditLog.query.filter_by(action="calendar.reset").count() == 1


def test_inactive_student_feed_is_gone(app):
    student = make_student()
    token = calendar_feed.commit_token(student)
    student.is_active = False
    db.session.commit()
    assert app.test_client().get(f"/calendar/{token}.ics").status_code == 404
