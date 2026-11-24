"""讀取公開作品頁：限定站台、固定連線至已檢查的公開位址，不跟隨轉址。"""
import http.client
import base64
import json
import re
import ipaddress
import socket
import ssl
import time
from html.parser import HTMLParser
from urllib.parse import urlsplit

MAX_BYTES = 250_000
ALLOWED = {"github.com", "www.canva.com", "canva.com"}

class ReadError(ValueError):
    pass

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(); self.hidden = 0; self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "svg", "noscript"}: self.hidden += 1
    def handle_endtag(self, tag):
        if tag in {"script", "style", "svg", "noscript"} and self.hidden: self.hidden -= 1
    def handle_data(self, data):
        if not self.hidden and data.strip(): self.parts.append(data.strip())

def redact_public_text(text, known=()):
    """盡量遮蓋已知身分與有明確標籤的個資，不能保證辨識所有姓名。"""
    from app.services.deidentify import redact
    text = redact(text, known)
    text = re.sub(r"(?i)(姓名|作者|負責人|聯絡人|name|author)\s*[:：]\s*[^\n,，;；]{1,40}", r"\1：[已遮蓋]", text)
    text = re.sub(r"[\u4e00-\u9fff]{2,3}[縣市][\u4e00-\u9fff0-9]{1,30}(?:路|街|巷|弄|段|號)[\u4e00-\u9fff0-9之\-]{0,20}", "[地址]", text)
    return text

def fetch(url):
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or host not in ALLOWED or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ReadError("目前只能分析 GitHub 或 Canva 的公開 HTTPS 網址。")
        path = parsed.path or "/"
        if host == "github.com":
            parts = [part for part in path.split("/") if part]
            if len(parts) < 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in parts[:2]):
                raise ReadError("請提供 GitHub 儲存庫網址。")
            host = "api.github.com"
            path = f"/repos/{parts[0]}/{parts[1].removesuffix('.git')}/readme"
        elif parsed.query:
            path += "?" + parsed.query
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        def public_address(entry):
            ip = ipaddress.ip_address(entry[4][0])
            return ip.is_global and not (ip.is_multicast or ip.is_reserved or ip.is_unspecified)
        if not addresses or any(not public_address(entry) for entry in addresses):
            raise ReadError("網址指向非公開網路，無法讀取。")
        deadline = time.monotonic() + 10
        sock = socket.create_connection((addresses[0][4][0], 443), timeout=4)
        sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
        try:
            sock.sendall((f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: PortfolioReader/1.0\r\nAccept: application/vnd.github+json,text/html,text/plain\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n").encode("ascii"))
            response = http.client.HTTPResponse(sock); response.begin()
            if response.status != 200:
                raise ReadError(f"網站回應 {response.status}，可能需要登入、拒絕存取或要求轉址。")
            if response.getheader("Content-Encoding", "identity").lower() not in ("", "identity"):
                raise ReadError("網站回傳不支援的壓縮格式。")
            kind = response.getheader("Content-Type", "").lower()
            if not ("text/html" in kind or "text/plain" in kind or (host == "api.github.com" and "application/json" in kind)):
                raise ReadError("頁面沒有可讀取的文字內容。")
            chunks = []; size = 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0: raise ReadError("讀取時間過長。")
                sock.settimeout(remaining)
                chunk = response.read1(min(8192, MAX_BYTES + 1 - size))
                if not chunk: break
                chunks.append(chunk); size += len(chunk)
                if size > MAX_BYTES: raise ReadError("頁面超過讀取大小限制。")
            text = b"".join(chunks).decode("utf-8", "replace")
            if host == "api.github.com":
                try:
                    data = json.loads(text)
                    text = base64.b64decode(data["content"], validate=False).decode("utf-8", "replace")
                except (KeyError, ValueError, TypeError):
                    raise ReadError("無法讀取儲存庫說明文件。")
            if "text/html" in kind:
                parser = TextExtractor(); parser.feed(text); text = "\n".join(parser.parts)
            text = text.strip()
            if len(text) < 50: raise ReadError("頁面沒有足夠的公開文字，可能需要登入或以圖片呈現。")
            return text[:12000]
        finally:
            sock.close()
    except ReadError: raise
    except (OSError, UnicodeError, ValueError, http.client.HTTPException) as exc:
        raise ReadError("無法安全讀取此網址，請確認連結公開且可正常開啟。") from exc

