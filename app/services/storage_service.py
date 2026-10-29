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
DELETED_SUFFIX = ".deleted.json"

_FILE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_STORED_NAME_RE = re.compile(r"^[^/\\:*?\"<>|]{1,255}$")


class StorageUnavailable(RuntimeError):
    """檔案拿不到（雲端沒連線、檔案不見）。訊息是給學生看的中文；OCR 佇列會直接顯示。"""


class DriveError(Exception):
    """Google 這一步沒成功；訊息給開發者看。"""


class DriveAuthExpired(DriveError):
    """授權過期或被撤銷（401／403）。"""


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

    def clear(self):
        self._access = self._refresh = self.folder_id = None
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
        folder_id = self.folder_id
        self.set(client.refresh(self._refresh))
        self.folder_id = folder_id
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
            if error.code in (401, 403):
                raise DriveAuthExpired(f"Google 回應 {error.code}") from error
            raise DriveError(f"Google 回應 {error.code}") from error
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
        file_id = self.client.upload(token, self.holder.folder_id, stored_name, data, mime_type,
                                     {"slp_owner": str(owner_id), "slp_folder": folder or ""})
        location = f"{DRIVE_PREFIX}{file_id}/{stored_name}"
        cache = self.cache_path(location)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)
        return location

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
