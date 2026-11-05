"""畢業缺口案件頁、通知頁、學生頁與同步觸發點。（僅為測試資料）"""
import io
import json

from app.extensions import db
from app.models import (ClassAdvisor, GraduationCase, GraduationCaseEvent, Notification,
                        SourceDocument, SystemSetting, User)
from app.services import graduation_case_service as svc
from tests.test_student_records import records_app

DISCLAIMER = "僅供提醒"


def _user(username, role, name):
    user = User(username=username, display_name=name, role=role)
    user.set_password("pw")
    db.session.add(user)
    db.session.flush()
    return user


def pages_app(tmp_path):
    app = records_app(tmp_path)
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        student.student_profile.class_name = "五專四甲"
        teacher = _user("tea", "teacher", "導師")
        _user("sta", "staff", "科辦")
        _user("other", "student", "別人")
        db.session.add(ClassAdvisor(teacher_id=teacher.id, class_name="五專四甲", school_year=115))
        db.session.add(SystemSetting(key="graduation_check_today", value="2026-03-01"))
        db.session.commit()
    return app


def as_user(app, username):
    client = app.test_client()
    client.post("/login", data={"username": username, "password": "pw"})
    return client


def make_case(app):
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        svc.sync_student(student)
        db.session.commit()
        return GraduationCase.query.filter_by(item="certificates", case_type="gap").one().id


def counts(app):
    with app.app_context():
        return (GraduationCase.query.count(), GraduationCaseEvent.query.count(),
                Notification.query.count())


def test_case_page_same_number_for_three_roles(tmp_path):
    app = pages_app(tmp_path)
    case_id = make_case(app)
    with app.app_context():
        number = db.session.get(GraduationCase, case_id).number
    for username in ("stu", "tea", "sta"):
        response = as_user(app, username).get(f"/graduation/cases/{case_id}")
        assert response.status_code == 200
        assert number in response.get_data(as_text=True)


def test_case_page_forbidden_for_other_student(tmp_path):
    app = pages_app(tmp_path)
    case_id = make_case(app)
    assert as_user(app, "other").get(f"/graduation/cases/{case_id}").status_code == 403


def test_opening_pages_creates_nothing(tmp_path):
    app = pages_app(tmp_path)
    case_id = make_case(app)
    before = counts(app)
    plan = (("stu", ["/student/graduation-check", f"/graduation/cases/{case_id}", "/notifications"]),
            ("tea", ["/teacher/dashboard", f"/graduation/cases/{case_id}"]),
            ("sta", ["/staff/dashboard", f"/graduation/cases/{case_id}"]))
    for username, paths in plan:
        client = as_user(app, username)
        for _ in range(2):
            for path in paths:
                assert client.get(path).status_code == 200, path
    assert counts(app) == before


def test_confirming_document_triggers_sync(tmp_path):
    app = pages_app(tmp_path)
    client = as_user(app, "stu")
    client.post("/student/learning-profile/documents", data={
        "document_type": "credential", "file": (io.BytesIO(b"demo"), "cert.pdf"),
    }, content_type="multipart/form-data")
    with app.app_context():
        assert GraduationCase.query.count() == 0
        document = SourceDocument.query.one()
        document_id = document.id
        revision = document.extraction.result_json["draft_revision"]
    response = client.post(f"/student/learning-profile/documents/{document_id}/review/confirm", data={
        "draft_revision": revision, "courses_json": "[]", "credentials_json": json.dumps([]),
    })
    assert response.status_code == 302
    with app.app_context():
        assert GraduationCase.query.filter_by(item="certificates", case_type="gap").count() == 1


def test_transfer_credit_save_triggers_sync(tmp_path):
    app = pages_app(tmp_path)
    client = as_user(app, "stu")
    response = client.post("/student/transfer-credit", data={"status": "submitted"})
    assert response.status_code == 302
    with app.app_context():
        assert GraduationCase.query.filter_by(item="certificates", case_type="gap").count() == 1


def test_teacher_confirm_transfer_triggers_sync(tmp_path):
    app = pages_app(tmp_path)
    as_user(app, "stu").post("/student/transfer-credit", data={"status": "completed"})
    with app.app_context():
        student_id = User.query.filter_by(username="stu").one().id
        Notification.query.delete()
        GraduationCaseEvent.query.delete()
        GraduationCase.query.delete()
        db.session.commit()
    response = as_user(app, "tea").post(f"/teacher/students/{student_id}/transfer-credit/confirm",
                                        data={"confirmed": "1"})
    assert response.status_code == 302
    with app.app_context():
        assert GraduationCase.query.filter_by(item="certificates", case_type="gap").count() == 1


def test_case_page_shows_disclaimers(tmp_path):
    app = pages_app(tmp_path)
    case_id = make_case(app)
    html = as_user(app, "stu").get(f"/graduation/cases/{case_id}").get_data(as_text=True)
    assert DISCLAIMER in html
    assert "不代表學生符合全部畢業資格" not in html
    with app.app_context():
        case = db.session.get(GraduationCase, case_id)
        case.status, case.close_reason, case.open_key = "closed", "improved", None
        db.session.commit()
    html = as_user(app, "stu").get(f"/graduation/cases/{case_id}").get_data(as_text=True)
    assert "不代表學生符合全部畢業資格" in html


def test_unread_count_drops_after_opening_case(tmp_path):
    app = pages_app(tmp_path)
    case_id = make_case(app)
    client = as_user(app, "stu")
    with app.app_context():
        student_id = User.query.filter_by(username="stu").one().id
        unread = Notification.query.filter_by(recipient_id=student_id, read_at=None).count()
    assert unread >= 1
    assert f"{unread} 則未讀通知" in client.get("/student/dashboard").get_data(as_text=True)
    client.get(f"/graduation/cases/{case_id}")
    with app.app_context():
        assert Notification.query.filter_by(recipient_id=student_id, read_at=None,
                                            case_id=case_id).count() == 0
        remaining = Notification.query.filter_by(recipient_id=student_id, read_at=None).count()
    assert remaining < unread
    page = client.get("/student/dashboard").get_data(as_text=True)
    assert (f"{remaining} 則未讀通知" in page) if remaining else ("則未讀通知" not in page)


def test_notifications_page_lists_messages(tmp_path):
    app = pages_app(tmp_path)
    case_id = make_case(app)
    with app.app_context():
        number = db.session.get(GraduationCase, case_id).number
    html = as_user(app, "tea").get("/notifications").get_data(as_text=True)
    assert number in html


def test_staff_recheck_only_for_staff(tmp_path):
    app = pages_app(tmp_path)
    assert as_user(app, "tea").post("/staff/graduation/recheck").status_code == 403
    assert as_user(app, "stu").post("/staff/graduation/recheck").status_code == 403
    response = as_user(app, "sta").post("/staff/graduation/recheck")
    assert response.status_code == 302
    with app.app_context():
        assert GraduationCase.query.filter_by(item="certificates", case_type="gap").count() == 1


def test_case_action_route_and_errors(tmp_path):
    app = pages_app(tmp_path)
    case_id = make_case(app)
    student = as_user(app, "stu")
    url = f"/graduation/cases/{case_id}/actions"
    assert student.post(url, data={"action": "verify"}).status_code == 403
    assert student.post(url, data={"action": "note", "note": ""}).status_code == 400
    assert student.post(url, data={"action": "start"}).status_code == 302
    with app.app_context():
        assert db.session.get(GraduationCase, case_id).status == "in_progress"


def test_inquiry_creates_case_and_notifies_teacher(tmp_path):
    app = pages_app(tmp_path)
    client = as_user(app, "stu")
    assert client.post("/student/graduation-check/inquiry", data={"note": ""}).status_code == 400
    response = client.post("/student/graduation-check/inquiry", data={"note": "請問證照怎麼算？"})
    assert response.status_code == 302
    with app.app_context():
        case = GraduationCase.query.filter_by(case_type="inquiry").one()
        tea = User.query.filter_by(username="tea").one()
        assert Notification.query.filter_by(recipient_id=tea.id, case_id=case.id).count() == 1


def test_student_page_shows_results_remedy_and_case(tmp_path):
    app = pages_app(tmp_path)
    case_id = make_case(app)
    with app.app_context():
        number = db.session.get(GraduationCase, case_id).number
    html = as_user(app, "stu").get("/student/graduation-check").get_data(as_text=True)
    assert DISCLAIMER in html
    assert number in html
    assert "有缺口" in html
    assert "第五點" in html and "109 學年度（含）以後入學" in html
    from app.services.graduation_check_service import REMEDY_TEXT
    assert REMEDY_TEXT["total_credits"] == "請洽科辦確認補修方式。"
