"""表單下載區（UC-28／F-53）的規則：上傳檢查、建立新版本、誰能下載、合成示範資料。

規格：docs/superpowers/specs/2026-11-08-forms-download-design.md
- 學生只能下載「上架中＋開放學生＋分類啟用中」的表單；老師同理看「開放老師」；科辦全部都能下載。
- 改版＝新增一版，舊版保留，不能覆寫。
"""
import hashlib

from flask import current_app

from app.extensions import db
from app.models import FormCategory, FormItem, FormItemVersion
from app.security import validate_upload_filename
from app.services import storage_service

ALLOWED_EXTENSIONS = ("pdf", "doc", "docx", "xls", "xlsx", "odt", "ods")
DEFAULT_MAX_BYTES = 10 * 1024 * 1024

# 檔案開頭的特徵（簡易 MIME 檢查）：副檔名與內容對不上就不收
_PDF, _ZIP, _OLE = b"%PDF", b"PK\x03\x04", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
SIGNATURES = {"pdf": _PDF, "docx": _ZIP, "xlsx": _ZIP, "odt": _ZIP, "ods": _ZIP, "doc": _OLE, "xls": _OLE}

STAFF_ROLES = ("staff",)


class UploadRejected(ValueError):
    """上傳不合格；訊息直接顯示給科辦看。"""


def max_bytes():
    return int(current_app.config.get("FORM_MAX_BYTES", DEFAULT_MAX_BYTES))


def check_upload(filename, data):
    """回傳清理後的檔名；不合格丟 UploadRejected。"""
    try:
        safe_name = validate_upload_filename(filename, ALLOWED_EXTENSIONS)
    except ValueError:
        raise UploadRejected("檔案格式不支援，只收 PDF、Word（doc、docx）、Excel（xls、xlsx）、ODT、ODS。") from None
    if not data:
        raise UploadRejected("檔案是空的，請重新選擇。")
    limit = max_bytes()
    if len(data) > limit:
        raise UploadRejected(f"檔案太大，單檔上限 {limit / 1024 / 1024:g} MB。")
    extension = safe_name.rsplit(".", 1)[-1].lower()
    if not data.startswith(SIGNATURES[extension]):
        raise UploadRejected("檔案內容和副檔名不符，請確認是原始的 PDF、Word、Excel 或 ODF 檔。")
    return safe_name


def add_version(item, filename, data, uploader, note=""):
    """檢查並存檔，新增下一版（不 commit）。"""
    safe_name = check_upload(filename, data)
    location = storage_service.save(data, owner_id=uploader.id, folder="forms", filename=safe_name)
    current = db.session.query(db.func.max(FormItemVersion.version_no)).filter_by(item_id=item.id).scalar() or 0
    version = FormItemVersion(
        item=item, version_no=current + 1, file_path=location,
        # 下載時用的檔名：保留原檔名的中文，只拿掉路徑
        original_filename=filename.replace("\\", "/").rsplit("/", 1)[-1][:255],
        file_size=len(data), file_sha256=hashlib.sha256(data).hexdigest(),
        note=(note or "").strip()[:200] or None, uploaded_by_id=uploader.id,
    )
    db.session.add(version)
    db.session.flush()
    db.session.expire(item, ["versions"])
    return version


def can_download(user, item):
    if not user or not item:
        return False
    if user.role in STAFF_ROLES:
        return True
    if not item.is_published or not item.category.is_active or not item.latest_version:
        return False
    if user.role == "student":
        return item.open_to_students
    if user.role == "teacher":
        return item.open_to_teachers
    return False


def visible_items(user, q=""):
    """回傳 [(分類, [表單…]), …]，只有使用者能下載的；空分類不列。"""
    keyword = (q or "").strip()
    groups = []
    categories = FormCategory.query.filter_by(is_active=True).order_by(FormCategory.sort_order, FormCategory.name)
    for category in categories:
        items = [item for item in category.items if can_download(user, item)]
        if keyword:
            items = [item for item in items if keyword in item.title or keyword in (item.description or "")]
        if items:
            groups.append((category, items))
    return groups


# ---------- 合成示範資料 ----------

def demo_pdf(text):
    """產生一個極小、可開啟的 PDF，內容只有一行英文說明（合成示範檔，不是學校正式表單）。"""
    line = f"Synthetic demo form - not an official school document. {text}".encode("ascii", "replace")
    line = line.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
    stream = b"BT /F1 12 Tf 40 780 Td (" + line + b") Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


# (分類, 名稱, 說明, 開放學生, 開放老師, 上架中, 版本數)
DEMO_FORMS = [
    ("實習", "校外實習申請表", "到校外實習前填寫，送實習輔導老師簽名。", True, True, True, 2),
    ("實習", "實習週誌", "實習期間每週填寫一次。", True, False, True, 1),
    ("實習", "實習訪視紀錄表", "老師訪視實習機構時填寫。", False, True, True, 1),
    ("專題", "專題指導老師同意書", "確定專題組員與指導老師後繳交。", True, True, True, 1),
    ("專題", "專題成果發表報名表", "期末發表前兩週報名。", True, False, True, 1),
    ("常用表格", "學生請假單", "請假三天以上要附證明。", True, False, True, 1),
    ("常用表格", "公假申請單", "參加校外競賽或活動前申請。", True, True, True, 1),
    ("常用表格", "舊版加退選單（已停用）", "已改用線上加退選，保留作為紀錄。", True, False, False, 1),
    ("相關法規", "資管科專題實施要點", "專題分組、時程與評分方式。", True, True, True, 1),
]


def seed_demo_forms(staff_user):
    """展示站用：4 個分類、9 份合成表單（含一份第 2 版、一份只開放老師、一份已下架）。不 commit。"""
    categories = {}
    for order, name in enumerate(("實習", "專題", "常用表格", "相關法規"), start=1):
        categories[name] = FormCategory(name=name, sort_order=order * 10, is_active=True)
        db.session.add(categories[name])
    db.session.flush()
    for number, (category, title, description, students, teachers, published, version_count) in enumerate(
            DEMO_FORMS, start=1):
        item = FormItem(category=categories[category], title=title, description=description,
                        open_to_students=students, open_to_teachers=teachers, is_published=published,
                        created_by_id=staff_user.id)
        db.session.add(item)
        db.session.flush()
        for version_no in range(1, version_count + 1):
            add_version(item, f"demo-form-{number:02d}.pdf", demo_pdf(f"Form {number:02d}, version {version_no}."),
                        staff_user, note="合成示範檔" if version_no == 1 else "示範改版")
