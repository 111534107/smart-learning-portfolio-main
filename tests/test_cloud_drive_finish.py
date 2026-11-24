"""雲端硬碟收尾：錯誤分類與中文說明、.env 設定檢查、測試連線、舊檔搬進學生資料夾（預覽／試跑／執行）。

Google 一律用假物件，不連網路；帳號、姓名、檔名都是合成資料（僅為測試資料）。
"""
import hashlib
import io
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

from app.extensions import db
from app.models import (AuditLog, LearningProfileOutput, Portfolio, PortfolioEvidence, SourceDocument, User)
from app.services import storage_migration, storage_service
from app.services.storage_service import (DriveApiDisabled, DriveAuthExpired, DriveCredentialError, DriveError,
                                          DriveNotFound, DrivePermissionDenied, DriveQuotaExceeded,
                                          DriveRateLimited, DriveRedirectMismatch, HttpDriveClient)
from tests.test_cloud_storage_routes import login, make_app
from tests.test_storage_service import FakeDriveClient

GOOD = {"STORAGE_BACKEND": "google_drive", "GOOGLE_OAUTH_CLIENT_ID": "123-abc.apps.googleusercontent.com",
        "GOOGLE_OAUTH_CLIENT_SECRET": "secret",
        "GOOGLE_STORAGE_REDIRECT_URI": "http://localhost:5185/admin/storage/google/callback"}


class FolderDriveClient(FakeDriveClient):
    """有學生子資料夾與帳號資訊的假雲端硬碟。"""

    def __init__(self, usage=1000, limit=100000, about_error=None, refresh_error=None):
        super().__init__()
        self.children = {}
        self.usage, self.limit = usage, limit
        self.about_error, self.refresh_error = about_error, refresh_error

    def refresh(self, refresh_token):
        if self.refresh_error:
            raise self.refresh_error
        return super().refresh(refresh_token)

    def ensure_child_folder(self, access_token, parent_id, name, app_properties):
        key = (parent_id, name)
        self.children.setdefault(key, f"child{len(self.children) + 1}")
        return self.children[key]

    def about(self, access_token):
        self.calls.append(("about", access_token))
        if self.about_error:
            raise self.about_error
        return {"user": {"emailAddress": "drive-test@example.com"},
                "storageQuota": {"usage": str(self.usage), "limit": str(self.limit)}}


def cloud_app(tmp_path, fake, connected=True, **config):
    app = make_app(tmp_path, fake, connected=connected, **config)
    app.config.update(GOOD)
    app.config.update(config)
    return app


# ---------- 錯誤分類 ----------

@pytest.mark.parametrize("status,body,expected", [
    (403, {"error": {"errors": [{"reason": "storageQuotaExceeded"}]}}, DriveQuotaExceeded),
    (403, {"error": {"errors": [{"reason": "userRateLimitExceeded"}]}}, DriveRateLimited),
    (429, {}, DriveRateLimited),
    (403, {"error": {"errors": [{"reason": "accessNotConfigured"}]}}, DriveApiDisabled),
    (403, {"error": {"status": "PERMISSION_DENIED", "details": [{"reason": "SERVICE_DISABLED"}]}}, DriveApiDisabled),
    (403, {"error": {"errors": [{"reason": "insufficientPermissions"}]}}, DrivePermissionDenied),
    (403, {}, DrivePermissionDenied),
    (401, {"error": {"code": 401}}, DriveAuthExpired),
    (401, {"error": "invalid_client"}, DriveCredentialError),
    (400, {"error": "invalid_grant"}, DriveAuthExpired),
    (400, {"error": "redirect_uri_mismatch"}, DriveRedirectMismatch),
    (404, {}, DriveNotFound),
    (500, b"not json", DriveError),
])
def test_google_errors_are_classified(status, body, expected):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    assert storage_service.classify_http_error(status, raw) is expected


def test_permission_denied_still_counts_as_auth_problem():
    assert issubclass(DrivePermissionDenied, DriveAuthExpired)


def test_explain_gives_chinese_action_for_each_error():
    assert "空間已滿" in storage_service.explain(DriveQuotaExceeded("x"))
    assert "GOOGLE_OAUTH_CLIENT_SECRET" in storage_service.explain(DriveCredentialError("x"))
    assert "啟用 Google Drive API" in storage_service.explain(DriveApiDisabled("x"))
    assert "測試使用者" in storage_service.explain(DrivePermissionDenied("x"))
    assert "稍後再試" in storage_service.explain(ValueError("x"))


def test_http_client_raises_classified_error_without_leaking_body(monkeypatch):
    def fake_urlopen(request, timeout):
        body = io.BytesIO(json.dumps({"error": {"errors": [{"reason": "storageQuotaExceeded"}],
                                                "message": "secret-detail"}}).encode())
        raise HTTPError(request.full_url, 403, "Forbidden", {}, body)

    monkeypatch.setattr(storage_service, "urlopen", fake_urlopen)
    client = HttpDriveClient(GOOD)
    with pytest.raises(DriveQuotaExceeded) as caught:
        client.download("tok", "file1")
    assert "secret-detail" not in str(caught.value)


# ---------- .env 設定檢查 ----------

def test_check_settings_all_good():
    checks = storage_service.check_settings(GOOD)
    assert all(item["ok"] for item in checks), checks
    assert "secret" not in json.dumps(checks, ensure_ascii=False)


@pytest.mark.parametrize("override,label,hint", [
    ({"STORAGE_BACKEND": "local"}, "STORAGE_BACKEND", "存本機"),
    ({"STORAGE_BACKEND": "dropbox"}, "STORAGE_BACKEND", "只能填 local 或 google_drive"),
    ({"GOOGLE_OAUTH_CLIENT_ID": "abc"}, "GOOGLE_OAUTH_CLIENT_ID", "格式不像"),
    ({"GOOGLE_OAUTH_CLIENT_SECRET": ""}, "GOOGLE_OAUTH_CLIENT_SECRET", "沒填"),
    ({"GOOGLE_OAUTH_CLIENT_SECRET": " secret "}, "GOOGLE_OAUTH_CLIENT_SECRET", "空白"),
    ({"GOOGLE_STORAGE_REDIRECT_URI": ""}, "GOOGLE_STORAGE_REDIRECT_URI", "沒填"),
    ({"GOOGLE_STORAGE_REDIRECT_URI": "localhost:5185/x"}, "GOOGLE_STORAGE_REDIRECT_URI", "完整網址"),
    ({"GOOGLE_STORAGE_REDIRECT_URI": "http://localhost:5185/student/google/callback"},
     "GOOGLE_STORAGE_REDIRECT_URI", "結尾路徑"),
    ({"GOOGLE_STORAGE_REDIRECT_URI": "http://192.168.0.5:5185/admin/storage/google/callback"},
     "GOOGLE_STORAGE_REDIRECT_URI", "https"),
])
def test_check_settings_points_out_each_problem(override, label, hint):
    checks = storage_service.check_settings({**GOOD, **override})
    bad = [item for item in checks if not item["ok"]]
    assert len(bad) == 1 and label in bad[0]["label"] and hint in bad[0]["hint"], bad


# ---------- 測試連線 ----------

def test_connection_stops_at_settings_when_unconfigured(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        result = storage_service.test_connection(app)
    assert not result["ok"]
    assert [step["label"] for step in result["steps"]] == [".env 設定"]


def test_connection_asks_to_connect_first(tmp_path):
    app = cloud_app(tmp_path, FolderDriveClient(), connected=False)
    with app.app_context():
        result = storage_service.test_connection(app)
    assert not result["ok"]
    assert result["steps"][-1]["label"] == "Google 授權"
    assert "連上 Google 雲端硬碟" in result["steps"][-1]["message"]


def test_connection_success_shows_account_quota_and_folder(tmp_path):
    fake = FolderDriveClient(usage=2500, limit=10000)
    app = cloud_app(tmp_path, fake)
    with app.app_context():
        result = storage_service.test_connection(app)
    assert result["ok"], result
    assert result["account"] == "drive-test@example.com"
    assert result["quota"]["percent"] == 25.0
    assert [step["label"] for step in result["steps"]] == [".env 設定", "Google 授權", "帳號與空間", "系統資料夾"]
    assert not [call for call in fake.calls if call[0] in ("upload", "trash", "set_app_properties")]


def test_connection_reports_expired_authorization(tmp_path):
    fake = FolderDriveClient(refresh_error=DriveAuthExpired("revoked"))
    app = cloud_app(tmp_path, fake, connected=False)
    with app.app_context():
        holder = storage_service.token_holder(app)
        holder.set({"access_token": "old", "expires_in": 0, "refresh_token": "r"})
        holder._expires_at = 0
        result = storage_service.test_connection(app)
    assert not result["ok"]
    assert result["steps"][-1] == {"label": "Google 授權", "ok": False,
                                   "message": DriveAuthExpired.user_message}


def test_connection_reports_full_quota(tmp_path):
    app = cloud_app(tmp_path, FolderDriveClient(usage=99, limit=100))
    with app.app_context():
        result = storage_service.test_connection(app)
    assert not result["ok"]
    assert result["steps"][-1]["label"] == "帳號與空間"
    assert "空間已滿" in result["steps"][-1]["message"]


def test_connection_reports_api_disabled(tmp_path):
    app = cloud_app(tmp_path, FolderDriveClient(about_error=DriveApiDisabled("403")))
    with app.app_context():
        result = storage_service.test_connection(app)
    assert result["steps"][-1]["message"] == DriveApiDisabled.user_message


def test_upload_failure_is_remembered_for_admin(tmp_path):
    fake = FolderDriveClient()
    app = cloud_app(tmp_path, fake)

    def full(*args, **kwargs):
        raise DriveQuotaExceeded("403")

    fake.upload = full
    with app.app_context():
        location = storage_service.save(b"data", 1, "learning-profile", "a.png")
        assert not location.startswith("drive:")
        assert "空間已滿" in storage_service.token_holder(app).last_error["message"]
    html = login(app, "admin_syn").get("/admin/storage").get_data(as_text=True)
    assert "最近一次存到雲端失敗" in html and "空間已滿" in html


# ---------- 管理員頁 ----------

def test_admin_page_lists_settings_checks_without_secret(tmp_path):
    app = cloud_app(tmp_path, FolderDriveClient(), GOOGLE_OAUTH_CLIENT_SECRET="very-secret-value")
    html = login(app, "admin_syn").get("/admin/storage").get_data(as_text=True)
    assert "data-storage-checks" in html and "GOOGLE_STORAGE_REDIRECT_URI" in html
    assert "very-secret-value" not in html
    assert "看哪些舊檔可以搬" in html


def test_admin_test_button_shows_steps_and_writes_audit(tmp_path):
    app = cloud_app(tmp_path, FolderDriveClient())
    client = login(app, "admin_syn")
    response = client.post("/admin/storage/google/test")
    assert response.status_code == 302
    html = client.get("/admin/storage").get_data(as_text=True)
    assert 'data-storage-test-result="ok"' in html
    assert "drive-test@example.com" in html
    with app.app_context():
        log = AuditLog.query.filter_by(action="system.storage_google_test").one()
        assert log.detail_json["ok"] is True


def test_student_cannot_test_connection_or_open_migration(tmp_path):
    app = cloud_app(tmp_path, FolderDriveClient())
    client = login(app)
    assert client.post("/admin/storage/google/test").status_code == 403
    assert client.get("/admin/storage/migration").status_code == 403
    assert client.post("/admin/storage/migration/execute", data={"confirm": "確定搬移"}).status_code == 403


def test_callback_with_wrong_client_secret_explains(tmp_path):
    fake = FolderDriveClient()

    def bad_exchange(code):
        raise DriveCredentialError("401")

    fake.exchange_code = bad_exchange
    app = cloud_app(tmp_path, fake, connected=False)
    client = login(app, "admin_syn")
    client.post("/admin/storage/google/connect")
    with client.session_transaction() as session:
        state = session["google_storage_state"]
    response = client.get("/admin/storage/google/callback", query_string={"state": state, "code": "c"},
                          follow_redirects=True)
    assert "不認得這組用戶端 ID 或密鑰" in response.get_data(as_text=True)


def test_google_workspace_page_shows_drive_status(tmp_path):
    app = make_app(tmp_path)
    html = login(app, "admin_syn").get("/admin/google-workspace").get_data(as_text=True)
    assert "data-drive-status" in html and "存本機" in html


# ---------- 舊檔搬進學生資料夾 ----------

def seed_old_files(app):
    """三種舊檔各一份在本機、一份找不到、一份已標記刪除、一份已在雲端。"""
    with app.app_context():
        student = User.query.filter_by(username="student_syn").one()
        local = storage_service.LocalStorage(app.config["UPLOAD_FOLDER"])
        transcript = local.save(b"transcript-bytes", student.id, "learning-profile", "成績單.png")
        evidence = local.save(b"evidence-bytes", student.id, "", "照片.png")
        backup = local.save(b"docx-bytes", student.id, "autobiography", "自傳_第1版.docx")
        removed = local.save(b"removed", student.id, "", "已刪.png")
        local.mark_deleted(removed, "student_deleted_evidence")
        db.session.add_all([
            SourceDocument(owner_id=student.id, document_type="transcript", display_name="成績單.png",
                           file_path=transcript, sha256="0" * 64),
            SourceDocument(owner_id=student.id, document_type="license", display_name="遺失.png",
                           file_path=str(Path(app.config["UPLOAD_FOLDER"]) / "nope" / "遺失.png"), sha256="1" * 64),
            SourceDocument(owner_id=student.id, document_type="license", display_name="雲端.png",
                           file_path="drive:fileX/abc_雲端.png", sha256="2" * 64),
        ])
        portfolio = Portfolio(student_id=student.id, title="合成經歷", category="project")
        db.session.add(portfolio)
        db.session.flush()
        db.session.add_all([
            PortfolioEvidence(portfolio_id=portfolio.id, evidence_type="file", display_name="照片.png",
                              file_path=evidence),
            PortfolioEvidence(portfolio_id=portfolio.id, evidence_type="file", display_name="已刪.png",
                              file_path=removed),
            LearningProfileOutput(student_id=student.id, output_type="autobiography",
                                  content_json={"version": 1, "backup_location": backup, "backup_status": "done"},
                                  source_snapshot_json={}),
        ])
        db.session.commit()
        return {"transcript": transcript, "evidence": evidence, "backup": backup}


def test_preview_counts_each_status_and_changes_nothing(tmp_path):
    app = cloud_app(tmp_path, FolderDriveClient())
    paths = seed_old_files(app)
    with app.app_context():
        result = storage_migration.preview()
        assert result["counts"] == {"ready": 3, "missing": 1, "drive": 1, "deleted": 1}
        assert result["total_bytes"] == len(b"transcript-bytes") + len(b"evidence-bytes") + len(b"docx-bytes")
        names = {item["name"] for item in result["items"] if item["status"] == "ready"}
        assert names == {"成績單.png", "照片.png", "自傳_第1版.docx"}
        assert result["by_student"][0]["folder"].startswith("student_syn_")
        assert SourceDocument.query.filter_by(display_name="成績單.png").one().file_path == paths["transcript"]


def test_dry_run_reads_files_and_lists_targets_without_calling_google(tmp_path):
    fake = FolderDriveClient()
    app = cloud_app(tmp_path, fake)
    seed_old_files(app)
    with app.app_context():
        result = storage_migration.dry_run()
    ready = [item for item in result["items"] if item["status"] == "ready"]
    assert {item["sha256"] for item in ready} == {hashlib.sha256(d).hexdigest() for d in
                                                  (b"transcript-bytes", b"evidence-bytes", b"docx-bytes")}
    assert any(item["target"].endswith("／成績單與證照") for item in ready)
    assert result["blockers"] == []
    assert fake.calls == []


def test_migration_page_preview_and_dry_run(tmp_path):
    app = cloud_app(tmp_path, FolderDriveClient())
    seed_old_files(app)
    client = login(app, "admin_syn")
    html = client.get("/admin/storage/migration").get_data(as_text=True)
    assert 'data-count-ready="3"' in html and "成績單.png" in html and "開始搬移" in html
    html = client.post("/admin/storage/migration").get_data(as_text=True)
    assert "試跑結果" in html and "SHA-256" in html


def test_migration_is_blocked_until_connected(tmp_path):
    app = cloud_app(tmp_path, FolderDriveClient(), connected=False)
    seed_old_files(app)
    client = login(app, "admin_syn")
    html = client.get("/admin/storage/migration").get_data(as_text=True)
    assert "還不能搬" in html and "開始搬移" not in html
    response = client.post("/admin/storage/migration/execute", data={"confirm": "確定搬移"})
    assert response.status_code == 400
    with app.app_context():
        assert SourceDocument.query.filter_by(display_name="成績單.png").one().file_path.startswith(
            app.config["UPLOAD_FOLDER"])


def test_migration_needs_confirm_text(tmp_path):
    fake = FolderDriveClient()
    app = cloud_app(tmp_path, fake)
    seed_old_files(app)
    response = login(app, "admin_syn").post("/admin/storage/migration/execute", data={"confirm": "好"})
    assert response.status_code == 400
    assert "確定搬移" in response.get_data(as_text=True)
    assert not [call for call in fake.calls if call[0] == "upload"]


def test_migration_execute_copies_to_student_folders_and_keeps_local(tmp_path):
    fake = FolderDriveClient()
    app = cloud_app(tmp_path, fake)
    paths = seed_old_files(app)
    response = login(app, "admin_syn").post("/admin/storage/migration/execute", data={"confirm": "確定搬移"})
    assert response.status_code == 200
    assert "已搬 3 個檔案" in response.get_data(as_text=True)
    with app.app_context():
        doc = SourceDocument.query.filter_by(display_name="成績單.png").one()
        assert doc.file_path.startswith("drive:")
        assert storage_service.read_bytes(doc.file_path) == b"transcript-bytes"
        evidence = PortfolioEvidence.query.filter_by(display_name="照片.png").one()
        assert evidence.file_path.startswith("drive:")
        output = LearningProfileOutput.query.one()
        assert output.content_json["backup_location"].startswith("drive:")
        assert output.content_json["backup_status"] == "done"
        # 已標記刪除的不搬
        assert not PortfolioEvidence.query.filter_by(display_name="已刪.png").one().file_path.startswith("drive:")
        log = AuditLog.query.filter_by(action="system.storage_migrate_to_drive").one()
        assert log.detail_json == {"moved": 3, "failed": 0, "remaining": 0}
    # 本機原檔保留，旁邊有搬移紀錄
    for path in paths.values():
        assert Path(path).is_file()
        marker = json.loads(Path(path + storage_migration.MIGRATED_SUFFIX).read_text(encoding="utf-8"))
        assert marker["moved_to"].startswith("drive:")
    uploaded = {f["name"].split("_", 1)[1]: f for f in fake.files.values()}
    assert set(uploaded) == {"成績單.png", "照片.png", "自傳_第1版.docx"}
    assert uploaded["成績單.png"]["folder"] != uploaded["照片.png"]["folder"]  # 不同種類子資料夾
    assert not any(f["trashed"] for f in fake.files.values())
    # 再按一次沒有東西要搬
    with app.app_context():
        assert storage_migration.preview()["counts"]["ready"] == 0


def test_migration_continues_after_one_failure(tmp_path):
    fake = FolderDriveClient()
    app = cloud_app(tmp_path, fake)
    seed_old_files(app)
    original = fake.upload
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise DriveRateLimited("429")
        return original(*args, **kwargs)

    fake.upload = flaky
    with app.app_context():
        admin = User.query.filter_by(username="admin_syn").one()
        outcome = storage_migration.execute(admin)
        assert len(outcome["moved"]) == 2 and len(outcome["failed"]) == 1
        assert "等一分鐘" in outcome["failed"][0]["message"]
        assert storage_migration.preview()["counts"]["ready"] == 1
