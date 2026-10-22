"""公開的新構想展示頁與本機 Google Drive 選檔驗證流程。"""
from flask import Blueprint, current_app, jsonify, render_template, request

from app.services.google_drive_preview import (
    GoogleDriveAuthorizationError,
    GoogleDriveUnavailableError,
    get_selected_file_metadata,
)


proposal_preview_bp = Blueprint("proposal_preview", __name__)


def _drive_preview_settings():
    values = {
        "client_id": str(current_app.config.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip(),
        "picker_api_key": str(current_app.config.get("GOOGLE_PICKER_API_KEY") or "").strip(),
        "project_number": str(current_app.config.get("GOOGLE_CLOUD_PROJECT_NUMBER") or "").strip(),
    }
    enabled = (
        current_app.config.get("FLASK_ENV") != "production"
        and current_app.config.get("GOOGLE_DRIVE_PREVIEW_ENABLED", False)
        and all(values.values())
    )
    return values, bool(enabled)


@proposal_preview_bp.get("/proposal-preview")
def proposal_preview():
    settings, drive_enabled = _drive_preview_settings()
    return render_template(
        "proposal_preview.html",
        drive_enabled=drive_enabled,
        google_client_id=settings["client_id"] if drive_enabled else "",
        google_picker_api_key=settings["picker_api_key"] if drive_enabled else "",
        google_project_number=settings["project_number"] if drive_enabled else "",
    )


@proposal_preview_bp.post("/proposal-preview/drive-file")
def proposal_preview_drive_file():
    _settings, drive_enabled = _drive_preview_settings()
    if not drive_enabled:
        return jsonify(error="Google Drive 展示尚未設定，請先完成本機 OAuth 設定。"), 503

    file_id = request.form.get("file_id", "")
    access_token = request.form.get("access_token", "")
    try:
        selected_file = get_selected_file_metadata(file_id, access_token)
    except ValueError as error:
        return jsonify(error="Google Drive 沒有回傳可使用的檔案。"), 400
    except GoogleDriveAuthorizationError:
        return jsonify(error="Google 權限已失效或未授權此檔案，請重新選取。"), 403
    except GoogleDriveUnavailableError:
        return jsonify(error="目前無法連線 Google Drive，請稍後再試。"), 502

    return jsonify(file=selected_file)
