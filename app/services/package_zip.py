"""備審一鍵打包（使用者 2026-11-13）：一個校系一個壓縮檔，可以下載或寄到學生自己的信箱。

壓縮檔內容（最外層一個資料夾「備審資料_校名科系」）：
- 01_備審資料.docx：和「下載 Word」同一份。
- 02_自傳_第N版.docx：該次送審的自傳，草稿打包則使用目前版本。
- 03_成績單與證照原始檔／：學生上傳、已確認的原始檔。
- 04_經歷佐證／<經歷標題>／：已確認經歷的佐證檔。
- 清單.txt：放了哪些、哪些沒放與原因；自傳提到學生選擇不放的經歷或證照時，另外提醒（自傳是學生的文字，系統不改）。

只放學生已確認的資料；學生選擇「不放進備審」的不放（簡章規定必備的類別除外，規則見 package_exclusion）。
原始成績單是整份檔案：裡面只要有一門課被選擇不放（且成績不是必備），整份就不放，免得那一科還是被看到。
草稿打包時，暫時拿不到的檔案會列在清單。送審時須能讀取所有納入的檔案，才能封存。
"""
import io
import re
import zipfile
from datetime import datetime, timedelta, timezone

from app.models import CredentialRecord, LearningCourseRecord, Portfolio, SourceDocument, User
from app.extensions import db
from app.services import autobiography_backup, autobiography_service, package_exclusion, package_export, storage_service
from app.services.package_service import draft_review_status, latest_review, render_package_docx

TAIPEI = timezone(timedelta(hours=8))
_UNSAFE = re.compile(r"[/\\:*?\"<>|\r\n\t]+")


def _safe(text, fallback="未命名"):
    return _UNSAFE.sub("_", str(text or "")).strip(" .")[:80] or fallback


def root_name(program):
    return f"備審資料_{_safe(program.school_name + program.department_name)}"


def download_name(program):
    return f"{root_name(program)}.zip"


def _kept_documents(student, required, skipped):
    """已確認、而且裡面的資料學生願意放的原始檔。"""
    documents = (SourceDocument.query.filter_by(owner_id=student.id, status="confirmed")
                 .order_by(SourceDocument.id).all())
    kept = []
    for document in documents:
        if document.document_type == "transcript":
            rows = LearningCourseRecord.query.filter_by(student_id=student.id, source_document_id=document.id,
                                                        confirmation_status="confirmed").all()
            hidden = len(rows) - len(package_exclusion.keep_courses(rows, required))
        else:
            rows = CredentialRecord.query.filter_by(student_id=student.id, source_document_id=document.id,
                                                    confirmation_status="confirmed").all()
            hidden = len(rows) - len(package_exclusion.keep_credentials(rows, required))
        if not rows:
            continue  # 這份檔案沒有任何已確認的資料
        if hidden:
            skipped.append(f"{document.display_name}：裡面有你選擇不放進備審的資料，原始檔沒有放")
            continue
        kept.append(document)
    return kept


def _excluded_mentions(student, required, content):
    """自傳裡提到、但學生選擇不放進備審的經歷與證照名稱（B24 2026-11-16 實測）。"""
    text = "\n".join(paragraph.get("text", "") for paragraph in content.get("paragraphs", []))
    portfolios = Portfolio.active().filter_by(student_id=student.id, status="confirmed").all()
    credentials = CredentialRecord.query.filter_by(student_id=student.id, confirmation_status="confirmed").all()
    names, kept = [], []
    for record in portfolios:
        kept_flag = package_exclusion.is_kept(record, package_exclusion.portfolio_keys(record), required)
        (kept if kept_flag else names).append(record.title)
    for record in credentials:
        (kept if package_exclusion.is_kept(record, ("credential",), required) else names).append(record.credential_name)
    # 有放的資料名稱先拿掉：排除「資料庫應用」時，自傳寫的「資料庫應用乙級」（有放）不算提到
    for name in sorted({name for name in kept if name}, key=len, reverse=True):
        text = text.replace(name, "\0")
    return [name for name in dict.fromkeys(names) if name and name in text]


def build_zip(student, program, *, review=None, draft_only=False):
    if review is None:
        review = latest_review(student, program)
    export = package_export.confirmed_export(review)
    if export and not draft_only:
        return package_export.read(student.id, export), export["manifest"]
    draft = autobiography_service.latest_draft(student, program)
    return render_zip(student, program, draft, draft_review_status(review))


def render_zip(student, program, draft, review_status):
    """回傳 (BytesIO, 清單)。清單是 {"included": [...], "skipped": [...], "notes": [...]}。"""
    required = package_exclusion.required_keys(program)
    root = root_name(program)
    included, skipped, notes, used = [], [], [], set()
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        def add(path, data, label):
            name, index = path, 1
            while name in used:  # 同名檔案加編號，不互相蓋掉
                stem, dot, extension = path.rpartition(".")
                index += 1
                name = f"{stem}_{index}.{extension}" if dot else f"{path}_{index}"
            used.add(name)
            archive.writestr(f"{root}/{name}", data)
            included.append(label)

        def add_stored(path, location, label):
            try:
                data = storage_service.read_bytes(location)
            except (OSError, storage_service.StorageUnavailable) as error:
                if review_status == "confirmed":
                    raise package_export.ExportUnavailable(
                        "有原始檔或佐證目前無法讀取，請確認附件可開啟後再送審。"
                    ) from error
                skipped.append(f"{label}：檔案暫時拿不到，沒有放")
                return
            add(path, data, label)

        add("01_備審資料.docx", render_package_docx(student, program, draft, review_status).getvalue(), "備審資料 Word")

        if draft:
            content = draft.content_json
            editor = db.session.get(User, content["editor_id"]) if content.get("editor_id") else None
            version = autobiography_service.version_of(draft)
            add(f"02_自傳_第{version}版.docx", autobiography_backup.build_docx(student, program, content, editor),
                f"自傳第 {version} 版")
            for name in _excluded_mentions(student, required, content):
                notes.append(f"自傳第 {version} 版提到「{name}」，但你選擇不把它放進備審；"
                             "自傳是你自己的文字，系統不會改，請自己決定要不要修改")
        else:
            skipped.append("自傳：還沒有草稿")

        for document in _kept_documents(student, required, skipped):
            add_stored(f"03_成績單與證照原始檔/{_safe(document.display_name)}", document.file_path,
                       f"原始檔：{document.display_name}")

        portfolios = (Portfolio.active().filter_by(student_id=student.id, status="confirmed")
                      .order_by(Portfolio.id).all())
        records = package_exclusion.keep_portfolios(portfolios, required)
        for record in portfolios:
            if record in records:
                continue
            for evidence in record.evidence_items:
                if evidence.file_path and evidence.is_available:
                    skipped.append(f"佐證：{record.title}／{evidence.display_name}：這筆經歷你選擇不放進備審，佐證沒有放")
        for record in records:
            for evidence in record.evidence_items:
                if evidence.external_url and evidence.is_available:
                    included.append(f"作品連結：{record.title}／{evidence.display_name}：{evidence.external_url}")
                    continue
                if not evidence.file_path or not evidence.is_available:
                    continue
                add_stored(f"04_經歷佐證/{_safe(record.title)}/{_safe(evidence.display_name)}", evidence.file_path,
                           f"佐證：{record.title}／{evidence.display_name}")

        now = datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M")
        edition = "導師已確認的送審版" if review_status == "confirmed" else "草稿，尚未經導師確認"
        lines = [f"備審資料打包｜{program.school_name} {program.department_name}",
                 f"版本：{edition}", f"產生時間：{now}（台北時間）", "",
                 "只包含你已確認、而且沒有選擇「不放進備審」的資料。正式規定以當年度招生簡章為準。", "",
                 "已放入："] + [f"- {item}" for item in included]
        if skipped:
            lines += ["", "沒有放入："] + [f"- {item}" for item in skipped]
        if notes:
            lines += ["", "請注意："] + [f"- {item}" for item in notes]
        archive.writestr(f"{root}/清單.txt", "\r\n".join(lines) + "\r\n")

    buffer.seek(0)
    return buffer, {"included": included, "skipped": skipped, "notes": notes}
