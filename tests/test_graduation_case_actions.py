"""畢業缺口案件的角色動作與權限。（僅為測試資料）"""
import pytest

from app import create_app
from app.extensions import db
from app.models import (ClassAdvisor, GraduationCase, GraduationCaseEvent, Notification,
                        StudentProfile, User)
from app.services import graduation_case_actions as actions
from app.services import graduation_case_service as svc


@pytest.fixture()
def app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        yield app


def make_user(username, role):
    user = User(username=username, display_name=username, role=role)
    user.set_password("pw")
    db.session.add(user)
    db.session.flush()
    return user


def make_world(class_name="資管科五甲"):
    student = make_user("s1", "student")
    db.session.add(StudentProfile(user_id=student.id, student_no="s1", class_name=class_name,
                                  admission_year=111))
    teacher = make_user("t1", "teacher")
    db.session.add(ClassAdvisor(teacher_id=teacher.id, class_name=class_name, school_year=115))
    other = make_user("t2", "teacher")
    db.session.add(ClassAdvisor(teacher_id=other.id, class_name="資管科五乙", school_year=115))
    staff = make_user("st1", "staff")
    admin = make_user("ad1", "admin")
    db.session.flush()
    return student, teacher, other, staff, admin


def make_case(student, status="pending", item="certificates"):
    case = GraduationCase(student_id=student.id, case_type="gap", item=item, status="pending",
                          initial_amount=2, current_amount=2, unit="張",
                          open_key=GraduationCase.open_key_for(student.id, item, "gap"))
    db.session.add(case)
    db.session.flush()
    if status != "pending":
        svc.record_event(case, "started", to_status=status)
    return case


def notified(user, case):
    return Notification.query.filter_by(recipient_id=user.id, case_id=case.id).count()


def test_student_note_moves_pending_to_in_progress_and_notifies_teacher(app):
    student, teacher, _, _, _ = make_world()
    case = make_case(student)
    event = actions.perform(case, student, "note", "我下週去考證照")
    assert event.event_type == "student_note"
    assert case.status == "in_progress"
    assert notified(teacher, case) == 1
    assert notified(student, case) == 0


def test_teacher_cannot_act_on_other_class(app):
    student, _, other, _, _ = make_world()
    case = make_case(student)
    assert actions.can_view(case, other) is False
    with pytest.raises(actions.CaseActionError) as exc:
        actions.perform(case, other, "note", "hi")
    assert exc.value.status_code == 403
    assert case.number in str(exc.value)


def test_student_cannot_verify(app):
    student, _, _, _, _ = make_world()
    case = make_case(student, "awaiting_verification")
    with pytest.raises(actions.CaseActionError) as exc:
        actions.perform(case, student, "verify")
    assert exc.value.status_code == 403
    assert case.status == "awaiting_verification"


def test_reject_requires_reason_and_returns_in_progress(app):
    student, teacher, _, staff, _ = make_world()
    case = make_case(student, "awaiting_verification")
    with pytest.raises(actions.CaseActionError) as exc:
        actions.perform(case, staff, "reject", "  ")
    assert exc.value.status_code == 400
    assert case.status == "awaiting_verification"
    actions.perform(case, staff, "reject", "證照影本不清楚")
    assert case.status == "in_progress"
    assert notified(student, case) == 1 and notified(teacher, case) == 1


def test_verify_closes_improved_and_clears_open_key(app):
    student, teacher, _, staff, _ = make_world()
    case = make_case(student, "awaiting_verification")
    actions.perform(case, staff, "verify")
    assert case.status == "closed" and case.close_reason == "improved"
    assert case.open_key is None and case.closed_at is not None and case.closed_by_id == staff.id
    assert notified(student, case) == 1 and notified(teacher, case) == 1


def test_close_no_gap_records_distinct_reason(app):
    student, _, _, staff, _ = make_world()
    case = make_case(student)
    with pytest.raises(actions.CaseActionError) as exc:
        actions.perform(case, staff, "close_no_gap", "")
    assert exc.value.status_code == 400
    actions.perform(case, staff, "close_no_gap", "經核對並無缺口")
    assert case.status == "closed" and case.close_reason == "no_gap" and case.open_key is None
    with pytest.raises(actions.CaseActionError) as exc:
        actions.perform(case, student, "note", "還有問題")
    assert exc.value.status_code == 400


def test_inquiry_from_grade2_not_in_risk(app):
    student, teacher, _, _, _ = make_world()
    case = actions.create_inquiry(student, "請問證照可以抵免嗎")
    assert case.case_type == "inquiry" and case.item == "general" and case.open_key is None
    assert case.status == "pending"
    assert notified(teacher, case) == 1
    with pytest.raises(actions.CaseActionError):
        actions.create_inquiry(student, " ")


def test_available_actions_by_role(app):
    student, teacher, other, staff, admin = make_world()
    case = make_case(student, "awaiting_verification")
    assert {"verify", "reject", "close_no_gap"} <= set(actions.available_actions(case, staff))
    assert not {"verify", "reject", "close_no_gap"} & set(actions.available_actions(case, student))
    assert "note" in actions.available_actions(case, teacher)
    assert actions.available_actions(case, other) == []
    assert actions.available_actions(case, admin) == [] and actions.can_view(case, admin) is False
    pending = make_case(student, item="credits")
    assert "start" in actions.available_actions(pending, student)
    assert "submit" not in actions.available_actions(pending, student)
