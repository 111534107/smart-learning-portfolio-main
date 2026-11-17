import pytest

from app import create_app
from app.extensions import db
from app.models import AuditLog, ClassAdvisor, StudentProfile, User
from app.services import teacher_scope


@pytest.fixture
def setup_classes(monkeypatch):
    monkeypatch.setattr(teacher_scope, "current_school_year", lambda: 115)
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        users = {}
        for name, role in [("test_staff", "staff"), ("test_admin", "admin"), ("test_teacher", "teacher"),
                           ("test_teacher2", "teacher"), ("test_inactive", "teacher"), ("test_student", "student")]:
            user = User(username=name, display_name=name, role=role)
            user.set_password("pw")
            db.session.add(user)
            users[name] = user
        db.session.flush()
        users["test_inactive"].is_active = False
        db.session.add(StudentProfile(user_id=users["test_student"].id, student_no="TEST-001", class_name="測試班"))
        db.session.commit()
        ids = {name: user.id for name, user in users.items()}
    return app, ids


def client_for(app, user_id):
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
    return client


def test_staff_assigns_two_teachers_and_records_add_remove(setup_classes):
    app, ids = setup_classes
    client = client_for(app, ids["test_staff"])
    page = client.get("/admin/classes")
    assert page.status_code == 200
    assert "導師班級" in page.get_data(as_text=True)
    dashboard = client.get("/staff/dashboard").get_data(as_text=True)
    assert "/admin/classes" in dashboard
    for name in ("test_teacher", "test_teacher2"):
        result = client.post("/admin/classes", data={"teacher_id": ids[name], "class_name": "測試班", "school_year": 115})
        assert result.status_code == 302
    with app.app_context():
        student = db.session.get(User, ids["test_student"])
        assert {u.id for u in teacher_scope.teachers_for_student(student)} == {ids["test_teacher"], ids["test_teacher2"]}
        assignment = ClassAdvisor.query.filter_by(teacher_id=ids["test_teacher"]).one()
        assignment_id = assignment.id
        assert AuditLog.query.filter_by(user_id=ids["test_staff"], action="class_advisor.assign", target_id=assignment_id).count() == 1
    assert client.post(f"/admin/classes/{assignment_id}/delete").status_code == 302
    with app.app_context():
        assert db.session.get(ClassAdvisor, assignment_id) is None
        assert AuditLog.query.filter_by(user_id=ids["test_staff"], action="class_advisor.remove", target_id=assignment_id).count() == 1
        assert {u.id for u in teacher_scope.teachers_for_student(db.session.get(User, ids["test_student"]))} == {ids["test_teacher2"]}


def test_admin_can_manage_but_teacher_and_student_cannot(setup_classes):
    app, ids = setup_classes
    assert client_for(app, ids["test_admin"]).get("/admin/classes").status_code == 200
    for name in ("test_teacher", "test_student"):
        client = client_for(app, ids[name])
        assert client.get("/admin/classes").status_code == 403
        assert client.post("/admin/classes", data={"teacher_id": ids["test_teacher"], "class_name": "測試班", "school_year": 115}).status_code == 403
        assert client.post("/admin/classes/1/delete").status_code == 403


def test_assignment_rejects_inactive_teacher_and_duplicate(setup_classes):
    app, ids = setup_classes
    client = client_for(app, ids["test_staff"])
    data = {"teacher_id": ids["test_inactive"], "class_name": "測試班", "school_year": 115}
    assert client.post("/admin/classes", data=data).status_code == 400
    data["teacher_id"] = ids["test_teacher"]
    assert client.post("/admin/classes", data={**data, "school_year": 99}).status_code == 400
    assert client.post("/admin/classes", data={**data, "class_name": "測" * 51}).status_code == 400
    assert client.post("/admin/classes", data=data).status_code == 302
    assert client.post("/admin/classes", data=data).status_code == 400
    with app.app_context():
        assert ClassAdvisor.query.count() == 1
        assert AuditLog.query.filter_by(action="class_advisor.assign").count() == 1


def test_staff_assignment_still_requires_csrf(setup_classes):
    app, ids = setup_classes
    app.config.update(TESTING=False, CSRF_ENABLED=True)
    client = client_for(app, ids["test_staff"])
    assert client.post("/admin/classes", data={"teacher_id": ids["test_teacher"], "class_name": "測試班", "school_year": 115}).status_code == 400
    with app.app_context():
        assert ClassAdvisor.query.count() == 0
    assert client.get("/admin/classes").status_code == 200
    with client.session_transaction() as session:
        token = session["csrf_token"]
    data = {"teacher_id": ids["test_teacher"], "class_name": "測試班", "school_year": 115}
    assert client.post("/admin/classes", data={**data, "csrf_token": "錯誤"}).status_code == 400
    assert client.post("/admin/classes", data={**data, "csrf_token": token}).status_code == 302
    with app.app_context():
        assert ClassAdvisor.query.count() == 1
