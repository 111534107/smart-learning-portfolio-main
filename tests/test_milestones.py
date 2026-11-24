"""里程碑（彩蛋）：只讀資料、判斷正確。（僅為測試資料）"""
from app.extensions import db
from app.models import CredentialRecord, StudentTarget, User
from app.services import milestones
from tests.test_autobiography import ANSWERS, app, choose_target, login, program  # noqa: F401


def test_no_milestone_at_start(app):
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        keys = [m["key"] for m in milestones.reached(student)]
        assert "first_autobiography" not in keys and "all_targets_drafted" not in keys


def test_first_autobiography_milestone_and_json_in_page(app):
    client = login(app)
    choose_target(app, client)
    client.post("/student/autobiography/generate", data={"program_id": program(app), **ANSWERS})
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        assert "first_autobiography" in [m["key"] for m in milestones.reached(student)]
    page = client.get("/student/targets").get_data(as_text=True)
    assert 'id="milestones-data"' in page and "first_autobiography" in page


def test_three_confirmed_credentials_milestone(app):
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        for index in range(3):
            db.session.add(CredentialRecord(student_id=student.id, credential_name=f"測試證照{index}",
                                            confirmation_status="confirmed"))
        db.session.commit()
        assert "credentials_3" in [m["key"] for m in milestones.reached(student)]


def test_teacher_gets_no_milestones(app):
    with app.app_context():
        teacher = User(username="t1", display_name="t1", role="teacher")
        teacher.set_password("pw")
        db.session.add(teacher)
        db.session.commit()
        assert milestones.reached(teacher) == []
