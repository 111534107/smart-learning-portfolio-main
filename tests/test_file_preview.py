"""照片預覽與上傳大小：學生、導師都能直接看圖片，超過大小限制要有中文說明。"""
import io

import pytest

from app import create_app
from app.extensions import db
from app.models import ClassAdvisor, Portfolio, SourceDocument, StudentProfile, User

PNG = b"\x89PNG\r\n\x1a\nfake"


@pytest.fixture()
def app(tmp_path):
    app = create_app({
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "TESTING": True,
        "UPLOAD_FOLDER": str(tmp_path),
    })
    with app.app_context():
        db.create_all()
        for username, role in (("stu", "student"), ("teacher", "teacher"), ("stranger", "teacher")):
            user = User(username=username, display_name=username, role=role)
            user.set_password("pw")
            db.session.add(user)
        db.session.flush()
        stu = User.query.filter_by(username="stu").one()
        db.session.add(StudentProfile(user_id=stu.id, student_no="111534100", class_name="資管科三甲", admission_year=113))
        teacher = User.query.filter_by(username="teacher").one()
        db.session.add(ClassAdvisor(teacher_id=teacher.id, class_name="資管科三甲", school_year=115))
        db.session.commit()
    yield app


def login(app, username):
    client = app.test_client()
    client.post("/login", data={"username": username, "password": "pw"})
    return client


def upload_evidence(app, client):
    client.post("/student/portfolio", data={"title": "黑客松", "category": "competition"})
    with app.app_context():
        record_id = Portfolio.query.one().id
    client.post(f"/student/portfolio/{record_id}/evidence", data={"file": (io.BytesIO(PNG), "award.png")},
                content_type="multipart/form-data")
    with app.app_context():
        return Portfolio.query.one().evidence_items[0].id


def test_class_teacher_sees_student_evidence_photo(app):
    evidence_id = upload_evidence(app, login(app, "stu"))
    teacher = login(app, "teacher")
    with app.app_context():
        student_id = User.query.filter_by(username="stu").one().id

    page = teacher.get(f"/teacher/students/{student_id}").get_data(as_text=True)
    photo = teacher.get(f"/teacher/evidence/{evidence_id}/view")

    assert f'src="/teacher/evidence/{evidence_id}/view"' in page
    assert photo.status_code == 200
    assert photo.mimetype == "image/png"


def test_other_teacher_cannot_see_evidence(app):
    evidence_id = upload_evidence(app, login(app, "stu"))

    assert login(app, "stranger").get(f"/teacher/evidence/{evidence_id}/view").status_code == 403


def test_uploaded_document_is_shown_on_review_page(app):
    client = login(app, "stu")
    client.post("/student/learning-profile/documents", data={
        "document_type": "credential", "file": (io.BytesIO(PNG), "cert.png"),
    }, content_type="multipart/form-data")
    with app.app_context():
        document_id = SourceDocument.query.one().id

    review = client.get(f"/student/learning-profile/documents/{document_id}/review").get_data(as_text=True)
    photo = client.get(f"/student/learning-profile/documents/{document_id}/view")

    assert f'src="/student/learning-profile/documents/{document_id}/view"' in review
    assert photo.status_code == 200
    assert photo.mimetype == "image/png"
    assert photo.headers["X-Content-Type-Options"] == "nosniff"


def test_upload_pages_tell_browser_the_size_limit(app):
    client = login(app, "stu")
    limit = str(app.config["MAX_CONTENT_LENGTH"])

    assert f'data-max-bytes="{limit}"' in client.get("/student/learning-profile/upload").get_data(as_text=True)


def test_too_large_upload_gets_chinese_message(app):
    app.config["MAX_CONTENT_LENGTH"] = 1024
    client = login(app, "stu")

    response = client.post("/student/learning-profile/documents", data={
        "document_type": "credential", "file": (io.BytesIO(b"x" * 4096), "big.png"),
    }, content_type="multipart/form-data")

    assert response.status_code == 413
    assert "檔案太大" in response.get_data(as_text=True)


def upload_confirmed_document(app, client):
    client.post("/student/learning-profile/documents", data={
        "document_type": "credential", "file": (io.BytesIO(PNG), "cert.png"),
    }, content_type="multipart/form-data")
    with app.app_context():
        document = SourceDocument.query.one()
        document.status = "confirmed"
        db.session.commit()
        return document.id


def test_class_teacher_sees_confirmed_source_document(app):
    document_id = upload_confirmed_document(app, login(app, "stu"))
    teacher = login(app, "teacher")
    with app.app_context():
        student_id = User.query.filter_by(username="stu").one().id

    page = teacher.get(f"/teacher/students/{student_id}").get_data(as_text=True)
    photo = teacher.get(f"/teacher/documents/{document_id}/view")

    assert f'src="/teacher/documents/{document_id}/view"' in page
    assert photo.status_code == 200
    assert photo.mimetype == "image/png"


def test_other_teacher_cannot_see_source_document(app):
    document_id = upload_confirmed_document(app, login(app, "stu"))

    assert login(app, "stranger").get(f"/teacher/documents/{document_id}/view").status_code == 403


def test_upload_field_offers_rotate_button(app):
    html = login(app, "stu").get("/student/learning-profile/upload").get_data(as_text=True)

    assert "data-rotate" in html


def test_inline_file_serves_relative_upload_path_from_working_directory(app, tmp_path, monkeypatch):
    # 預設 UPLOAD_FOLDER 是相對路徑 instance/uploads（相對於專案資料夾）；
    # Flask 的 send_file 會把相對路徑當成相對於 app/ 資料夾，造成本機展示站預覽 500。
    from app.services.file_preview import inline_file

    monkeypatch.chdir(tmp_path)
    relative = tmp_path / "instance" / "uploads" / "synthetic.png"
    relative.parent.mkdir(parents=True)
    relative.write_bytes(PNG)

    with app.test_request_context():
        response = inline_file("instance/uploads/synthetic.png", "synthetic.png")
        response.direct_passthrough = False
        assert response.status_code == 200
        assert response.get_data() == PNG
