"""備審一鍵打包（使用者 2026-11-13）：一個校系一個壓縮檔，可以下載或寄到學生自己的信箱。

壓縮檔內容（最外層一個資料夾「備審資料_校名科系」）：
- 01_備審資料.docx：和「下載 Word」同一份。
- 02_自傳_第N版.docx：最新一版自傳（還沒寫就沒有）。
- 03_成績單與證照原始檔／：學生上傳、已確認的原始檔。
- 04_經歷佐證／<經歷標題>／：已確認經歷的佐證檔。
- 清單.txt：放了哪些、哪些沒放與原因。

只放學生已確認的資料；學生選擇「不放進備審」的不放（簡章規定必備的類別除外，規則見 package_exclusion）。
原始成績單是整份檔案：裡面只要有一門課被選擇不放（且成績不是必備），整份就不放，免得那一科還是被看到。
檔案暫時拿不到（例如雲端沒連線）不會讓打包失敗，只在清單註明。
"""
import io
import re
import zipfile
from datetime import datetime, timedelta, timezone

from app.models import CredentialRecord, LearningCourseRecord, Portfolio, SourceDocument, User
from app.extensions import db
from app.services import autobiography_backup, autobiography_service, package_exclusion, storage_service
from app.services.package_service import build_package_docx

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


def build_zip(student, program):
    """回傳 (BytesIO, 清單)。清單是 {"included": [...], "skipped": [...]}。"""
    required = package_exclusion.required_keys(program)
    root = root_name(program)
    included, skipped, used = [], [], set()
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
            except storage_service.StorageUnavailable:
                skipped.append(f"{label}：檔案暫時拿不到，沒有放")
                return
            add(path, data, label)

        add("01_備審資料.docx", build_package_docx(student, program).getvalue(), "備審資料 Word")

        draft = autobiography_service.latest_draft(student, program)
        if draft:
            content = draft.content_json
            editor = db.session.get(User, content["editor_id"]) if content.get("editor_id") else None
            version = autobiography_service.version_of(draft)
            add(f"02_自傳_第{version}版.docx", autobiography_backup.build_docx(student, program, content, editor),
                f"自傳第 {version} 版")
        else:
            skipped.append("自傳：還沒有草稿")

        for document in _kept_documents(student, required, skipped):
            add_stored(f"03_成績單與證照原始檔/{_safe(document.display_name)}", document.file_path,
                       f"原始檔：{document.display_name}")

        records = package_exclusion.keep_portfolios(
            Portfolio.active().filter_by(student_id=student.id, status="confirmed").order_by(Portfolio.id).all(),
            required)
        for record in records:
            for evidence in record.evidence_items:
                if not evidence.file_path or not evidence.is_available:
                    continue
                add_stored(f"04_經歷佐證/{_safe(record.title)}/{_safe(evidence.display_name)}", evidence.file_path,
                           f"佐證：{record.title}／{evidence.display_name}")

        now = datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M")
        lines = [f"備審資料打包｜{program.school_name} {program.department_name}", f"產生時間：{now}（台北時間）", "",
                 "只包含你已確認、而且沒有選擇「不放進備審」的資料。正式規定以當年度招生簡章為準。", "",
                 "已放入："] + [f"- {item}" for item in included]
        if skipped:
            lines += ["", "沒有放入："] + [f"- {item}" for item in skipped]
        archive.writestr(f"{root}/清單.txt", "\r\n".join(lines) + "\r\n")

    buffer.seek(0)
    return buffer, {"included": included, "skipped": skipped}
