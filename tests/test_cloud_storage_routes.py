"""上傳流程改走 StorageService：Drive 模式（假物件）與本機模式的上傳、預覽、OCR、刪除標記，以及管理員連線頁。"""
import io
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image

from app import create_app
from app.extensions import db
from app.models import Portfolio, PortfolioEvidence, SourceDocument, User
from app.services import storage_service
from tests.test_storage_service import FakeDriveClient


def png_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (1600, 1200), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def make_app(tmp_path, fake=None, connected=True, **config):
    settings = {"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                "UPLOAD_FOLDER": str(tmp_path / "uploads"), "DOCUMENT_ANALYSIS_PROVIDER": "fake",
                "OCR_QUEUE_MODE": "inline", **config}
    if fake is not None:
        settings.update(STORAGE_BACKEND="google_drive", GOOGLE_OAUTH_CLIENT_ID="cid",
                        GOOGLE_OAUTH_CLIENT_SECRET="secret",
                        GOOGLE_STORAGE_REDIRECT_URI="http://localhost/admin/storage/google/callback",
                        GOOGLE_STORAGE_CLIENT=fake)
    app = create_app(settings)
    with app.app_context():
        db.create_all()
        for username, role in (("student_syn", "student"), ("other_syn", "student"), ("admin_syn", "admin")):
            user = User(username=username, display_name=f"合成{role}", role=role)
            user.set_password("pw")
            db.session.add(user)
        db.session.commit()
    if fake is not None and connected:
        storage_service.token_holder(app).set({"access_token": "tok-1", "expires_in": 3600,
                                               "refresh_token": "refresh-1"})
    return app


def login(app, username="student_syn"):
    client = app.test_client()
    client.post("/login", data={"username": username, "password": "pw"})
    return client


def upload_transcript(client):
    return client.post("/student/learning-profile/documents",
                       data={"document_type": "transcript", "file": (io.BytesIO(png_bytes()), "transcript.png")},
                       content_type="multipart/form-data")


# ---------- 成績單：Drive 模式 ----------

def test_drive_mode_upload_ocr_and_preview(tmp_path):
    fake = FakeDriveClient()
    app = make_app(tmp_path, fake)
    client = login(app)

    response = upload_transcript(client)

    assert response.status_code == 302
    with app.app_context():
        document = SourceDocument.query.one()
        assert document.file_path.startswith("drive:file1/")
        assert document.status == "extracted"  # 背景 OCR 讀得到檔案
        location, document_id = document.file_path, document.id
    assert fake.files["file1"]["data"] == png_bytes()

    # 本機快取被清掉後，預覽會透過後端向 Drive 取回
    with app.app_context():
        storage_service.cache_path(location).unlink()
    view = client.get(f"/student/learning-profile/documents/{document_id}/view")
    assert view.status_code == 200
    assert view.data == png_bytes()
    assert view.headers["X-Content-Type-Options"] == "nosniff"


def test_drive_mode_processing_preview_thumbnail_is_in_cache(tmp_path):
    fake = FakeDriveClient()
    app = make_app(tmp_path, fake, OCR_QUEUE_MODE="manual")
    client = login(app)
    upload_transcript(client)
    with app.app_context():
        document = SourceDocument.query.one()
        from app.services import ocr_queue
        ocr_queue.run_job(app, document.id)
        preview = ocr_queue.preview_path(document.file_path)
        assert preview.is_file()
        assert preview.parent == storage_service.cache_path(document.file_path).parent
        document_id = document.id
    assert client.get(f"/student/learning-profile/documents/{document_id}/preview").status_code == 200


def test_drive_unavailable_preview_is_404_not_500(tmp_path):
    fake = FakeDriveClient()
    app = make_app(tmp_path, fake)
    client = login(app)
    upload_transcript(client)
    with app.app_context():
        document = SourceDocument.query.one()
        storage_service.cache_path(document.file_path).unlink()
        storage_service.token_holder(app).clear()
        document_id = document.id

    assert client.get(f"/student/learning-profile/documents/{document_id}/view").status_code == 404
    assert client.get(f"/student/learning-profile/documents/{document_id}/source").status_code == 404


def test_drive_unavailable_ocr_shows_chinese_error(tmp_path):
    fake = FakeDriveClient()
    app = make_app(tmp_path, fake, OCR_QUEUE_MODE="manual")
    client = login(app)
    upload_transcript(client)
    with app.app_context():
        document = SourceDocument.query.one()
        storage_service.cache_path(document.file_path).unlink()
        storage_service.token_holder(app).clear()
        document_id = document.id
    from app.services import ocr_queue
    ocr_queue.run_job(app, document_id)
    with app.app_context():
        document = db.session.get(SourceDocument, document_id)
        assert document.status == "analysis_failed"
        assert "雲端" in document.extraction.error_message


def test_other_student_cannot_view_drive_document(tmp_path):
    fake = FakeDriveClient()
    app = make_app(tmp_path, fake)
    upload_transcript(login(app))
    with app.app_context():
        document_id = SourceDocument.query.one().id
    assert login(app, "other_syn").get(f"/student/learning-profile/documents/{document_id}/view").status_code == 403


# ---------- 成績單：本機模式（照現有行為） ----------

def test_local_mode_upload_ocr_and_preview_unchanged(tmp_path):
    app = make_app(tmp_path)
    client = login(app)
    upload_transcript(client)
    with app.app_context():
        document = SourceDocument.query.one()
        assert Path(document.file_path).is_file()
        assert Path(document.file_path).parent == tmp_path / "uploads" / "learning-profile" / str(document.owner_id)
        assert document.status == "extracted"
        document_id = document.id
    view = client.get(f"/student/learning-profile/documents/{document_id}/view")
    assert view.status_code == 200 and view.data == png_bytes()


def test_drive_mode_without_connection_still_uploads_locally(tmp_path):
    fake = FakeDriveClient()
    app = make_app(tmp_path, fake, connected=False)
    client = login(app)
    assert upload_transcript(client).status_code == 302
    with app.app_context():
        document = SourceDocument.query.one()
        assert Path(document.file_path).is_file()
        assert document.status == "extracted"
    assert fake.calls == []


# ---------- 佐證檔案與刪除標記 ----------

def make_portfolio(app):
    with app.app_context():
        student = User.query.filter_by(username="student_syn").one()
        portfolio = Portfolio(student_id=student.id, title="合成經歷", category="project")
        db.session.add(portfolio)
        db.session.commit()
        return portfolio.id


def upload_evidence(client, portfolio_id):
    return client.post(f"/student/portfolio/{portfolio_id}/evidence",
                       data={"file": (io.BytesIO(png_bytes()), "photo.png")}, content_type="multipart/form-data")


def test_drive_mode_evidence_upload_view_and_delete_marks_only(tmp_path):
    fake = FakeDriveClient()
    app = make_app(tmp_path, fake)
    portfolio_id = make_portfolio(app)
    client = login(app)

    assert upload_evidence(client, portfolio_id).status_code == 302
    with app.app_context():
        evidence = PortfolioEvidence.query.one()
        assert evidence.file_path.startswith("drive:file1/")
        evidence_id = evidence.id
    assert client.get(f"/student/evidence/{evidence_id}/view").data == png_bytes()
    assert client.get(f"/student/evidence/{evidence_id}").data == png_bytes()

    assert client.post(f"/student/evidence/{evidence_id}/delete").status_code == 302
    with app.app_context():
        assert PortfolioEvidence.query.one().deleted_at is not None  # 資料列保留，只標記刪除（M10）
    assert fake.files["file1"]["trashed"] is False  # 只標記，不永久刪除
    assert fake.files["file1"]["app_properties"]["slp_deleted_reason"] == "student_deleted_evidence"


def test_local_mode_evidence_delete_keeps_file_with_marker(tmp_path):
    app = make_app(tmp_path)
    portfolio_id = make_portfolio(app)
    client = login(app)
    upload_evidence(client, portfolio_id)
    with app.app_context():
        evidence = PortfolioEvidence.query.one()
        location, evidence_id = evidence.file_path, evidence.id

    client.post(f"/student/evidence/{evidence_id}/delete")

    assert Path(location).is_file()
    assert json.loads(Path(location + ".deleted.json").read_text(encoding="utf-8"))["reason"] == "student_deleted_evidence"


def test_portfolio_delete_marks_evidence_files(tmp_path):
    app = make_app(tmp_path)
    portfolio_id = make_portfolio(app)
    client = login(app)
    upload_evidence(client, portfolio_id)
    with app.app_context():
        location = PortfolioEvidence.query.one().file_path

    client.post(f"/student/portfolio/{portfolio_id}/delete")

    assert Path(location).is_file()
    assert Path(location + ".deleted.json").is_file()


# ---------- 管理員連線頁 ----------

def test_admin_storage_page_shows_local_when_unconfigured(tmp_path):
    app = make_app(tmp_path)
    html = login(app, "admin_syn").get("/admin/storage").get_data(as_text=True)
    assert "檔案存放設定" in html
    assert "目前存在：本機" in html
    assert "尚未設定" in html


def test_student_cannot_open_admin_storage_page(tmp_path):
    app = make_app(tmp_path)
    assert login(app).get("/admin/storage").status_code == 403


def test_admin_connects_google_drive_with_drive_file_scope(tmp_path):
    fake = FakeDriveClient()
    app = make_app(tmp_path, fake, connected=False)
    client = login(app, "admin_syn")
    assert "已設定，尚未連線" in client.get("/admin/storage").get_data(as_text=True)

    response = client.post("/admin/storage/google/connect")
    assert response.status_code == 302
    target = urlparse(response.headers["Location"])
    query = parse_qs(target.query)
    assert target.netloc == "accounts.google.com"
    assert query["scope"] == ["https://www.googleapis.com/auth/drive.file"]
    assert query["redirect_uri"] == ["http://localhost/admin/storage/google/callback"]
    state = query["state"][0]

    bad = client.get("/admin/storage/google/callback", query_string={"state": "wrong", "code": "c"})
    assert bad.status_code == 400

    client.post("/admin/storage/google/connect")
    with client.session_transaction() as session:
        state = session["google_storage_state"]
    done = client.get("/admin/storage/google/callback", query_string={"state": state, "code": "code-1"})
    assert done.status_code == 302
    assert ("exchange_code", "code-1") in fake.calls
    assert "目前存在：Google 雲端硬碟" in client.get("/admin/storage").get_data(as_text=True)

    client.post("/admin/storage/google/disconnect")
    assert not storage_service.token_holder(app).connected


def test_admin_connect_without_settings_goes_back_with_message(tmp_path):
    app = make_app(tmp_path)
    client = login(app, "admin_syn")
    response = client.post("/admin/storage/google/connect")
    assert response.status_code == 302
    assert urlparse(response.headers["Location"]).path == "/admin/storage"
