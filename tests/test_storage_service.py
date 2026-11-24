"""檔案存放可替換（V2 架構、V1 規格「檔案存放要做成可替換的」）：本機與 Google 雲端硬碟。

Google 一律用假物件，不連網路；帳號、檔名都是合成資料。
"""
import json
from pathlib import Path

import pytest

from app import create_app
from app.services import storage_service
from app.services.storage_service import StorageUnavailable


class FakeDriveClient:
    """假的 Google 雲端硬碟：記下每次呼叫，檔案放在字典裡。"""

    def __init__(self):
        self.files = {}
        self.folders = []
        self.calls = []
        self.fail_upload = False
        self.refreshed = 0

    def exchange_code(self, code):
        self.calls.append(("exchange_code", code))
        return {"access_token": "tok-1", "expires_in": 3600, "refresh_token": "refresh-1"}

    def refresh(self, refresh_token):
        self.refreshed += 1
        self.calls.append(("refresh", refresh_token))
        return {"access_token": f"tok-r{self.refreshed}", "expires_in": 3600}

    def ensure_folder(self, access_token, name):
        self.calls.append(("ensure_folder", access_token, name))
        if not self.folders:
            self.folders.append("folder-1")
        return self.folders[0]

    def upload(self, access_token, folder_id, name, data, mime_type, app_properties):
        self.calls.append(("upload", access_token, folder_id, name))
        if self.fail_upload:
            raise storage_service.DriveError("假的上傳失敗")
        file_id = f"file{len(self.files) + 1}"
        self.files[file_id] = {"name": name, "data": data, "mime": mime_type, "folder": folder_id,
                               "app_properties": dict(app_properties), "trashed": False}
        return file_id

    def download(self, access_token, file_id):
        self.calls.append(("download", access_token, file_id))
        return self.files[file_id]["data"]

    def set_app_properties(self, access_token, file_id, app_properties):
        self.calls.append(("set_app_properties", access_token, file_id))
        self.files[file_id]["app_properties"].update(app_properties)

    def trash(self, access_token, file_id):
        self.calls.append(("trash", access_token, file_id))
        self.files[file_id]["trashed"] = True


def make_app(tmp_path, **config):
    return create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                       "UPLOAD_FOLDER": str(tmp_path / "uploads"), **config})


def drive_app(tmp_path, fake, connected=True):
    app = make_app(tmp_path, STORAGE_BACKEND="google_drive", GOOGLE_OAUTH_CLIENT_ID="cid",
                   GOOGLE_OAUTH_CLIENT_SECRET="secret",
                   GOOGLE_STORAGE_REDIRECT_URI="http://localhost/admin/storage/google/callback",
                   GOOGLE_STORAGE_CLIENT=fake)
    if connected:
        storage_service.token_holder(app).set({"access_token": "tok-1", "expires_in": 3600,
                                               "refresh_token": "refresh-1"})
    return app


# ---------- 本機（預設，照現有行為） ----------

def test_default_backend_is_local_and_keeps_plain_path(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        assert storage_service.active_backend_name() == "local"
        location = storage_service.save(b"abc", owner_id=7, folder="learning-profile", filename="t.pdf")

        path = Path(location)
        assert not location.startswith(("drive:", "local:"))  # 沿用舊資料的寫法：沒有前綴就是本機
        assert path.parent == tmp_path / "uploads" / "learning-profile" / "7"
        assert path.name.endswith("_t.pdf")
        assert storage_service.read_bytes(location) == b"abc"
        assert storage_service.exists(location)
        assert storage_service.local_path(location) == path


def test_local_location_with_prefix_is_also_understood(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        location = storage_service.save(b"abc", owner_id=1, folder="", filename="a.png")
        assert storage_service.read_bytes("local:" + location) == b"abc"


def test_local_mark_deleted_keeps_file_and_writes_marker(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        location = storage_service.save(b"abc", owner_id=1, folder="", filename="a.png")
        storage_service.mark_deleted(location, reason="student_deleted_evidence")

        assert Path(location).is_file()  # 不直接永久刪除：送審快照或之後依政策清除時還找得到
        marker = json.loads(Path(location + ".deleted.json").read_text(encoding="utf-8"))
        assert marker["reason"] == "student_deleted_evidence" and marker["deleted_at"]
        assert storage_service.is_marked_deleted(location)


def test_local_missing_file_is_not_found(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        missing = str(tmp_path / "uploads" / "nope.pdf")
        assert not storage_service.exists(missing)
        assert storage_service.local_path_or_none(missing) is None


def test_mark_deleted_ignores_empty_location(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        storage_service.mark_deleted(None)
        storage_service.mark_deleted("")


# ---------- Google 雲端硬碟（假物件） ----------

def test_drive_save_uploads_with_drive_prefix_and_keeps_local_cache(tmp_path):
    fake = FakeDriveClient()
    app = drive_app(tmp_path, fake)
    with app.app_context():
        assert storage_service.active_backend_name() == "google_drive"
        location = storage_service.save(b"pdf-bytes", owner_id=7, folder="learning-profile", filename="t.pdf")

        assert location.startswith("drive:file1/")
        assert location.endswith("_t.pdf")
        stored = fake.files["file1"]
        assert stored["data"] == b"pdf-bytes" and stored["folder"] == "folder-1"
        assert stored["mime"] == "application/pdf"
        assert stored["app_properties"] == {"slp_owner": "7", "slp_folder": "learning-profile"}
        # 背景 OCR 不必再下載一次
        assert storage_service.cache_path(location).read_bytes() == b"pdf-bytes"
        assert storage_service.local_path(location) == storage_service.cache_path(location)


def test_drive_read_downloads_when_cache_missing(tmp_path):
    fake = FakeDriveClient()
    app = drive_app(tmp_path, fake)
    with app.app_context():
        location = storage_service.save(b"img", owner_id=1, folder="", filename="a.png")
        storage_service.cache_path(location).unlink()

        assert storage_service.read_bytes(location) == b"img"
        assert ("download", "tok-1", "file1") in fake.calls
        assert storage_service.cache_path(location).read_bytes() == b"img"


def test_drive_read_without_connection_and_cache_raises_chinese_error(tmp_path):
    fake = FakeDriveClient()
    app = drive_app(tmp_path, fake)
    with app.app_context():
        location = storage_service.save(b"img", owner_id=1, folder="", filename="a.png")
        storage_service.cache_path(location).unlink()
        storage_service.token_holder(app).clear()

        with pytest.raises(StorageUnavailable) as error:
            storage_service.read_bytes(location)
        assert "雲端" in str(error.value)
        assert isinstance(error.value, RuntimeError)  # OCR 佇列把 RuntimeError 當成給學生看的訊息
        assert not storage_service.exists(location)
        assert storage_service.local_path_or_none(location) is None


def test_drive_mode_without_connection_falls_back_to_local(tmp_path):
    fake = FakeDriveClient()
    app = drive_app(tmp_path, fake, connected=False)
    with app.app_context():
        location = storage_service.save(b"abc", owner_id=1, folder="", filename="a.pdf")
        assert not location.startswith("drive:")
        assert Path(location).read_bytes() == b"abc"
        assert fake.calls == []


def test_drive_mode_without_oauth_settings_falls_back_to_local(tmp_path):
    fake = FakeDriveClient()
    app = make_app(tmp_path, STORAGE_BACKEND="google_drive", GOOGLE_STORAGE_CLIENT=fake)
    with app.app_context():
        assert storage_service.active_backend_name() == "local"
        assert not storage_service.save(b"a", owner_id=1, folder="", filename="a.pdf").startswith("drive:")


def test_drive_upload_failure_falls_back_to_local(tmp_path):
    fake = FakeDriveClient()
    fake.fail_upload = True
    app = drive_app(tmp_path, fake)
    with app.app_context():
        location = storage_service.save(b"abc", owner_id=1, folder="", filename="a.pdf")
        assert not location.startswith("drive:")
        assert Path(location).read_bytes() == b"abc"


def test_drive_mark_deleted_only_marks_and_discard_moves_to_trash(tmp_path):
    fake = FakeDriveClient()
    app = drive_app(tmp_path, fake)
    with app.app_context():
        kept = storage_service.save(b"a", owner_id=1, folder="", filename="a.pdf")
        storage_service.mark_deleted(kept, reason="student_deleted_evidence")
        assert fake.files["file1"]["trashed"] is False
        assert fake.files["file1"]["app_properties"]["slp_deleted_reason"] == "student_deleted_evidence"
        assert fake.files["file1"]["app_properties"]["slp_deleted_at"]

        orphan = storage_service.save(b"b", owner_id=1, folder="", filename="b.pdf")
        storage_service.discard(orphan)  # 資料庫沒存進去的孤兒檔：丟到垃圾桶（Google 30 天後才清）
        assert fake.files["file2"]["trashed"] is True


def test_drive_folder_is_created_once(tmp_path):
    fake = FakeDriveClient()
    app = drive_app(tmp_path, fake)
    with app.app_context():
        storage_service.save(b"a", owner_id=1, folder="", filename="a.pdf")
        storage_service.save(b"b", owner_id=1, folder="", filename="b.pdf")
    assert [c[0] for c in fake.calls].count("ensure_folder") == 1


def test_token_holder_refreshes_expired_token(tmp_path):
    fake = FakeDriveClient()
    now = [1000.0]
    holder = storage_service.TokenHolder(clock=lambda: now[0])
    holder.set({"access_token": "tok-1", "expires_in": 3600, "refresh_token": "refresh-1"})
    assert holder.access_token(fake) == "tok-1"

    now[0] += 3600
    assert holder.access_token(fake) == "tok-r1"
    assert fake.calls == [("refresh", "refresh-1")]

    holder.clear()
    assert holder.access_token(fake) is None
    assert not holder.connected


def test_token_holder_without_refresh_token_expires(tmp_path):
    fake = FakeDriveClient()
    now = [0.0]
    holder = storage_service.TokenHolder(clock=lambda: now[0])
    holder.set({"access_token": "tok-1", "expires_in": 3600})
    now[0] += 4000
    assert holder.access_token(fake) is None


def test_drive_location_rejects_bad_file_id(tmp_path):
    fake = FakeDriveClient()
    app = drive_app(tmp_path, fake)
    with app.app_context():
        with pytest.raises(StorageUnavailable):
            storage_service.read_bytes("drive:../../etc/passwd")
        with pytest.raises(StorageUnavailable):
            storage_service.read_bytes("drive:abc/../../x.pdf")
