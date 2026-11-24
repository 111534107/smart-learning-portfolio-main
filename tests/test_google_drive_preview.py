"""Google Drive 展示原型只驗證使用者選取的單一檔案中繼資料。"""
import json

import pytest

from app.services import google_drive_preview


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


def test_selected_file_lookup_requests_only_expected_metadata(monkeypatch):
    requests = []

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse({
            "id": "file_123",
            "name": "作品證明.pdf",
            "mimeType": "application/pdf",
            "webViewLink": "https://drive.google.com/file/d/file_123/view",
        })

    monkeypatch.setattr(google_drive_preview, "urlopen", fake_urlopen)

    file_data = google_drive_preview.get_selected_file_metadata("file_123", "one-time-token")

    request, timeout = requests[0]
    assert request.full_url.endswith("fields=id,name,mimeType,webViewLink")
    assert request.get_header("Authorization") == "Bearer one-time-token"
    assert timeout == 8
    assert file_data["name"] == "作品證明.pdf"
    assert set(file_data) == {"id", "name", "mimeType", "webViewLink"}


@pytest.mark.parametrize("file_id,token", [("", "token"), ("../allFiles", "token"), ("file_123", "")])
def test_selected_file_lookup_rejects_invalid_inputs_before_network(monkeypatch, file_id, token):
    def unexpected_urlopen(*_args, **_kwargs):
        raise AssertionError("invalid input must not reach Google")

    monkeypatch.setattr(google_drive_preview, "urlopen", unexpected_urlopen)

    with pytest.raises(ValueError):
        google_drive_preview.get_selected_file_metadata(file_id, token)


def test_selected_file_lookup_rejects_drive_folders(monkeypatch):
    monkeypatch.setattr(
        google_drive_preview,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse({
            "id": "folder_123",
            "name": "作品資料夾",
            "mimeType": "application/vnd.google-apps.folder",
            "webViewLink": "https://drive.google.com/drive/folders/folder_123",
        }),
    )

    with pytest.raises(ValueError, match="folder"):
        google_drive_preview.get_selected_file_metadata("folder_123", "token")


def test_selected_file_lookup_rejects_non_google_file_links(monkeypatch):
    monkeypatch.setattr(
        google_drive_preview,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse({
            "id": "file_123",
            "name": "作品證明.pdf",
            "mimeType": "application/pdf",
            "webViewLink": "https://attacker.example/file_123",
        }),
    )

    with pytest.raises(ValueError, match="link"):
        google_drive_preview.get_selected_file_metadata("file_123", "token")


def test_selected_file_lookup_maps_expired_or_denied_google_authorization(monkeypatch):
    from urllib.error import HTTPError

    def denied(*_args, **_kwargs):
        raise HTTPError("https://www.googleapis.com/", 403, "denied", {}, None)

    monkeypatch.setattr(google_drive_preview, "urlopen", denied)

    with pytest.raises(google_drive_preview.GoogleDriveAuthorizationError):
        google_drive_preview.get_selected_file_metadata("file_123", "token")
