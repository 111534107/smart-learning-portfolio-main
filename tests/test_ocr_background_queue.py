"""成績單上傳後在背景排隊辨識：先跳「辨識中」頁，完成後自動進確認頁。僅為測試資料。"""
import io

from app import create_app
from app.extensions import db
from app.models import AuditLog, DocumentExtraction, SourceDocument, User
from app.services import document_analysis_service, ocr_queue


def queue_app(tmp_path, mode="manual"):
    app = create_app({
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "TESTING": True,
        "UPLOAD_FOLDER": str(tmp_path),
        "DOCUMENT_ANALYSIS_PROVIDER": "fake",
        "OCR_QUEUE_MODE": mode,
    })
    with app.app_context():
        db.create_all()
        for username, name in (("student_demo", "測試學生甲"), ("student_other", "測試學生乙")):
            student = User(username=username, display_name=name, role="student")
            student.set_password("pw")
            db.session.add(student)
        db.session.commit()
    return app


def login(client, username="student_demo"):
    client.post("/login", data={"username": username, "password": "pw"})


def upload(client, next_path=None):
    data = {"document_type": "transcript", "file": (io.BytesIO(b"synthetic transcript"), "synthetic_transcript.pdf")}
    if next_path:
        data["next"] = next_path
    return client.post("/student/learning-profile/documents", data=data, content_type="multipart/form-data")


def only_document_id(app):
    with app.app_context():
        return SourceDocument.query.one().id


def test_upload_saves_file_and_redirects_to_processing_page_without_running_ocr(tmp_path):
    app = queue_app(tmp_path)
    client = app.test_client()
    login(client)

    response = upload(client)

    assert response.status_code == 302
    document_id = only_document_id(app)
    assert response.headers["Location"].endswith(f"/student/learning-profile/documents/{document_id}/processing")
    with app.app_context():
        document = db.session.get(SourceDocument, document_id)
        assert document.status == "queued"
        assert DocumentExtraction.query.count() == 0
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "辨識中" in page
    assert f"/student/learning-profile/documents/{document_id}/status" in page
    status = client.get(f"/student/learning-profile/documents/{document_id}/status").get_json()
    assert status["state"] == "queued"


def test_successful_job_moves_processing_page_to_review(tmp_path):
    app = queue_app(tmp_path)
    client = app.test_client()
    login(client)
    upload(client, next_path="/student/targets")
    document_id = only_document_id(app)

    ocr_queue.run_job(app, document_id)

    status = client.get(f"/student/learning-profile/documents/{document_id}/status?next=/student/targets").get_json()
    assert status["state"] == "done"
    assert status["redirect"].startswith(f"/student/learning-profile/documents/{document_id}/review?next=")
    assert "targets" in status["redirect"]
    with app.app_context():
        assert db.session.get(SourceDocument, document_id).status == "extracted"
        extraction = DocumentExtraction.query.one()
        assert extraction.status == "extracted"
        assert extraction.result_json["draft_revision"]
        assert AuditLog.query.filter_by(action="learning_profile.ocr_completed").count() == 1
    # 辨識完成後再打開「辨識中」頁，直接帶去確認頁
    page = client.get(f"/student/learning-profile/documents/{document_id}/processing?next=/student/targets")
    assert page.status_code == 302
    assert "/review" in page.headers["Location"]


def test_review_page_waits_while_job_is_queued(tmp_path):
    app = queue_app(tmp_path)
    client = app.test_client()
    login(client)
    upload(client)
    document_id = only_document_id(app)

    response = client.get(f"/student/learning-profile/documents/{document_id}/review")

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/documents/{document_id}/processing")


def test_failed_job_shows_reason_and_can_be_retried(tmp_path, monkeypatch):
    app = queue_app(tmp_path)
    client = app.test_client()
    login(client)
    upload(client)
    document_id = only_document_id(app)

    def broken(*args, **kwargs):
        raise RuntimeError("辨識引擎沒有回應")

    monkeypatch.setattr(ocr_queue, "analyze_document", broken)
    ocr_queue.run_job(app, document_id)

    status = client.get(f"/student/learning-profile/documents/{document_id}/status").get_json()
    assert status["state"] == "failed"
    assert "辨識引擎沒有回應" in status["error"]
    page = client.get(f"/student/learning-profile/documents/{document_id}/processing").get_data(as_text=True)
    assert "辨識引擎沒有回應" in page
    assert f"/student/learning-profile/documents/{document_id}/retry" in page
    assert "重新上傳" in page
    with app.app_context():
        assert db.session.get(SourceDocument, document_id).status == "analysis_failed"
        assert DocumentExtraction.query.one().status == "failed"
        assert AuditLog.query.filter_by(action="learning_profile.ocr_failed").count() == 1

    monkeypatch.setattr(ocr_queue, "analyze_document", document_analysis_service.analyze_document)
    retry = client.post(f"/student/learning-profile/documents/{document_id}/retry")
    assert retry.status_code == 302
    assert retry.headers["Location"].endswith(f"/documents/{document_id}/processing")
    assert client.get(f"/student/learning-profile/documents/{document_id}/status").get_json()["state"] == "queued"
    ocr_queue.run_job(app, document_id)
    assert client.get(f"/student/learning-profile/documents/{document_id}/status").get_json()["state"] == "done"
    with app.app_context():
        extraction = DocumentExtraction.query.one()
        assert extraction.status == "extracted"
        assert extraction.error_message is None


def test_unexpected_error_does_not_leave_job_stuck(tmp_path, monkeypatch):
    app = queue_app(tmp_path)
    client = app.test_client()
    login(client)
    upload(client)
    document_id = only_document_id(app)
    monkeypatch.setattr(ocr_queue, "analyze_document", lambda *a, **k: 1 / 0)

    ocr_queue.run_job(app, document_id)

    status = client.get(f"/student/learning-profile/documents/{document_id}/status").get_json()
    assert status["state"] == "failed"
    assert status["error"]


def test_repeated_status_queries_and_duplicate_runs_do_not_duplicate_work(tmp_path, monkeypatch):
    app = queue_app(tmp_path)
    client = app.test_client()
    login(client)
    upload(client)
    document_id = only_document_id(app)
    calls = []
    real = document_analysis_service.analyze_document

    def counting(*args, **kwargs):
        calls.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(ocr_queue, "analyze_document", counting)
    first = [client.get(f"/student/learning-profile/documents/{document_id}/status").get_json() for _ in range(3)]
    ocr_queue.run_job(app, document_id)
    ocr_queue.run_job(app, document_id)
    after = [client.get(f"/student/learning-profile/documents/{document_id}/status").get_json() for _ in range(3)]

    assert {item["state"] for item in first} == {"queued"}
    assert {item["state"] for item in after} == {"done"}
    assert len(calls) == 1
    with app.app_context():
        assert DocumentExtraction.query.count() == 1
        assert AuditLog.query.filter_by(action="learning_profile.ocr_completed").count() == 1
    # 已完成的文件不能再按「重新辨識」排隊
    assert client.post(f"/student/learning-profile/documents/{document_id}/retry").status_code == 409


def test_other_student_cannot_see_or_retry_someone_elses_job(tmp_path):
    app = queue_app(tmp_path)
    owner = app.test_client()
    login(owner)
    upload(owner)
    document_id = only_document_id(app)
    other = app.test_client()
    login(other, "student_other")

    assert other.get(f"/student/learning-profile/documents/{document_id}/status").status_code == 403
    assert other.get(f"/student/learning-profile/documents/{document_id}/processing").status_code == 403
    assert other.post(f"/student/learning-profile/documents/{document_id}/retry").status_code == 403
    assert other.get("/student/learning-profile/documents/9999/status").status_code == 404
    anonymous = app.test_client()
    assert anonymous.get(f"/student/learning-profile/documents/{document_id}/status").status_code in (302, 401, 403)


def test_server_restart_marks_unfinished_jobs_failed(tmp_path):
    app = queue_app(tmp_path)
    client = app.test_client()
    login(client)
    upload(client)
    upload(client)
    with app.app_context():
        first, second = SourceDocument.query.order_by(SourceDocument.id).all()
        second.status = "processing"
        db.session.commit()
        ids = (first.id, second.id)

        assert ocr_queue.recover_interrupted_jobs() == 2

        for document_id in ids:
            document = db.session.get(SourceDocument, document_id)
            assert document.status == "analysis_failed"
            assert "重新啟動" in document.extraction.error_message
    status = client.get(f"/student/learning-profile/documents/{ids[0]}/status").get_json()
    assert status["state"] == "failed"
    assert client.post(f"/student/learning-profile/documents/{ids[0]}/retry").status_code == 302


def test_thread_mode_runs_job_in_background(tmp_path):
    app = queue_app(tmp_path, mode="thread")
    client = app.test_client()
    login(client)

    response = upload(client)
    document_id = only_document_id(app)

    assert response.headers["Location"].endswith(f"/documents/{document_id}/processing")
    assert ocr_queue.wait_until_idle(timeout=10)
    assert client.get(f"/student/learning-profile/documents/{document_id}/status").get_json()["state"] == "done"


def test_pending_document_is_listed_as_processing_and_cannot_be_reanalyzed(tmp_path):
    app = queue_app(tmp_path)
    client = app.test_client()
    login(client)
    upload(client)
    document_id = only_document_id(app)

    page = client.get("/student/learning-profile").get_data(as_text=True)

    assert f"/student/learning-profile/documents/{document_id}/processing" in page
    assert "辨識中…" in page
    assert client.post(f"/student/learning-profile/documents/{document_id}/reanalyze").status_code == 409


def upload_png(client):
    from PIL import Image
    stream = io.BytesIO()
    Image.new("RGB", (3200, 2200), "white").save(stream, format="PNG")
    stream.seek(0)
    return client.post("/student/learning-profile/documents", data={
        "document_type": "transcript", "file": (stream, "synthetic_transcript.png")},
        content_type="multipart/form-data")


def test_worker_makes_owner_only_page_preview_for_the_processing_page(tmp_path):
    app = queue_app(tmp_path)
    client = app.test_client()
    login(client)
    upload_png(client)
    document_id = only_document_id(app)
    preview_url = f"/student/learning-profile/documents/{document_id}/preview"

    assert client.get(preview_url).status_code == 404
    assert "preview" not in client.get(f"/student/learning-profile/documents/{document_id}/status").get_json()
    ocr_queue.run_job(app, document_id)

    status = client.get(f"/student/learning-profile/documents/{document_id}/status").get_json()
    assert status["preview"].endswith(preview_url)
    response = client.get(preview_url)
    assert response.status_code == 200
    assert response.mimetype == "image/png"
    assert response.headers["Cache-Control"] == "private, no-store"
    other = app.test_client()
    login(other, "student_other")
    assert other.get(preview_url).status_code == 403


def test_preview_failure_does_not_fail_the_job(tmp_path):
    app = queue_app(tmp_path)
    client = app.test_client()
    login(client)
    upload(client)  # 內容不是真的 PDF，做不出預覽圖
    document_id = only_document_id(app)

    ocr_queue.run_job(app, document_id)

    status = client.get(f"/student/learning-profile/documents/{document_id}/status").get_json()
    assert status["state"] == "done"
    assert "preview" not in status


def test_status_reports_queue_position_and_found_count(tmp_path):
    app = queue_app(tmp_path)
    owner = app.test_client()
    login(owner)
    upload(owner)
    other = app.test_client()
    login(other, "student_other")
    upload(other)
    with app.app_context():
        first_id, second_id = [d.id for d in SourceDocument.query.order_by(SourceDocument.id)]

    assert owner.get(f"/student/learning-profile/documents/{first_id}/status").get_json()["ahead"] == 0
    assert other.get(f"/student/learning-profile/documents/{second_id}/status").get_json()["ahead"] == 1
    ocr_queue.run_job(app, first_id)
    assert other.get(f"/student/learning-profile/documents/{second_id}/status").get_json()["ahead"] == 0
    done = owner.get(f"/student/learning-profile/documents/{first_id}/status").get_json()
    assert done["found"] == 1  # 假辨識結果固定一門課
    page = owner.get(f"/student/learning-profile/documents/{first_id}/processing?stay=1")
    assert page.status_code == 302  # 完成後仍直接帶去確認頁


def test_english_engine_error_is_shown_in_chinese_and_kept_in_audit_log(tmp_path, monkeypatch):
    app = queue_app(tmp_path)
    client = app.test_client()
    login(client)
    upload(client)
    document_id = only_document_id(app)

    def broken(*args, **kwargs):
        raise RuntimeError("Failed to load document (PDFium: Data format error).")

    monkeypatch.setattr(ocr_queue, "analyze_document", broken)
    ocr_queue.run_job(app, document_id)

    status = client.get(f"/student/learning-profile/documents/{document_id}/status").get_json()
    assert "PDFium" not in status["error"]
    assert "檔案" in status["error"]
    page = client.get(f"/student/learning-profile/documents/{document_id}/processing").get_data(as_text=True)
    assert "PDFium" not in page
    assert '<img class="ocr-sheet__img" id="ocr-preview" hidden' in page
    with app.app_context():
        log = AuditLog.query.filter_by(action="learning_profile.ocr_failed").one()
        assert "PDFium" in log.detail_json["raw_error"]
