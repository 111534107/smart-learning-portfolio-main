"""科主任全年級學生檢視（唯讀）與轉學生由科主任、科辦處理（2026-11-19）。僅為測試資料。"""
from datetime import date

from flask import url_for
from markupsafe import escape
import pytest

from app import create_app
from app.extensions import db
from app.models import (AdmissionProgram, AuditLog, CredentialRecord, LearningCourseRecord, LearningProfileOutput,
                        SchoolAwardRecord, SourceDocument, StudentProfile, StudentTarget, TransferCreditRecord, User)
from app.models.attendance import AttendanceSummary
from app.services import autobiography_service
from app.services.chief_student_view import graduation_summary
from app.services.journey_service import academic_year_of

SECRET_BIO = "這是祕密自傳全文XYZ"


@pytest.fixture
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "UPLOAD_FOLDER": str(tmp_path / "up")})
    with app.app_context():
        db.create_all()
        people = {}
        for name, role, title in [("chief", "staff", "主任"), ("vice", "staff", "副主任"), ("assist", "staff", "科助"),
                                  ("clerk", "staff", "其他行政人員"), ("t1", "teacher", None), ("s1", "student", None),
                                  ("s2", "student", None), ("s3", "student", None)]:
            user = User(username=name, display_name=name, role=role, job_title=title)
            user.set_password("pw")
            db.session.add(user)
            people[name] = user
        db.session.flush()
        year = academic_year_of(date.today())
        db.session.add_all([
            StudentProfile(user_id=people["s1"].id, student_no="S1", class_name="甲班", admission_year=year - 4),   # 專五
            StudentProfile(user_id=people["s2"].id, student_no="S2", class_name="乙班", admission_year=year),        # 專一
            StudentProfile(user_id=people["s3"].id, student_no="S3", class_name="甲班", admission_year=year - 2)])
        s1 = people["s1"]
        document = SourceDocument(owner_id=s1.id, document_type="credential", display_name="證.png", file_path="x",
                                  sha256="0" * 64, status="confirmed")
        db.session.add(document)
        db.session.flush()
        db.session.add_all([
            LearningCourseRecord(student_id=s1.id, school_year=1, semester="上", course_name="資料結構", normalized_course_name="資料結構",
                                 credits=3, score=88, confirmation_status="confirmed"),
            CredentialRecord(student_id=s1.id, credential_name="電腦軟體應用", level="丙級", confirmation_status="confirmed",
                             source_document_id=document.id),
            SchoolAwardRecord(student_id=s1.id, record_key="k1", record_type="reward", date="114/10/10", name="嘉獎", count=1,
                              reason="協助活動"),
            AttendanceSummary(student_id=s1.id, school_year=114, semester=1, totals={"曠課": 0, "病假": 4}),
        ])
        program = AdmissionProgram(program_code="D1", admission_year=115, school_name="測試大學", department_name="資管系", status="published")
        db.session.add(program)
        db.session.flush()
        db.session.add(StudentTarget(student_id=s1.id, rule_version_id=program.id))
        db.session.add(LearningProfileOutput(
            student_id=s1.id, output_type=autobiography_service.OUTPUT_TYPE, source_snapshot_json={},
            content_json={"program_id": program.id, "version": 1, "provider": "demo",
                          "paragraphs": [{"title": "段一", "text": SECRET_BIO}]}))
        db.session.commit()
        ids = {name: user.id for name, user in people.items()}
        ids["doc"] = document.id
    return app, ids


def login(app, name):
    client = app.test_client()
    path = "/staff/login" if name in ("chief", "vice", "assist", "clerk", "t1") else "/login"
    client.post(path, data={"username": name, "password": "pw"})
    return client


# ---------- 只有科主任看得到 ----------

def test_only_chief_and_vice_can_open_the_student_overview_and_detail(app):
    app_, ids = app
    for name in ("chief", "vice"):
        client = login(app_, name)
        assert client.get("/staff/students").status_code == 200
        assert client.get(f"/staff/students/{ids['s1']}").status_code == 200
        assert client.get(f"/staff/students/{ids['s1']}/admissions").status_code == 200
    for name in ("assist", "clerk", "t1", "s1"):
        client = login(app_, name)
        assert client.get("/staff/students").status_code == 403, name
        assert client.get(f"/staff/students/{ids['s1']}").status_code == 403, name
        assert client.get(f"/staff/students/{ids['s1']}/admissions").status_code == 403, name
    assert login(app_, "assist").get(f"/staff/documents/{ids['doc']}/view").status_code == 403
    assert app_.test_client().get("/staff/students").status_code in (401, 403)
    assert app_.test_client().get(f"/staff/students/{ids['s1']}/admissions").status_code in (401, 403)


def test_list_filters_by_grade_class_name_and_status(app):
    app_, ids = app
    client = login(app_, "chief")
    page = client.get("/staff/students").get_data(as_text=True)
    assert "S1" in page and "S2" in page and "S3" in page and "共 3 位" in page
    assert "S1" in client.get("/staff/students?grade=5").get_data(as_text=True)
    only_one = client.get("/staff/students?grade=1").get_data(as_text=True)
    assert "S2" in only_one and "S1" not in only_one.split("<tbody>")[1]
    by_class = client.get("/staff/students?class_name=甲班").get_data(as_text=True)
    assert "S3" in by_class and "S2" not in by_class.split("<tbody>")[1]
    assert "共 1 位" in client.get("/staff/students?q=S2").get_data(as_text=True)
    assert "共 0 位" in client.get("/staff/students?q=不存在").get_data(as_text=True)


def test_student_pages_split_read_only_data_and_log_the_sections_viewed(app):
    app_, ids = app
    with app_.app_context():
        db.session.add(TransferCreditRecord(student_id=ids["s1"], status="submitted"))
        db.session.commit()
    client = login(app_, "chief")
    learning = client.get(f"/staff/students/{ids['s1']}").get_data(as_text=True)
    admissions = client.get(f"/staff/students/{ids['s1']}/admissions").get_data(as_text=True)
    for expected in ('id="grad"', "資料結構", "電腦軟體應用", "協助活動", "病假 4", "看原檔", "已送出申請"):
        assert expected in learning, expected
        assert expected not in admissions, expected
    for expected in ("測試大學", SECRET_BIO, "實習履歷"):
        assert expected in admissions, expected
        assert expected not in learning, expected
    assert "<form" not in learning.split('id="grad"')[1].split("</section>")[0]
    assert "<form" not in admissions.split('id="autobiography"')[1].split("</section>")[0]
    assert client.get(f"/staff/students/{ids['t1']}/admissions").status_code == 404
    with app_.app_context():
        logs = AuditLog.query.filter_by(action="staff.student_view").order_by(AuditLog.id).all()
        assert len(logs) == 2
        for log in logs:
            assert log.user_id == ids["chief"] and log.target_id == ids["s1"]
        assert logs[0].detail_json == {"sections": ["基本資料", "畢業門檻", "成績", "證照", "缺曠合計", "獎懲", "轉學抵免進度"]}
        assert logs[1].detail_json == {"sections": ["基本資料", "目標校系與備審", "自傳", "實習履歷"]}


def test_student_detail_navigation_preserves_list_filters(app):
    app_, ids = app
    client = login(app_, "chief")
    with app_.app_context():
        status, _, _ = graduation_summary(db.session.get(User, ids["s1"]))
    filters = {"grade": 5, "class_name": "甲班", "q": "S1", "status": status}
    with app_.test_request_context():
        listing = url_for("staff.chief_students", **filters)
        learning = url_for("staff.chief_student_detail", student_id=ids["s1"], **filters)
    admissions = learning.replace("?", "/admissions?", 1)
    assert f'href="{escape(learning)}"' in client.get(listing).get_data(as_text=True)
    for current, other in ((learning, admissions), (admissions, learning)):
        page = client.get(current).get_data(as_text=True)
        assert f'href="{escape(listing)}"' in page
        assert f'href="{escape(current)}" aria-current="page"' in page
        assert f'href="{escape(other)}"' in page


def test_chief_can_open_confirmed_original_file_only(app):
    app_, ids = app
    client = login(app_, "chief")
    assert client.get("/staff/documents/9999/view").status_code == 404
    with app_.app_context():
        db.session.get(SourceDocument, ids["doc"]).status = "uploaded"
        db.session.commit()
    assert client.get(f"/staff/documents/{ids['doc']}/view").status_code == 404


# ---------- 轉學生 ----------

FORM = {"student_no": "T1130001", "display_name": "測試轉學生", "school_email": "t1130001@stu.ukn.edu.tw",
        "class_name": "甲班", "admission_year": "114"}


def test_staff_cannot_create_transfer_student(app):
    app_, _ = app
    for name in ("assist", "chief", "clerk", "t1", "s1"):
        assert login(app_, name).post("/staff/transfer-students", data=FORM).status_code == 403
    with app_.app_context():
        assert User.query.filter_by(username=FORM["student_no"]).count() == 0


def test_staff_confirms_existing_transfer_credit(app):
    app_, ids = app
    with app_.app_context():
        db.session.add(TransferCreditRecord(student_id=ids["s1"], status="not_started"))
        db.session.commit()
    assist = login(app_, "assist")
    assert assist.post(f"/staff/transfer-students/{ids['s1']}/confirm", data={"confirmed": "1"}).status_code == 302
    with app_.app_context():
        record = TransferCreditRecord.query.filter_by(student_id=ids["s1"]).one()
        assert record.teacher_confirmed and record.teacher_id == ids["assist"]
    assert login(app_, "t1").post(f"/teacher/students/{ids['s1']}/transfer-credit/confirm", data={"confirmed": "1"}).status_code == 403
