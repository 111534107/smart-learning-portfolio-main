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
