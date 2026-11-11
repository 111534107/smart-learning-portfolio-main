"""自傳「兩邊都存」的學校端備份：每建立一版自傳，就另存一份 Word 檔到學校的檔案存放（使用者 10-28 決定）。

- 存放位置交給 storage_service：管理員連上 Google 雲端硬碟時存到「智慧學習歷程系統上傳檔」資料夾，
  否則存本機 UPLOAD_FOLDER/autobiography/<學生 id>/。
- 存檔時只把該版標成 backup_status="pending" 就完成；Word 檔在背景執行緒產生並上傳（沿用 ocr_queue 的做法，
  不用 Celery）。失敗自動重試（最多 BACKUP_MAX_ATTEMPTS 次）；仍失敗標成 "failed"，頁面顯示「備份失敗」與
  「再試一次」，同一位學生同一校系下次存檔也會一起補備份。
- AUTOBIOGRAPHY_BACKUP_MODE：thread＝背景執行緒（預設）；inline＝存檔後直接跑（自動化測試預設）；manual＝只排隊。
  只適用單一程序的伺服器；伺服器重開時排隊中的版本會在下次存檔或按「再試一次」時補上。
- 位置寫進該版 content_json["backup_location"]；Word 檔名與內文都註明修改者（學生本人／導師姓名）與時間。
- 正式版本仍在資料庫；這份 Word 只是備份。學生自己的 Google 文件另走 google_docs_service。
"""
import io
import queue
import re
import threading
import time
from datetime import datetime, timedelta, timezone

from docx import Document
from sqlalchemy.orm.attributes import flag_modified

from app.extensions import db
from app.services import storage_service

FOLDER = "autobiography"
TAIPEI = timezone(timedelta(hours=8))
BACKUP_MAX_ATTEMPTS = 3
BACKUP_RETRY_DELAYS = (2, 10)  # 第 1、2 次失敗後各等幾秒再試

# 狀態代碼 → 給使用者看的文字。不顯示本機路徑或 Drive 內部位置。
STATUS_LABELS = {
    "cloud": f"已備份到學校雲端（{storage_service.FOLDER_NAME}）",
    "local": "已備份到本機（學校雲端未連線）",
    "pending": "備份中",
    "failed": "備份失敗",
}

_UNSAFE = re.compile(r"[/\\:*?\"<>|\s]+")


def _safe(text):
    return _UNSAFE.sub("", str(text or "")) or "未命名"


def _account(student):
    profile = getattr(student, "student_profile", None)
    return (profile.student_no if profile and profile.student_no else None) or student.username


def editor_label(content, editor=None):
    """修改者：學生本人／導師 姓名／AI 產生。editor 是 content["editor_id"] 對應的使用者（可為 None）。"""
    role = content.get("editor_role")
    if role == "student":
        return "學生本人"
    if role == "teacher":
        return f"導師 {editor.display_name}" if editor else "導師"
    if role == "ai":
        return "AI 產生"
    return "修改者不明"


def _saved_at(content):
    """這一版存檔的時間（台北）；舊資料沒有就用現在。"""
    text = content.get("saved_at")
    try:
        moment = datetime.fromisoformat(text) if text else datetime.now(timezone.utc)
    except ValueError:
        moment = datetime.now(timezone.utc)
    return moment.astimezone(TAIPEI)


def filename_for(student, program, version, content=None, editor=None):
    tail = ""
    if content is not None:
        tail = f"_{_safe(editor_label(content, editor))}_{_saved_at(content).strftime('%Y%m%d-%H%M')}"
    return (f"自傳_{_safe(_account(student))}_{_safe(program.school_name + program.department_name)}"
            f"_第{version}版{tail}.docx")


def build_docx(student, program, content, editor=None):
    """標題含學生姓名、目標校系；副標含第幾版、修改者與時間；每段一個段落（段落標題另起小標）。"""
    document = Document()
    when = _saved_at(content).strftime("%Y-%m-%d %H:%M")
    document.add_heading(f"自傳｜{student.display_name}｜{program.school_name} {program.department_name}", level=1)
    document.add_paragraph(f"第 {content.get('version')} 版｜修改者：{editor_label(content, editor)}｜{when}（台北時間）")
    for paragraph in content.get("paragraphs", []):
        if paragraph.get("title"):
            document.add_heading(paragraph["title"], level=2)
        document.add_paragraph(paragraph.get("text", ""))
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def write_backup(student, program, content, editor=None):
    """產生 Word 並存檔，回傳位置；失敗直接丟例外（由背景工作決定要不要重試）。"""
    data = build_docx(student, program, content, editor)
    return storage_service.save(data, student.id, FOLDER,
                                filename_for(student, program, content.get("version"), content, editor))


def mark_pending(content):
    """存檔時呼叫：只標記「待備份」與存檔時間，不碰 Drive。"""
    content["backup_location"] = ""
    content["backup_status"] = "pending"
    content["backup_attempts"] = 0
    content.setdefault("saved_at", datetime.now(timezone.utc).isoformat())
    content.pop("backup_error", None)


# ---- 背景佇列（與 ocr_queue 相同模式：單一程序、一條 daemon 執行緒） ----
_jobs = queue.Queue()
_worker = None
_worker_lock = threading.Lock()


def enqueue(app, output_id):
    """把已提交、標成 pending 的版本交給背景備份；呼叫前要先 commit。"""
    mode = app.config.get("AUTOBIOGRAPHY_BACKUP_MODE", "thread")
    if mode == "inline":
        run_job(app, output_id)
    elif mode == "thread":
        _ensure_worker()
        _jobs.put((app, output_id))


def _ensure_worker():
    global _worker
    with _worker_lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_work_forever, name="autobiography-backup", daemon=True)
            _worker.start()


def _work_forever():
    while True:
        app, output_id = _jobs.get()
        try:
            run_job(app, output_id)
        except Exception:  # 單一工作出錯不能讓整條排隊停掉
            app.logger.exception("自傳備份背景工作失敗：output_id=%s", output_id)
        finally:
            _jobs.task_done()


def wait_until_idle(timeout=None):
    """等排隊中的備份都跑完（測試與實測用）；逾時回傳 False。"""
    with _jobs.all_tasks_done:
        return _jobs.all_tasks_done.wait_for(lambda: not _jobs.unfinished_tasks, timeout)


def _update(output, drop=(), **fields):
    content = dict(output.content_json or {})
    content.update(fields)
    for key in drop:
        content.pop(key, None)
    output.content_json = content
    flag_modified(output, "content_json")
    db.session.commit()


def run_job(app, output_id, sleep=time.sleep):
    """備份一個版本：失敗自動重試（最多 AUTOBIOGRAPHY_BACKUP_MAX_ATTEMPTS 次），仍失敗標成 failed。回傳是否成功。"""
    from app.models import AdmissionProgram, LearningProfileOutput, User

    with app.app_context():
        output = db.session.get(LearningProfileOutput, output_id)
        if output is None or (output.content_json or {}).get("backup_status") != "pending":
            return False
        content = dict(output.content_json)
        student = db.session.get(User, output.student_id)
        program = db.session.get(AdmissionProgram, content.get("program_id"))
        editor = db.session.get(User, content["editor_id"]) if content.get("editor_id") else None
        attempts = app.config.get("AUTOBIOGRAPHY_BACKUP_MAX_ATTEMPTS", BACKUP_MAX_ATTEMPTS)
        delays = app.config.get("AUTOBIOGRAPHY_BACKUP_RETRY_DELAYS", BACKUP_RETRY_DELAYS)
        error, tried = "找不到學生或校系", 0
        for attempt in range(1, attempts + 1):
            if student is None or program is None:
                break
            tried = attempt
            try:
                location = write_backup(student, program, content, editor)
            except Exception as exc:  # Drive 慢、斷線、權限錯誤都算失敗，等一下再試
                error = str(exc) or exc.__class__.__name__
                app.logger.warning("自傳備份失敗（學生 %s 第 %s 版，第 %s 次）：%s",
                                   output.student_id, content.get("version"), attempt, error)
                db.session.rollback()
                if attempt < attempts:
                    sleep(delays[min(attempt - 1, len(delays) - 1)] if delays else 0)
                continue
            output = db.session.get(LearningProfileOutput, output_id)
            _update(output, drop=("backup_error",), backup_location=location, backup_status="done",
                    backup_attempts=(output.content_json.get("backup_attempts") or 0) + attempt)
            return True
        output = db.session.get(LearningProfileOutput, output_id)
        _update(output, backup_location="", backup_status="failed", backup_error=error[:300],
                backup_attempts=(output.content_json.get("backup_attempts") or 0) + tried)
        return False


def retry(app, output):
    """「再試一次」：失敗的版本重新排進背景備份。"""
    if status_of(output) != "failed":
        return False
    _update(output, backup_status="pending")
    enqueue(app, output.id)
    return True


def failed_versions(student_id, program_id):
    """同一位學生同一校系備份失敗或卡在待備份（例如伺服器重開）的版本，下次存檔時一起補。"""
    from app.models import LearningProfileOutput

    outputs = LearningProfileOutput.query.filter_by(student_id=student_id, output_type="autobiography_ai").all()
    return [o for o in outputs if (o.content_json or {}).get("program_id") == program_id
            and status_of(o) in ("failed", "pending")]


def schedule_after_save(app, output):
    """存檔 commit 之後呼叫：排入新版本，並補排同校系之前失敗的版本。"""
    for old in [o for o in failed_versions(output.student_id, (output.content_json or {}).get("program_id"))
                if o.id != output.id]:
        _update(old, backup_status="pending")
        enqueue(app, old.id)
    enqueue(app, output.id)
    db.session.expire_all()  # inline 模式在另一個 session 更新過，讓呼叫端重新讀


def status_of(output):
    """這一版的備份狀態：cloud／local／pending／failed；舊資料沒有備份欄位時回傳 None。"""
    content = output.content_json or {}
    if "backup_location" not in content and "backup_status" not in content:
        return None
    status = content.get("backup_status")
    if status in ("pending", "failed"):
        return status
    location = content.get("backup_location") or ""
    if not location:
        return "failed"
    return "cloud" if location.startswith(storage_service.DRIVE_PREFIX) else "local"


def status_label(output):
    return STATUS_LABELS.get(status_of(output))
