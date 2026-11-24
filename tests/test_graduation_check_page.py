"""畢業門檻頁：學生登入後可看到證照與學分提醒；只用已確認資料。（僅為測試資料）"""
from app.extensions import db
from app.models import CredentialRecord, LearningCourseRecord
from tests.test_student_records import login, records_app


def test_graduation_page_shows_reminder_with_confirmed_data(tmp_path):
    app = records_app(tmp_path)
    with app.app_context():
        from app.models import User
        student = User.query.filter_by(username="stu").one()
        db.session.add(CredentialRecord(student_id=student.id, credential_name="電腦軟體應用 丙級",
                                        level="丙級", confirmation_status="confirmed"))
        db.session.add(CredentialRecord(student_id=student.id, credential_name="網頁設計 丙級",
                                        level="丙級", confirmation_status="draft"))
        db.session.add(LearningCourseRecord(student_id=student.id, course_name="國文", normalized_course_name="國文",
                                            credits=8, score=80, confirmation_status="confirmed"))
        db.session.commit()
    client = app.test_client()
    login(client)

    response = client.get("/student/graduation-check")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "畢業門檻提醒" in html
    assert "電腦軟體應用 丙級" in html
    assert "網頁設計 丙級" not in html
    assert "僅供提醒" in html


def test_graduation_page_needs_student_login(tmp_path):
    client = records_app(tmp_path).test_client()

    response = client.get("/student/graduation-check")

    assert response.status_code in (302, 401, 403)


def test_graduation_attendance_is_scoped_to_student_and_date(tmp_path, monkeypatch):
    from datetime import date

    from app.models import AttendanceSummary, User
    from app.services import graduation_check_service

    app = records_app(tmp_path)
    monkeypatch.setattr(graduation_check_service, "check_today", lambda: date(2026, 11, 18))
    client = app.test_client()
    login(client)

    def attendance_card():
        page = client.get("/student/graduation-check").get_data(as_text=True)
        return page.split('id="graduation-attendance"', 1)[1].split("</section>", 1)[0]

    assert "尚未匯入" in attendance_card()
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        other = User(username="attendance_other", display_name="缺曠測試學生", role="student")
        other.set_password("test-only")
        db.session.add(other)
        db.session.flush()
        db.session.add_all([
            AttendanceSummary(student_id=student.id, school_year=114, semester=2, totals={"曠課": 0}),
            AttendanceSummary(student_id=other.id, school_year=115, semester=1, totals={"曠課": 777}),
        ])
        db.session.commit()

    card = attendance_card()
    assert "最近已確認 · 114 學年度第 2 學期" in card
    assert "<dt>曠課</dt><dd>0</dd>" in card
    assert "<dt>遲到</dt><dd>未提供</dd>" in card
    assert "777" not in card
    assert "/student/attendance-records#saved-attendance" in card

    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        db.session.add(AttendanceSummary(student_id=student.id, school_year=115, semester=1,
                                         totals={"至今缺課總時數": 12, "應上課 1/3 總時數": 90}))
        db.session.commit()

    card = attendance_card()
    assert "尚未匯入" not in card
    assert "最近已確認" not in card
    assert "<dt>至今缺課總時數</dt><dd>12</dd>" in card
    assert "<dt>應上課 1/3 總時數</dt><dd>90</dd>" in card
