from datetime import date

from app import create_app
from app.extensions import db
from app.models import ClassAdvisor, StudentProfile, User


def transfer_app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        student = User(username="transfer-student", display_name="測試轉學生", role="student")
        student.set_password("pw")
        teacher = User(username="transfer-teacher", display_name="測試導師", role="teacher")
        teacher.set_password("pw")
        other_teacher = User(username="other-teacher", display_name="其他導師", role="teacher")
        other_teacher.set_password("pw")
        staff = User(username="transfer-staff", display_name="測試科助", role="staff", job_title="科助")
        staff.set_password("pw")
        db.session.add_all([student, teacher, other_teacher, staff])
        db.session.flush()
        db.session.add(StudentProfile(user_id=student.id, student_no="TEST-TRANSFER", class_name="專四甲"))
        db.session.add(ClassAdvisor(teacher_id=teacher.id, class_name="專四甲", school_year=115))
        db.session.commit()
    return app


def signed_in(app, username):
    client = app.test_client()
    client.post("/login", data={"username": username, "password": "pw"})
    return client


def test_transfer_credit_tour_distinguishes_school_application_and_record():
    page = signed_in(transfer_app(), 'transfer-student').get('/student/transfer-credit').get_data(as_text=True)
    assert 'data-tour="先到學校抵免系統辦理正式申請。"' in page
    assert 'data-tour="選狀態、填待補資料，再儲存進度。"' in page


def test_student_can_record_transfer_credit_status_and_staff_can_confirm():
    app = transfer_app()
    student = signed_in(app, "transfer-student")

    page = student.get("/student/transfer-credit")
    assert page.status_code == 200
    assert "只供申請進度整理" in page.get_data(as_text=True)
    assert "https://ec.ukn.edu.tw/CT_web/login.aspx" in page.get_data(as_text=True)

    response = student.post("/student/transfer-credit", data={
        "status": "submitted",
        "submitted_on": "2026-10-13",
        "missing_documents": "前校課程大綱",
        "note": "已在校方系統送出申請",
    })
    assert response.status_code == 302

    teacher = signed_in(app, "transfer-teacher")
    response = signed_in(app, "transfer-staff").post("/staff/transfer-students/1/confirm", data={"confirmed": "1"})
    assert response.status_code == 302

    with app.app_context():
        from app.models import TransferCreditRecord
        record = TransferCreditRecord.query.one()
        assert record.status == "submitted"
        assert record.submitted_on == date(2026, 10, 13)
        assert record.missing_documents == "前校課程大綱"
        assert record.teacher_confirmed is True
        assert record.teacher_id == 4  # 科辦（測試科助）確認

    teacher_page = teacher.get("/teacher/students/1")
    assert teacher_page.status_code == 200
    assert "轉學生抵免進度" in teacher_page.get_data(as_text=True)


def test_student_cannot_save_invalid_transfer_status_or_date():
    app = transfer_app()
    student = signed_in(app, "transfer-student")

    bad_status = student.post("/student/transfer-credit", data={"status": "approved"})
    bad_date = student.post("/student/transfer-credit", data={"status": "submitted", "submitted_on": "not-a-date"})

    assert bad_status.status_code == 400
    assert bad_date.status_code == 400
    with app.app_context():
        from app.models import TransferCreditRecord
        assert TransferCreditRecord.query.count() == 0


def test_teacher_can_no_longer_confirm_transfer_record():
    app = transfer_app()
    student = signed_in(app, "transfer-student")
    student.post("/student/transfer-credit", data={"status": "submitted"})

    for name in ("other-teacher", "transfer-teacher"):
        response = signed_in(app, name).post("/teacher/students/1/transfer-credit/confirm", data={"confirmed": "1"})
        assert response.status_code == 403  # 改由科主任或科辦確認（2026-11-19），導師只能看
    with app.app_context():
        from app.models import TransferCreditRecord
        assert TransferCreditRecord.query.one().teacher_confirmed is False


def test_student_update_clears_previous_teacher_confirmation():
    app = transfer_app()
    student = signed_in(app, "transfer-student")
    student.post("/student/transfer-credit", data={"status": "submitted"})
    signed_in(app, "transfer-staff").post("/staff/transfer-students/1/confirm", data={"confirmed": "1"})

    student.post("/student/transfer-credit", data={"status": "needs_documents", "missing_documents": "課程大綱"})

    with app.app_context():
        from app.models import TransferCreditRecord
        record = TransferCreditRecord.query.one()
        assert record.teacher_confirmed is False
        assert record.teacher_id is None
