"""雲端提案展示需保持匿名安全，Google 選檔只在 OAuth 設定完成時啟用。"""
from app import create_app


def preview_app(**overrides):
    config = {
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "TESTING": True,
        "GOOGLE_DRIVE_PREVIEW_ENABLED": False,
        "GOOGLE_OAUTH_CLIENT_ID": "",
        "GOOGLE_PICKER_API_KEY": "",
        "GOOGLE_CLOUD_PROJECT_NUMBER": "",
    }
    config.update(overrides)
    return create_app(config)


def test_proposal_preview_is_public_fake_data_and_shows_drive_setup_state():
    response = preview_app().test_client().get("/proposal-preview")

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "展示用假資料" in page
    assert "Google Drive 尚未設定" in page
    assert "access_token" not in page
    assert "proposal-preview-drive.js" not in page


def test_drive_picker_is_enabled_only_when_all_local_oauth_settings_exist():
    response = preview_app(
        GOOGLE_DRIVE_PREVIEW_ENABLED=True,
        GOOGLE_OAUTH_CLIENT_ID="client-id.apps.googleusercontent.com",
        GOOGLE_PICKER_API_KEY="public-picker-key",
        GOOGLE_CLOUD_PROJECT_NUMBER="123456789",
    ).test_client().get("/proposal-preview")

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'data-drive-enabled="true"' in page
    assert "client-id.apps.googleusercontent.com" in page
    assert "public-picker-key" in page
    assert "123456789" in page
    assert "drive.file" in page


def test_drive_picker_remains_disabled_in_production_even_with_local_settings():
    response = preview_app(
        FLASK_ENV="production",
        GOOGLE_DRIVE_PREVIEW_ENABLED=True,
        GOOGLE_OAUTH_CLIENT_ID="client-id.apps.googleusercontent.com",
        GOOGLE_PICKER_API_KEY="public-picker-key",
        GOOGLE_CLOUD_PROJECT_NUMBER="123456789",
    ).test_client().get("/proposal-preview")

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'data-drive-enabled="false"' in page
    assert "proposal-preview-drive.js" not in page


def test_selected_drive_file_endpoint_returns_metadata_without_echoing_token(monkeypatch):
    from app.routes import proposal_preview as preview_routes

    seen = {}

    def fake_get_selected_file_metadata(file_id, access_token):
        seen.update(file_id=file_id, access_token=access_token)
        return {
            "id": file_id,
            "name": "作品證明.pdf",
            "mimeType": "application/pdf",
            "webViewLink": "https://drive.google.com/file/d/demo/view",
        }

    monkeypatch.setattr(preview_routes, "get_selected_file_metadata", fake_get_selected_file_metadata)
    client = preview_app(
        GOOGLE_DRIVE_PREVIEW_ENABLED=True,
        GOOGLE_OAUTH_CLIENT_ID="client-id.apps.googleusercontent.com",
        GOOGLE_PICKER_API_KEY="public-picker-key",
        GOOGLE_CLOUD_PROJECT_NUMBER="123456789",
    ).test_client()

    response = client.post(
        "/proposal-preview/drive-file",
        data={"file_id": "picked-file-123", "access_token": "ephemeral-google-token"},
    )

    assert response.status_code == 200
    assert seen == {"file_id": "picked-file-123", "access_token": "ephemeral-google-token"}
    assert response.json["file"]["name"] == "作品證明.pdf"
    assert b"ephemeral-google-token" not in response.data


def test_drive_file_endpoint_is_disabled_without_oauth_configuration():
    response = preview_app().test_client().post(
        "/proposal-preview/drive-file",
        data={"file_id": "picked-file-123", "access_token": "ephemeral-google-token"},
    )

    assert response.status_code == 503
    assert "尚未設定" in response.json["error"]


def test_drive_file_endpoint_requires_csrf_token_outside_test_mode():
    app = preview_app(TESTING=False, CSRF_ENABLED=True)
    client = app.test_client()
    page = client.get("/proposal-preview")
    assert page.status_code == 200

    rejected = client.post(
        "/proposal-preview/drive-file",
        data={"file_id": "picked-file-123", "access_token": "ephemeral-google-token"},
    )

    assert rejected.status_code == 400
