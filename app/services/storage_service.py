"""學生上傳檔案的存放（V1 規格「檔案存放要做成可替換的」、V2 架構提案 決策 2、3）。

其他程式只拿資料庫裡的「檔案位置」字串呼叫這裡，不用知道檔案實際放在哪：
- 本機：沿用舊資料的寫法，位置就是檔案路徑（沒有前綴；也接受 local: 前綴）。
- Google 雲端硬碟：位置是 drive:<檔案 ID>/<存檔名稱>；存檔名稱只用來決定本機快取的副檔名。

原則：
1. 預設本機。STORAGE_BACKEND=google_drive 而且管理員已連上 Google 才存到 Drive；
   沒設定、沒連線或上傳失敗一律改存本機，畫面不會壞。
2. 只要 drive.file 權限：系統只碰自己建立的檔案，看不到那個帳號 Drive 裡其他檔案。
3. 權杖只放伺服器記憶體（TokenHolder），伺服器重開就要請管理員重新連線。
4. 讀 Drive 的檔案會留一份本機快取（instance/uploads/drive-cache），OCR、預覽、裁切都讀快取。
5. 刪除只標記（本機寫旁邊的 .deleted.json；Drive 寫 appProperties），不直接永久刪除；
   依學校政策到期才清除（還沒做）。資料庫沒存進去的孤兒檔才丟掉（本機刪除、Drive 移到垃圾桶）。
"""
import json
import mimetypes
import re
import secrets
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from flask import current_app

from app.services.google_docs_service import AUTH_URL, SCOPE, TOKEN_URL

DRIVE_PREFIX = "drive:"
LOCAL_PREFIX = "local:"
CACHE_FOLDER = "drive-cache"
FOLDER_NAME = "智慧學習歷程系統上傳檔"
FOLDER_MIME = "application/vnd.google-apps.folder"
# 每位學生在學校雲端有自己的資料夾（11-13）：「<學號>_<姓名>」，底下依種類再分，
# 要整包拿走時在 Google 雲端硬碟對學生資料夾按「下載」就會壓縮成一個檔。
SUBFOLDER_LABELS = {"learning-profile": "成績單與證照", "": "經歷佐證", "autobiography": "自傳"}
DELETED_SUFFIX = ".deleted.json"

_FILE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_STORED_NAME_RE = re.compile(r"^[^/\\:*?\"<>|]{1,255}$")


class StorageUnavailable(RuntimeError):
    """檔案拿不到（雲端沒連線、檔案不見）。訊息是給學生看的中文；OCR 佇列會直接顯示。"""


class DriveError(Exception):
    """Google 這一步沒成功；訊息給開發者看。"""


class DriveAuthExpired(DriveError):
    """授權過期或被撤銷（401、invalid_grant）。"""

    user_message = "Google 授權已過期或被撤銷，請按「連上 Google 雲端硬碟」重新連線。"


class DriveCredentialError(DriveError):
    """用戶端 ID 或密鑰錯（Google 回 invalid_client／unauthorized_client）。"""

    user_message = ("Google 不認得這組用戶端 ID 或密鑰。請核對 .env 的 GOOGLE_OAUTH_CLIENT_ID、"
                    "GOOGLE_OAUTH_CLIENT_SECRET 是否從同一個 OAuth 用戶端複製、沒有多空白，改完重開網站。")


class DriveRedirectMismatch(DriveError):
    """重新導向網址和 Google Cloud 上登記的不一致。"""

    user_message = ("重新導向網址不一致：.env 的 GOOGLE_STORAGE_REDIRECT_URI 要和 Google Cloud「已授權的重新導向 URI」"
                    "逐字相同（含 http、主機、埠號、結尾路徑）。")


class DrivePermissionDenied(DriveAuthExpired):
    """權限不足（403 insufficientPermissions 等）：多半是同意畫面沒勾 drive.file，或帳號不在測試使用者名單。"""

    user_message = ("Google 回應權限不足。請確認同意畫面有勾選 drive.file、連線的帳號在「測試使用者」名單裡，"
                    "然後重新連線。")


class DriveApiDisabled(DriveError):
    """專案沒啟用 Google Drive API（403 accessNotConfigured）。"""

    user_message = "這個 Google Cloud 專案還沒啟用 Google Drive API。請到「API 和服務 → 程式庫」啟用後等幾分鐘再試。"


class DriveQuotaExceeded(DriveError):
    """雲端硬碟空間滿了（403 storageQuotaExceeded）。"""

    user_message = "這個 Google 帳號的雲端硬碟空間已滿，新上傳的檔案先存本機。請清出空間或改用學校帳號。"


class DriveRateLimited(DriveError):
    """短時間呼叫太多次（403／429 rateLimitExceeded）。"""

    user_message = "Google 暫時限制呼叫次數，請等一分鐘再試。"


class DriveNotFound(DriveError):
    """檔案或資料夾不存在（404），可能被人從雲端硬碟手動刪掉。"""

    user_message = "雲端上找不到這個檔案或資料夾，可能被人從 Google 雲端硬碟手動刪除或移到垃圾桶。"


DriveError.user_message = "連不上 Google 或 Google 回應異常，請稍後再試；一直失敗請看伺服器日誌。"

_TOKEN_ERRORS = {"invalid_client": DriveCredentialError, "unauthorized_client": DriveCredentialError,
                 "invalid_grant": DriveAuthExpired, "redirect_uri_mismatch": DriveRedirectMismatch}
_REASON_ERRORS = {
    "storageQuotaExceeded": DriveQuotaExceeded, "quotaExceeded": DriveQuotaExceeded,
    "userRateLimitExceeded": DriveRateLimited, "rateLimitExceeded": DriveRateLimited,
    "accessNotConfigured": DriveApiDisabled, "SERVICE_DISABLED": DriveApiDisabled,
    "insufficientPermissions": DrivePermissionDenied, "insufficientFilePermissions": DrivePermissionDenied,
    "ACCESS_TOKEN_SCOPE_INSUFFICIENT": DrivePermissionDenied, "appNotAuthorizedToFile": DrivePermissionDenied,
}


def classify_http_error(status, body):
    """把 Google 的錯誤回應（狀態碼＋JSON 內文）換成上面其中一種例外類別。內文不會被記錄或顯示。"""
    try:
        payload = json.loads(body.decode("utf-8") if isinstance(body, bytes) else (body or ""))
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        payload = {}
    payload = payload if isinstance(payload, dict) else {}
    error = payload.get("error")
    if isinstance(error, str) and error in _TOKEN_ERRORS:
        return _TOKEN_ERRORS[error]
    reasons = []
    if isinstance(error, dict):
        reasons += [item.get("reason") for item in error.get("errors") or [] if isinstance(item, dict)]
        reasons += [item.get("reason") for item in error.get("details") or [] if isinstance(item, dict)]
        reasons.append(error.get("status"))
    for reason in reasons:
        if reason in _REASON_ERRORS:
            return _REASON_ERRORS[reason]
    if status == 401:
        return DriveAuthExpired
    if status == 403:
        return DrivePermissionDenied
    if status == 404:
        return DriveNotFound
    if status == 429:
        return DriveRateLimited
    return DriveError


def explain(error):
    """給管理員看的中文說明；不是 DriveError 就用通用說法。"""
    if isinstance(error, DriveError):
        return type(error).user_message
    if isinstance(error, StorageUnavailable):
        return str(error)
    return DriveError.user_message


UNAVAILABLE_MESSAGE = "雲端檔案暫時拿不到，請稍後再試；如果一直這樣，請通知系統管理員重新連結 Google 雲端硬碟。"


def configured(config):
    return all(config.get(key) for key in
               ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_STORAGE_REDIRECT_URI"))


def wants_drive(config):
    return (config.get("STORAGE_BACKEND") or "local").strip().lower() == "google_drive"


# ---------- 權杖：只放伺服器記憶體 ----------

class TokenHolder:
    """整個系統共用一組 Drive 權杖（管理員連線的帳號）；背景 OCR 也用得到。只放記憶體。"""

    def __init__(self, clock=time.time):
        self._clock = clock
        self.clear()

    def set(self, token):
        self._access = token["access_token"]
        self._expires_at = self._clock() + max(60, int(token.get("expires_in") or 3600)) - 30
        self._refresh = token.get("refresh_token") or self._refresh
        self.folder_id = None
        self.child_folders = {}

    def clear(self):
        self.last_error = None  # 最近一次存雲端失敗：{"at": 時間, "message": 中文說明}；只給管理員頁看
        self._access = self._refresh = self.folder_id = None
        self.child_folders = {}  # (上層資料夾, 用途) → 資料夾編號；換帳號或重新連線就清掉
        self._expires_at = 0

    @property
    def connected(self):
        return bool(self._refresh or (self._access and self._expires_at > self._clock()))

    def access_token(self, client):
        if self._access and self._expires_at > self._clock():
            return self._access
        if not self._refresh:
            self._access = None
            return None
        folder_id, child_folders = self.folder_id, self.child_folders
        self.set(client.refresh(self._refresh))
        self.folder_id, self.child_folders = folder_id, child_folders
        return self._access


def token_holder(app):
    return app.extensions.setdefault("google_storage_token", TokenHolder())


def new_state():
    return secrets.token_urlsafe(24)


def authorization_url(config, state):
    """access_type=offline：更新權杖也只放記憶體，讓伺服器開著的期間背景 OCR 不會斷線。"""
    return AUTH_URL + "?" + urlencode({
        "client_id": config["GOOGLE_OAUTH_CLIENT_ID"],
        "redirect_uri": config["GOOGLE_STORAGE_REDIRECT_URI"],
        "response_type": "code",
        "scope": SCOPE,
        "state": state,
        "access_type": "offline",
        "include_granted_scopes": "false",
        "prompt": "consent",
    })


# ---------- 真的 Google（只在正式執行時用；測試一律換成替身） ----------

class HttpDriveClient:
    """用標準函式庫呼叫 Google OAuth 與 Drive v3；權杖只在每次呼叫時放進標頭。"""

    API = "https://www.googleapis.com/drive/v3/files"
    UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"

    def __init__(self, config, timeout=20):
        self._config = config
        self._timeout = timeout

    def exchange_code(self, code):
        payload = self._token_request({"code": code, "redirect_uri": self._config["GOOGLE_STORAGE_REDIRECT_URI"],
                                       "grant_type": "authorization_code"})
        if SCOPE not in str(payload.get("scope", SCOPE)).split():
            raise DriveAuthExpired("使用者沒有同意 drive.file")
        return payload

    def refresh(self, refresh_token):
        return self._token_request({"refresh_token": refresh_token, "grant_type": "refresh_token"})

    def ensure_folder(self, access_token, name):
        """找系統之前建的資料夾（drive.file 只看得到自己建的），沒有就建一個。"""
        query = f"mimeType='{FOLDER_MIME}' and appProperties has {{ key='slp_role' and value='upload_root' }} and trashed=false"
        found = self._json(Request(f"{self.API}?" + urlencode({"q": query, "fields": "files(id)", "pageSize": 1}),
                                   headers=self._auth(access_token)))
        files = found.get("files") or []
        if files:
            return self._file_id(files[0].get("id"))
        body = json.dumps({"name": name, "mimeType": FOLDER_MIME, "appProperties": {"slp_role": "upload_root"}},
                          ensure_ascii=False).encode()
        created = self._json(Request(f"{self.API}?fields=id", data=body, method="POST",
                                     headers=self._auth(access_token, "application/json; charset=UTF-8")))
        return self._file_id(created.get("id"))

    def ensure_child_folder(self, access_token, parent_id, name, app_properties):
        """在 parent_id 底下找系統之前建的子資料夾（用 appProperties 認，不靠名稱），沒有就建一個。"""
        conditions = [f"mimeType='{FOLDER_MIME}'", f"'{self._file_id(parent_id)}' in parents", "trashed=false"]
        for key, value in sorted(app_properties.items()):
            if not re.fullmatch(r"[A-Za-z0-9_-]{0,64}", str(value)) or not re.fullmatch(r"[a-z_]{1,32}", key):
                raise DriveError("資料夾屬性格式不對")
            conditions.append(f"appProperties has {{ key='{key}' and value='{value}' }}")
        found = self._json(Request(f"{self.API}?" + urlencode({"q": " and ".join(conditions), "fields": "files(id)",
                                                               "pageSize": 1}), headers=self._auth(access_token)))
        files = found.get("files") or []
        if files:
            return self._file_id(files[0].get("id"))
        body = json.dumps({"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id],
                           "appProperties": app_properties}, ensure_ascii=False).encode()
        created = self._json(Request(f"{self.API}?fields=id", data=body, method="POST",
                                     headers=self._auth(access_token, "application/json; charset=UTF-8")))
        return self._file_id(created.get("id"))

    def upload(self, access_token, folder_id, name, data, mime_type, app_properties):
        boundary = "slp-" + uuid.uuid4().hex
        metadata = json.dumps({"name": name, "parents": [folder_id], "appProperties": app_properties},
                              ensure_ascii=False).encode()
        body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode() + metadata
                + f"\r\n--{boundary}\r\nContent-Type: {mime_type}\r\n\r\n".encode() + data
                + f"\r\n--{boundary}--\r\n".encode())
        payload = self._json(Request(f"{self.UPLOAD}?uploadType=multipart&fields=id", data=body, method="POST",
                                     headers=self._auth(access_token, f"multipart/related; boundary={boundary}")))
        return self._file_id(payload.get("id"))

    def download(self, access_token, file_id):
        return self._read(Request(f"{self.API}/{quote(self._file_id(file_id), safe='')}?alt=media",
                                  headers=self._auth(access_token)))

    def set_app_properties(self, access_token, file_id, app_properties):
        body = json.dumps({"appProperties": app_properties}).encode()
        self._json(Request(f"{self.API}/{quote(self._file_id(file_id), safe='')}?fields=id", data=body,
                           method="PATCH", headers=self._auth(access_token, "application/json")))

    def trash(self, access_token, file_id):
        body = json.dumps({"trashed": True}).encode()
        self._json(Request(f"{self.API}/{quote(self._file_id(file_id), safe='')}?fields=id", data=body,
                           method="PATCH", headers=self._auth(access_token, "application/json")))

    def about(self, access_token):
        """測試連線用：連上的是哪個帳號、空間用了多少。drive.file 權限就能讀。"""
        return self._json(Request("https://www.googleapis.com/drive/v3/about?fields=user(emailAddress),storageQuota",
                                  headers=self._auth(access_token)))

    def _token_request(self, fields):
        body = urlencode({**fields, "client_id": self._config["GOOGLE_OAUTH_CLIENT_ID"],
                          "client_secret": self._config["GOOGLE_OAUTH_CLIENT_SECRET"]}).encode()
        payload = self._json(Request(TOKEN_URL, data=body, method="POST",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"}))
        if not isinstance(payload.get("access_token"), str):
            raise DriveError("Google 沒有回傳權杖")
        return payload

    @staticmethod
    def _file_id(file_id):
        if not isinstance(file_id, str) or not _FILE_ID_RE.fullmatch(file_id):
            raise DriveError("Google 回傳的檔案 ID 格式不對")
        return file_id

    @staticmethod
    def _auth(access_token, content_type=None):
        headers = {"Authorization": f"Bearer {access_token}"}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _read(self, request):
        try:
            with urlopen(request, timeout=self._timeout) as response:
                return response.read()
        except HTTPError as error:
            try:
                body = error.read()
            except Exception:  # 讀不到錯誤內文就只看狀態碼
                body = b""
            kind = classify_http_error(error.code, body)
            raise kind(f"Google 回應 {error.code}（{kind.__name__}）") from error
        except (URLError, TimeoutError, OSError) as error:
            raise DriveError("連不上 Google") from error

    def _json(self, request):
        try:
            payload = json.loads(self._read(request).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise DriveError("Google 回傳格式不對") from error
        if not isinstance(payload, dict):
            raise DriveError("Google 回傳格式不對")
        return payload


def client_for(app):
    """測試在設定裡放 GOOGLE_STORAGE_CLIENT 替身；沒有就用真的 HTTP 用戶端。"""
    return app.config.get("GOOGLE_STORAGE_CLIENT") or HttpDriveClient(app.config)


# ---------- 兩種存放 ----------

def _stored_name(filename):
    return f"{uuid.uuid4().hex}_{filename}"


def _owner_folder_name(owner_id):
    """學生資料夾名稱：「<學號或帳號>_<姓名>」；找不到使用者時用編號。"""
    from app.extensions import db
    from app.models import User

    user = db.session.get(User, owner_id) if isinstance(owner_id, int) else None
    if user is None:
        return f"使用者{owner_id}"
    profile = getattr(user, "student_profile", None)
    account = (profile.student_no if profile and profile.student_no else None) or user.username
    return re.sub(r"[/\\:*?\"<>|\s]+", "", f"{account}_{user.display_name}") or f"使用者{owner_id}"


def _mark(reason):
    return {"deleted_at": datetime.now(timezone.utc).isoformat(), "reason": reason or "deleted"}


class LocalStorage:
    """存在伺服器本機 UPLOAD_FOLDER（現有行為）。"""

    name = "local"

    def __init__(self, root):
        self.root = Path(root)

    def save(self, data, owner_id, folder, filename):
        directory = self.root / folder / str(owner_id) if folder else self.root / str(owner_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / _stored_name(filename)
        path.write_bytes(data)
        return str(path)

    @staticmethod
    def path(location):
        return Path(location[len(LOCAL_PREFIX):] if location.startswith(LOCAL_PREFIX) else location)

    def cache_path(self, location):
        return self.path(location)

    def local_path(self, location):
        path = self.path(location)
        if not path.is_file():
            raise StorageUnavailable("找不到原始檔案，請重新上傳。")
        return path

    def mark_deleted(self, location, reason):
        path = self.path(location)
        if path.is_file():
            Path(str(path) + DELETED_SUFFIX).write_text(json.dumps(_mark(reason), ensure_ascii=False), encoding="utf-8")

    def is_marked_deleted(self, location):
        return Path(str(self.path(location)) + DELETED_SUFFIX).is_file()

    def discard(self, location):
        self.path(location).unlink(missing_ok=True)


class GoogleDriveStorage:
    """存在 Google 雲端硬碟（系統建立的資料夾），本機只留快取。"""

    name = "google_drive"

    def __init__(self, holder, client, cache_root):
        self.holder = holder
        self.client = client
        self.cache_root = Path(cache_root)

    def _token(self):
        token = self.holder.access_token(self.client)
        if not token:
            raise StorageUnavailable(UNAVAILABLE_MESSAGE)
        return token

    def save(self, data, owner_id, folder, filename):
        token = self._token()
        if not self.holder.folder_id:
            self.holder.folder_id = self.client.ensure_folder(token, FOLDER_NAME)
        stored_name = _stored_name(filename)
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        file_id = self.client.upload(token, self._target_folder(token, owner_id, folder or ""), stored_name, data,
                                     mime_type, {"slp_owner": str(owner_id), "slp_folder": folder or ""})
        location = f"{DRIVE_PREFIX}{file_id}/{stored_name}"
        cache = self.cache_path(location)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)
        return location

    def _child(self, token, parent_id, purpose, name, app_properties):
        key = (parent_id, purpose)
        if key not in self.holder.child_folders:
            self.holder.child_folders[key] = self.client.ensure_child_folder(token, parent_id, name, app_properties)
        return self.holder.child_folders[key]

    def _target_folder(self, token, owner_id, folder):
        """這個檔案要放的資料夾：上傳檔／<學號>_<姓名>／<種類>。資料夾編號記在記憶體，不重複問 Google。"""
        if not hasattr(self.client, "ensure_child_folder"):
            return self.holder.folder_id  # 舊的用戶端替身沒有子資料夾功能：照舊放在最上層
        student_folder = self._child(token, self.holder.folder_id, f"student:{owner_id}", _owner_folder_name(owner_id),
                                     {"slp_role": "student_folder", "slp_owner": str(owner_id)})
        kind = re.sub(r"[^A-Za-z0-9_-]", "_", folder)[:64]
        return self._child(token, student_folder, f"kind:{kind}", SUBFOLDER_LABELS.get(folder, folder or "其他"),
                           {"slp_role": "kind_folder", "slp_owner": str(owner_id), "slp_folder": kind})

    @staticmethod
    def parse(location):
        file_id, _, stored_name = location[len(DRIVE_PREFIX):].partition("/")
        if (not _FILE_ID_RE.fullmatch(file_id) or not _STORED_NAME_RE.fullmatch(stored_name)
                or stored_name in {".", ".."}):
            raise StorageUnavailable("檔案位置格式不對。")
        return file_id, stored_name

    def cache_path(self, location):
        file_id, stored_name = self.parse(location)
        return self.cache_root / file_id / stored_name

    def local_path(self, location):
        path = self.cache_path(location)
        if path.is_file():
            return path
        file_id, _ = self.parse(location)
        try:
            data = self.client.download(self._token(), file_id)
        except DriveError as error:
            current_app.logger.warning("從 Google 雲端硬碟取檔失敗：%s", error)
            raise StorageUnavailable(UNAVAILABLE_MESSAGE) from error
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def mark_deleted(self, location, reason):
        file_id, _ = self.parse(location)
        mark = _mark(reason)
        self.client.set_app_properties(self._token(), file_id,
                                       {"slp_deleted_at": mark["deleted_at"], "slp_deleted_reason": mark["reason"]})
        cache = self.cache_path(location)
        if cache.is_file():
            Path(str(cache) + DELETED_SUFFIX).write_text(json.dumps(mark, ensure_ascii=False), encoding="utf-8")

    def is_marked_deleted(self, location):
        return Path(str(self.cache_path(location)) + DELETED_SUFFIX).is_file()

    def discard(self, location):
        file_id, _ = self.parse(location)
        self.client.trash(self._token(), file_id)
        self.cache_path(location).unlink(missing_ok=True)


# ---------- 給其他程式用的入口（都要在 app context 裡） ----------

def _local(app):
    return LocalStorage(app.config["UPLOAD_FOLDER"])


def _drive(app):
    return GoogleDriveStorage(token_holder(app), client_for(app), Path(app.config["UPLOAD_FOLDER"]) / CACHE_FOLDER)


def active_backend_name():
    """新上傳的檔案現在會存到哪裡：local 或 google_drive。"""
    app = current_app._get_current_object()
    if wants_drive(app.config) and configured(app.config) and token_holder(app).connected:
        return GoogleDriveStorage.name
    return LocalStorage.name


def backend_for(location):
    app = current_app._get_current_object()
    return _drive(app) if str(location).startswith(DRIVE_PREFIX) else _local(app)


def save(data, owner_id, folder, filename):
    """存檔並回傳要寫進資料庫的位置字串。Drive 不能用時改存本機。"""
    app = current_app._get_current_object()
    if active_backend_name() == GoogleDriveStorage.name:
        try:
            return _drive(app).save(data, owner_id, folder, filename)
        except (DriveError, StorageUnavailable) as error:
            app.logger.warning("存到 Google 雲端硬碟失敗，這次改存本機：%s", error)
            token_holder(app).last_error = {"at": datetime.now(timezone.utc), "message": explain(error)}
    return _local(app).save(data, owner_id, folder, filename)


def cache_path(location):
    """本機上「應該」放這個檔案的路徑（不下載）；OCR 縮圖放在它旁邊。"""
    return backend_for(location).cache_path(location)


def local_path(location):
    """確保本機有一份可以直接讀的檔案並回傳路徑；拿不到就丟 StorageUnavailable。"""
    if not location:
        raise StorageUnavailable("找不到原始檔案，請重新上傳。")
    return backend_for(location).local_path(location)


def local_path_or_none(location):
    try:
        return local_path(location)
    except StorageUnavailable:
        return None


def exists(location):
    return local_path_or_none(location) is not None


def read_bytes(location):
    return local_path(location).read_bytes()


def mark_deleted(location, reason="deleted"):
    """刪除先標記；Drive 暫時連不上時只記日誌，不擋住學生的刪除動作。"""
    if not location:
        return
    try:
        backend_for(location).mark_deleted(location, reason)
    except (DriveError, StorageUnavailable) as error:
        current_app.logger.warning("標記刪除失敗（檔案保留，之後再處理）：%s", error)


def is_marked_deleted(location):
    return bool(location) and backend_for(location).is_marked_deleted(location)


def discard(location):
    """資料庫沒存進去的孤兒檔才用；有紀錄的檔案一律用 mark_deleted。"""
    if not location:
        return
    try:
        backend_for(location).discard(location)
    except (DriveError, StorageUnavailable) as error:
        current_app.logger.warning("丟棄孤兒檔失敗：%s", error)


# ---------- 給管理員看的設定檢查與測試連線（不顯示任何金鑰內容） ----------

CALLBACK_PATH = "/admin/storage/google/callback"


def check_settings(config):
    """逐項檢查 .env 的雲端硬碟設定，回傳 [{"label", "ok", "hint"}]。只看格式，不連網路、不回傳金鑰。"""
    from urllib.parse import urlparse

    backend = (config.get("STORAGE_BACKEND") or "local").strip().lower()
    client_id = (config.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
    raw_secret = config.get("GOOGLE_OAUTH_CLIENT_SECRET") or ""
    secret_ok = bool(raw_secret.strip()) and raw_secret == raw_secret.strip()
    redirect = (config.get("GOOGLE_STORAGE_REDIRECT_URI") or "").strip()
    parsed = urlparse(redirect) if redirect else None
    checks = [
        {"label": "存放方式 STORAGE_BACKEND", "ok": backend == "google_drive",
         "hint": "已設為 google_drive。" if backend == "google_drive" else
         ("目前是 local（存本機）。要改存雲端請填 google_drive。" if backend == "local"
          else f"「{backend}」不是可用的值，只能填 local 或 google_drive。")},
        {"label": "用戶端 ID GOOGLE_OAUTH_CLIENT_ID", "ok": client_id.endswith(".apps.googleusercontent.com"),
         "hint": "格式正確。" if client_id.endswith(".apps.googleusercontent.com") else
         ("沒填。" if not client_id else "格式不像 Google 用戶端 ID（應以 .apps.googleusercontent.com 結尾）。")},
        {"label": "用戶端密鑰 GOOGLE_OAUTH_CLIENT_SECRET", "ok": secret_ok,
         "hint": "已填（不顯示內容）。" if secret_ok else ("沒填。" if not raw_secret.strip() else "前後有空白，請刪掉。")},
    ]
    if not redirect:
        redirect_ok, redirect_hint = False, "沒填。"
    elif parsed.scheme not in ("http", "https") or not parsed.netloc:
        redirect_ok, redirect_hint = False, "要是完整網址，例如 http://localhost:5019" + CALLBACK_PATH + "。"
    elif parsed.path != CALLBACK_PATH:
        redirect_ok, redirect_hint = False, f"結尾路徑要是 {CALLBACK_PATH}。"
    elif parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1"):
        redirect_ok, redirect_hint = False, "Google 只允許 localhost 用 http，其他主機要用 https。"
    else:
        redirect_ok, redirect_hint = True, f"{redirect}（要和 Google Cloud 登記的完全一樣，且用同一個主機與埠號開網站）"
    checks.append({"label": "重新導向網址 GOOGLE_STORAGE_REDIRECT_URI", "ok": redirect_ok, "hint": redirect_hint})
    return checks


def last_check(app):
    return app.extensions.get("google_storage_last_check")


def test_connection(app):
    """管理員按「測試連線」：依序檢查設定 → 權杖 → 帳號 → 系統資料夾。不上傳、不刪任何檔案。

    回傳 {"ok", "steps": [{"label","ok","message"}], "account", "quota", "at"}，同時記在記憶體給頁面顯示。
    """
    steps = []
    result = {"ok": False, "steps": steps, "account": None, "quota": None, "at": datetime.now(timezone.utc)}
    app.extensions["google_storage_last_check"] = result

    bad = [item for item in check_settings(app.config) if not item["ok"]]
    steps.append({"label": ".env 設定", "ok": not bad,
                  "message": "都填好了。" if not bad else "；".join(f"{i['label']}：{i['hint']}" for i in bad)})
    if bad:
        return result
    holder = token_holder(app)
    if not holder.connected:
        steps.append({"label": "Google 授權", "ok": False, "message": "還沒連線，請先按「連上 Google 雲端硬碟」。"})
        return result
    client = client_for(app)
    stage = "Google 授權"
    try:
        token = holder.access_token(client)
        if not token:
            raise DriveAuthExpired("沒有可用的權杖")
        steps.append({"label": stage, "ok": True, "message": "權杖有效。"})
        if hasattr(client, "about"):
            stage = "帳號與空間"
            about = client.about(token) or {}
            result["account"] = ((about.get("user") or {}).get("emailAddress")) or None
            quota = about.get("storageQuota") or {}
            if quota.get("limit"):
                used, limit = int(quota.get("usage") or 0), int(quota["limit"])
                result["quota"] = {"used": used, "limit": limit, "percent": round(used * 100 / limit, 1)}
                if result["quota"]["percent"] >= 95:
                    raise DriveQuotaExceeded("空間已用 95% 以上")
            message = f"連上的帳號：{result['account'] or '（Google 沒提供）'}"
            if result["quota"]:
                message += f"；空間已用 {result['quota']['percent']}%"
            steps.append({"label": stage, "ok": True, "message": message + "。"})
        stage = "系統資料夾"
        if not holder.folder_id:
            holder.folder_id = client.ensure_folder(token, FOLDER_NAME)
        steps.append({"label": stage, "ok": True, "message": f"「{FOLDER_NAME}」可以使用。"})
    except (DriveError, StorageUnavailable) as error:
        current_app.logger.warning("Google 雲端硬碟測試連線失敗：%s", error)
        steps.append({"label": stage, "ok": False, "message": explain(error)})
        return result
    result["ok"] = True
    return result
