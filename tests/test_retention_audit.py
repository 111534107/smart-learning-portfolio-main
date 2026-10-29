"""M10 刪除與保留、M11 操作紀錄（規格第 4 節）。

- 學生刪除經歷或佐證：只標記 deleted_at，資料列保留，畫面看不到。
- 已經出現在送審快照裡的經歷與佐證不能刪。
- 確認、送審、刪除、上傳、目標校系、自傳都寫 audit_logs；紀錄只記動作、對象類型與編號。
"""
import io
import json
from datetime import date

import pytest
from PIL import Image

from app import create_app
from app.extensions import db
from app.models import (
    AdmissionProgram,
    AuditLog,
    ClassAdvisor,
    DocumentExtraction,
    LearningProfileOutput,
    Portfolio,
    PortfolioEvidence,
    SourceDocument,
    StudentProfile,
    User,
)
from app.services.admission_service import import_seed_programs
from app.services.journey_service import academic_year_of
from tests.board_helpers import fill_board

GRADE3_ADMISSION_YEAR = academic_year_of(date.today()) - 2
GRADE5_ADMISSION_YEAR = academic_year_of(date.today()) - 4  # 自傳到專五才開放生成
STUDENT_NAME = "測試學生甲"
STUDENT_NO = "111534188"
BLOCKED_MESSAGE = "這筆已經送導師確認，不能刪除；如果內容有誤，請修改後再送一次"
ANSWERS = {"motivation": "喜歡把需求變成系統。", "proud": "黑客松負責後端。", "challenge": "", "future": "想學資料分析。"}


@pytest.fixture()
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "UPLOAD_FOLDER": str(tmp_path), "DOCUMENT_ANALYSIS_PROVIDER": "fake",
                      "OCR_QUEUE_MODE": "inline"})
    with app.app_context():
        db.create_all()
        import_seed_programs()
        for username, name, role in (("stu", STUDENT_NAME, "student"), ("teacher", "導師", "teacher"),
                                     ("admin", "管理者", "admin")):
            user = User(username=username, display_name=name, role=role)
            user.set_password("pw")
            db.session.add(user)
        db.session.flush()
        stu = User.query.filter_by(username="stu").one()
        db.session.add(StudentProfile(user_id=stu.id, student_no=STUDENT_NO, class_name="資管科三甲",
                                      admission_year=GRADE5_ADMISSION_YEAR))
        teacher = User.query.filter_by(username="teacher").one()
        db.session.add(ClassAdvisor(teacher_id=teacher.id, class_name="資管科三甲", school_year=115))
        db.session.commit()
        fill_board(stu)  # 拼圖要完成才能生成自傳
        yield app


def login(app, username="stu"):
    client = app.test_client()
    client.post("/login", data={"username": username, "password": "pw"})
    return client


def user_id(app, username="stu"):
    with app.app_context():
        return User.query.filter_by(username=username).one().id


def program_id(app):
    with app.app_context():
        return AdmissionProgram.query.filter_by(program_code="208003").one().id


def png_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (1600, 1200), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def add_record(app, title="校園黑客松", status="confirmed"):
    with app.app_context():
        record = Portfolio(student_id=user_id(app), title=title, category="competition", school_year=3, status=status)
        db.session.add(record)
        db.session.commit()
        return record.id


def upload_evidence(client, record_id):
    return client.post(f"/student/portfolio/{record_id}/evidence",
                       data={"file": (io.BytesIO(png_bytes()), "photo.png")}, content_type="multipart/form-data")


def evidence_id_of(app, record_id):
    with app.app_context():
        return PortfolioEvidence.query.filter_by(portfolio_id=record_id).one().id


def send_review(app, client):
    pid = program_id(app)
    client.post("/student/targets", data={"program_id": pid})
    client.post(f"/student/targets/{pid}/review")
    return pid


def actions(app):
    with app.app_context():
        return [log.action for log in AuditLog.query.order_by(AuditLog.id)]


def logs_of(app, action):
    with app.app_context():
        return [{"target_type": log.target_type, "target_id": log.target_id, "user_id": log.user_id,
                 "detail": log.detail_json} for log in AuditLog.query.filter_by(action=action)]


# ---------- M10：刪除先標記 ----------

def test_deleted_record_row_stays_but_disappears_from_pages(app):
    record_id = add_record(app, title="要刪掉的活動")
    client = login(app)

    response = client.post(f"/student/portfolio/{record_id}/delete")

    assert response.status_code == 302
    with app.app_context():
        record = db.session.get(Portfolio, record_id)
        assert record is not None and record.deleted_at is not None
    assert "要刪掉的活動" not in client.get("/student/portfolio").get_data(as_text=True)
    assert client.get(f"/student/portfolio/{record_id}/edit").status_code == 404
    assert "要刪掉的活動" not in login(app, "teacher").get(
        f"/teacher/students/{user_id(app)}").get_data(as_text=True)


def test_deleted_record_is_left_out_of_autobiography_facts_and_journey(app):
    from app.services.autobiography_service import build_facts
    from app.services.journey_service import build_journey

    record_id = add_record(app, title="不該再出現的競賽")
    login(app).post(f"/student/portfolio/{record_id}/delete")

    with app.app_context():
        student = db.session.get(User, user_id(app))
        program = db.session.get(AdmissionProgram, program_id(app))
        assert all("不該再出現的競賽" not in fact["text"] for fact in build_facts(student, program)["items"])
        assert "不該再出現的競賽" not in json.dumps(build_journey(student), ensure_ascii=False, default=str)


def test_deleted_evidence_row_stays_but_disappears(app):
    record_id = add_record(app, status="draft")
    client = login(app)
    upload_evidence(client, record_id)
    evidence_id = evidence_id_of(app, record_id)

    assert client.post(f"/student/evidence/{evidence_id}/delete").status_code == 302

    with app.app_context():
        evidence = db.session.get(PortfolioEvidence, evidence_id)
        assert evidence is not None and evidence.deleted_at is not None
        assert db.session.get(Portfolio, record_id).evidence_items == []
    assert client.get(f"/student/evidence/{evidence_id}/view").status_code == 404
    assert "photo.png" not in client.get(f"/student/portfolio/{record_id}/edit").get_data(as_text=True)


# ---------- M10：送審過的不能刪 ----------

def test_record_in_review_snapshot_cannot_be_deleted(app):
    record_id = add_record(app, title="已送審的競賽")
    client = login(app)
    send_review(app, client)

    response = client.post(f"/student/portfolio/{record_id}/delete", follow_redirects=True)

    assert BLOCKED_MESSAGE in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Portfolio, record_id).deleted_at is None
    assert logs_of(app, "portfolio.delete_blocked")[0]["target_id"] == record_id
    assert "portfolio.delete" not in actions(app)


def test_evidence_of_submitted_record_cannot_be_deleted(app):
    record_id = add_record(app)
    client = login(app)
    upload_evidence(client, record_id)
    evidence_id = evidence_id_of(app, record_id)
    send_review(app, client)

    response = client.post(f"/student/evidence/{evidence_id}/delete", follow_redirects=True)

    assert BLOCKED_MESSAGE in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(PortfolioEvidence, evidence_id).deleted_at is None
    assert logs_of(app, "evidence.delete_blocked")[0]["target_id"] == evidence_id


def test_teacher_snapshot_unchanged_after_student_deletes_other_record(app):
    from app.models import PackageReview

    kept = add_record(app, title="送審時的競賽")
    client = login(app)
    send_review(app, client)
    later = add_record(app, title="送審後才加的")
    with app.app_context():
        before = PackageReview.query.one().snapshot_json

    assert client.post(f"/student/portfolio/{later}/delete").status_code == 302

    with app.app_context():
        assert PackageReview.query.one().snapshot_json == before
        assert db.session.get(Portfolio, later).deleted_at is not None
        assert db.session.get(Portfolio, kept).deleted_at is None


# ---------- M11：操作紀錄 ----------

def test_portfolio_confirm_and_delete_are_logged(app):
    record_id = add_record(app, status="draft")
    client = login(app)
    upload_evidence(client, record_id)
    evidence_id = evidence_id_of(app, record_id)

    client.post(f"/student/portfolio/{record_id}/confirm")
    client.post(f"/student/evidence/{evidence_id}/delete")
    client.post(f"/student/portfolio/{record_id}/delete")

    assert logs_of(app, "portfolio.confirm")[0]["target_id"] == record_id
    assert logs_of(app, "evidence.upload")[0]["target_type"] == "portfolio_evidence"
    assert logs_of(app, "evidence.delete")[0]["target_id"] == evidence_id
    assert logs_of(app, "portfolio.delete")[0] == {"target_type": "portfolio", "target_id": record_id,
                                                   "user_id": user_id(app), "detail": None}


def test_document_upload_and_ocr_confirm_are_logged(app):
    client = login(app)
    client.post("/student/learning-profile/documents",
                data={"document_type": "transcript", "file": (io.BytesIO(png_bytes()), "transcript.png")},
                content_type="multipart/form-data")
    with app.app_context():
        uploaded_id = SourceDocument.query.one().id
        # 確認頁另用一份剛擷取完的文件（和 test_learning_profile_confirmation 一樣），不受 OCR 版本號影響
        document = SourceDocument(owner_id=user_id(app), document_type="transcript", display_name="t.pdf",
                                  file_path="t.pdf", sha256="c" * 64, status="extracted")
        db.session.add(document)
        db.session.flush()
        db.session.add(DocumentExtraction(source_document_id=document.id, provider="fake", status="extracted",
                                          result_json={"courses": []}))
        db.session.commit()
        document_id = document.id

    response = client.post(f"/student/learning-profile/documents/{document_id}/review/confirm",
                           data={"scores_unlocked": "1", "courses_json": json.dumps(
                               [{"course_name": "程式設計", "credits": 3, "score": 92}]), "credentials_json": "[]"})

    assert response.status_code == 302
    upload = logs_of(app, "learning_profile.document_upload")[0]
    assert (upload["target_type"], upload["target_id"]) == ("source_document", uploaded_id)
    assert upload["detail"] == {"document_type": "transcript"}
    assert logs_of(app, "learning_profile.document_confirm")[0]["target_id"] == document_id


def test_target_add_remove_and_review_are_logged(app):
    pid = program_id(app)
    client = login(app)
    client.post("/student/targets", data={"program_id": pid})
    client.post(f"/student/targets/{pid}/review")
    client.post(f"/student/targets/{pid}/remove")

    assert logs_of(app, "student_target.add")[0]["target_id"] == pid
    assert logs_of(app, "student_target.remove")[0]["target_id"] == pid
    assert logs_of(app, "package_review.request")[0]["target_type"] == "package_review"


def test_autobiography_generate_save_and_teacher_edit_are_logged(app):
    add_record(app)
    client = login(app)
    pid = program_id(app)
    client.post("/student/targets", data={"program_id": pid})
    client.post("/student/autobiography/generate", data={"program_id": pid, **ANSWERS})
    with app.app_context():
        first = LearningProfileOutput.query.filter_by(output_type="autobiography_ai").one()
        first_id, count = first.id, len(first.content_json["paragraphs"])
    client.post(f"/student/autobiography/{first_id}/save", data={f"paragraph_{i}": "學生改的" for i in range(count)})
    with app.app_context():
        second_id = LearningProfileOutput.query.order_by(LearningProfileOutput.id.desc()).first().id
    teacher = login(app, "teacher")
    teacher.post(f"/teacher/students/{user_id(app)}/autobiography/{second_id}/edit",
                 data={f"paragraph_{i}": "導師改的" for i in range(count)})

    assert logs_of(app, "autobiography.generate")[0]["target_id"] == first_id
    assert logs_of(app, "autobiography.save")[0]["target_id"] == second_id
    teacher_edit = logs_of(app, "autobiography.teacher_edit")[0]
    assert teacher_edit["user_id"] == user_id(app, "teacher")
    assert teacher_edit["target_type"] == "learning_profile_output"


def test_non_student_login_is_logged(app):
    login(app, "teacher")
    login(app, "admin")

    assert [log["user_id"] for log in logs_of(app, "user.login")] == [user_id(app, "teacher"), user_id(app, "admin")]


def test_logs_never_contain_student_name_or_number(app):
    record_id = add_record(app, title="校園黑客松", status="draft")
    client = login(app)
    upload_evidence(client, record_id)
    client.post(f"/student/portfolio/{record_id}/confirm")
    send_review(app, client)
    client.post(f"/student/portfolio/{record_id}/delete")
    client.post("/student/autobiography/generate", data={"program_id": program_id(app), **ANSWERS})

    with app.app_context():
        dumped = json.dumps([[log.action, log.target_type, log.target_id, log.detail_json]
                             for log in AuditLog.query.all()], ensure_ascii=False)
    for secret in (STUDENT_NAME, STUDENT_NO, "校園黑客松", "photo.png", "黑客松負責後端"):
        assert secret not in dumped


# ---------- 管理者「操作紀錄」頁 ----------

def test_admin_can_see_and_filter_audit_logs(app):
    record_id = add_record(app, status="draft")
    client = login(app)
    client.post(f"/student/portfolio/{record_id}/confirm")
    client.post(f"/student/portfolio/{record_id}/delete")
    admin = login(app, "admin")

    page = admin.get("/admin/audit-logs").get_data(as_text=True)
    filtered = admin.get("/admin/audit-logs?action=portfolio.delete").get_data(as_text=True)

    assert "操作紀錄" in page
    assert "portfolio.confirm" in page and "portfolio.delete" in page
    assert "portfolio.confirm" not in filtered.split("<tbody")[1]
    assert STUDENT_NAME not in page and STUDENT_NO not in page
    assert "/admin/audit-logs" in admin.get("/admin/dashboard").get_data(as_text=True)


def test_audit_log_page_is_admin_only(app):
    assert login(app).get("/admin/audit-logs").status_code in (302, 403)
    assert login(app, "teacher").get("/admin/audit-logs").status_code in (302, 403)
