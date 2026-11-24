import pytest

from app import create_app
from app.extensions import db
from app.models import AdmissionProgram, ClassAdvisor, Notification, PackageReview, StudentProfile, StudentTarget, User


@pytest.fixture
def review_setup():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "MIN_REVIEW_GRADE": 1})
    with app.app_context():
        db.create_all()
        users = [User(username=name, display_name=name, role=role) for name, role in [
            ("student", "student"), ("teacher1", "teacher"), ("teacher2", "teacher"),
            ("other", "teacher"), ("inactive", "teacher"), ("student2", "student"),
        ]]
        for user in users:
            user.set_password("pw")
        users[4].is_active = False
        db.session.add_all(users)
        db.session.flush()
        student, teacher1, teacher2, other, inactive, student2 = users
        db.session.add_all([
            StudentProfile(user_id=student.id, student_no="DEMO-1", class_name="測試甲班", admission_year=110),
            StudentProfile(user_id=student2.id, student_no="DEMO-2", class_name="測試乙班", admission_year=110),
            ClassAdvisor(teacher_id=teacher1.id, class_name="測試甲班", school_year=114),
            ClassAdvisor(teacher_id=teacher1.id, class_name="測試甲班", school_year=115),
            ClassAdvisor(teacher_id=teacher2.id, class_name="測試甲班", school_year=115),
            ClassAdvisor(teacher_id=inactive.id, class_name="測試甲班", school_year=115),
            ClassAdvisor(teacher_id=other.id, class_name="測試乙班", school_year=115),
        ])
        program = AdmissionProgram(program_code="DEMO1", admission_year=115, school_name="測試大學", department_name="資訊管理系", status="published")
        db.session.add(program)
        db.session.flush()
        db.session.add(StudentTarget(student_id=student.id, rule_version_id=program.id))
        db.session.commit()
        ids = {u.username: u.id for u in users}
        ids["program"] = program.id
    return app, ids


def login(client, username, staff=False):
    return client.post("/staff/login" if staff else "/login", data={"username": username, "password": "pw"})


def test_submission_notifies_each_active_class_teacher_and_links_to_review(review_setup):
    app, ids = review_setup
    student_client = app.test_client()
    login(student_client, "student")
    assert student_client.post(f"/student/targets/{ids['program']}/review").status_code == 302
    with app.app_context():
        notes = Notification.query.order_by(Notification.recipient_id).all()
        review = PackageReview.query.one()
        assert {n.recipient_id for n in notes} == {ids["teacher1"], ids["teacher2"]}
        assert len(notes) == 2
        note_id = next(n.id for n in notes if n.recipient_id == ids["teacher1"])
        assert all(n.link == f"/teacher/students/{ids['student']}#teacher-target-{ids['program']}" for n in notes)
    teacher_client = app.test_client()
    login(teacher_client, "teacher1", staff=True)
    opened = teacher_client.get(f"/notifications/{note_id}/open")
    assert opened.status_code == 302
    assert opened.location.endswith(f"/teacher/students/{ids['student']}#teacher-target-{ids['program']}")
    page = teacher_client.get(opened.location)
    assert page.status_code == 200
    assert f'id="teacher-target-{ids["program"]}"' in page.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Notification, note_id).read_at is not None
    other_client = app.test_client()
    login(other_client, "other", staff=True)
    assert other_client.get(f"/notifications/{note_id}/open").status_code == 404


@pytest.mark.parametrize("decision,comment", [("confirmed", ""), ("needs_revision", "請補充資料")])
def test_teacher_decision_notifies_student_and_links_to_result(review_setup, decision, comment):
    app, ids = review_setup
    student_client, teacher_client = app.test_client(), app.test_client()
    login(student_client, "student")
    student_client.post(f"/student/targets/{ids['program']}/review")
    with app.app_context():
        review = PackageReview.query.one()
        review_id = review.id
        taken_at = review.snapshot_json["taken_at"]
    login(teacher_client, "teacher1", staff=True)
    result = teacher_client.post(f"/teacher/package-reviews/{review_id}", data={"decision": decision, "comment": comment, "taken_at": taken_at})
    assert result.status_code == 302
    with app.app_context():
        note = Notification.query.filter_by(recipient_id=ids["student"]).one()
        note_id, link = note.id, note.link
        assert link == f"/student/package-reviews/{review_id}/result"
        assert ("已確認" if decision == "confirmed" else "建議修改") in note.message
    opened = student_client.get(f"/notifications/{note_id}/open")
    assert opened.status_code == 302
    assert opened.location.endswith(link)
    page = student_client.get(opened.location, follow_redirects=True)
    assert page.status_code == 200
    if comment:
        assert comment in page.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Notification, note_id).read_at is not None
    other_student = app.test_client()
    login(other_student, "student2")
    assert other_student.get(f"/notifications/{note_id}/open").status_code == 404
    assert teacher_client.post(f"/teacher/package-reviews/{review_id}", data={"decision": decision, "comment": comment, "taken_at": taken_at}).status_code == 302
    with app.app_context():
        assert Notification.query.filter_by(recipient_id=ids["student"]).count() == 1
        StudentTarget.query.filter_by(student_id=ids["student"], rule_version_id=ids["program"]).delete()
        db.session.commit()
    cancelled_page = student_client.get(link)
    assert cancelled_page.status_code == 200
    assert "這個目標校系已取消" in cancelled_page.get_data(as_text=True)
    if comment:
        assert comment in cancelled_page.get_data(as_text=True)
    assert other_student.get(link).status_code == 404


def test_updated_pending_submission_notifies_teachers_without_duplicates_per_action(review_setup):
    app, ids = review_setup
    client = app.test_client()
    login(client, "student")
    url = f"/student/targets/{ids['program']}/review"
    assert client.post(url).status_code == 302
    assert client.post(url).status_code == 302
    with app.app_context():
        assert PackageReview.query.count() == 1
        assert Notification.query.filter_by(recipient_id=ids["teacher1"]).count() == 2
        assert Notification.query.filter_by(recipient_id=ids["teacher2"]).count() == 2


def test_student_is_warned_when_class_has_no_active_teacher(review_setup):
    app, ids = review_setup
    with app.app_context():
        for username in ("teacher1", "teacher2"):
            db.session.get(User, ids[username]).is_active = False
        db.session.commit()
    client = app.test_client()
    login(client, "student")
    response = client.post(f"/student/targets/{ids['program']}/review", follow_redirects=True)
    assert response.status_code == 200
    assert "目前沒有找到你班級的導師" in response.get_data(as_text=True)
    with app.app_context():
        assert PackageReview.query.count() == 1
        assert Notification.query.count() == 0
