from datetime import date

import pytest

from app import create_app
from app.extensions import db
from app.models import AdmissionProgram, ClassAdvisor, GraduationCase, GraduationCaseEvent, Notification, PackageReview, Portfolio, PortfolioSubmission, StudentProfile, StudentTarget, SubmissionAssignment, User
from app.services import admin_todos, graduation_case_service, review_snapshot_service, teacher_scope


@pytest.fixture
def setup_year(monkeypatch):
    monkeypatch.setattr(teacher_scope, "current_school_year", lambda: 115, raising=False)
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "MIN_REVIEW_GRADE": 1})
    with app.app_context():
        db.create_all()
        roles = [("test_student", "student"), ("test_old", "teacher"), ("test_current1", "teacher"),
                 ("test_current2", "teacher"), ("test_inactive", "teacher"), ("test_future", "teacher")]
        users = {}
        for name, role in roles:
            user = User(username=name, display_name=name, role=role)
            user.set_password("pw")
            db.session.add(user)
            users[name] = user
        db.session.flush()
        users["test_inactive"].is_active = False
        student = users["test_student"]
        db.session.add(StudentProfile(user_id=student.id, student_no="TEST-001", class_name="測試五甲", admission_year=111))
        for name, year in [("test_old", 114), ("test_current1", 115), ("test_current2", 115), ("test_inactive", 115), ("test_future", 116)]:
            db.session.add(ClassAdvisor(teacher_id=users[name].id, class_name="測試五甲", school_year=year))
        program = AdmissionProgram(program_code="TESTYEAR", admission_year=115, school_name="測試學校", department_name="測試科系", status="published")
        db.session.add(program)
        db.session.flush()
        db.session.add(StudentTarget(student_id=student.id, rule_version_id=program.id))
        db.session.commit()
        ids = {name: user.id for name, user in users.items()}
        ids["program"] = program.id
    return app, ids


def test_school_year_rolls_over_on_august_first():
    assert teacher_scope.school_year_for_date(date(2026, 7, 31)) == 114
    assert teacher_scope.school_year_for_date(date(2026, 8, 1)) == 115


def test_only_current_year_active_advisors_can_access_and_receive(setup_year):
    app, ids = setup_year
    with app.app_context():
        student = db.session.get(User, ids["test_student"])
        current = {ids["test_current1"], ids["test_current2"]}
        assert {u.id for u in teacher_scope.teachers_for_student(student)} == current
        assert {u.id for u in review_snapshot_service.review_teachers(student)} == current
        assert {u.id for u in graduation_case_service.advisors_for(student)} == current
        for name in ("test_old", "test_future", "test_inactive"):
            assert not teacher_scope.can_view_student(db.session.get(User, ids[name]), student)
        for name in ("test_current1", "test_current2"):
            assert teacher_scope.can_view_student(db.session.get(User, ids[name]), student)
        assert not admin_todos.classes_without_advisor()
        student.is_active = False
        db.session.flush()
        assert not teacher_scope.can_view_student(db.session.get(User, ids["test_current1"]), student)
        student.is_active = True
        for name in ("test_current1", "test_current2"):
            db.session.get(User, ids[name]).is_active = False
        db.session.flush()
        assert "測試五甲" in admin_todos.classes_without_advisor()


def test_submission_and_teacher_page_respect_current_year(setup_year):
    app, ids = setup_year
    student = app.test_client()
    student.post("/login", data={"username": "test_student", "password": "pw"})
    assert student.post(f"/student/targets/{ids['program']}/review").status_code == 302
    with app.app_context():
        notes = Notification.query.all()
        assert {n.recipient_id for n in notes} == {ids["test_current1"], ids["test_current2"]}
        review = PackageReview.query.one()
        review_id, taken_at = review.id, review.snapshot_json["taken_at"]
    old = app.test_client()
    old.post("/staff/login", data={"username": "test_old", "password": "pw"})
    assert old.get(f"/teacher/students/{ids['test_student']}").status_code == 403
    assert old.post(f"/teacher/package-reviews/{review_id}", data={"decision": "confirmed", "taken_at": taken_at}).status_code == 403
    current = app.test_client()
    current.post("/staff/login", data={"username": "test_current1", "password": "pw"})
    assert current.get(f"/teacher/students/{ids['test_student']}").status_code == 200


def test_old_teacher_cannot_read_existing_student_notifications(setup_year):
    app, ids = setup_year
    with app.app_context():
        case = GraduationCase(student_id=ids["test_student"], case_type="gap", item="certificates", status="pending")
        db.session.add(case)
        db.session.flush()
        event = GraduationCaseEvent(case_id=case.id, event_type="created")
        db.session.add(event)
        db.session.flush()
        notes = [
            Notification(recipient_id=ids["test_old"], message="測試學生送審隱私", link=f"/teacher/students/{ids['test_student']}#teacher-target-1"),
            Notification(recipient_id=ids["test_old"], message="測試學生案件隱私", event_id=event.id),
            Notification(recipient_id=ids["test_old"], message="一般通知可以看", link="/forms"),
        ]
        db.session.add_all(notes)
        db.session.commit()
        private_id = notes[0].id
    client = app.test_client()
    client.post("/staff/login", data={"username": "test_old", "password": "pw"})
    html = client.get("/notifications").get_data(as_text=True)
    assert "測試學生送審隱私" not in html
    assert "測試學生案件隱私" not in html
    assert "一般通知可以看" in html
    assert 'aria-label="1 則未讀通知"' in html
    assert client.get(f"/notifications/{private_id}/open").status_code == 404
    with app.app_context():
        assert db.session.get(Notification, private_id).read_at is None


def test_new_academic_year_revokes_old_access_without_deleting_notifications(setup_year, monkeypatch):
    app, ids = setup_year
    with app.app_context():
        note = Notification(recipient_id=ids["test_current1"], message="測試新年度前的送審",
                            link=f"/teacher/students/{ids['test_student']}#teacher-target-1")
        db.session.add(note)
        db.session.commit()
        note_id = note.id
    client = app.test_client()
    client.post("/staff/login", data={"username": "test_current1", "password": "pw"})
    assert "測試新年度前的送審" in client.get("/notifications").get_data(as_text=True)
    monkeypatch.setattr(teacher_scope, "current_school_year", lambda: 116)
    assert client.get(f"/teacher/students/{ids['test_student']}").status_code == 403
    assert "測試新年度前的送審" not in client.get("/notifications").get_data(as_text=True)
    assert client.get(f"/notifications/{note_id}/open").status_code == 404
    with app.app_context():
        assert db.session.get(Notification, note_id) is not None
        assert {u.id for u in teacher_scope.teachers_for_student(db.session.get(User, ids["test_student"]))} == {ids["test_future"]}


def test_old_legacy_review_assignment_does_not_bypass_current_year_scope(setup_year):
    app, ids = setup_year
    with app.app_context():
        portfolio = Portfolio(student_id=ids["test_student"], title="僅為測試資料的舊送審", category="activity")
        db.session.add(portfolio)
        db.session.flush()
        submission = PortfolioSubmission(portfolio_id=portfolio.id, version_no=1, status="submitted")
        db.session.add(submission)
        db.session.flush()
        db.session.add_all([
            SubmissionAssignment(submission_id=submission.id, teacher_id=ids["test_old"]),
            SubmissionAssignment(submission_id=submission.id, teacher_id=ids["test_current1"]),
        ])
        db.session.commit()
        submission_id = submission.id
    old = app.test_client()
    old.post("/staff/login", data={"username": "test_old", "password": "pw"})
    assert "僅為測試資料的舊送審" not in old.get("/teacher/reviews").get_data(as_text=True)
    assert old.post(f"/teacher/reviews/{submission_id}/feedback", data={"comment": "測試"}).status_code == 403
    current = app.test_client()
    current.post("/staff/login", data={"username": "test_current1", "password": "pw"})
    assert "僅為測試資料的舊送審" in current.get("/teacher/reviews").get_data(as_text=True)
    assert current.post(f"/teacher/reviews/{submission_id}/feedback", data={"comment": "測試"}).status_code == 302
