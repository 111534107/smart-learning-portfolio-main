"""畢業缺口案件資料表：編號格式、open_key 唯一、通知去重。（僅為測試資料）"""
import pytest
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.extensions import db
from app.models import GraduationCase, GraduationCaseEvent, Notification, User


@pytest.fixture()
def app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        yield app


def make_student():
    student = User(username="cstu", display_name="cstu", role="student")
    student.set_password("pw")
    db.session.add(student)
    db.session.flush()
    return student


def make_case(student, open_key="k"):
    case = GraduationCase(student_id=student.id, case_type="gap", item="丙級", open_key=open_key)
    db.session.add(case)
    db.session.flush()
    return case


def test_case_number_format(app):
    case = make_case(make_student())
    assert case.number == f"G-{case.id:06d}"
    assert case.status == "pending"
    assert case.is_open is True
    assert GraduationCase.open_key_for(3, "丙級", "gap") == "3:丙級:gap"


def test_open_key_unique_while_open(app):
    student = make_student()
    make_case(student, open_key="same")
    with pytest.raises(IntegrityError):
        make_case(student, open_key="same")


def test_closed_cases_allow_null_open_key(app):
    student = make_student()
    make_case(student, open_key=None)
    make_case(student, open_key=None)
    assert GraduationCase.query.count() == 2


def test_notification_unique_per_recipient_event(app):
    student = make_student()
    case = make_case(student)
    event = GraduationCaseEvent(case_id=case.id, event_type="created")
    db.session.add(event)
    db.session.flush()
    db.session.add(Notification(recipient_id=student.id, event_id=event.id, message="a"))
    db.session.flush()
    with pytest.raises(IntegrityError):
        db.session.add(Notification(recipient_id=student.id, event_id=event.id, message="b"))
        db.session.flush()
