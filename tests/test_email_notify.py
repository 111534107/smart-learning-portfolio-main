"""電子郵件通知（2026-11-12）。全部用假 SMTP，不會真的寄信。（僅為測試資料）"""
from datetime import date

import pytest

from app import create_app
from app.extensions import db
from app.models import (AuditLog, ClassAdvisor, CredentialRecord, LearningCourseRecord, Notification,
                        StudentProfile, SystemSetting, User)
from app.services import check_dates, email_notify
from app.services import graduation_case_service as svc
from app.services.eligibility_service import normalize_course_name

GAP_DAY = date(2026, 3, 1)  # 111 入學：專四下（正式）


@pytest.fixture()
def app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "WTF_CSRF_ENABLED": False, "MAIL_RETRY_DELAY": 0})
    with app.app_context():
        db.create_all()
        yield app


@pytest.fixture()
def sent(monkeypatch):
    """假 SMTP：讓 smtp_ready 為真，記下寄出的信。"""
    box = []
    monkeypatch.setattr(email_notify, "smtp_ready", lambda: True)
    monkeypatch.setattr(email_notify, "_send", lambda to, subject, body: box.append((to, subject, body)))
    return box


def make_user(username, role, email=None):
    user = User(username=username, display_name=username, role=role, email=email)
    user.set_password("pw-123456789")
    db.session.add(user)
    db.session.flush()
    return user


def setup_gap():
    teacher = make_user("t1", "teacher", "t1@example.test")
    db.session.add(ClassAdvisor(teacher_id=teacher.id, class_name="資管科五甲", school_year=115))
    student = make_user("s1", "student", "s1@example.test")
    db.session.add(StudentProfile(user_id=student.id, student_no="s1", class_name="資管科五甲", admission_year=111))
    db.session.add(CredentialRecord(student_id=student.id, credential_name="電腦軟體應用 丙級", level="丙級",
                                    issue_date=date(2025, 1, 1), confirmation_status="confirmed"))
    db.session.flush()
    return student, teacher


def email_logs():
    return AuditLog.query.filter_by(action="email.notify").all()


def test_gap_case_sends_email_to_student_and_advisor(app, sent):
    student, teacher = setup_gap()
    svc.sync_student(student, today=GAP_DAY)
    to = {row[0] for row in sent}
    assert {"s1@example.test", "t1@example.test"} <= to
    assert all(row[1] == email_notify.SUBJECT for row in sent)
    assert all("請登入查看" in row[2] and "丙級" not in row[2] for row in sent)
    assert {log.detail_json["status"] for log in email_logs()} == {"sent"}
    count = len(sent)
    svc.sync_student(student, today=GAP_DAY)  # 冪等：沒有新事件就不再寄
    assert len(sent) == count


def test_without_smtp_logs_but_does_not_send(app, monkeypatch):
    calls = []
    monkeypatch.setattr(email_notify, "_send", lambda *a: calls.append(a))
    student, _ = setup_gap()
    svc.sync_student(student, today=GAP_DAY)
    assert calls == []
    logs = email_logs()
    assert logs and {log.detail_json["status"] for log in logs} == {"logged"}


def test_user_opt_out_and_global_switch(app, sent):
    student, teacher = setup_gap()
    student.email_notify = False
    svc.sync_student(student, today=GAP_DAY)
    assert {row[0] for row in sent} == {"t1@example.test"}
    assert Notification.query.filter_by(recipient_id=student.id).count() >= 1  # 站內通知照常
    sent.clear()
    email_notify.set_globally_enabled(False, None)
    assert email_notify.notify(teacher, "graduation_case") == "disabled"
    assert sent == []


def test_send_failure_retries_and_does_not_raise(app, monkeypatch):
    attempts = []

    def boom(*a):
        attempts.append(a)
        raise OSError("smtp down")

    monkeypatch.setattr(email_notify, "smtp_ready", lambda: True)
    monkeypatch.setattr(email_notify, "_send", boom)
    student, _ = setup_gap()
    svc.sync_student(student, today=GAP_DAY)  # 不丟例外
    assert len(attempts) >= 3  # 每位收件者 1 次 + 重試 2 次
    failed = [log for log in email_logs() if log.detail_json["status"] == "failed"]
    assert failed and failed[0].detail_json["attempts"] == 3


def test_semester_warning_notifies_once(app, sent):
    student, teacher = setup_gap()
    for name in ("計算機概論", "程式設計", "會計學"):
        db.session.add(LearningCourseRecord(student_id=student.id, course_name=name,
                                            normalized_course_name=normalize_course_name(name), credits=3,
                                            score=40, school_year=1, semester="上", confirmation_status="confirmed"))
    db.session.flush()
    svc.sync_student(student, today=GAP_DAY)
    keys = [n.notify_key for n in Notification.query.filter(Notification.notify_key.like("semwarn:%")).all()]
    assert keys and len(keys) == 2 * len(set(keys))  # 學生、導師各一
    before = len(sent)
    svc.sync_student(student, today=GAP_DAY)
    assert len(sent) == before


def test_check_date_countdown_reminder(app, sent):
    student, _ = setup_gap()
    db.session.add(SystemSetting(key=check_dates.FIRST_KEY, value="2026-03-05"))
    db.session.flush()
    svc.sync_student(student, today=GAP_DAY)
    rows = Notification.query.filter(Notification.notify_key.like("countdown:%")).all()
    assert [r.recipient_id for r in rows] == [student.id]
    svc.sync_student(student, today=GAP_DAY)
    assert Notification.query.filter(Notification.notify_key.like("countdown:%")).count() == 1


def login(client, user):
    with client.session_transaction() as sess:
        sess["user_id"] = user.id


def test_account_toggle_and_admin_switch(app):
    student = make_user("s2", "student", "s2@example.test")
    admin = make_user("a1", "admin")
    db.session.commit()
    client = app.test_client()
    client.post("/login", data={"username": "s2", "password": "pw-123456789"})
    page = client.get("/account/password").get_data(as_text=True)
    assert "電子郵件通知" in page
    client.post("/account/email-notify", data={})
    assert db.session.get(User, student.id).email_notify is False
    admin_client = app.test_client()
    admin_client.post("/login", data={"username": "a1", "password": "pw-123456789"})
    resp = admin_client.post("/admin/email-notify", data={})
    assert resp.status_code == 302
    assert email_notify.globally_enabled() is False
