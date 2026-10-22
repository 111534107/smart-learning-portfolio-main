import pytest

from app import create_app
from app.extensions import db
from app.models import (
    AdmissionProgram,
    ClassAdvisor,
    PackageReview,
    StudentProfile,
    StudentTarget,
    User,
)
from app.services.admission_service import import_seed_programs


@pytest.fixture()
def app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        import_seed_programs()
        for username, role in (("stu", "student"), ("other", "student"), ("teacher", "teacher"),
                               ("stranger", "teacher"), ("admin", "admin")):
            user = User(username=username, display_name=username, role=role)
            user.set_password("pw")
            db.session.add(user)
        db.session.flush()
        stu = User.query.filter_by(username="stu").one()
        other = User.query.filter_by(username="other").one()
        db.session.add(StudentProfile(user_id=stu.id, student_no="111534100", class_name="資管科三甲", admission_year=113))
        db.session.add(StudentProfile(user_id=other.id, student_no="111534200", class_name="資管科三乙", admission_year=113))
        teacher = User.query.filter_by(username="teacher").one()
        db.session.add(ClassAdvisor(teacher_id=teacher.id, class_name="資管科三甲", school_year=115))
        hidden = AdmissionProgram(program_code="000000", admission_year=115, school_name="候選大學",
                                  department_name="未公開系", status="candidate")
        db.session.add(hidden)
        db.session.commit()
        yield app


def login(client, username):
    client.post("/login", data={"username": username, "password": "pw"})
    return client


def program_id(app, code):
    with app.app_context():
        return AdmissionProgram.query.filter_by(program_code=code).one().id


def test_student_sees_only_published_programs(app):
    html = login(app.test_client(), "stu").get("/student/targets").get_data(as_text=True)

    assert "國立臺北商業大學" in html
    assert "候選大學" not in html


def test_student_cannot_select_candidate_program(app):
    client = login(app.test_client(), "stu")

    response = client.post("/student/targets", data={"program_id": program_id(app, "000000")})

    assert response.status_code == 404


def test_selecting_target_opens_gap_page(app):
    client = login(app.test_client(), "stu")
    pid = program_id(app, "208003")

    response = client.post("/student/targets", data={"program_id": pid})
    html = client.get(f"/student/targets/{pid}").get_data(as_text=True)

    assert response.status_code == 302
    assert "data-gap-board" in html
    assert "證照證明" in html
    with app.app_context():
        assert StudentTarget.query.count() == 1


def test_selecting_same_target_twice_does_not_duplicate(app):
    client = login(app.test_client(), "stu")
    pid = program_id(app, "208003")
    client.post("/student/targets", data={"program_id": pid})
    client.post("/student/targets", data={"program_id": pid})

    with app.app_context():
        assert StudentTarget.query.count() == 1


def test_request_review_creates_one_pending_review(app):
    client = login(app.test_client(), "stu")
    pid = program_id(app, "208003")
    client.post("/student/targets", data={"program_id": pid})

    client.post(f"/student/targets/{pid}/review")
    client.post(f"/student/targets/{pid}/review")

    with app.app_context():
        reviews = PackageReview.query.all()
        assert [r.status for r in reviews] == ["pending"]


def test_teacher_sees_own_class_and_can_confirm(app):
    pid = program_id(app, "208003")
    login(app.test_client(), "stu").post("/student/targets", data={"program_id": pid})
    student_client = login(app.test_client(), "stu")
    student_client.post(f"/student/targets/{pid}/review")
    with app.app_context():
        review = PackageReview.query.one()
        review_id, taken_at = review.id, review.snapshot_json["taken_at"]
        stu_id = User.query.filter_by(username="stu").one().id
        other_id = User.query.filter_by(username="other").one().id

    teacher = login(app.test_client(), "teacher")
    dashboard = teacher.get("/teacher/dashboard").get_data(as_text=True)
    assert "111534100" in dashboard
    assert "111534200" not in dashboard
    assert teacher.get(f"/teacher/students/{stu_id}").status_code == 200
    assert teacher.get(f"/teacher/students/{other_id}").status_code == 403

    response = teacher.post(f"/teacher/package-reviews/{review_id}", data={"decision": "confirmed", "comment": "",
                                                                         "taken_at": taken_at})

    assert response.status_code == 302
    with app.app_context():
        review = PackageReview.query.one()
        assert review.status == "confirmed"
        assert review.teacher.username == "teacher"


def test_other_teacher_cannot_decide(app):
    pid = program_id(app, "208003")
    client = login(app.test_client(), "stu")
    client.post("/student/targets", data={"program_id": pid})
    client.post(f"/student/targets/{pid}/review")
    with app.app_context():
        review_id = PackageReview.query.one().id

    response = login(app.test_client(), "stranger").post(
        f"/teacher/package-reviews/{review_id}", data={"decision": "confirmed"})

    assert response.status_code == 403


def test_needs_revision_requires_comment(app):
    pid = program_id(app, "208003")
    client = login(app.test_client(), "stu")
    client.post("/student/targets", data={"program_id": pid})
    client.post(f"/student/targets/{pid}/review")
    with app.app_context():
        review_id = PackageReview.query.one().id

    response = login(app.test_client(), "teacher").post(
        f"/teacher/package-reviews/{review_id}", data={"decision": "needs_revision", "comment": "  "})

    assert response.status_code == 400


def test_student_downloads_package_for_selected_target_only(app):
    client = login(app.test_client(), "stu")
    pid = program_id(app, "208003")
    other_pid = program_id(app, "208001")
    client.post("/student/targets", data={"program_id": pid})

    ok = client.get(f"/student/targets/{pid}/package.docx")
    missing = client.get(f"/student/targets/{other_pid}/package.docx")

    assert ok.status_code == 200
    assert ok.data.startswith(b"PK")
    assert missing.status_code == 404


def test_admin_can_publish_candidate_and_update_mapping(app):
    admin = login(app.test_client(), "admin")
    hidden = program_id(app, "000000")
    with app.app_context():
        item_id = AdmissionProgram.query.filter_by(program_code="208001").one().items[1].id

    assert "候選大學" in admin.get("/admin/programs").get_data(as_text=True)
    admin.post(f"/admin/programs/{hidden}/toggle-status")
    admin.post(f"/admin/program-items/{item_id}", data={"categories": ["credential", "competition"], "mapping_status": "confirmed"})

    with app.app_context():
        assert db.session.get(AdmissionProgram, hidden).status == "published"
        item = AdmissionProgram.query.filter_by(program_code="208001").one().items[1]
        assert item.category_keys == ["credential", "competition"]
        assert item.mapping_status == "confirmed"


def test_admin_assigns_class_to_teacher(app):
    admin = login(app.test_client(), "admin")
    with app.app_context():
        stranger_id = User.query.filter_by(username="stranger").one().id

    admin.post("/admin/classes", data={"teacher_id": stranger_id, "class_name": "資管科三乙", "school_year": "115"})

    with app.app_context():
        assert ClassAdvisor.query.filter_by(teacher_id=stranger_id, class_name="資管科三乙").count() == 1


def test_student_cannot_open_teacher_or_admin_pages(app):
    client = login(app.test_client(), "stu")

    assert client.get("/admin/programs").status_code == 403
    assert client.get("/teacher/students/1").status_code == 403
