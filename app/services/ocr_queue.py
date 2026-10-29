"""成績單與證照的背景辨識排隊。

上傳時只存檔並把文件標成 queued，真正的 OCR 交給本機一條背景執行緒依序處理，
學生先看到「辨識中」頁。不用 Celery 等外部服務；一次只跑一份，避免顯示卡記憶體不夠。

狀態沿用 SourceDocument.status：queued → processing → extracted／analysis_failed。
OCR_QUEUE_MODE：thread＝背景執行緒（預設）；inline＝在請求裡直接跑完（自動化測試預設）；
manual＝只排隊不執行（測試自己呼叫 run_job）。
只適用單一程序的伺服器：開多個程序時，啟動時的「中斷工作標成失敗」會誤標別的程序的工作。
"""
from pathlib import Path
import queue
import threading
from uuid import uuid4

from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import AuditLog, DocumentExtraction, SourceDocument
from app.services import storage_service
from app.services.document_analysis_service import analyze_document
from app.services.upload_quality import resolution_check

PENDING_STATUSES = ("queued", "processing")
PREVIEW_LONG_SIDE = 1100
UNEXPECTED_ERROR = "辨識時發生未預期的錯誤，請按「重新辨識」或改傳其他檔案。"
UNREADABLE_ERROR = "檔案讀不出來，可能是檔案損毀、加了密碼，或不是成績單／證照的圖片或 PDF。"
INTERRUPTED_ERROR = "伺服器重新啟動，這次辨識被中斷了，請按「重新辨識」。"

_jobs = queue.Queue()
_worker = None
_worker_lock = threading.Lock()


def enqueue(app, document_id):
    """把已標成 queued 的文件交給辨識；呼叫前要先提交資料庫。"""
    mode = app.config.get("OCR_QUEUE_MODE", "thread")
    if mode == "inline":
        run_job(app, document_id)
    elif mode == "thread":
        _ensure_worker()
        _jobs.put((app, document_id))


def _ensure_worker():
    global _worker
    with _worker_lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_work_forever, name="ocr-queue", daemon=True)
            _worker.start()


def _work_forever():
    while True:
        app, document_id = _jobs.get()
        try:
            run_job(app, document_id)
        except Exception:  # 單一工作出錯不能讓整條排隊停掉
            app.logger.exception("OCR 背景工作失敗：document_id=%s", document_id)
        finally:
            _jobs.task_done()


def wait_until_idle(timeout=None):
    """等排隊中的工作都跑完（測試與瀏覽器實測用）；逾時回傳 False。"""
    with _jobs.all_tasks_done:
        return _jobs.all_tasks_done.wait_for(lambda: not _jobs.unfinished_tasks, timeout)


def run_job(app, document_id):
    """辨識一份 queued 文件；同一份文件重複呼叫只會真的跑一次。"""
    with app.app_context():
        # 先搶下這份工作，避免兩個執行者同時辨識同一份文件
        claimed = SourceDocument.query.filter_by(id=document_id, status="queued").update(
            {"status": "processing"}, synchronize_session=False)
        db.session.commit()
        if claimed != 1:
            return False

        document = db.session.get(SourceDocument, document_id)
        provider = app.config["DOCUMENT_ANALYSIS_PROVIDER"]
        result, error, raw_error = None, None, None
        try:
            # 檔案可能在 Google 雲端硬碟：先取回本機快取（拿不到會丟出中文的 StorageUnavailable）
            source_path = storage_service.local_path(document.file_path)
            # 先做第一頁縮圖給「辨識中」頁顯示；PDF 轉圖不能跨執行緒同時做，所以放在同一條執行緒
            make_preview(app, document.file_path)
            result = analyze_document(document.document_type, source_path, provider,
                                      ocr_engine=app.config.get("OCR_ENGINE"))
            result = {**result, "draft_revision": uuid4().hex}
            resolution = resolution_check(document.document_type, source_path.read_bytes(), document.display_name)
            if resolution:
                result["processing_steps"] = [*(result.get("processing_steps") or []), {
                    "step": "resolution_checked", "long_side": resolution["long_side"], "level": resolution["level"]}]
                if resolution["level"] == "low":
                    result["warnings"] = [*(result.get("warnings") or []), resolution["message"]]
        except RuntimeError as exc:
            result, error, raw_error = None, student_error(str(exc)), str(exc)
        except Exception as exc:
            app.logger.exception("OCR 辨識發生未預期錯誤：document_id=%s", document_id)
            result, error, raw_error = None, UNEXPECTED_ERROR, repr(exc)

        db.session.rollback()
        document = db.session.get(SourceDocument, document_id)
        extraction = document.extraction or DocumentExtraction(source_document_id=document.id)
        extraction.provider = provider
        if error is None:
            extraction.result_json = result
            extraction.status = document.status = "extracted"
            extraction.error_message = None
        else:
            extraction.status = "failed"
            extraction.error_message = error
            document.status = "analysis_failed"
        db.session.add(extraction)
        # 有些提供者以 None 表示「此類型沒有這一欄」，所以用 or [] 而不是預設值
        db.session.add(AuditLog(
            user_id=document.owner_id,
            action="learning_profile.ocr_completed" if error is None else "learning_profile.ocr_failed",
            target_type="source_document",
            target_id=document.id,
            detail_json={
                "document_type": document.document_type,
                "file_name": document.display_name,
                "provider": provider,
                "status": extraction.status,
                "parsed_count": len((result or {}).get("courses") or []) + len((result or {}).get("credentials") or []),
                "processing_steps": (result or {}).get("processing_steps", []),
                "raw_text": (result or {}).get("raw_text"),
                "error_message": extraction.error_message,
                "raw_error": raw_error,
            },
        ))
        db.session.commit()
        return True


def student_error(message):
    """辨識套件的英文錯誤學生看不懂：沒有中文就換成中文說明，原文留在操作日誌。"""
    if any(0x4E00 <= ord(char) <= 0x9FFF for char in message or ""):
        return message
    return UNREADABLE_ERROR


def preview_path(file_path):
    """第一頁縮圖存在原檔（雲端檔案則是本機快取）旁邊。"""
    path = storage_service.cache_path(file_path)
    return path.with_name(path.name + ".preview.png")


def make_preview(app, file_path):
    """做不出縮圖（檔案壞掉、格式不對）不影響辨識，頁面改用示意圖。"""
    from app.services.ocr_pipeline import load_document_pages

    pages = None
    try:
        pages = load_document_pages(storage_service.local_path(file_path))
        page = next(iter(pages))
        page.thumbnail((PREVIEW_LONG_SIDE, PREVIEW_LONG_SIDE))
        page.save(preview_path(file_path), format="PNG")
        page.close()
        return True
    except Exception:
        app.logger.info("無法產生辨識中頁的預覽圖：%s", Path(file_path).name, exc_info=True)
        return False
    finally:
        if pages is not None and hasattr(pages, "close"):
            pages.close()


def queue_position(document):
    """前面還有幾份在排隊或辨識中（含別人的，只回數字）。"""
    return SourceDocument.query.filter(
        SourceDocument.status.in_(PENDING_STATUSES), SourceDocument.id < document.id).count()


def recover_interrupted_jobs():
    """伺服器重開時，上一次沒跑完的工作已經沒有執行緒在跑：標成失敗，讓學生按重新辨識。"""
    documents = SourceDocument.query.filter(SourceDocument.status.in_(PENDING_STATUSES)).all()
    for document in documents:
        extraction = document.extraction or DocumentExtraction(
            source_document_id=document.id, provider="ocr_queue")
        extraction.status = "failed"
        extraction.error_message = INTERRUPTED_ERROR
        document.status = "analysis_failed"
        db.session.add(extraction)
        db.session.add(AuditLog(
            user_id=document.owner_id,
            action="learning_profile.ocr_failed",
            target_type="source_document",
            target_id=document.id,
            detail_json={"document_type": document.document_type, "status": "failed",
                         "error_message": INTERRUPTED_ERROR},
        ))
    db.session.commit()
    return len(documents)


def recover_on_startup(app):
    """create_app 時呼叫；資料表還沒建（例如第一次資料庫遷移）就略過。"""
    with app.app_context():
        try:
            if inspect(db.engine).has_table(SourceDocument.__tablename__):
                count = recover_interrupted_jobs()
                if count:
                    app.logger.warning("有 %s 份文件的辨識因伺服器重開而中斷，已標成失敗。", count)
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.warning("啟動時無法檢查中斷的辨識工作，略過。", exc_info=True)
