from hashlib import sha256
from io import BytesIO
import json
import math
import re
from datetime import date, datetime, timezone
from urllib.parse import urlparse
from uuid import uuid4
from urllib.parse import urlparse

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for

from app.extensions import db
from app.models import (
    AdmissionProgram,
    AgentTask,
    AuditLog,
    CredentialRecord,
    DocumentExtraction,
    GraduationCase,
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
from app.routes.graduation import sync_after_commit
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
from app.services.gap_service import ALL_LABELS, analyze_gap, chapter_order, student_evidence
from app.services.admission_links import admission_links, load_school_links
from app.services import school_directory
from app.services.admission_schedule import CHECKED_ON, channel_label, latest_timeline, timeline
from app.services.matching_service import rank_programs
from app.services.transfer_exam import is_transfer
from app.services import graduation_check_service

from app.services.gap_checklist import download_checklist, review_timeline
from app.services.journey_service import CATEGORY_LABELS, EXPERIENCE_CATEGORIES, build_journey
from app.services.package_service import build_package_docx, latest_review
from app.services.file_preview import inline_file
from app.services.record_status import learning_profile_state, portfolio_state
from app.services import ai_quota_service, audit_service, autobiography_backup, autobiography_review, autobiography_service, ocr_queue, package_exclusion, review_snapshot_service, storage_service, student_rules
from app.services.gemini_client import AIUnavailable, ai_ready
from app.services.course_review_presentation import (
    build_course_review_groups,
    prepare_course_review_rows,
    traditionalize_course_name,
)


MATCHING_PAGE_SIZE = 20  # 推薦排序一次先列幾間，按「看更多」再多這麼多間

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


def _blank_score(course):
    """OCR 沒讀到成績（空白或標「待確認」）：鎖定成績時仍允許學生補上。"""
    value = course.get("score") if isinstance(course, dict) else None
    return value is None or str(value).strip() == "" or "待確認" in str(value)


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


@student_bp.get("/student/graduation-check")
@role_required("student")
def graduation_check():
    user = get_current_user()
    cases = (GraduationCase.query.filter_by(student_id=user.id)
             .order_by(GraduationCase.id.desc()).all())
    item_cases = {}
    for case in cases:  # 每個檢核項目只掛最新的缺口案件
        if case.case_type == "gap":
            item_cases.setdefault(case.item, case)
    curriculum = graduation_check_service.load_curriculum()
    assessment = graduation_check_service.assess(user, curriculum=curriculum)
    from app.services import check_dates, semester_warning
    return render_template("student_graduation_check.html", user=user,
                           warnings=semester_warning.build(user, curriculum=curriculum),
                           warning_labels=semester_warning.LEVEL_LABELS, warning_note=semester_warning.NOTE,
                           countdown=check_dates.countdown(assessment["stage"]),
                           result=graduation_check_service.evaluate(user, curriculum=curriculum),
                           assessment=assessment,
                           overall=graduation_check_service.overall_result(assessment),
                           item_cases=item_cases,
                           other_cases=[c for c in cases if c.case_type != "gap"],
                           check=graduation_check_service)


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


@student_bp.get("/student/journey.docx")
@role_required("student")
def journey_docx():
    """評審意見 7：把五年資料匯出成可以修改的 Word。"""
    from app.services import journey_docx as exporter
    user = get_current_user()
    audit_service.record(user, "student.journey_docx", "user", user.id, commit=True)
    return send_file(
        exporter.build(user), as_attachment=True, download_name=f"我的五年學習歷程-{user.display_name}.docx",
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


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
        photo_check=_photo_check(document),
        next_path=safe_next(request.args.get("next")),
        review_result=review_result,
        review_courses=review_courses,
        review_groups=build_course_review_groups(review_courses),
    )


def _photo_check(document):
    """證照、成績單照片模糊或歪斜時提醒重拍（評審意見 3）；只提醒不擋。讀不到檔案就不提醒。"""
    from app.services import photo_quality
    try:
        file_bytes = storage_service.read_bytes(document.file_path)
    except Exception:
        return None
    result = photo_quality.check(file_bytes, document.display_name)
    return result if result and result["message"] else None


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

def _same_term_course(user, fields):
    """已確認的成績中，同一年級、同一學期、同一門課的那一筆；沒有年級或學期時不比對，回傳 None。"""
    probe = LearningCourseRecord(school_year=fields["school_year"], semester=fields["semester"],
                                 grade_level=fields["grade_level"], course_name=fields["course_name"])
    profile = user.student_profile
    admission_year = profile.admission_year if profile else None
    key = graduation_check_service.course_term_key(probe, admission_year)
    if key is None:
        return None
    candidates = LearningCourseRecord.query.filter_by(
        student_id=user.id, semester=fields["semester"], confirmation_status="confirmed").all()
    for course in candidates:
        if graduation_check_service.course_term_key(course, admission_year) == key:
            return course
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
                    if all_fields_locked or (field == "score" and not scores_unlocked and not _blank_score(original)):
                        item[field] = original.get(field)
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
                # 空白成績（原本就沒讀到）可以直接補，不必先解鎖（11-04 實測）
                if isinstance(item, dict) and not (index < len(original_courses) and _blank_score(original_courses[index])):
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
            fields = dict(
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
            )
            existing = _same_term_course(user, fields)
            if existing is not None:
                # 重複上傳成績單（例如專四的歷年成績單又列出專三的課）：更新原本那一筆，不再新增
                for key, value in fields.items():
                    setattr(existing, key, value)
            else:
                db.session.add(LearningCourseRecord(student_id=user.id, **fields))
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
        return render_template("student_input_error.html", message=str(exc), back_url=url_for("student.learning_profile_document_review", document_id=document.id)), 400
    # 確認已提交；同步失敗只回復同步本身，不影響確認結果
    sync_after_commit(user)
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
    story = {}
    for key, label, limit in STORY_FIELDS:
        value = request.form.get(key, "").strip()
        if len(value) > limit:
            raise ValueError(f"{label}最多 {limit} 字")
        story[key] = value or None
    if story["domain_tags"]:
        tags = [tag for tag in re.split(r"[、,，;；/\s]+", story["domain_tags"]) if tag]
        story["domain_tags"] = "、".join(dict.fromkeys(tags))[:200] or None
    return {
        "title": title,
        "category": category,
        "school_year": school_year,
        "semester": semester,
        "description": request.form.get("description", "").strip(),
        **story,
    }


# 經歷的四個細節欄位（key, 名稱, 字數上限），表單與錯誤訊息共用
STORY_FIELDS = (("role", "我負責的部分", 1000), ("achievement", "數字成果", 300),
                 ("learned", "學到什麼", 1000), ("domain_tags", "相關領域", 200))


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
        unconfirmed_count=sum(1 for r in records if r.status != "confirmed"),
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
    if portfolio.status != "confirmed":
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
    # 送件狀態記在 submission；不能把草稿送出誤視為學生已確認。
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
        return render_template("student_input_error.html", message="檔案格式不支援，請選擇允許的格式後重試。", back_url=url_for("student.portfolio_edit", portfolio_id=portfolio.id)), 400
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


def _home_major_known(user):
    class_name = user.student_profile.class_name if user.student_profile else ""
    return any(name in (class_name or "") for name in ("資管科", "資訊管理科"))


def _is_home_major(program, known):
    department = (program.department_name or "").split("（", 1)[0].split("(", 1)[0].replace(" ", "")
    return known and department in {"資管系", "資訊管理系", "資訊管理學系"}


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
            db.session.add(StudentTarget(student_id=user.id, rule_version_id=program.id))
            audit_service.record(user, "student_target.add", "admission_program", program.id)
            db.session.commit()
        if not error:
            return redirect(url_for("student.target_gap", program_id=program.id))
    journey = build_journey(user)
    evidence = student_evidence(user, journey)
    selected = {t.rule_version_id for t in StudentTarget.query.filter_by(student_id=user.id).all()}
    all_programs = published_programs()
    track = "transfer" if request.args.get("track") == "transfer" else "twotech"
    track_counts = {"twotech": sum(not is_transfer(p) for p in all_programs),
                    "transfer": sum(is_transfer(p) for p in all_programs)}
    programs = [p for p in all_programs if is_transfer(p) == (track == "transfer")]
    slots = student_rules.target_slots(user)
    track_targets = [t for t in slots["current"] if is_transfer(t.program) == (track == "transfer")]
    old_targets = [t for t in slots["old"] if is_transfer(t.program) == (track == "transfer")]
    all_program_count = len(programs)
    program_options = sorted(programs, key=lambda p: (p.school_name, p.department_name, p.admission_category or ""))
    channels = {p.id: channel_label(p) for p in programs}
    entry_grades = {
        p.id: {"2": "二年級", "3": "三年級"}.get((p.program_code or "").rsplit("-", 1)[-1], "")
        if p.admission_category == "插大（轉學考）" else ""
        for p in programs
    }
    gaps = {p.id: analyze_gap(user, p, journey, evidence) for p in programs}
    # 單一排行：全部校系依準備度由高到低；本科系只加標籤，不再分組排在前面（老師看第一名要能直接對上準備度）。
    # 科別不明時不猜測本科系。
    major_known = _home_major_known(user)

    def is_home_major(program):
        return _is_home_major(program, major_known)

    def readiness_order(program):
        return (gaps[program.id]["readiness"] is None,
                -(gaps[program.id]["readiness"] or 0),
                program.school_name, program.department_name, program.id)

    selected_programs = sorted((p for p in program_options if p.id in selected), key=readiness_order)

    major_filter = request.args.get("major", "all")
    if major_filter not in {"all", "home", "other"} or not major_known:
        major_filter = "all"
    program_filter = request.args.get("program_id", "")
    program_filter = program_filter if program_filter.isdigit() and any(str(p.id) == program_filter for p in programs) else ""
    if major_filter == "home":
        programs = [p for p in programs if is_home_major(p)]
    elif major_filter == "other":
        programs = [p for p in programs if not is_home_major(p)]
    if program_filter:
        programs = [p for p in programs if str(p.id) == program_filter]
    # 依地區、學校找（2026-11-13 導師：選校系要分北中南）：地圖與區域按鈕用篩選前的校系，才看得到全部學校
    schools = school_directory.by_name()
    map_points = school_directory.map_points(programs, schools)
    region_filter = request.args.get("region", "")
    region_filter = region_filter if region_filter in school_directory.REGIONS else ""
    school_filter = request.args.get("school", "").strip()
    school_filter = school_filter if school_filter in schools else ""
    region_counts = {region: sum(1 for point in map_points if point["region"] == region)
                     for region in school_directory.REGIONS}
    if region_filter:
        programs = [p for p in programs if schools.get(p.school_name) and schools[p.school_name].region == region_filter]
    if school_filter:
        programs = [p for p in programs if p.school_name == school_filter]
    school_card = next((point for point in map_points if point["school"].name == school_filter), None)
    search_query = request.args.get("q", "").strip()[:60]
    if search_query:
        needle = "".join(search_query.split()).lower()
        programs = [p for p in programs
                    if needle in "".join(f"{p.school_name}{p.department_name}{channels[p.id]}{p.admission_category or ''}".split()).lower()]

    programs.sort(key=readiness_order)
    home_program_ids = {p.id for p in programs if is_home_major(p)}
    program_groups = [{"label": "全部校系（依準備度由高到低）", "programs": programs}]
    school_links = load_school_links()
    return render_template(
        "student_targets.html",
        user=user,
        programs=programs,
        track=track,
        track_counts=track_counts,
        old_targets=old_targets,
        all_program_count=all_program_count,
        program_options=program_options,
        channels=channels,
        entry_grades=entry_grades,
        major_known=major_known,
        major_filter=major_filter,
        program_filter=program_filter,
        search_query=search_query,
        home_program_ids=home_program_ids,
        program_groups=program_groups,
        selected=selected,
        selected_programs=selected_programs,
        slots=student_rules.target_slots(user),
        cancelled_programs=[p for p in _cancelled_autobiography_programs(user)
                            if is_transfer(p) == (track == "transfer")],
        gaps=gaps,
        links={p.id: admission_links(p, school_links) for p in program_options},
        school_links={p.id: school_directory.school_links(p, schools) for p in program_options},
        map_points=map_points,
        region_filter=region_filter,
        school_filter=school_filter,
        region_counts=region_counts,
        regions=[r for r in school_directory.REGIONS if region_counts[r]],
        school_card=school_card,
        map_size=(school_directory.MAP_WIDTH, school_directory.MAP_HEIGHT),
        # 點選地區時放大到那一區（2026-11-13 使用者要求）；圓點跟著縮小，放大後不會變得很大
        map_view_box=school_directory.region_view_box(region_filter) if region_filter else
        f"0 0 {school_directory.MAP_WIDTH} {school_directory.MAP_HEIGHT}",
        map_zoom=(school_directory.MAP_HEIGHT / float(school_directory.region_view_box(region_filter).split()[3]))
        if region_filter else 1,
        focus=focus_view(user, journey, targets=track_targets),
        error=error,
    ), (400 if error else 200)


@student_bp.get("/student/pathways")
@role_required("student")
def pathways():
    """B19、B20：二技、插大、統測進四技三條路並排比較，附法條與官方出處。"""
    from app.services import pathways as pathway_content

    user = get_current_user()
    return render_template(
        "student_pathways.html",
        user=user,
        pathways=pathway_content.build_pathways(url_for("student.target_list", track="twotech"),
                                                url_for("student.transfer_plans")),
        default_status=pathway_content.default_status(student_rules.grade_of(user)),
        checked_on=pathway_content.CHECKED_ON,
        today=date.today(),
    )


def _own_transfer_plan(user, plan_id):
    from app.models import TransferPlan

    plan = db.session.get(TransferPlan, plan_id)
    if not plan or plan.student_id != user.id:
        abort(404)
    return plan


@student_bp.get("/student/transfer-plans")
@student_bp.post("/student/transfer-plans")
@role_required("student")
def transfer_plans():
    """B18 插大準備：學生自填目標校系、簡章、考科與日期，依考期倒數與考科進度算準備度。"""
    from app.models import TransferPlan
    from app.services import transfer_plan as tp

    user = get_current_user()
    error = None
    if request.method == "POST":
        try:
            fields, names = tp.parse_plan_form(request.form)
        except tp.PlanFormError as exc:
            error = str(exc)
        else:
            plan = TransferPlan(student_id=user.id, updated_by_id=user.id, **fields)
            tp.apply_subjects(plan, names)
            db.session.add(plan)
            db.session.flush()
            audit_service.record(user, "transfer_plan.add", "transfer_plan", plan.id)
            db.session.commit()
            return redirect(url_for("student.transfer_plans", _anchor=f"plan-{plan.id}"))
    rows = TransferPlan.query.filter_by(student_id=user.id).order_by(TransferPlan.exam_date.is_(None),
                                                                      TransferPlan.exam_date, TransferPlan.id).all()
    return render_template(
        "student_transfer_plans.html",
        user=user,
        plans=[{"plan": plan, "ready": tp.readiness(plan)} for plan in rows if not plan.archived],
        archived=[plan for plan in rows if plan.archived],
        examples=tp.example_schools(),
        default_year=tp.target_year(),
        error=error,
    )


@student_bp.post("/student/transfer-plans/<int:plan_id>")
@role_required("student")
def transfer_plan_update(plan_id):
    from app.services import transfer_plan as tp

    user = get_current_user()
    plan = _own_transfer_plan(user, plan_id)
    try:
        fields, names = tp.parse_plan_form(request.form)
    except tp.PlanFormError as exc:
        flash(str(exc), "error")
        return redirect(url_for("student.transfer_plans", _anchor=f"plan-{plan.id}"))
    for key, value in fields.items():
        setattr(plan, key, value)
    tp.apply_subjects(plan, names)
    plan.updated_by_id = user.id
    audit_service.record(user, "transfer_plan.update", "transfer_plan", plan.id)
    db.session.commit()
    return redirect(url_for("student.transfer_plans", _anchor=f"plan-{plan.id}"))


@student_bp.post("/student/transfer-plans/<int:plan_id>/progress")
@role_required("student")
def transfer_plan_progress(plan_id):
    from app.services.transfer_plan import clamp_progress

    user = get_current_user()
    plan = _own_transfer_plan(user, plan_id)
    for subject in plan.subjects:
        key = f"progress_{subject.id}"
        if key in request.form:
            subject.progress = clamp_progress(request.form[key])
    plan.updated_by_id = user.id
    db.session.commit()
    return redirect(url_for("student.transfer_plans", _anchor=f"plan-{plan.id}"))


@student_bp.post("/student/transfer-plans/<int:plan_id>/archive")
@role_required("student")
def transfer_plan_archive(plan_id):
    user = get_current_user()
    plan = _own_transfer_plan(user, plan_id)
    plan.archived = True
    audit_service.record(user, "transfer_plan.archive", "transfer_plan", plan.id)
    db.session.commit()
    return redirect(url_for("student.transfer_plans"))


@student_bp.get("/student/matching")
@role_required("student")
def matching():
    """A3 媒合排序：校系依可不可報與準備度排成一張排行，點進去看細項（10-28 導師建議）。
    二技、插大分兩個分頁；可用關鍵字（學校或科系）搜尋，再加科系、學制、是否可報篩選；先列前 20 間，按「看更多」再載入。"""
    user = get_current_user()
    selected = {t.rule_version_id for t in StudentTarget.query.filter_by(student_id=user.id).all()}
    active_filters = {key: request.args.get(key, "").strip() for key in ("department", "level", "eligible", "q")}
    track = "transfer" if request.args.get("track") == "transfer" else "twotech"
    try:
        show = max(MATCHING_PAGE_SIZE, int(request.args.get("show", MATCHING_PAGE_SIZE)))
    except ValueError:
        show = MATCHING_PAGE_SIZE
    ranked = rank_programs(user, published_programs())
    track_counts = {"twotech": sum(1 for r in ranked if not is_transfer(r["program"])),
                    "transfer": sum(1 for r in ranked if is_transfer(r["program"]))}
    rows = [r for r in ranked if is_transfer(r["program"]) == (track == "transfer")]
    total = len(rows)
    major_known = _home_major_known(user)
    major_filter = request.args.get("major", "all")
    if major_filter not in {"all", "home", "other"} or not major_known:
        major_filter = "all"
    if major_filter != "all":
        rows = [r for r in rows if _is_home_major(r["program"], major_known) == (major_filter == "home")]
    rows.sort(key=lambda r: (r["status"] == "ineligible", r["fit"] is None, -(r["fit"] or 0), r["program"].school_name, r["program"].department_name, r["program"].id))
    for row in rows:
        row["home_major"] = _is_home_major(row["program"], major_known)
        row["reasons"] = [reason for reason in row["reasons"] if not (reason.startswith("暫依你的科別") and "排前面" in reason)]
        qualification = row.get("qualification") or {}
        unmatched = [item["reason"] for item in qualification.get("conditions", [])
                     if item.get("required", True) and item.get("status") == "not_matched" and item.get("reason")]
        row["ineligible_reason"] = "；".join(unmatched) if qualification.get("status") == "not_eligible" and unmatched else ("；".join(row["reasons"]) or "請查看資格說明")
    if active_filters["q"]:
        words = active_filters["q"].split()
        rows = [r for r in rows if all(word in f"{r['program'].school_name}{r['program'].department_name}" for word in words)]
    if active_filters["department"]:
        rows = [r for r in rows if active_filters["department"] in (r["program"].department_name or "")]
    if active_filters["level"]:
        rows = [r for r in rows if r["program"].admission_category == active_filters["level"]]
    if active_filters["eligible"]:
        rows = [r for r in rows if r["status"] == active_filters["eligible"]]
    filters = {category: MatchFilterOption.active_options(category) for category in ("department", "level", "eligible")}
    chart = "column" if request.args.get("chart") == "column" else "bar"
    return render_template(
        "student_matching.html",
        user=user,
        rows=rows[:show],
        matched=len(rows),
        more=len(rows) > show,
        show=show,
        total=total,
        track=track,
        track_counts=track_counts,
        selected=selected,
        category_labels=CATEGORY_LABELS,
        filters=filters,
        active_filters={k: v for k, v in active_filters.items() if v},
        chart=chart,
        major_known=major_known,
        major_filter=major_filter,
    )


@student_bp.get("/student/matching/<int:program_id>")
@role_required("student")
def matching_detail(program_id):
    """排序細項整頁（手機用）：一律以登入者為準，不接受網址帶學生編號。"""
    user = get_current_user()
    program = _published_program_or_404(program_id)
    row = rank_programs(user, [program])[0]
    selected = {t.rule_version_id for t in StudentTarget.query.filter_by(student_id=user.id).all()}
    upcoming = (row["schedule"] or {}).get("next")
    days_left = (upcoming["start"].date() - date.today()).days if upcoming and upcoming.get("start") else None
    return render_template(
        "student_matching_detail.html",
        user=user,
        row=row,
        selected=selected,
        days_left=days_left,
        category_labels=CATEGORY_LABELS,
    )


@student_bp.get("/student/schedule")
@role_required("student")
def schedule():
    """招生時程：二技技優甄審的全國日程，以及每個目標校系該看哪裡。"""
    user = get_current_user()
    targets = StudentTarget.query.filter_by(student_id=user.id).order_by(StudentTarget.selected_at).all()
    school_links = load_school_links()
    from app.services import calendar_feed
    calendar_url = url_for("student.calendar_ics", token=calendar_feed.commit_token(user), _external=True)
    return render_template(
        "student_schedule.html",
        user=user,
        calendar_url=calendar_url,
        skill=latest_timeline("skill_review"),
        checked_on=CHECKED_ON,
        targets=[{"program": t.program, "schedule": timeline(t.program), "channel_label": channel_label(t.program),
                  "links": admission_links(t.program, school_links)} for t in targets],
    )


@student_bp.post("/student/calendar/reset")
@role_required("student")
def calendar_reset():
    """重設行事曆訂閱網址（網址外流時用）；舊網址立刻失效。"""
    from app.services import audit_service, calendar_feed
    user = get_current_user()
    calendar_feed.reset_token(user)
    audit_service.record(user, "calendar.reset", "user", user.id)
    db.session.commit()
    return redirect(url_for("student.schedule") + "#calendar")


@student_bp.get("/calendar/<token>.ics")
def calendar_ics(token):
    """行事曆訂閱（不用登入，靠私密網址）。Google 日曆伺服器會定期來抓。"""
    from app.services import calendar_feed
    student = calendar_feed.find_student(token)
    if student is None:
        abort(404)
    body = calendar_feed.build_ics(student)
    return current_app.response_class(body, mimetype="text/calendar", headers={
        "Content-Disposition": 'inline; filename="schedule.ics"', "Cache-Control": "no-store"})


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
        target_track="transfer" if is_transfer(program) else "twotech",
        gap=gap,
        chapters=autobiography_service.custom_contents(user, program),
        targets=[t.program for t in targets],
        review=review,
        review_timeline=review_timeline(user, program),
        autobiography=autobiography,
        download_checklist=download_checklist(user, program, gap, review, autobiography),
        mail_recipients=_package_recipients(user),
        labels=ALL_LABELS,
    )


@student_bp.post("/student/targets/<int:program_id>/review")
@role_required("student")
def target_request_review(program_id):
    user = get_current_user()
    program = _selected_target_or_404(user, program_id)
    reason = student_rules.review_block_reason(user)
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


def _package_recipients(user):
    from app.services import backup_email
    return backup_email.recipients(user)


PACKAGE_MAIL_DAILY_LIMIT = 5  # 每位學生每天最多寄幾次備審打包
PACKAGE_MAIL_SUBJECT = "【資管科學習歷程】你的備審資料打包"


@student_bp.get("/student/targets/<int:program_id>/package.zip")
@role_required("student")
def target_package_zip(program_id):
    """一鍵打包：備審 Word、自傳、已確認的原始檔與佐證，壓縮成一個檔下載。"""
    from app.services import package_zip
    user = get_current_user()
    program = _selected_target_or_404(user, program_id)
    data, manifest = package_zip.build_zip(user, program)
    audit_service.record(user, "package.zip_download", "admission_program", program.id,
                         detail={"files": len(manifest["included"]), "skipped": len(manifest["skipped"])}, commit=True)
    return send_file(data, as_attachment=True, download_name=package_zip.download_name(program),
                     mimetype="application/zip")


@student_bp.post("/student/targets/<int:program_id>/package/send")
@role_required("student")
def target_package_send(program_id):
    """把打包寄到學生自己的學校信箱或已確認的備用信箱。太大就只寄下載連結（要登入才能下載）。"""
    from app.services import backup_email, email_notify, package_zip
    user = get_current_user()
    program = _selected_target_or_404(user, program_id)
    recipient = next((r for r in backup_email.recipients(user) if r["key"] == request.form.get("to")), None)
    if recipient is None:
        return _blocked(user, "這個信箱還不能收備審資料：備用信箱要先到「帳號設定」綁定並點確認信的連結。")[0], 400
    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    sent_today = AuditLog.query.filter(AuditLog.user_id == user.id, AuditLog.action == "package.mail",
                                       AuditLog.created_at >= day_start).count()
    if sent_today >= PACKAGE_MAIL_DAILY_LIMIT:
        return _blocked(user, f"今天已經寄了 {PACKAGE_MAIL_DAILY_LIMIT} 次備審打包，請明天再寄，或直接用「打包下載」。")[0], 429
    data, manifest = package_zip.build_zip(user, program)
    payload = data.getvalue()
    label = f"{program.school_name} {program.department_name}"
    limit = float(current_app.config.get("MAIL_MAX_ATTACHMENT_MB", 15)) * 1024 * 1024
    intro = f"{user.display_name} 您好：\n\n這是你在資管科智慧學習歷程系統要求寄出的備審資料打包（{label}）。\n"
    outro = "\n如果不是你本人要求的，請登入系統修改密碼並通知導師。這封信由系統自動寄出，請勿直接回覆。\n"
    if len(payload) <= limit:
        body = intro + "壓縮檔在附件，裡面的「清單.txt」列出放了哪些檔案。\n" + outro
        attachments = [(package_zip.download_name(program), payload, "application/zip")]
    else:
        base = (current_app.config.get("MAIL_SITE_URL") or "").rstrip("/")
        link = f"{base}{url_for('student.target_package_zip', program_id=program.id)}"
        body = intro + f"檔案太大，沒辦法放在信裡。請登入系統後用這個連結下載：\n{link}\n" + outro
        attachments = []
    status = email_notify.deliver(recipient["address"], PACKAGE_MAIL_SUBJECT, body, attachments, user_id=user.id)
    result = "link" if status == "sent" and not attachments else status
    # 操作紀錄只記寄到哪一種信箱與結果，不記信箱與內容
    audit_service.record(user, "package.mail", "admission_program", program.id,
                         detail={"to": recipient["key"], "status": result, "bytes": len(payload),
                                 "files": len(manifest["included"])}, commit=True)
    return redirect(url_for("student.target_gap", program_id=program.id, mailed=result) + "#package-title")


# ---------- 學生選擇不放進備審的資料（導師 2026-11-12） ----------

EXCLUSION_KINDS = {"course": ("成績", LearningCourseRecord), "credential": ("證照", CredentialRecord),
                   "portfolio": ("經歷", Portfolio)}


def _exclusion_keys(kind, record):
    return {"course": ("grades",), "credential": ("credential",)}.get(kind) or package_exclusion.portfolio_keys(record)


def _exclusion_groups(user, targets):
    """已確認的成績、證照、經歷，各附上能不能排除（簡章規定必備的不能）。"""
    courses = (LearningCourseRecord.query.filter_by(student_id=user.id, confirmation_status="confirmed")
               .order_by(LearningCourseRecord.school_year, LearningCourseRecord.id).all())
    credentials = (CredentialRecord.query.filter_by(student_id=user.id, confirmation_status="confirmed")
                   .order_by(CredentialRecord.id).all())
    records = (Portfolio.active().filter_by(student_id=user.id, status="confirmed").order_by(Portfolio.id).all())

    def row(kind, record, name, detail):
        return {"id": record.id, "name": name, "detail": detail, "excluded": record.excluded_from_package,
                "lock": package_exclusion.lock_state(targets, _exclusion_keys(kind, record))}

    return [
        {"kind": "course", "label": "成績", "rows": [
            row("course", c, c.course_name,
                f"{c.score} 分" if c.score is not None else (c.status_mark or "")) for c in courses]},
        {"kind": "credential", "label": "證照", "rows": [
            row("credential", c, autobiography_service.credential_label(c), "") for c in credentials]},
        {"kind": "portfolio", "label": "經歷", "rows": [
            row("portfolio", r, r.title, CATEGORY_LABELS.get(r.category, "")) for r in records]},
    ]


@student_bp.get("/student/package-exclusions")
@student_bp.post("/student/package-exclusions")
@role_required("student")
def package_exclusions():
    user = get_current_user()
    targets = [t.program for t in StudentTarget.query.filter_by(student_id=user.id).order_by(StudentTarget.selected_at)]
    program_id = request.values.get("program_id", type=int)
    back_program = next((p for p in targets if p.id == program_id), None)
    error = None
    if request.method == "POST":
        kind = request.form.get("kind", "")
        if kind not in EXCLUSION_KINDS:
            abort(400)
        label, model = EXCLUSION_KINDS[kind]
        record = db.session.get(model, request.form.get("record_id", type=int) or 0)
        if not record or record.student_id != user.id or getattr(record, "deleted_at", None):
            abort(404)
        excluded = request.form.get("excluded") == "1"
        lock = package_exclusion.lock_state(targets, _exclusion_keys(kind, record))
        if excluded and lock["locked"]:
            names = "、".join(f"{p.school_name} {p.department_name}" for p in lock["programs"])
            error = f"這筆{label}不能排除：{names}{package_exclusion.REQUIRED_REASON}這類資料。"
        else:
            record.excluded_from_package = excluded
            audit_service.record(user, "package_exclusion.set", model.__tablename__, record.id,
                                 detail={"excluded": excluded}, commit=True)
            return redirect(url_for("student.package_exclusions", saved=1,
                                    program_id=back_program.id if back_program else None))
    return render_template(
        "student_package_exclusions.html",
        user=user,
        targets=targets,
        back_program=back_program,
        groups=_exclusion_groups(user, targets),
        reason=package_exclusion.REQUIRED_REASON,
        error=error,
    ), (400 if error else 200)


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
        questions=autobiography_service.guided_questions(program),
        valued_label=autobiography_service.VALUED_LABEL,
        answers=answers or (draft.content_json.get("answers", {}) if draft else autobiography_service.carried_answers(user)),
        facts=autobiography_service.build_facts(user, program) if program else None,
        version=autobiography_service.version_of(draft) if draft else None,
        backup_label=autobiography_backup.status_label(draft) if draft else None,
        paragraph_reviews=paragraph_reviews,
        pieces=autobiography_service.bio_pieces(user, program, draft) if program else {"facts": [], "own": []},
        strength_inventory=autobiography_service.strength_inventory(user, program),
        school_turns=ai_quota_service.remaining(user) if ai_ready() and not autobiography_service.ollama_ready() else None,
        ai_on=ai_ready() or autobiography_service.ollama_ready(),
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
    answers = {question["key"]: request.form.get(question["key"], "")
               for question in autobiography_service.guided_questions(program)}
    # 學生要先用自己的話寫（比重高的項目一定要寫到），AI 只整理（導師 2026-11-12）
    problem = autobiography_service.own_words_problem(program, answers)
    if problem:
        return _render_autobiography(user, program, targets, error=problem, answers=answers, status=400)
    # 學生自己的金鑰：只放在這個函式的變數裡用一次，不存資料庫、不放 session、不放網址
    own_key = "" if current_app.config.get("LOCAL_DEMO_MODE") else request.form.get("own_api_key", "").strip() or None
    used_own_key = bool(own_key)
    try:
        # 學校金鑰每人每天有次數限制；先扣，AI 失敗時 rollback 就會退回
        if not own_key and ai_ready() and not autobiography_service.ollama_ready():
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
    from app.routes.google_docs import auto_create_after_generate
    auto_created = auto_create_after_generate(user, output)  # 學生已連過 Google 就自動放一份到他的雲端硬碟
    return redirect(url_for("student.autobiography", program_id=program.id,
                            used_own_key=1 if used_own_key else None,
                            google="auto_created" if auto_created else None))


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


@student_bp.post("/student/autobiography/<int:output_id>/backup-retry")
@role_required("student")
def autobiography_backup_retry(output_id):
    """備份失敗時的「再試一次」：重新排進背景備份，存檔本身不受影響。"""
    user = get_current_user()
    output = db.session.get(LearningProfileOutput, output_id)
    if not output or output.output_type != autobiography_service.OUTPUT_TYPE:
        abort(404)
    if output.student_id != user.id:
        abort(403)
    autobiography_backup.retry(current_app._get_current_object(), output)
    return redirect(url_for(
        "student.autobiography", program_id=output.content_json.get("program_id")))


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
