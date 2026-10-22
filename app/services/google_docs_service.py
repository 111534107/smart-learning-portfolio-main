"""自傳在 Google 文件中編輯（示範版，V2 提案 D1～D6）。

原則：
1. Google 只當外部編輯工具；自傳的正式版本仍存在系統資料庫，每次取回都存成新的一版。
2. 只要 drive.file 權限：系統只能碰「自己建立的」那份文件，看不到學生 Drive 裡其他檔案。
3. 權杖只放在伺服器記憶體（TokenStore），瀏覽器 cookie 只有一個隨機編號；伺服器重啟或過期就要重新授權，不長期保存。
4. 文件格式：每段一行「## 標題 [來源 F1 F2]」，下面是內文。取回時依這個格式拆段，並重新檢查來源編號。
"""
import json
import re
import secrets
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

SCOPE = "https://www.googleapis.com/auth/drive.file"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
DOC_MIME = "application/vnd.google-apps.document"

_FILE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_HEADING_RE = re.compile(r"^##\s*(?P<title>.*?)\s*(?:\[(?P<marks>[^\]]*)\])?\s*$")
_SOURCE_RE = re.compile(r"F\d+")


class GoogleDocsError(Exception):
    """Google 這一步沒成功；訊息給開發者看，畫面上用固定的中文提示。"""


class GoogleDocsUnavailable(GoogleDocsError):
    """Google 暫時無法使用（逾時、5xx、回傳格式不對）。"""


class GoogleDocsAuthExpired(GoogleDocsError):
    """授權過期或被撤銷（401／403），要重新登入 Google。"""


def configured(config):
    return all(config.get(key) for key in
               ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REDIRECT_URI"))


def new_state():
    return secrets.token_urlsafe(24)


def authorization_url(config, state):
    """授權碼流程第一步。access_type=online：不要更新權杖，過期就重新授權。"""
    return AUTH_URL + "?" + urlencode({
        "client_id": config["GOOGLE_OAUTH_CLIENT_ID"],
        "redirect_uri": config["GOOGLE_OAUTH_REDIRECT_URI"],
        "response_type": "code",
        "scope": SCOPE,
        "state": state,
        "access_type": "online",
        "include_granted_scopes": "false",
        "prompt": "select_account",
    })


def doc_link(file_id):
    if not _FILE_ID_RE.fullmatch(file_id or ""):
        raise GoogleDocsUnavailable("Google 回傳的文件 ID 格式不對")
    return f"https://docs.google.com/document/d/{file_id}/edit"


# ---------- 權杖：只放伺服器記憶體 ----------

class TokenStore:
    """伺服器記憶體裡的權杖表：編號 → (使用者 id, 權杖, 到期時間)。cookie 只存編號。"""

    def __init__(self, clock=time.time):
        self._items = {}
        self._clock = clock

    def put(self, user_id, access_token, expires_in):
        self._drop_expired()
        ref = uuid.uuid4().hex
        lifetime = max(60, min(int(expires_in or 3600), 3600))
        self._items[ref] = (user_id, access_token, self._clock() + lifetime - 30)
        return ref

    def get(self, ref, user_id):
        item = self._items.get(ref or "")
        if not item:
            return None
        owner, token, expires_at = item
        if owner != user_id or expires_at <= self._clock():
            self._items.pop(ref, None)
            return None
        return token

    def drop(self, ref):
        self._items.pop(ref or "", None)

    def _drop_expired(self):
        now = self._clock()
        for ref in [r for r, (_, _, expires_at) in self._items.items() if expires_at <= now]:
            self._items.pop(ref, None)


def token_store(app):
    return app.extensions.setdefault("google_docs_tokens", TokenStore())


# ---------- 文件內容：草稿 ⇄ 純文字 ----------

def document_text(program_label, version, paragraphs):
    lines = [
        f"自傳草稿｜{program_label}（系統第 {version} 版）",
        "說明：每段第一行「## 標題 [來源 F1 F2]」請保留；方括號裡是這段引用的資料編號，可以刪減，但不要自己編新的。",
        "改完後回到系統按「從 Google 文件取回」，系統會存成新的一版並重新檢查來源。",
        "",
    ]
    for paragraph in paragraphs:
        marks = " ".join(paragraph.get("sources", []))
        lines.append(f"## {paragraph.get('title', '')} [{'來源 ' + marks if marks else ''}]")
        lines.append(paragraph.get("text", ""))
        lines.append("")
    return "\n".join(lines)


def parse_document_text(text):
    """把匯出的純文字拆回段落；第一個「## 」之前的說明文字不要。"""
    text = (text or "").replace("﻿", "").replace("\r\n", "\n").replace("\r", "\n")
    paragraphs, current = [], None
    for line in text.split("\n"):
        match = _HEADING_RE.match(line.strip()) if line.strip().startswith("##") else None
        if match:
            current = {"title": match.group("title").strip()[:30], "sources": _SOURCE_RE.findall(match.group("marks") or ""),
                       "lines": []}
            paragraphs.append(current)
        elif current is not None:
            current["lines"].append(line.rstrip())
    return [{"title": p["title"], "text": "\n".join(p["lines"]).strip(), "sources": list(dict.fromkeys(p["sources"]))}
            for p in paragraphs]


def check_sources(paragraphs, facts):
    """沿用自傳的 evidence 檢查：來源編號必須是這份草稿的事實清單裡有、而且有 evidence_id 的；其他標成不存在。"""
    known = {fact["id"] for fact in facts if fact.get("evidence_id")}
    checked = []
    for paragraph in paragraphs:
        item = {"title": paragraph["title"], "text": paragraph["text"],
                "sources": [s for s in paragraph["sources"] if s in known]}
        unknown = [s for s in paragraph["sources"] if s not in known]
        if unknown:
            item["unknown_sources"] = unknown
        checked.append(item)
    return checked


# ---------- 真的 Google（只在正式執行時用；測試一律換成替身） ----------

class HttpGoogleDocsClient:
    """用標準函式庫呼叫 Google OAuth 與 Drive v3；權杖只在每次呼叫時放進標頭。"""

    def __init__(self, config, timeout=10):
        self._config = config
        self._timeout = timeout

    def exchange_code(self, code):
        body = urlencode({
            "code": code,
            "client_id": self._config["GOOGLE_OAUTH_CLIENT_ID"],
            "client_secret": self._config["GOOGLE_OAUTH_CLIENT_SECRET"],
            "redirect_uri": self._config["GOOGLE_OAUTH_REDIRECT_URI"],
            "grant_type": "authorization_code",
        }).encode()
        payload = self._json(Request(TOKEN_URL, data=body, method="POST",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"}))
        if not isinstance(payload.get("access_token"), str):
            raise GoogleDocsUnavailable("Google 沒有回傳權杖")
        if SCOPE not in str(payload.get("scope", SCOPE)).split():
            raise GoogleDocsAuthExpired("使用者沒有同意 drive.file")
        return {"access_token": payload["access_token"], "expires_in": payload.get("expires_in", 3600)}

    def create_document(self, access_token, title, text):
        """上傳純文字並要求轉成 Google 文件，放在學生 My Drive 根目錄。"""
        boundary = "autobiography-" + uuid.uuid4().hex
        metadata = json.dumps({"name": title, "mimeType": DOC_MIME}, ensure_ascii=False)
        body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{metadata}\r\n"
                f"--{boundary}\r\nContent-Type: text/plain; charset=UTF-8\r\n\r\n{text}\r\n--{boundary}--\r\n").encode()
        payload = self._json(Request(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id", data=body, method="POST",
            headers=self._auth(access_token, f"multipart/related; boundary={boundary}")))
        file_id = payload.get("id")
        doc_link(file_id)
        return file_id

    def export_text(self, access_token, file_id):
        doc_link(file_id)
        url = (f"https://www.googleapis.com/drive/v3/files/{quote(file_id, safe='')}/export?"
               + urlencode({"mimeType": "text/plain"}))
        return self._read(Request(url, method="GET", headers=self._auth(access_token))).decode("utf-8")

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
                raise GoogleDocsAuthExpired(f"Google 回應 {error.code}") from error
            raise GoogleDocsUnavailable(f"Google 回應 {error.code}") from error
        except (URLError, TimeoutError, OSError) as error:
            raise GoogleDocsUnavailable("連不上 Google") from error

    def _json(self, request):
        try:
            payload = json.loads(self._read(request).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GoogleDocsUnavailable("Google 回傳格式不對") from error
        if not isinstance(payload, dict):
            raise GoogleDocsUnavailable("Google 回傳格式不對")
        return payload


def client_for(app):
    """測試在設定裡放 GOOGLE_DOCS_CLIENT 替身；沒有就用真的 HTTP 用戶端。"""
    return app.config.get("GOOGLE_DOCS_CLIENT") or HttpGoogleDocsClient(app.config)
