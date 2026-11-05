"""畢業缺口案件同步服務。（僅為測試資料）"""
from datetime import date

import pytest

from app import create_app
from app.extensions import db
from app.models import (ClassAdvisor, CredentialRecord, GraduationCase, GraduationCaseEvent,
                        Notification, StudentProfile, User)
from app.services import graduation_case_service as svc
from app.services import graduation_check_service as check

GAP_DAY = date(2026, 3, 1)  # 111 入學：專四下（正式）


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


def make_student(admission_year=111, with_profile=True, class_name="資管科五甲"):
    student = make_user("gcstu", "student")
    if with_profile:
        db.session.add(StudentProfile(user_id=student.id, student_no="gcstu", class_name=class_name,
                                      admission_year=admission_year))
        db.session.flush()
    return student


def add_credential(student, name, level=None):
    db.session.add(CredentialRecord(student_id=student.id, credential_name=name, level=level,
                                    issue_date=date(2025, 1, 1), confirmation_status="confirmed"))
    db.session.flush()


def add_advisor(username, class_name="資管科五甲"):
    teacher = make_user(username, "teacher")
    db.session.add(ClassAdvisor(teacher_id=teacher.id, class_name=class_name, school_year=115))
    db.session.flush()
    return teacher


def cases(student, case_type=None, item=None):
    query = GraduationCase.query.filter_by(student_id=student.id)
    if case_type:
        query = query.filter_by(case_type=case_type)
    if item:
        query = query.filter_by(item=item)
    return query.all()


def notices(user):
    return Notification.query.filter_by(recipient_id=user.id).all()


def test_grade4_second_term_gap_creates_case_and_notifies(app):
    teacher = add_advisor("t1")
    student = make_student()
    add_credential(student, "電腦軟體應用 丙級", "丙級")
    events = svc.sync_student(student, today=GAP_DAY)
    rows = cases(student, "gap", "certificates")
    assert len(rows) == 1 and rows[0].status == "pending" and rows[0].current_amount == 2
    assert any(e.event_type == "created" and e.case_id == rows[0].id for e in events)
    assert len(notices(student)) >= 1
    cert_notes = Notification.query.filter_by(case_id=rows[0].id).all()
    assert sorted(n.recipient_id for n in cert_notes) == sorted([student.id, teacher.id])
    assert rows[0].number in cert_notes[0].message


def test_sync_twice_is_idempotent(app):
    add_advisor("t1")
    student = make_student()
    add_credential(student, "電腦軟體應用 丙級", "丙級")
    assert svc.sync_student(student, today=GAP_DAY)
    case_count = GraduationCase.query.count()
    event_count = GraduationCaseEvent.query.count()
    notice_count = Notification.query.count()
    assert svc.sync_student(student, today=GAP_DAY) == []
    assert GraduationCase.query.count() == case_count
    assert GraduationCaseEvent.query.count() == event_count
    assert Notification.query.count() == notice_count


def test_partial_improvement_updates_same_case(app):
    add_advisor("t1")
    student = make_student()
    svc.sync_student(student, today=GAP_DAY)
    case = cases(student, "gap", "certificates")[0]
    assert case.current_amount == 3
    before = Notification.query.count()
    add_credential(student, "電腦軟體應用 丙級", "丙級")
    events = svc.sync_student(student, today=GAP_DAY)
    db.session.refresh(case)
    assert case.current_amount == 2 and case.status == "pending"
    assert [e.event_type for e in events if e.case_id == case.id] == ["recalculated"]
    assert len(cases(student, "gap", "certificates")) == 1
    # 其他項目可能有新通知，但這個案件不應新增
    assert Notification.query.filter_by(case_id=case.id).count() == 2
    assert Notification.query.count() >= before


def test_gap_resolved_moves_to_awaiting_verification(app):
    staff = make_user("office", "staff")
    student = make_student()
    svc.sync_student(student, today=GAP_DAY)
    for name in ("電腦軟體應用 丙級", "網頁設計 丙級", "軟體設計 乙級"):
        add_credential(student, name, name[-2:])
    svc.sync_student(student, today=GAP_DAY)
    case = cases(student, "gap", "certificates")[0]
    assert case.status == "awaiting_verification"
    event = case.events.filter_by(event_type="auto_verify").one()
    assert event.from_status == "pending" and event.to_status == "awaiting_verification"
    assert [n.case_id for n in notices(staff)] == [case.id]
    # 再同步一次不重複
    assert svc.sync_student(student, today=GAP_DAY) == []


def test_no_transcript_creates_data_needed_not_gap(app):
    student = make_student()
    svc.sync_student(student, today=GAP_DAY)
    assert cases(student, "gap", "required_credits") == []
    assert len(cases(student, "data_needed", "credits")) == 1
    assert len(cases(student, "data_needed", "certificates")) == 0
    assert len(notices(student)) >= 1


def test_transfer_pending_creates_no_credit_gap(app):
    from app.models import TransferCreditRecord
    from tests.test_graduation_assessment import fill_ended_terms
    student = make_student()
    fill_ended_terms(student, 111, GAP_DAY)
    db.session.add(TransferCreditRecord(student_id=student.id, status="submitted"))
    db.session.flush()
    svc.sync_student(student, today=GAP_DAY)
    for item in svc.CREDIT_ITEMS:
        assert cases(student, "gap", item) == []
    assert cases(student, "data_needed", "credits") == []


def test_grade1_creates_nothing(app):
    student = make_student(admission_year=115)
    assert svc.sync_student(student, today=date(2026, 10, 1)) == []
    assert GraduationCase.query.count() == 0
    assert Notification.query.count() == 0


def test_all_advisors_notified_once(app):
    t1 = add_advisor("t1")
    t2 = add_advisor("t2")
    add_advisor("other", class_name="資管科五乙")
    student = make_student()
    svc.sync_student(student, today=GAP_DAY)
    svc.sync_student(student, today=GAP_DAY)
    case = cases(student, "gap", "certificates")[0]
    for teacher in (t1, t2):
        assert Notification.query.filter_by(recipient_id=teacher.id, case_id=case.id).count() == 1
    assert {u.id for u in svc.advisors_for(student)} == {t1.id, t2.id}


def _counts():
    return (GraduationCase.query.count(), GraduationCaseEvent.query.count(), Notification.query.count())


def test_closed_while_gap_then_same_gap_opens_nothing(app):
    student = make_student()
    svc.sync_student(student, today=GAP_DAY)
    old = cases(student, "gap", "certificates")[0]
    svc.record_event(old, "verified", to_status="closed", note="測試結案")
    old.close_reason = "improved"
    db.session.flush()
    assert old.open_key is None and old.status == "closed"
    before = _counts()
    assert svc.sync_student(student, today=GAP_DAY) == []
    assert _counts() == before


def test_close_then_met_then_gap_opens_linked_case(app):
    from app.services import graduation_case_actions as actions
    staff = make_user("office", "staff")
    teacher = add_advisor("t1")
    student = make_student()
    svc.sync_student(student, today=GAP_DAY)
    old = cases(student, "gap", "certificates")[0]
    actions.perform(old, staff, "close_no_gap", "證書補救已核可")
    _three_certs(student)
    assert [e for e in svc.sync_student(student, today=GAP_DAY) if e.case.item == "certificates"] == []
    db.session.refresh(old)
    assert old.last_result == "met"
    CredentialRecord.query.filter_by(student_id=student.id).first().confirmation_status = "rejected"
    db.session.flush()
    svc.sync_student(student, today=GAP_DAY)
    rows = cases(student, "gap", "certificates")
    assert len(rows) == 2
    new = [row for row in rows if row.id != old.id][0]
    assert new.previous_case_id == old.id and new.status == "pending" and new.current_amount == 1
    assert Notification.query.filter_by(case_id=new.id, recipient_id=teacher.id).count() == 1


def test_closed_then_larger_gap_opens_linked_case(app):
    from app.services import graduation_case_actions as actions
    staff = make_user("office", "staff")
    student = make_student()
    add_credential(student, "電腦軟體應用 丙級", "丙級")
    svc.sync_student(student, today=GAP_DAY)
    old = cases(student, "gap", "certificates")[0]
    assert old.current_amount == 2
    actions.perform(old, staff, "close_no_gap", "誤判")
    CredentialRecord.query.filter_by(student_id=student.id).first().confirmation_status = "rejected"
    db.session.flush()
    svc.sync_student(student, today=GAP_DAY)
    rows = cases(student, "gap", "certificates")
    assert len(rows) == 2
    new = [row for row in rows if row.id != old.id][0]
    assert new.previous_case_id == old.id and new.current_amount == 3


def test_submit_while_gap_then_sync_stays_awaiting(app):
    from app.services import graduation_case_actions as actions
    make_user("office", "staff")
    student = make_student()
    svc.sync_student(student, today=GAP_DAY)
    case = cases(student, "gap", "certificates")[0]
    actions.perform(case, student, "start")
    actions.perform(case, student, "submit", "已依第五點第（1）款加修六學分")
    assert case.status == "awaiting_verification"
    before = _counts()
    assert svc.sync_student(student, today=GAP_DAY) == []
    db.session.refresh(case)
    assert case.status == "awaiting_verification"
    assert _counts() == before


def test_reject_then_sync_stays_in_progress(app):
    from app.services import graduation_case_actions as actions
    staff = make_user("office", "staff")
    student = make_student()
    svc.sync_student(student, today=GAP_DAY)
    case = cases(student, "gap", "certificates")[0]
    _three_certs(student)
    svc.sync_student(student, today=GAP_DAY)
    assert case.status == "awaiting_verification"
    actions.perform(case, staff, "reject", "證照影本不清楚")
    assert case.status == "in_progress"
    before = _counts()
    assert svc.sync_student(student, today=GAP_DAY) == []
    db.session.refresh(case)
    assert case.status == "in_progress"
    assert _counts() == before


def test_close_no_gap_then_sync_opens_nothing(app):
    from app.services import graduation_case_actions as actions
    staff = make_user("office", "staff")
    student = make_student()
    svc.sync_student(student, today=GAP_DAY)
    case = cases(student, "gap", "certificates")[0]
    actions.perform(case, staff, "close_no_gap", "已取得國立大專院校入學資格")
    before = _counts()
    svc.sync_student(student, today=GAP_DAY)
    svc.sync_all(today=GAP_DAY)
    assert _counts() == before
    assert len(cases(student, "gap", "certificates")) == 1


def test_data_needed_insufficient_again_returns_to_in_progress(app):
    from tests.test_graduation_assessment import fill_ended_terms
    from app.models import LearningCourseRecord
    make_user("office", "staff")
    student = make_student()
    svc.sync_student(student, today=GAP_DAY)
    case = cases(student, "data_needed", "credits")[0]
    fill_ended_terms(student, 111, GAP_DAY)
    svc.sync_student(student, today=GAP_DAY)
    assert case.status == "awaiting_verification"
    LearningCourseRecord.query.filter_by(student_id=student.id).first().confirmation_status = "draft"
    db.session.flush()
    events = svc.sync_student(student, today=GAP_DAY)
    db.session.refresh(case)
    assert case.status == "in_progress"
    assert [e.event_type for e in events if e.case_id == case.id] == ["recalculated"]
    assert svc.sync_student(student, today=GAP_DAY) == []


def test_data_needed_closed_while_insufficient_opens_nothing(app):
    from app.services import graduation_case_actions as actions
    staff = make_user("office", "staff")
    student = make_student()
    svc.sync_student(student, today=GAP_DAY)
    case = cases(student, "data_needed", "credits")[0]
    actions.perform(case, staff, "close_no_gap", "紙本成績單已核對")
    before = _counts()
    svc.sync_student(student, today=GAP_DAY)
    assert _counts() == before


def test_sync_without_profile_creates_nothing(app):
    student = make_student(with_profile=False)
    assert svc.sync_student(student, today=GAP_DAY) == []
    assert GraduationCase.query.count() == 0


def test_status_change_writes_audit_log(app):
    from app.models import AuditLog
    student = make_student()
    svc.sync_student(student, today=GAP_DAY)
    case = cases(student, "gap", "certificates")[0]
    svc.record_event(case, "started", to_status="in_progress")
    row = AuditLog.query.filter_by(action="graduation_case.status", target_id=case.id).one()
    assert row.target_type == "graduation_case"


def test_data_changed_written_once_per_result(app):
    from tests.test_graduation_assessment import fill_ended_terms
    from app.models import TransferCreditRecord
    student = make_student()
    fill_ended_terms(student, 111, GAP_DAY)
    svc.sync_student(student, today=GAP_DAY)
    case = cases(student, "gap", "total_credits")[0]
    db.session.add(TransferCreditRecord(student_id=student.id, status="submitted"))
    db.session.flush()
    first = svc.sync_student(student, today=GAP_DAY)
    assert [e.event_type for e in first if e.case_id == case.id] == ["data_changed"]
    assert svc.sync_student(student, today=GAP_DAY) == []


def test_sync_all_counts_events(app):
    student = make_student()
    add_credential(student, "電腦軟體應用 丙級", "丙級")
    assert svc.sync_all(today=GAP_DAY) > 0
    assert svc.sync_all(today=GAP_DAY) == 0


def test_sync_all_isolates_failures_and_loads_curriculum_once(app, monkeypatch):
    bad = make_student()
    good = make_user("gcstu2", "student")
    db.session.add(StudentProfile(user_id=good.id, student_no="gcstu2", class_name="資管科五甲",
                                  admission_year=111))
    db.session.flush()
    loads = {"n": 0}
    original_load = check.load_curriculum

    def counting_load():
        loads["n"] += 1
        return original_load()

    original_assess = check.assess

    def flaky_assess(student, today=None, curriculum=None):
        if student.id == bad.id:
            raise ValueError("壞資料")
        return original_assess(student, today=today, curriculum=curriculum)

    monkeypatch.setattr(check, "load_curriculum", counting_load)
    monkeypatch.setattr(check, "assess", flaky_assess)
    assert svc.sync_all(today=GAP_DAY) > 0
    assert cases(good, "gap", "certificates")
    assert cases(bad) == []
    assert loads["n"] == 1


def _three_certs(student):
    for name in ("電腦軟體應用 丙級", "網頁設計 丙級", "軟體設計 乙級"):
        add_credential(student, name, name[-2:])


def test_data_needed_resolved_notifies_exactly_staff(app):
    from tests.test_graduation_assessment import fill_ended_terms
    s1 = make_user("office1", "staff")
    s2 = make_user("office2", "staff")
    add_advisor("t1")
    student = make_student()
    svc.sync_student(student, today=GAP_DAY)
    case = cases(student, "data_needed", "credits")[0]
    fill_ended_terms(student, 111, GAP_DAY)
    svc.sync_student(student, today=GAP_DAY)
    db.session.refresh(case)
    assert case.status == "awaiting_verification"
    event = case.events.filter_by(event_type="auto_verify").one()
    rows = Notification.query.filter_by(case_id=case.id, event_id=event.id).all()
    assert sorted(n.recipient_id for n in rows) == sorted([s1.id, s2.id])


def test_open_key_conflict_falls_back_to_existing_case(app, monkeypatch):
    student = make_student()
    svc.sync_student(student, today=GAP_DAY)
    original = svc._open_case
    calls = {"n": 0}

    def flaky(student_id, item, case_type):
        if item == "certificates" and case_type == "gap" and calls["n"] == 0:
            calls["n"] += 1
            return None  # 模擬並行：第一次查不到
        return original(student_id, item, case_type)

    monkeypatch.setattr(svc, "_open_case", flaky)
    svc.sync_student(student, today=GAP_DAY)
    assert calls["n"] == 1
    rows = [c for c in cases(student, "gap", "certificates") if c.is_open]
    assert len(rows) == 1
    assert rows[0].events.filter_by(event_type="created").count() == 1


def test_non_formal_student_existing_case_goes_to_verification(app):
    staff = make_user("office", "staff")
    student = make_student()
    svc.sync_student(student, today=GAP_DAY)
    case = cases(student, "gap", "certificates")[0]
    _three_certs(student)
    svc.sync_student(student, today=date(2025, 10, 1))  # 專四上，非正式
    db.session.refresh(case)
    assert case.status == "awaiting_verification"
    assert Notification.query.filter_by(recipient_id=staff.id, case_id=case.id).count() == 1


def test_gap_reappears_in_awaiting_verification_returns_to_in_progress(app):
    teacher = add_advisor("t1")
    student = make_student()
    svc.sync_student(student, today=GAP_DAY)
    case = cases(student, "gap", "certificates")[0]
    _three_certs(student)
    svc.sync_student(student, today=GAP_DAY)
    db.session.refresh(case)
    assert case.status == "awaiting_verification"
    CredentialRecord.query.filter_by(student_id=student.id).first().confirmation_status = "rejected"
    db.session.flush()
    events = svc.sync_student(student, today=GAP_DAY)
    db.session.refresh(case)
    mine = [e for e in events if e.case_id == case.id]
    assert [e.event_type for e in mine] == ["recalculated"]
    assert case.status == "in_progress" and case.current_amount == 1
    got = Notification.query.filter_by(case_id=case.id, event_id=mine[0].id).all()
    assert sorted(n.recipient_id for n in got) == sorted([student.id, teacher.id])


def test_gap_growth_updates_amount_without_notice(app):
    student = make_student()
    add_credential(student, "電腦軟體應用 丙級", "丙級")
    svc.sync_student(student, today=GAP_DAY)
    case = cases(student, "gap", "certificates")[0]
    assert case.current_amount == 2
    notices_before = Notification.query.filter_by(case_id=case.id).count()
    CredentialRecord.query.filter_by(student_id=student.id).first().confirmation_status = "rejected"
    db.session.flush()
    events = svc.sync_student(student, today=GAP_DAY)
    db.session.refresh(case)
    assert [e.event_type for e in events if e.case_id == case.id] == ["recalculated"]
    assert case.current_amount == 3 and case.status == "pending"
    assert Notification.query.filter_by(case_id=case.id).count() == notices_before
