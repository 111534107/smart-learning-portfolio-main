from hashlib import sha256
from io import BytesIO
import json
import math
import re
from datetime import date, datetime, timezone
from urllib.parse import urlparse
from uuid import uuid4
from urllib.parse import urlparse

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, send_file, url_for

from app.extensions import db
from app.models import (
    AdmissionProgram,
    AgentTask,
    AuditLog,
    CredentialRecord,
    DocumentExtraction,
    LearningCourseRecord,
    LearningProfileOutput,
    MatchFilterOption,
    Portfolio,
    PortfolioEvidence,
    SourceDocument,
    StudentProfile,
    StudentTarget,
    User,
)
from app.routes.main import get_current_user, role_required
from app.services.focus_service import focus_view
from app.services.portfolio_service import owned_portfolio, create_submission_snapshot
from app.security import validate_upload_filename
from app.models.learning_profile import grade_number
from app.services.flow import flash_done, readiness, safe_next, target_program
from app.services.document_analysis_service import ALLOWED_DOCUMENT_TYPES, analyze_document, score_band
from app.services.learning_profile_docx_service import output_to_docx_bytes
from app.services.learning_profile_service import generate_learning_profile_outputs
from app.services.activity_fit import build_activity_fit
from app.services.admission_service import published_programs
from app.services.gap_service import ALL_LABELS, analyze_gap, chapter_order
from app.services.admission_links import admission_links, load_school_links
from app.services.admission_schedule import CHECKED_ON, channel_label, latest_timeline, timeline
from app.services.matching_service import rank_programs
from app.services.gap_checklist import download_checklist, review_timeline
from app.services.journey_service import CATEGORY_LABELS, EXPERIENCE_CATEGORIES, build_journey
from app.services.package_service import build_package_docx, latest_review
from app.services.file_preview import inline_file
from app.services.record_status import learning_profile_state, portfolio_state
from app.services import ai_quota_service, audit_service, autobiography_backup, autobiography_review, autobiography_service, ocr_queue, review_snapshot_service, storage_service, student_rules
from app.services.gemini_client import AIUnavailable, ai_ready
from app.services.course_review_presentation import (
    build_course_review_groups,
    prepare_course_review_rows,
    traditionalize_course_name,
)


student_bp = Blueprint("student", __name__)


@student_bp.post("/student/learning-profile/documents")
@role_required("student")
def learning_profile_document_upload():
    user = get_current_user()
    document_type = request.form.get("document_type", "").strip()
    uploaded = request.files.get("file")

    def upload_error(message):
        # 留在上傳頁、用中文說明，不要整頁只剩英文錯誤（10-27 實測問題 4）
        return render_template("learning_profile_upload.html", user=user,
                               document_type=document_type if document_type in ALLOWED_DOCUMENT_TYPES else "transcript",
                               next_path=safe_next(request.form.get("next")), error=message), 400

    if document_type not in ALLOWED_DOCUMENT_TYPES:
        return upload_error("請先選擇要上傳的是成績單還是證照。")
    if not uploaded or not uploaded.filename:
        return upload_error("請先選擇要上傳的檔案。")
    try:
        safe_name = validate_upload_filename(
            uploaded.filename,
            current_app.config["LEARNING_PROFILE_ALLOWED_EXTENSIONS"],
        )
    except ValueError:
        return upload_error("只接受 PNG、JPG 圖片或 PDF 檔，請換一個檔案再上傳。")

    file_bytes = uploaded.read()
    if not file_bytes:
        return upload_error("這個檔案是空的，請換一個檔案再上傳。")
    # 成績單圖片太小時 OCR 只會產生亂字：不存檔，直接請學生改傳
    from app.services.upload_quality import resolution_check
    resolution = resolution_check(document_type, file_bytes, safe_name)
    if resolution and resolution["level"] == "too_small":
        return render_template("learning_profile_upload.html", user=user, document_type=document_type,
                               next_path=safe_next(request.form.get("next")),
                               error=resolution["message"]), 400
    location = storage_service.save(file_bytes, owner_id=user.id, folder="learning-profile", filename=safe_name)
    try:
        document = SourceDocument(
            owner_id=user.id,
            document_type=document_type,
            display_name=safe_name,
            file_path=location,
            sha256=sha256(file_bytes).hexdigest(),
            status="queued",
        )
        db.session.add(document)
        db.session.flush()
        audit_service.record(user, "learning_profile.document_upload", "source_document", document.id,
                             detail={"document_type": document_type})
        db.session.commit()
    except Exception:
        db.session.rollback()
        storage_service.discard(location)
        raise
    # 辨識要 7～30 秒：先跳「辨識中」頁，背景跑完再自動進確認頁；從校系頁來的會帶著 next
    ocr_queue.enqueue(current_app._get_current_object(), document.id)
    return redirect(url_for("student.learning_profile_document_processing", document_id=document.id,
                            next=safe_next(request.form.get("next"))))


def _ocr_job_state(document):
    if document.status in ocr_queue.PENDING_STATUSES:
        return document.status
    return "failed" if document.status == "analysis_failed" else "done"


@student_bp.get("/student/learning-profile/documents/<int:document_id>/processing")
@role_required("student")
def learning_profile_document_processing(document_id):
    document = _owned_source_document(document_id)
    next_path = safe_next(request.args.get("next"))
    state = _ocr_job_state(document)
    if state == "done":
        return redirect(url_for("student.learning_profile_document_review", document_id=document.id, next=next_path))
    has_preview = ocr_queue.preview_path(document.file_path).is_file()
    return render_template("learning_profile_processing.html", user=get_current_user(), document=document,
                           state=state, next_path=next_path,
                           ahead=ocr_queue.queue_position(document) if state == "queued" else 0,
                           preview_url=url_for("student.learning_profile_document_preview", document_id=document.id)
                           if has_preview else None,
                           error=document.extraction.error_message if document.extraction else None)


@student_bp.get("/student/learning-profile/documents/<int:document_id>/status")
@role_required("student")
def learning_profile_document_status(document_id):
    """「辨識中」頁定時查詢；只回狀態，不回辨識內容。"""
    document = _owned_source_document(document_id)
    state = _ocr_job_state(document)
    payload = {"state": state}
    if ocr_queue.preview_path(document.file_path).is_file():
        payload["preview"] = url_for("student.learning_profile_document_preview", document_id=document.id)
    if state == "queued":
        payload["ahead"] = ocr_queue.queue_position(document)
    elif state == "done":
        result = (document.extraction.result_json if document.extraction else None) or {}
        payload["found"] = len(result.get("courses") or []) + len(result.get("credentials") or [])
        payload["redirect"] = url_for("student.learning_profile_document_review", document_id=document.id,
                                      next=safe_next(request.args.get("next")))
    elif state == "failed":
        payload["error"] = (document.extraction.error_message if document.extraction else None) or "辨識失敗"
    return payload


@student_bp.get("/student/learning-profile/documents/<int:document_id>/preview")
@role_required("student")
def learning_profile_document_preview(document_id):
    """「辨識中」頁顯示的第一頁縮圖；由背景辨識先做好。"""
    document = _owned_source_document(document_id)
    path = ocr_queue.preview_path(document.file_path)
    if not path.is_file():
        abort(404)
    response = send_file(path, mimetype="image/png")
    response.headers["Cache-Control"] = "private, no-store"
    return response


@student_bp.post("/student/learning-profile/documents/<int:document_id>/retry")
@role_required("student")
def learning_profile_document_retry(document_id):
    document = _owned_source_document(document_id)
    if document.status != "analysis_failed":
        abort(409, description="這份文件不是辨識失敗的狀態，不需要重新辨識。")
    if not storage_service.exists(document.file_path):
        abort(409, description="找不到原始檔案，請重新上傳。")
    document.status = "queued"
    db.session.commit()
    ocr_queue.enqueue(current_app._get_current_object(), document.id)
    return redirect(url_for("student.learning_profile_document_processing", document_id=document.id,
                            next=safe_next(request.form.get("next"))))


# 成績單與證照分成兩頁：各自只列自己的文件與資料
PROFILE_PAGES = {"transcript": "student.learning_profile", "credential": "student.learning_profile_credentials"}


def _profile_page_url(document_type):
    return url_for(PROFILE_PAGES.get(document_type, "student.learning_profile"))


def _learning_profile_page(kind):
    user = get_current_user()
    documents = SourceDocument.query.filter_by(owner_id=user.id, document_type=kind).order_by(
        SourceDocument.created_at.desc()).all()
    courses = LearningCourseRecord.query.filter_by(student_id=user.id).order_by(
        LearningCourseRecord.school_year, LearningCourseRecord.id).all() if kind == "transcript" else []
    credentials = CredentialRecord.query.filter_by(student_id=user.id).order_by(
        CredentialRecord.id).all() if kind == "credential" else []
    outputs = LearningProfileOutput.query.filter_by(student_id=user.id).order_by(LearningProfileOutput.created_at.desc()).all()
    return render_template(
        "learning_profile.html",
        user=user,
        kind=kind,
        documents=documents,
        outputs=outputs,
        courses=courses,
        credentials=credentials,
        record_state=learning_profile_state,
    )


@student_bp.get("/student/learning-profile")
@role_required("student")
def learning_profile():
    return _learning_profile_page("transcript")


@student_bp.get("/student/learning-profile/credentials")
@role_required("student")
def learning_profile_credentials():
    return _learning_profile_page("credential")


@student_bp.get("/student/learning-profile/upload")
@role_required("student")
def learning_profile_upload_page():
    document_type = request.args.get("type")
    return render_template("learning_profile_upload.html", user=get_current_user(),
                           document_type=document_type if document_type in ALLOWED_DOCUMENT_TYPES else "transcript",
                           next_path=safe_next(request.args.get("next")))


@student_bp.post("/student/learning-profile/generate")
@role_required("student")
def learning_profile_generate():
    try:
        school_year = int(request.form.get("school_year", ""))
        if not 1 <= school_year <= 999:
            raise ValueError
    except ValueError:
        return "school_year is required", 400
    generate_learning_profile_outputs(get_current_user(), school_year)
    return redirect(url_for("student.learning_profile"))


@student_bp.get("/student/learning-profile/outputs/<int:output_id>/docx")
@role_required("student")
def learning_profile_output_docx(output_id):
    output = db.session.get(LearningProfileOutput, output_id)
    if not output:
        abort(404)
    user = get_current_user()
    if output.student_id != user.id:
        abort(403)
    stream = output_to_docx_bytes(output, user.display_name)
    return send_file(
        stream,
        as_attachment=True,
        download_name=f"learning-profile-{output.output_type}-{output.id}.docx",
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@student_bp.get("/student/learning-profile/documents/<int:document_id>/review")
@role_required("student")
def learning_profile_document_review(document_id):
    document = db.session.get(SourceDocument, document_id)
    if not document:
        abort(404)
    user = get_current_user()
    if document.owner_id != user.id:
        abort(403)
    if document.status in ocr_queue.PENDING_STATUSES:
        return redirect(url_for("student.learning_profile_document_processing", document_id=document.id,
                                next=safe_next(request.args.get("next"))))
    result = document.extraction.result_json if document.extraction and document.extraction.result_json else {}
    if document.document_type == "credential":
        from app.services.credential_analysis import prepare_credential_review_result
        review_result = prepare_credential_review_result(
            result,
            preserve_confirmed_credentials=bool(
                document.extraction and document.extraction.status == "confirmed"),
        )
    else:
        review_result = result
    review_courses = prepare_course_review_rows(result.get("courses") or [])
    return render_template(
        "learning_profile_review.html", user=user, document=document,
        next_path=safe_next(request.args.get("next")),
        review_result=review_result,
        review_courses=review_courses,
        review_groups=build_course_review_groups(review_courses),
    )


@student_bp.get("/student/learning-profile/documents/<int:document_id>/view")
@role_required("student")
def learning_profile_document_view(document_id):
    """確認頁旁邊顯示學生上傳的成績單或證照，方便對照。"""
    document = db.session.get(SourceDocument, document_id)
    if not document:
        abort(404)
    if document.owner_id != get_current_user().id:
        abort(403)
    return inline_file(document.file_path, document.display_name)


def _owned_source_document(document_id):
    document = db.session.get(SourceDocument, document_id)
    if not document:
        abort(404)
    if document.owner_id != get_current_user().id:
        abort(403)
    return document


def _claim_extraction(extraction, expected_updated_at, expected_revision):
    """Serialize draft replacement/confirmation without adding a DB column."""
    changed = DocumentExtraction.query.filter_by(
        id=extraction.id, updated_at=expected_updated_at,
    ).filter(
        DocumentExtraction.result_json["draft_revision"].as_string() == expected_revision,
    ).update({"updated_at": datetime.now(timezone.utc)}, synchronize_session=False)
    if changed != 1:
        db.session.rollback()
        abort(409, description="資料已更新，請重新開啟確認頁面。")


@student_bp.post("/student/learning-profile/documents/<int:document_id>/reanalyze")
@role_required("student")
def learning_profile_document_reanalyze(document_id):
    document = _owned_source_document(document_id)
    if document.status in ocr_queue.PENDING_STATUSES:
        abort(409, description="這份文件正在背景辨識，請等辨識完成。")
    extraction = document.extraction
    # Capture both before slow OCR; a later writer must win even if the ORM
    # instance is refreshed or the database truncates timestamp precision.
    started_updated_at = extraction.updated_at if extraction else None
    started_revision = (extraction.result_json or {}).get("draft_revision") if extraction else None
    provider = current_app.config["DOCUMENT_ANALYSIS_PROVIDER"]
    try:
        source_path = storage_service.local_path(document.file_path)
        result = analyze_document(document.document_type, source_path, provider)
        if not isinstance(result, dict) or any(
            not isinstance(result.get(key, []), list)
            or any(not isinstance(item, dict) for item in result.get(key, []))
            for key in ("courses", "credentials")
        ):
            raise RuntimeError("invalid analysis result")
    except (RuntimeError, OSError):
        db.session.rollback()
        previous_result = extraction.result_json if extraction and extraction.result_json else {}
        if document.document_type == "credential":
            from app.services.credential_analysis import prepare_credential_review_result
            review_result = prepare_credential_review_result(
                previous_result,
                preserve_confirmed_credentials=bool(
                    extraction and extraction.status == "confirmed"),
            )
        else:
            review_result = previous_result
        return render_template(
            "learning_profile_review.html", document=document,
            review_result=review_result,
            review_courses=prepare_course_review_rows(previous_result.get("courses") or []),
            review_groups=build_course_review_groups(
                prepare_course_review_rows(previous_result.get("courses") or [])
            ),
            review_error="重新分析失敗。先前擷取資料與已確認紀錄均保留，請稍後再試。",
        ), 503

    previous = (extraction.result_json or {}) if extraction else {}
    history = []
    # Keep only five flat snapshots; never copy history into a snapshot.
    for snapshot in previous.get("history", [])[-4:]:
        history.append({**snapshot, "result": {
            key: value for key, value in snapshot.get("result", {}).items() if key != "history"
        }})
    if extraction:
        _claim_extraction(extraction, started_updated_at, started_revision)
        history.append({
            "result": {key: value for key, value in previous.items() if key != "history"},
            "provider": extraction.provider,
            "status": extraction.status,
            "confirmed_at": extraction.confirmed_at.isoformat() if extraction.confirmed_at else None,
            "confirmed_by_id": extraction.confirmed_by_id,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        })
    else:
        extraction = DocumentExtraction(source_document_id=document.id)
        db.session.add(extraction)
    extraction.result_json = {**result, "draft_revision": uuid4().hex, "history": history}
    extraction.provider = provider
    extraction.status = document.status = "extracted"
    extraction.error_message = None
    extraction.confirmed_at = None
    extraction.confirmed_by_id = None
    db.session.commit()
    return redirect(url_for("student.learning_profile_document_review", document_id=document.id))


@student_bp.get("/student/learning-profile/documents/<int:document_id>/source")
@role_required("student")
def learning_profile_document_source(document_id):
    document = _owned_source_document(document_id)
    source_path = storage_service.local_path_or_none(document.file_path)
    if source_path is None:
        abort(404)
    response = send_file(source_path.resolve(), as_attachment=True, download_name=document.display_name)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@student_bp.get("/student/learning-profile/documents/<int:document_id>/courses/<int:course_index>/source")
@role_required("student")
def learning_profile_course_source(document_id, course_index):
    document = _owned_source_document(document_id)
    result = document.extraction.result_json if document.extraction else None
    result = result or {}
    if result.get("draft_revision") and request.args.get("revision") not in (None, result["draft_revision"]):
        abort(409, description="草稿已更新，請重新開啟確認頁面。")
    courses = result.get("courses", [])
    if course_index >= len(courses):
        abort(404)
    course = courses[course_index]
    page_number = course.get("source_page")
    bbox = course.get("source_bbox")
    rotation = course.get("source_rotation", 0)
    if (type(page_number) is not int or page_number < 1
            or not isinstance(bbox, (list, tuple)) or len(bbox) != 4
            or any(type(value) not in (int, float) or not math.isfinite(value) for value in bbox)
            or type(rotation) not in (int, float) or not math.isfinite(rotation)
            or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]):
        abort(400, description="原圖位置資料不完整。")
    return _source_crop_response(document, page_number, bbox, rotation)


@student_bp.get("/student/learning-profile/documents/<int:document_id>/credentials/<int:analysis_index>/fields/<field_key>/source")
@role_required("student")
def learning_profile_credential_field_source(document_id, analysis_index, field_key):
    """證照確認頁每個欄位旁的預覽圖：原圖中辨識出這個欄位的那一塊。"""
    document = _owned_source_document(document_id)
    result = (document.extraction.result_json if document.extraction else None) or {}
    if result.get("draft_revision") and request.args.get("revision") not in (None, result["draft_revision"]):
        abort(409, description="草稿已更新，請重新開啟確認頁面。")
    analyses = result.get("credential_analyses") or (
        [result["credential_analysis"]] if result.get("credential_analysis") else [])
    if analysis_index >= len(analyses):
        abort(404)
    field = ((analyses[analysis_index] or {}).get("fields") or {}).get(field_key)
    if not field:
        abort(404)
    page_number, bbox = field.get("page"), field.get("bbox")
    if (type(page_number) is not int or page_number < 1
            or not isinstance(bbox, (list, tuple)) or len(bbox) != 4
            or any(type(value) not in (int, float) or not math.isfinite(value) for value in bbox)
            or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]):
        abort(404)
    # 四周留一點邊，學生比較容易看出這塊在證照上的哪裡
    return _source_crop_response(document, page_number, bbox, padding=max(6, (bbox[3] - bbox[1]) * .15))


def _source_crop_response(document, page_number, bbox, rotation=0, padding=0):
    """把原始檔第 page_number 頁的 bbox 區域（四周留 padding 像素）裁成 PNG 回傳；課程與證照欄位共用。"""
    from app.services.ocr_pipeline import load_document_pages

    pages = None
    try:
        pages = load_document_pages(storage_service.local_path(document.file_path))
        for number, page in enumerate(pages, start=1):
            try:
                if number != page_number:
                    continue
                oriented = page.rotate(rotation, expand=True) if rotation else page
                try:
                    left = max(0, math.floor(bbox[0] - padding))
                    top = max(0, math.floor(bbox[1] - padding))
                    right = min(oriented.width, math.ceil(bbox[2] + padding))
                    bottom = min(oriented.height, math.ceil(bbox[3] + padding))
                    if right <= left or bottom <= top:
                        abort(400, description="原圖位置超出頁面。")
                    stream = BytesIO()
                    with oriented.crop((left, top, right, bottom)) as crop:
                        crop.save(stream, format="PNG")
                    stream.seek(0)
                finally:
                    if oriented is not page:
                        oriented.close()
                response = send_file(stream, mimetype="image/png")
                response.headers["Cache-Control"] = "private, no-store"
                response.headers["X-Content-Type-Options"] = "nosniff"
                return response
            finally:
                page.close()
    except RuntimeError:
        abort(503, description="暫時無法讀取原圖，請稍後再試。")
    finally:
        if pages is not None and hasattr(pages, "close"):
            pages.close()
    abort(404)


def _load_record_list(raw_value, field_name):
    try:
        value = json.loads(raw_value or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} 格式錯誤") from exc
    if not isinstance(value, list):
        raise ValueError(f"{field_name} 必須是清單")
    return value


def _normalise_name(value):
    return "".join(str(value or "").split())


def _course_integer(value, label, upper=None):
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not re.fullmatch(r"\d+", str(value).strip()):
        raise ValueError(f"{label}必須是零或正整數")
    value = int(value)
    if upper is not None and value > upper:
        raise ValueError(f"{label}必須介於 0 至 {upper}")
    return value



SEMESTER_WORDS = {"一": "上", "1": "上", "上": "上", "二": "下", "2": "下", "下": "下"}


def _course_semester(value):
    """成績單印「一」「二」或 1、2，系統統一存「上」「下」（10-27 實測問題 3）。"""
    text = str(value or "").strip()
    return SEMESTER_WORDS.get(text, text or None)


def _course_grade(user, school_year, grade_level):
    """課程放在幾年級（1～5）。學生在確認頁填的年級優先；辨識草稿帶的是民國學年度（例如 115）時，
    用入學年度換算成年級，換不出來就留空，不把 115 當成年級存進去。"""
    typed = grade_number(grade_level)
    if typed:
        return typed
    try:
        year = int(school_year)
    except (TypeError, ValueError):
        return None
    if 1 <= year <= 5:
        return year
    profile = user.student_profile
    if profile and profile.admission_year and 1 <= year - profile.admission_year + 1 <= 5:
        return year - profile.admission_year + 1
    return None

@student_bp.post("/student/learning-profile/documents/<int:document_id>/review/confirm")
@role_required("student")
def learning_profile_document_confirm(document_id):
    document = db.session.get(SourceDocument, document_id)
    if not document:
        abort(404)
    user = get_current_user()
    if document.owner_id != user.id:
        abort(403)
    next_path = safe_next(request.form.get("next"))
    program = target_program(next_path)
    before = readiness(user, program)
    extraction = document.extraction
    if not extraction:
        return "document extraction is required", 400
    result = extraction.result_json or {}
    revision = result.get("draft_revision")
    started_updated_at = extraction.updated_at
    if revision and request.form.get("draft_revision") != revision:
        return "草稿已更新，請重新開啟確認頁面後再儲存。", 409
    try:
        scores_unlocked = request.form.get("scores_unlocked") == "1"
        all_fields_locked = request.form.get("all_fields_locked") == "1"
        if request.form.get("course_input_mode") == "fields":
            courses = []
            for index, original in enumerate(result.get("courses", [])):
                item = dict(original)
                for field in ("course_name", "credits", "score", "semester", "grade_level"):
                    key = f"course_{index}_{field}"
                    if key not in request.form:
                        raise ValueError("課程欄位不完整，請重新開啟確認頁面")
                    if all_fields_locked or (field == "score" and not scores_unlocked):
                        item[field] = original.get("score")
                    else:
                        item[field] = request.form[key].strip()
                courses.append(item)
        else:
            if revision and "courses_json" not in request.form:
                raise ValueError("課程資料不完整，請重新開啟確認頁面")
            courses = _load_record_list(request.form.get("courses_json"), "courses_json")
        if not scores_unlocked:
            original_courses = result.get("courses", [])
            for index, item in enumerate(courses):
                if isinstance(item, dict):
                    item["score"] = (
                        original_courses[index].get("score")
                        if index < len(original_courses) else None
                    )
        if all_fields_locked:
            original_courses = result.get("courses", [])
            for index, item in enumerate(courses):
                if isinstance(item, dict) and index < len(original_courses):
                    for field in ("course_name", "credits", "score", "semester", "grade_level"):
                        item[field] = original_courses[index].get(field)
        credentials_json = request.form.get("credentials_json")
        if (document.document_type == "credential"
                and request.form.get("credential_input_mode") == "json"
                and credentials_json is None):
            raise ValueError("證照 JSON 資料不完整，請重新開啟確認頁面")
        if revision and credentials_json is None and request.form.get("credential_name") is None:
            raise ValueError("證照資料不完整，請重新開啟確認頁面")
        if (document.document_type == "credential"
                and request.form.get("credential_name") is not None
                and request.form.get("credential_input_mode") != "json"):
            original_credentials = result.get("credentials") or []
            first = dict(original_credentials[0]) if original_credentials and isinstance(original_credentials[0], dict) else {}
            first.update({
                "credential_name": request.form.get("credential_name", ""),
                "level": request.form.get("credential_level", ""),
                "issuing_organization": request.form.get("credential_issuing_organization", ""),
                "issue_date": request.form.get("credential_issue_date", ""),
            })
            first.pop("certificate_number", None)
            credentials_json = json.dumps([first, *original_credentials[1:]])
        credentials = _load_record_list(credentials_json, "credentials_json")
        _claim_extraction(extraction, started_updated_at, revision)
        db.session.query(LearningCourseRecord).filter_by(
            student_id=user.id, source_document_id=document.id
        ).delete()
        db.session.query(CredentialRecord).filter_by(
            student_id=user.id, source_document_id=document.id
        ).delete()
        for item in courses:
            if not isinstance(item, dict):
                raise ValueError("課程資料格式錯誤")
            course_name = traditionalize_course_name(str(item.get("course_name") or "").strip())
            normalized_name = _normalise_name(course_name)
            if not normalized_name:
                raise ValueError("課程名稱為必填")
            status_mark = str(item.get("status_mark") or "").strip() or None
            if status_mark not in {None, "抵", "免", "補"}:
                raise ValueError("課程狀態只可使用 抵、免、補")
            score = item.get("score")
            if status_mark:
                score = None
            else:
                score = _course_integer(score, "分數", 100)
            makeup_season = str(item.get("makeup_season") or "").strip() or None
            if makeup_season not in {None, "summer", "winter"}:
                raise ValueError("重補修類別只可使用暑期或寒期")
            credits = _course_integer(item.get("credits"), "學分", 99)
            grade_level = str(item.get("grade_level") or "").strip() or None
            if grade_level in {"1", "2", "3", "4", "5"}:
                grade_level += "年級"
            if grade_level and grade_level not in {
                "一年級", "二年級", "三年級", "四年級", "五年級",
                "1年級", "2年級", "3年級", "4年級", "5年級",
            }:
                raise ValueError("修課年級只可使用 一年級 至 五年級（或 1 至 5年級）")
            item.update(course_name=course_name, credits=credits, score=score,
                        grade_level=grade_level, makeup_season=makeup_season,
                        score_band=score_band(score))
            course_year = _course_grade(user, item.get("school_year"), grade_level)
            if student_rules.grade_block_reason(user) is None:
                # 組員確認頁只填年級（grade_level）時，也要檢查不能填比現在高的年級
                student_rules.check_record_year(
                    user, course_year if course_year is not None else grade_number(grade_level))
            db.session.add(LearningCourseRecord(
                student_id=user.id,
                source_document_id=document.id,
                school_year=course_year,
                semester=_course_semester(item.get("semester")),
                grade_level=grade_level,
                course_name=course_name,
                normalized_course_name=normalized_name,
                credits=credits,
                score=score,
                status_mark=status_mark,
                makeup_season=makeup_season,
                confirmation_status="confirmed",
            ))
        for item in credentials:
            if not isinstance(item, dict):
                raise ValueError("證照資料格式錯誤")
            credential_name = str(item.get("credential_name") or "").strip()
            if not credential_name:
                raise ValueError("證照名稱為必填")
            issue_date_text = str(item.get("issue_date") or "").strip()
            try:
                issue_date = date.fromisoformat(issue_date_text) if issue_date_text else None
            except ValueError as exc:
                raise ValueError("製發日期須為有效的西元日期（YYYY-MM-DD）") from exc
            db.session.add(CredentialRecord(
                student_id=user.id,
                source_document_id=document.id,
                credential_name=credential_name,
                issue_date=issue_date,
                level=str(item.get("level") or "").strip() or None,
                issuing_organization=str(item.get("issuing_organization") or "").strip() or None,
                category=str(item.get("category") or "").strip() or None,
                confirmation_status="confirmed",
            ))
        extraction.status = "confirmed"
        extraction.confirmed_at = datetime.now(timezone.utc)
        extraction.confirmed_by_id = user.id
        # Also version legacy drafts after their first confirmation, preventing
        # an old unversioned form from overwriting that student's corrections.
        extraction.result_json = {
            **result, "courses": courses, "credentials": credentials, "draft_revision": uuid4().hex,
        }
        document.status = "confirmed"
        audit_service.record(user, "learning_profile.document_confirm", "source_document", document.id,
                             detail={"course_count": len(courses), "credential_count": len(credentials)})
        db.session.commit()
    except (TypeError, ValueError) as exc:
        db.session.rollback()
        return str(exc), 400
    saved = [f"{len(courses)} 門課程" if courses else "", f"{len(credentials)} 張證照" if credentials else ""]
    flash_done("已儲存 " + ("、".join(part for part in saved if part) or "確認結果") + "。", user, program, before)
    return redirect(next_path or _profile_page_url(document.document_type))


def _record_form_values(user):
    """讀取並檢查活動／競賽／服務學習／幹部經歷的表單；有錯時丟出 ValueError。"""
    title = request.form.get("title", "").strip()
    category = request.form.get("category", "").strip()
    if not title:
        raise ValueError("請填寫名稱")
    if category not in EXPERIENCE_CATEGORIES:
        raise ValueError("請選擇類別：活動、競賽、服務學習或幹部經歷")
    try:
        raw_year = request.form.get("school_year", "").strip()
        school_year = int(raw_year) if raw_year else None
        raw_semester = request.form.get("semester", "").strip()
        semester = int(raw_semester) if raw_semester else None
    except ValueError as exc:
        raise ValueError("年級與學期請填數字") from exc
    if school_year is not None and not (1 <= school_year <= 5 or 100 <= school_year <= 200):
        raise ValueError("年級請填 1～5，或民國學年度（例如 113）")
    if semester not in (None, 1, 2):
        raise ValueError("學期只能是上學期或下學期")
    student_rules.check_record_year(user, school_year)
    return {
        "title": title,
        "category": category,
        "school_year": school_year,
        "semester": semester,
        "description": request.form.get("description", "").strip(),
    }


def _record_status():
    """表單按「儲存並確認」是 confirmed；只按「儲存」是 draft（內容改過要重新確認）。"""
    return "confirmed" if request.form.get("confirm") else "draft"


def _render_record_form(user, portfolio=None, values=None, error=None, next_path=None):
    """新增與編輯共用同一個表單頁（student_portfolio_form.html）。"""
    return render_template(
        "student_portfolio_form.html",
        user=user,
        portfolio=portfolio,
        values=values,
        categories=EXPERIENCE_CATEGORIES,
        category_labels=CATEGORY_LABELS,
        error=error,
        next_path=next_path,
        locked_message=review_snapshot_service.LOCKED_MESSAGE,
    ), (400 if error else 200)


@student_bp.get("/student/portfolio")
@student_bp.post("/student/portfolio")
@role_required("student")
def portfolio_list():
    user = get_current_user()
    if request.method == "POST":
        next_path = safe_next(request.form.get("next"))
        program = target_program(next_path)
        before = readiness(user, program)
        try:
            values = _record_form_values(user)
        except ValueError as exc:
            return _render_record_form(user, values=request.form, error=str(exc), next_path=next_path)
        db.session.add(Portfolio(student_id=user.id, status=_record_status(), **values))
        db.session.commit()
        flash_done(f"已新增「{values['title']}」。", user, program, before)
        return redirect(next_path or url_for("student.portfolio_list", added=values["category"]))
    records = Portfolio.active().filter_by(student_id=user.id).order_by(Portfolio.created_at.desc()).all()
    return render_template(
        "student_portfolio.html",
        user=user,
        grouped={key: [r for r in records if r.category == key] for key in EXPERIENCE_CATEGORIES},
        legacy=[r for r in records if r.category not in EXPERIENCE_CATEGORIES],
        unconfirmed_count=sum(1 for r in records if r.status == "draft"),
        categories=EXPERIENCE_CATEGORIES,
        category_labels=CATEGORY_LABELS,
        record_state=portfolio_state,
        fit=build_activity_fit(user, [r for r in records if r.category in EXPERIENCE_CATEGORIES]),
    )


@student_bp.get("/student/portfolio/new")
@role_required("student")
def portfolio_new():
    return _render_record_form(get_current_user(), values={"category": request.args.get("category", "")},
                               next_path=safe_next(request.args.get("next")))


@student_bp.get("/student/portfolio/<int:portfolio_id>/edit")
@student_bp.post("/student/portfolio/<int:portfolio_id>/edit")
@role_required("student")
def portfolio_edit(portfolio_id):
    user = get_current_user()
    portfolio = owned_portfolio(portfolio_id, user)
    if request.method == "POST":
        try:
            values = _record_form_values(user)
        except ValueError as exc:
            return _render_record_form(user, portfolio, values=request.form, error=str(exc))
        for key, value in values.items():
            setattr(portfolio, key, value)
        # 內容改過就要重新確認（舊流程 submitted 的也一樣），未確認的不會進自傳
        portfolio.status = _record_status()
        db.session.commit()
        return redirect(url_for("student.portfolio_list"))
    return _render_record_form(user, portfolio, values=portfolio)


@student_bp.post("/student/portfolio/<int:portfolio_id>/confirm")
@role_required("student")
def portfolio_confirm(portfolio_id):
    """學生確認這筆經歷內容正確；確認過的經歷才會被 AI 寫進自傳。"""
    user = get_current_user()
    portfolio = owned_portfolio(portfolio_id, user)
    if portfolio.status == "draft":
        portfolio.status = "confirmed"
        audit_service.record(user, "portfolio.confirm", "portfolio", portfolio.id)
        db.session.commit()
    return redirect(url_for("student.portfolio_list", confirmed=1))


@student_bp.post("/student/portfolio/<int:portfolio_id>/delete")
@role_required("student")
def portfolio_delete(portfolio_id):
    """刪除先標記 deleted_at，資料列與檔案都保留（規格 M10）；送審過的不能刪。"""
    user = get_current_user()
    portfolio = owned_portfolio(portfolio_id, user)
    if review_snapshot_service.is_submitted(portfolio):
        audit_service.record(user, "portfolio.delete_blocked", "portfolio", portfolio.id, commit=True)
        return redirect(url_for("student.portfolio_edit", portfolio_id=portfolio.id, locked=1))
    now = datetime.now(timezone.utc)
    evidence = list(portfolio.evidence_items)
    for item in evidence:
        item.deleted_at = now
    portfolio.deleted_at = now
    audit_service.record(user, "portfolio.delete", "portfolio", portfolio.id)
    db.session.commit()
    for item in evidence:  # 檔案也只標記，不直接永久刪除（V2 第 7 頁）
        if item.file_path:
            storage_service.mark_deleted(item.file_path, reason="student_deleted_portfolio")
    return redirect(url_for("student.portfolio_list", deleted=1))


@student_bp.post("/student/portfolio/<int:portfolio_id>/submit")
@role_required("student")
def portfolio_submit(portfolio_id):
    portfolio = owned_portfolio(portfolio_id, get_current_user())
    submission = create_submission_snapshot(portfolio, get_current_user())
    portfolio.status = "submitted"
    db.session.add(submission)
    db.session.commit()
    return redirect(url_for("student.portfolio_list"))


@student_bp.post("/student/portfolio/<int:portfolio_id>/evidence")
@role_required("student")
def evidence_upload(portfolio_id):
    portfolio = owned_portfolio(portfolio_id, get_current_user())
    external_url = request.form.get("external_url", "").strip()
    if external_url:
        parsed = urlparse(external_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return "連結必須是 http 或 https 網址", 400
        link_name = request.form.get("link_name", "").strip() or external_url
        link = PortfolioEvidence(
            portfolio_id=portfolio.id,
            evidence_type="link",
            display_name=link_name,
            external_url=external_url,
        )
        db.session.add(link)
        db.session.flush()
        audit_service.record(get_current_user(), "evidence.upload", "portfolio_evidence", link.id)
        db.session.commit()
        return redirect(url_for("student.portfolio_edit", portfolio_id=portfolio.id))
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return "file is required", 400
    try:
        safe_name = validate_upload_filename(uploaded.filename, current_app.config["ALLOWED_UPLOAD_EXTENSIONS"])
    except ValueError as exc:
        return str(exc), 400
    location = storage_service.save(uploaded.read(), owner_id=get_current_user().id, folder="", filename=safe_name)
    evidence = PortfolioEvidence(portfolio_id=portfolio.id, evidence_type="file", display_name=safe_name, file_path=location)
    db.session.add(evidence)
    db.session.flush()
    audit_service.record(get_current_user(), "evidence.upload", "portfolio_evidence", evidence.id)
    db.session.commit()
    return redirect(url_for("student.portfolio_edit", portfolio_id=portfolio.id))


def _owned_evidence_or_404(evidence_id):
    evidence = db.session.get(PortfolioEvidence, evidence_id)
    if not evidence or evidence.deleted_at:
        abort(404)
    owned_portfolio(evidence.portfolio_id, get_current_user())
    if evidence.external_url:
        return redirect(evidence.external_url)
    if not storage_service.exists(evidence.file_path):
        abort(404)
    return evidence


@student_bp.get("/student/evidence/<int:evidence_id>")
@role_required("student")
def evidence_download(evidence_id):
    evidence = _owned_evidence_or_404(evidence_id)
    return send_file(storage_service.local_path(evidence.file_path).resolve(), as_attachment=True,
                     download_name=evidence.display_name)


@student_bp.get("/student/evidence/<int:evidence_id>/view")
@role_required("student")
def evidence_view(evidence_id):
    """在瀏覽器直接顯示圖片或 PDF（規則見 services/file_preview.py）。"""
    evidence = _owned_evidence_or_404(evidence_id)
    return inline_file(evidence.file_path, evidence.display_name)


@student_bp.post("/student/evidence/<int:evidence_id>/delete")
@role_required("student")
def evidence_delete(evidence_id):
    user = get_current_user()
    evidence = db.session.get(PortfolioEvidence, evidence_id)
    if not evidence or evidence.deleted_at:
        abort(404)
    portfolio = owned_portfolio(evidence.portfolio_id, user)
    if review_snapshot_service.is_submitted(portfolio):
        audit_service.record(user, "evidence.delete_blocked", "portfolio_evidence", evidence.id, commit=True)
        return redirect(url_for("student.portfolio_edit", portfolio_id=portfolio.id, locked=1))
    evidence.deleted_at = datetime.now(timezone.utc)  # 只標記，資料列保留（規格 M10）
    audit_service.record(user, "evidence.delete", "portfolio_evidence", evidence.id)
    db.session.commit()
    if evidence.file_path:
        storage_service.mark_deleted(evidence.file_path, reason="student_deleted_evidence")
    return redirect(url_for("student.portfolio_edit", portfolio_id=portfolio.id))


# ---------- 主線後半：目標校系、缺件比對、請導師確認、產出備審資料 ----------

def _blocked(user, reason):
    """不能使用某個功能時的說明頁（年級還沒到、或還不知道入學學年度）。"""
    back = urlparse(request.referrer).path if request.referrer else ""
    return render_template(
        "student_blocked.html", user=user, reason=reason, back=back or url_for("student.target_list"),
    ), 403


def _published_program_or_404(program_id):
    program = db.session.get(AdmissionProgram, program_id)
    if not program or program.status != "published":
        abort(404)
    return program


def _selected_target_or_404(user, program_id):
    program = _published_program_or_404(program_id)
    if not StudentTarget.query.filter_by(student_id=user.id, rule_version_id=program.id).first():
        abort(404)
    return program


@student_bp.get("/student/targets")
@student_bp.post("/student/targets")
@role_required("student")
def target_list():
    user = get_current_user()
    error = None
    if request.method == "POST":
        try:
            program = _published_program_or_404(int(request.form.get("program_id", "")))
        except ValueError:
            abort(400)
        reason = student_rules.grade_block_reason(user)
        if reason:
            return _blocked(user, reason)
        if not StudentTarget.query.filter_by(student_id=user.id, rule_version_id=program.id).first():
            slots = student_rules.target_slots(user)
            if slots["limit"] is not None and slots["used"] >= slots["limit"]:
                error = f"目標校系同時最多 {slots['limit']} 所，請先取消一所再加入新的。"
            else:
                db.session.add(StudentTarget(student_id=user.id, rule_version_id=program.id))
                audit_service.record(user, "student_target.add", "admission_program", program.id)
                db.session.commit()
        if not error:
            return redirect(url_for("student.target_gap", program_id=program.id))
    journey = build_journey(user)
    selected = {t.rule_version_id for t in StudentTarget.query.filter_by(student_id=user.id).all()}
    # 已選的目標放最上面，其他照原本順序（10-27 實測問題 14）
    programs = sorted(published_programs(), key=lambda p: p.id not in selected)
    school_links = load_school_links()
    return render_template(
        "student_targets.html",
        user=user,
        programs=programs,
        selected=selected,
        slots=student_rules.target_slots(user),
        cancelled_programs=_cancelled_autobiography_programs(user),
        gaps={p.id: analyze_gap(user, p, journey) for p in programs},
        links={p.id: admission_links(p, school_links) for p in programs},
        focus=focus_view(user, journey),
        error=error,
    ), (400 if error else 200)


@student_bp.get("/student/matching")
@role_required("student")
def matching():
    """A3 媒合排序：全部正式校系依可不可報與契合度排序，每一間都寫理由。可用科系、學制、是否可報篩選。"""
    user = get_current_user()
    journey = build_journey(user)
    has_confirmed_data = any(journey["confirmed_totals"].values())
    selected = {t.rule_version_id for t in StudentTarget.query.filter_by(student_id=user.id).all()}
    active_filters = {key: request.args.get(key, "").strip() for key in ("department", "level", "eligible")}
    rows = rank_programs(user, published_programs(), journey=journey)
    total = len(rows)
    if active_filters["department"]:
        rows = [r for r in rows if active_filters["department"] in (r["program"].department_name or "")]
    if active_filters["level"]:
        rows = [r for r in rows if r["program"].admission_category == active_filters["level"]]
    if active_filters["eligible"]:
        rows = [r for r in rows if r["status"] == active_filters["eligible"]]
    # 同一報考狀態內以已確認資料算出的準備度排序；同校校系收在一起。
    rows.sort(key=lambda r: ({"eligible": 0, "needs_check": 1, "ineligible": 2}[r["status"]],
                             r["fit"] is None, -(r["fit"] or 0)))
    school_groups = []
    by_school = {}
    for row in rows:
        name = row["program"].school_name
        if name not in by_school:
            group = {"name": name, "rows": [], "best": row}
            by_school[name] = group
            school_groups.append(group)
        by_school[name]["rows"].append(row)
    filters = {category: MatchFilterOption.active_options(category) for category in ("department", "level", "eligible")}
    chart = "column" if request.args.get("chart") == "column" else "bar"
    return render_template(
        "student_matching.html",
        user=user,
        rows=rows,
        school_groups=school_groups,
        total=total,
        selected=selected,
        category_labels=ALL_LABELS,
        filters=filters,
        active_filters={k: v for k, v in active_filters.items() if v},
        chart=chart,
        has_confirmed_data=has_confirmed_data,
    )


@student_bp.get("/student/matching/<int:program_id>")
@role_required("student")
def matching_detail(program_id):
    """排序細項整頁（手機用）：一律以登入者為準，不接受網址帶學生編號。"""
    user = get_current_user()
    program = _published_program_or_404(program_id)
    row = rank_programs(user, [program])[0]
    selected = {t.rule_version_id for t in StudentTarget.query.filter_by(student_id=user.id).all()}
    return render_template(
        "student_matching_detail.html",
        user=user,
        row=row,
        selected=selected,
        category_labels=ALL_LABELS,
    )


@student_bp.get("/student/schedule")
@role_required("student")
def schedule():
    """招生時程：二技技優甄審的全國日程，以及每個目標校系該看哪裡。"""
    user = get_current_user()
    targets = StudentTarget.query.filter_by(student_id=user.id).order_by(StudentTarget.selected_at).all()
    school_links = load_school_links()
    return render_template(
        "student_schedule.html",
        user=user,
        skill=latest_timeline("skill_review"),
        checked_on=CHECKED_ON,
        targets=[{"program": t.program, "schedule": timeline(t.program), "channel_label": channel_label(t.program),
                  "links": admission_links(t.program, school_links)} for t in targets],
    )


@student_bp.post("/student/agent/advise")
@role_required("student")
def agent_advise():
    """升學 Agent：排序校系，並為已選的目標校系準備自傳草稿。背景執行，結果頁邊做邊顯示每一步。"""
    from app.services.agent_advisor import start_advisor
    config = current_app.config
    # 測試與 5013 記憶體展示站（所有請求共用一條 SQLite 連線）照舊同步執行
    background = config.get("AGENT_BACKGROUND", not (current_app.testing or config.get("LOCAL_DEMO_MODE")))
    task_id = start_advisor(get_current_user(), background=background)
    return redirect(url_for("student.agent_run", task_id=task_id))


def _own_agent_task(task_id):
    task = db.session.get(AgentTask, task_id)
    if not task or task.requester_id != get_current_user().id or task.task_type != "agent_advisor":
        abort(404)
    return task


@student_bp.get("/student/agent/runs/<int:task_id>")
@role_required("student")
def agent_run(task_id):
    from app.services.agent_advisor import TOOL_LINEUP
    from app.services.agent_engine import expire_if_stale
    task = expire_if_stale(_own_agent_task(task_id))
    return render_template("student_agent_run.html", user=get_current_user(), task=task, run=task.result_json or {},
                           lineup=TOOL_LINEUP)


@student_bp.get("/student/agent/runs/<int:task_id>/progress")
@role_required("student")
def agent_run_progress(task_id):
    from app.services.agent_engine import progress
    return jsonify(progress(_own_agent_task(task_id)))


@student_bp.post("/student/targets/<int:program_id>/remove")
@role_required("student")
def target_remove(program_id):
    user = get_current_user()
    if StudentTarget.query.filter_by(student_id=user.id, rule_version_id=program_id).delete():
        audit_service.record(user, "student_target.remove", "admission_program", program_id)
    db.session.commit()
    return redirect(url_for("student.target_list"))


@student_bp.get("/student/targets/<int:program_id>")
@role_required("student")
def target_gap(program_id):
    user = get_current_user()
    program = _selected_target_or_404(user, program_id)
    journey = build_journey(user)
    targets = StudentTarget.query.filter_by(student_id=user.id).order_by(StudentTarget.selected_at).all()
    gap = analyze_gap(user, program, journey)
    review = latest_review(user, program)
    autobiography = autobiography_service.latest_draft(user, program)
    return render_template(
        "student_gap.html",
        user=user,
        program=program,
        gap=gap,
        chapters=chapter_order(program),
        targets=[t.program for t in targets],
        review=review,
        review_timeline=review_timeline(user, program),
        autobiography=autobiography,
        download_checklist=download_checklist(user, program, gap, review, autobiography),
        labels=ALL_LABELS,
    )


@student_bp.post("/student/targets/<int:program_id>/review")
@role_required("student")
def target_request_review(program_id):
    user = get_current_user()
    program = _selected_target_or_404(user, program_id)
    reason = student_rules.review_block_reason(user) or student_rules.over_limit_reason(user)
    if reason:
        return _blocked(user, reason)
    review_snapshot_service.request_review(user, program)
    return redirect(url_for("student.target_gap", program_id=program.id, sent=1))


@student_bp.get("/student/targets/<int:program_id>/package.docx")
@role_required("student")
def target_package(program_id):
    user = get_current_user()
    program = _selected_target_or_404(user, program_id)
    return send_file(
        build_package_docx(user, program),
        as_attachment=True,
        download_name=f"備審資料-{program.school_name}-{program.department_name}.docx",
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


# ---------- AI 自傳小幫手：先回答幾題，AI 再依資料與校系加權寫草稿 ----------

def _autobiography_program(user, program_id):
    """自傳要針對一個目標校系寫；沒指定就用第一個目標校系。"""
    targets = [t.program for t in StudentTarget.query.filter_by(student_id=user.id).order_by(StudentTarget.selected_at)]
    if not targets:
        return None, []
    if program_id:
        program = next((p for p in targets if p.id == program_id), None)
        if not program:
            abort(404)
        return program, targets
    return targets[0], targets


def _render_autobiography(user, program, targets, error=None, answers=None, status=503, stale=None):
    """stale：用舊頁面存檔被擋下時，顯示最新版，並把沒存到的文字列出來（不讓學生白打）。"""
    draft = autobiography_service.latest_draft(user, program) if program else None
    asking = program and (not draft or request.args.get("redo") or error) and not stale
    paragraph_reviews = []
    if draft:
        content = draft.content_json
        paragraph_reviews = autobiography_review.review_paragraphs(
            content.get("paragraphs", []), content.get("facts", []), content.get("answers", {}),
        )
    return render_template(
        "student_autobiography.html",
        user=user,
        program=program,
        targets=targets,
        draft=draft,
        asking=asking,
        questions=autobiography_service.QUESTIONS,
        answers=answers or (draft.content_json.get("answers", {}) if draft else {}),
        facts=autobiography_service.build_facts(user, program) if program else None,
        version=autobiography_service.version_of(draft) if draft else None,
        backup_label=autobiography_backup.status_label(draft) if draft else None,
        paragraph_reviews=paragraph_reviews,
        school_turns=ai_quota_service.remaining(user) if ai_ready() else None,
        review_note=student_rules.review_open_note(user),
        error=error,
        stale=stale,
    ), (409 if stale else status if error else 200)


@student_bp.get("/student/autobiography")
@role_required("student")
def autobiography():
    user = get_current_user()
    program, targets = _autobiography_program(user, request.args.get("program_id", type=int))
    return _render_autobiography(user, program, targets)


@student_bp.post("/student/autobiography/generate")
@role_required("student")
def autobiography_generate():
    user = get_current_user()
    program, targets = _autobiography_program(user, request.form.get("program_id", type=int))
    if not program:
        return redirect(url_for("student.target_list"))
    reason = student_rules.autobiography_block_reason(user)
    if reason:
        return _blocked(user, reason)
    answers = {key: request.form.get(key, "") for key, _, _ in autobiography_service.QUESTIONS}
    # 學生自己的金鑰：只放在這個函式的變數裡用一次，不存資料庫、不放 session、不放網址
    own_key = "" if current_app.config.get("LOCAL_DEMO_MODE") else request.form.get("own_api_key", "").strip() or None
    used_own_key = bool(own_key)
    try:
        # 學校金鑰每人每天有次數限制；先扣，AI 失敗時 rollback 就會退回
        if not own_key and ai_ready():
            ai_quota_service.consume(user)
        output = autobiography_service.generate_draft(user, program, answers, api_key=own_key)
        audit_service.record(user, "autobiography.generate", "learning_profile_output", output.id,
                             detail={"program_id": program.id, "provider": output.content_json.get("provider")},
                             commit=True)
    except ai_quota_service.QuotaExceeded as exc:
        return _render_autobiography(user, program, targets, error=str(exc), answers=answers, status=429)
    except AIUnavailable as exc:
        db.session.rollback()
        return _render_autobiography(user, program, targets, error=str(exc), answers=answers)
    finally:
        own_key = None
    return redirect(url_for("student.autobiography", program_id=program.id,
                            used_own_key=1 if used_own_key else None))


@student_bp.post("/student/autobiography/<int:output_id>/save")
@role_required("student")
def autobiography_save(output_id):
    user = get_current_user()
    output = db.session.get(LearningProfileOutput, output_id)
    if not output or output.output_type != autobiography_service.OUTPUT_TYPE:
        abort(404)
    if output.student_id != user.id:
        abort(403)
    count = len(output.content_json.get("paragraphs", []))
    texts = [request.form.get(f"paragraph_{i}", "") for i in range(count)]
    try:
        saved = autobiography_service.save_edits(output, texts, user)
    except autobiography_service.StaleVersion as exc:
        program, targets = _autobiography_program(user, output.content_json["program_id"])
        return _render_autobiography(user, program, targets, stale={"message": str(exc), "texts": texts,
                                                                    "paragraphs": output.content_json["paragraphs"]})
    audit_service.record(user, "autobiography.save", "learning_profile_output", saved.id, commit=True)
    return redirect(url_for("student.autobiography", program_id=output.content_json["program_id"], saved=1))


@student_bp.get("/student/autobiography/versions")
@role_required("student")
def autobiography_versions():
    """自傳的所有版本：誰在什麼時候改的、和上一版差在哪裡。不能刪除。"""
    user = get_current_user()
    program_id = request.args.get("program_id", type=int)
    # 取消目標後仍可以看那個校系的自傳紀錄（唯讀，主持人 2026-10-10）
    program = next((p for p in _cancelled_autobiography_programs(user) if p.id == program_id), None)
    cancelled = program is not None
    if not program:
        program, targets = _autobiography_program(user, program_id)
    if not program:
        return redirect(url_for("student.target_list"))
    return render_template("autobiography_versions.html", user=user, program=program, cancelled=cancelled,
                           **_version_view(user, program, request.args.get("v", type=int)))


def _cancelled_autobiography_programs(user):
    """學生取消了目標、但留有自傳版本的校系。"""
    chosen = {t.rule_version_id for t in StudentTarget.query.filter_by(student_id=user.id)}
    outputs = LearningProfileOutput.query.filter_by(student_id=user.id, output_type=autobiography_service.OUTPUT_TYPE)
    ids = {o.content_json.get("program_id") for o in outputs} - chosen - {None}
    return AdmissionProgram.query.filter(AdmissionProgram.id.in_(ids)).all() if ids else []


def _version_view(student, program, selected_id):
    """版本頁共用的資料（學生和導師都會用）。"""
    versions = list(reversed(autobiography_service.versions(student, program)))
    if not versions:
        return {"versions": [], "selected": None, "diff": [], "editors": {}}
    selected = next((v for v in versions if v.id == selected_id), versions[0])
    by_id = {v.id: v for v in versions}
    previous = by_id.get(selected.content_json.get("based_on"))
    if previous is None:
        older = [v for v in versions if v.id < selected.id]
        previous = older[0] if older else None
    editor_ids = {v.content_json.get("editor_id") for v in versions} - {None}
    editors = {u.id: u for u in User.query.filter(User.id.in_(editor_ids)).all()} if editor_ids else {}
    return {
        "versions": versions,
        "selected": selected,
        "previous": previous,
        "diff": autobiography_service.version_diff(selected, previous),
        "editors": editors,
        "version_of": autobiography_service.version_of,
        "backup_label": autobiography_backup.status_label,
    }
