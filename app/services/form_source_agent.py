"""表單代理（2026-11-13 使用者決定）：自己到學校官網、資管科官網抓表單，放進表單下載區，科辦不用手動上傳。

流程：
1. 科辦按「從學校網站更新表單」→ 依 SOURCES 逐一讀學校網站的表單頁。
2. 找出每份表單與檔案（同一份有 PDF、Word、ODT 時優先 PDF），下載回系統存成一版。
3. 新表單建立成「待核准上架」，主任或副主任核准後學生、老師才看得到。
   已核准過的表單，學校網站換了新檔案就自動新增一版（同一個官方來源的最新版），並記操作紀錄。
4. 抓不到的來源、下載失敗的檔案都列在結果裡給科辦看，不會讓整批中斷。

安全：只連 SOURCES 裡的學校網域（*.ukn.edu.tw），轉址到其他網域就不跟；每次連線有逾時與大小上限；
只讀公開網頁，不登入、不送出任何學生資料。
"""
import hashlib
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser

from app.extensions import db
from app.models import FormCategory, FormItem
from app.services import form_library_service

ALLOWED_HOST = re.compile(r"(^|\.)ukn\.edu\.tw$", re.I)
TIMEOUT_SECONDS = 15
MAX_PAGE_BYTES = 2 * 1024 * 1024
USER_AGENT = "ukn-im-form-agent/1.0 (school project; public pages only)"
FILE_EXT = re.compile(r"\.(pdf|docx?|xlsx?|odt|ods)(?:$|\?)", re.I)
PREFERRED = ("pdf", "docx", "doc", "odt", "xlsx", "xls", "ods")
ROW_TAGS = ("tr", "li", "p")
# 學校網站的附件常走下載程式（/app/index.php?Action=downloadfile&…），副檔名只出現在連結文字
DOWNLOAD_SCRIPT = re.compile(r"Action=downloadfile", re.I)


@dataclass
class Source:
    """一個學校網站上的表單頁。layout：items＝列表頁連到每份表單的頁面；table＝列表頁直接列檔案。"""
    key: str
    office: str
    category: str
    url: str
    layout: str
    students: bool = True
    teachers: bool = True


# 2026-11-13 實際查過的頁面（學校網站改版時改這裡）
SOURCES = [
    Source("im-internship", "資管科", "實習", "https://im.ukn.edu.tw/p/412-1028-1193.php?Lang=zh-tw", "items"),
    Source("im-project", "資管科", "專題", "https://im.ukn.edu.tw/p/412-1028-1194.php?Lang=zh-tw", "items"),
    Source("im-rules", "資管科", "相關法規", "https://im.ukn.edu.tw/p/412-1028-1209.php?Lang=zh-tw", "items"),
    Source("sa-life", "學務處生活輔導組", "常用表格", "https://ukn05.ukn.edu.tw/p/412-1003-3494.php?Lang=zh-tw", "table"),
]


@dataclass
class FoundForm:
    source: Source
    title: str
    page_url: str
    files: list = field(default_factory=list)  # [(副檔名, 網址)]

    @property
    def best_file(self):
        return min(self.files, key=lambda f: PREFERRED.index(f[0]) if f[0] in PREFERRED else 99) if self.files else None


class _Links(HTMLParser):
    """收集 <a> 的網址、文字，以及它所在的表格列（tr）、清單項目（li）或段落（p）的整段文字。
    學務處的表單頁是一段一份（<p>學生公假申請書 (<a>PDF</a>)</p>），資管科是表格或清單。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self._open, self._containers, self._anchor, self.title, self._in_title = [], [], [], None, "", False

    def handle_starttag(self, tag, attrs):
        if tag in ROW_TAGS:
            self._containers.append([])
            self._open.append(len(self._containers) - 1)
        elif tag == "a":
            self._anchor = {"href": dict(attrs).get("href") or "", "text": [],
                            "container": self._open[-1] if self._open else None}
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in ROW_TAGS and self._open:
            self._open.pop()
        elif tag == "a" and self._anchor is not None:
            self.links.append(self._anchor)
            self._anchor = None
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._anchor is not None:
            self._anchor["text"].append(data)
        for index in self._open:
            self._containers[index].append(data)

    def results(self):
        clean = lambda parts: re.sub(r"\s+", " ", "".join(parts)).strip()
        return [{"href": unescape(link["href"]), "text": clean(link["text"]),
                 "row": clean(self._containers[link["container"]]) if link["container"] is not None else ""}
                for link in self.links]


def parse_links(html):
    parser = _Links()
    parser.feed(html)
    return parser.results(), re.sub(r"\s+", " ", parser.title).strip()


def _allowed(url):
    parts = urllib.parse.urlsplit(url)
    return parts.scheme in ("http", "https") and bool(parts.hostname) and bool(ALLOWED_HOST.search(parts.hostname))


class _SchoolOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _allowed(newurl):
            raise urllib.error.HTTPError(newurl, code, "轉址到學校以外的網站", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, limit=MAX_PAGE_BYTES):
    """實際連線（測試時換成假物件）：回傳 bytes；不是學校網域、太大或連不上丟 OSError。"""
    if not _allowed(url):
        raise OSError("只抓學校網站（ukn.edu.tw）")
    quoted = urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%")
    request = urllib.request.Request(quoted, headers={"User-Agent": USER_AGENT})
    with urllib.request.build_opener(_SchoolOnlyRedirect()).open(request, timeout=TIMEOUT_SECONDS) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise OSError("檔案太大")
    return data


def _title_from_row(row):
    """「學生公假申請書 (PDF)」「班級座次表 (PDF) (DOC)」→ 拿掉格式標記與編號。"""
    text = re.sub(r"[\(（]\s*(PDF|DOCX?|ODT|XLSX?|ODS)\s*[\)）]", " ", row, flags=re.I)
    text = re.sub(r"\b(PDF|DOCX?|ODT)\b", " ", text, flags=re.I)
    text = re.sub(r"^\s*\d{1,2}\s*[\.、]\s*", "", text)
    return re.sub(r"\s+", " ", text).strip(" -｜|")[:100]


def _file_ext(link, url):
    """連結是不是檔案：網址本身是 .pdf 等，或是學校下載程式而連結文字以 .pdf 等結尾。回傳副檔名或 None。"""
    match = FILE_EXT.search(urllib.parse.urlsplit(url).path)
    if match:
        return match.group(1).lower()
    if DOWNLOAD_SCRIPT.search(url):
        match = re.search(r"\.(pdf|docx?|xlsx?|odt|ods)\s*$", link["text"], re.I)
        return match.group(1).lower() if match else None
    return None


def _files_on(links, base):
    files = []
    for link in links:
        url = urllib.parse.urljoin(base, link["href"])
        ext = _file_ext(link, url)
        if ext and _allowed(url) and url not in [f[1] for f in files]:
            files.append((ext, url))
    return files


def discover(source, fetcher=None):
    """讀一個來源，回傳 [FoundForm]。"""
    fetcher = fetcher or fetch  # 呼叫時才取，測試替換 fetch 才會生效
    html = fetcher(source.url).decode("utf-8", "replace")
    links, _ = parse_links(html)
    found = {}
    if source.layout == "table":
        for link in links:
            url = urllib.parse.urljoin(source.url, link["href"])
            ext = _file_ext(link, url)
            title = _title_from_row(link["row"] or link["text"])
            if not ext or not _allowed(url) or not title:
                continue
            form = found.setdefault(title, FoundForm(source, title, source.url))
            if url not in [f[1] for f in form.files]:
                form.files.append((ext, url))
        return list(found.values())
    # items：列表頁 → 每份表單一頁（RPAGE 的 /p/405-… 網址）
    pages = []
    for link in links:
        url = urllib.parse.urljoin(source.url, link["href"])
        if re.search(r"/p/405-\d+-\d+,c\d+\.php", url) and _allowed(url) and link["text"] and url not in [p[1] for p in pages]:
            pages.append((_title_from_row(link["text"]), url))
    forms = []
    for title, url in pages:
        page_links, page_title = parse_links(fetcher(url).decode("utf-8", "replace"))
        files = _files_on(page_links, url)
        forms.append(FoundForm(source, _title_from_row(title or page_title), url, files))
    return forms


def _category(name):
    category = FormCategory.query.filter_by(name=name).first()
    if not category:
        last = db.session.query(db.func.max(FormCategory.sort_order)).scalar() or 0
        category = FormCategory(name=name, sort_order=last + 10, is_active=True)
        db.session.add(category)
        db.session.flush()
    return category


def _filename(form, ext):
    return f"{form.title}.{ext}"


def sync(staff, fetcher=None, sources=None):
    """抓全部來源並寫進表單下載區（不 commit）。回傳結果摘要給科辦看。"""
    summary = {"new": [], "updated": [], "unchanged": 0, "errors": []}
    fetcher = fetcher or fetch
    for source in sources or SOURCES:
        try:
            forms = discover(source, fetcher)
        except Exception as error:  # 單一來源失敗不影響其他來源
            summary["errors"].append(f"{source.office}「{source.category}」頁面讀不到（{type(error).__name__}）")
            continue
        for form in forms:
            best = form.best_file
            if not best:
                summary["errors"].append(f"「{form.title}」找不到可下載的檔案")
                continue
            ext, url = best
            try:
                data = fetcher(url, form_library_service.max_bytes())
            except Exception as error:
                summary["errors"].append(f"「{form.title}」下載失敗（{type(error).__name__}）")
                continue
            item = FormItem.query.filter_by(origin="agent", title=form.title).first()
            try:
                if item is None:
                    item = FormItem(category=_category(source.category), title=form.title,
                                    description=f"來源：{source.office}網站（系統自動抓取）",
                                    open_to_students=source.students, open_to_teachers=source.teachers,
                                    is_published=False, origin="agent", created_by_id=staff.id, source_url=url)
                    db.session.add(item)
                    db.session.flush()
                    form_library_service.add_version(item, _filename(form, ext), data, staff, note=f"自動抓取：{url}")
                    summary["new"].append(form.title)
                    continue
                latest = item.latest_version
                if latest and latest.file_sha256 == hashlib.sha256(data).hexdigest():
                    summary["unchanged"] += 1
                    continue
                form_library_service.add_version(item, _filename(form, ext), data, staff, note=f"學校網站更新：{url}")
                form_library_service.set_source_url(item, url)
                summary["updated"].append(form.title)
            except form_library_service.UploadRejected as error:
                summary["errors"].append(f"「{form.title}」檔案不合格：{error}")
    return summary


def approve(item, approver):
    """主任、副主任核准上架（不 commit）。"""
    item.is_published = True
    item.approved_by_id = approver.id
    item.approved_at = datetime.now(timezone.utc)


def pending_items():
    """待核准上架：沒上架、也還沒有人核准過（下架過的不算）。"""
    return (FormItem.query.filter(FormItem.is_published.is_(False), FormItem.approved_at.is_(None))
            .order_by(FormItem.created_at).all())
