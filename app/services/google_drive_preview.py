"""Google Drive 選檔展示：只讀取使用者透過 Picker 選中的單一檔案中繼資料。"""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


class GoogleDriveAuthorizationError(Exception):
    """Google 拒絕了本次檔案授權。"""


class GoogleDriveUnavailableError(Exception):
    """Google API 暫時無法使用。"""


_FILE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,512}$")
_ALLOWED_LINK_HOSTS = {"drive.google.com", "docs.google.com"}
_FIELDS = "id,name,mimeType,webViewLink"


def get_selected_file_metadata(file_id, access_token):
    """向 Drive files.get 驗證使用者選取的檔案，只索取展示所需中繼資料。

    access_token 只用於這一次 HTTPS 呼叫；不寫入應用程式 session、資料庫或日誌。
    """
    if not isinstance(file_id, str) or not _FILE_ID_RE.fullmatch(file_id):
        raise ValueError("invalid Google Drive file id")
    if (
        not isinstance(access_token, str)
        or not access_token
        or len(access_token) > 8192
        or "\r" in access_token
        or "\n" in access_token
    ):
        raise ValueError("invalid Google access token")

    url = f"https://www.googleapis.com/drive/v3/files/{quote(file_id, safe='')}?fields={quote(_FIELDS, safe=',')}"
    request = Request(
        url,
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        if error.code in (401, 403):
            raise GoogleDriveAuthorizationError from error
        raise GoogleDriveUnavailableError from error
    except (URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GoogleDriveUnavailableError from error

    if not isinstance(payload, dict) or payload.get("id") != file_id:
        raise ValueError("Google Drive returned a different file")
    name = payload.get("name")
    mime_type = payload.get("mimeType")
    if not isinstance(name, str) or not name.strip() or len(name) > 1000:
        raise ValueError("Google Drive returned an invalid file name")
    if not isinstance(mime_type, str) or not mime_type.strip():
        raise ValueError("Google Drive returned an invalid file type")
    if mime_type == "application/vnd.google-apps.folder":
        raise ValueError("folder is not a file")

    web_view_link = payload.get("webViewLink")
    if web_view_link:
        parsed = urlparse(web_view_link)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_LINK_HOSTS:
            raise ValueError("Google Drive returned an unsafe file link")
    else:
        web_view_link = None

    return {
        "id": file_id,
        "name": name,
        "mimeType": mime_type,
        "webViewLink": web_view_link,
    }
