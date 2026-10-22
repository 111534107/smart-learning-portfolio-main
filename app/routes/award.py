"""獎懲記錄匯入：上傳 → AI 逐列讀出 → 學生確認 → 寫進「活動與經歷」。規則見 services/award_record_service.py。"""

from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for

from app.extensions import db
from app.models import DocumentExtraction, Portfolio, SourceDocument
from app.routes.main import get_current_user, role_required
from app.security import validate_upload_filename
from app.services import ai_quota_service, award_record_service
from app.services.journey_service import CATEGORY_LABELS, EXPERIENCE_CATEGORIES, grade_for

award_bp = Blueprint("award", __name__)

DOCUMENT_TYPE = "award_record"


def _owned_award_document_or_404(document_id):
    document = db.session.get(SourceDocument, document_id)
    if not document or document.document_type != DOCUMENT_TYPE:
        abort(404)
    if document.owner_id != get_current_user().id:
        abort(403)
    return document


def _read_rows(user, stored_path, safe_name):
    """請 AI 逐列讀出；學校金鑰每人每天有次數限制，AI 沒讀出來就退回次數。"""
    if not award_record_service.gemini_client.ai_ready():
        return award_record_service.extract_rows(stored_path, safe_name)
    try:
        ai_quota_service.consume(user)
    except ai_quota_service.QuotaExceeded:
        return [], [f"今天學校 AI 的 {current_app.config.get('SCHOOL_AI_DAILY_LIMIT', 5)} 次已經用完了，"
                    "明天會恢復；現在可以對照上方的原始檔，自己填寫下面的表格。"]
    rows, warnings = award_record_service.extract_rows(stored_path, safe_name)
    if not rows:
        ai_quota_service.refund(user)
    return rows, warnings


@award_bp.get("/student/award-records")
@role_required("student")
def award_upload_page():
    user = get_current_user()
    documents = SourceDocument.query.filter_by(owner_id=user.id, document_type=DOCUMENT_TYPE).order_by(
        SourceDocument.created_at.desc()).all()
    return render_template("award_upload.html", user=user, documents=documents)


@award_bp.post("/student/award-records")
@role_required("student")
def award_upload():
    user = get_current_user()
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return "請選擇檔案", 400
    try:
        safe_name = validate_upload_filename(uploaded.filename, current_app.config["LEARNING_PROFILE_ALLOWED_EXTENSIONS"])
    except ValueError as exc:
        return str(exc), 400
    file_bytes = uploaded.read()
    if not file_bytes:
        return "檔案是空的", 400

    folder = Path(current_app.config["UPLOAD_FOLDER"]) / "learning-profile" / str(user.id)
    folder.mkdir(parents=True, exist_ok=True)
    stored_path = folder / f"{uuid4().hex}_{safe_name}"
    stored_path.write_bytes(file_bytes)
    try:
        rows, warnings = _read_rows(user, stored_path, safe_name)
        document = SourceDocument(owner_id=user.id, document_type=DOCUMENT_TYPE, display_name=safe_name,
                                  file_path=str(stored_path), sha256=sha256(file_bytes).hexdigest(), status="extracted")
        db.session.add(document)
        db.session.flush()
        db.session.add(DocumentExtraction(
            source_document_id=document.id, provider="gemini" if rows else "manual", status="extracted",
            result_json=award_record_service.build_draft(rows, warnings),
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        stored_path.unlink(missing_ok=True)
        raise
    return redirect(url_for("award.award_review", document_id=document.id))


def _render_review(user, document, rows, warnings, error=None, status=200):
    if not rows:
        rows = [{"reason": "", "category": "", "school_year": "", "semester": "", "detail": ""}
                for _ in range(award_record_service.BLANK_ROWS)]
    return render_template(
        "award_review.html", user=user, document=document, rows=rows, warnings=warnings, error=error,
        categories=EXPERIENCE_CATEGORIES, category_labels=CATEGORY_LABELS,
    ), status


@award_bp.get("/student/award-records/<int:document_id>/review")
@role_required("student")
def award_review(document_id):
    document = _owned_award_document_or_404(document_id)
    draft = (document.extraction.result_json or {}) if document.extraction else {}
    return _render_review(get_current_user(), document, draft.get("rows") or [], draft.get("warnings") or [])


@award_bp.post("/student/award-records/<int:document_id>/confirm")
@role_required("student")
def award_confirm(document_id):
    user = get_current_user()
    document = _owned_award_document_or_404(document_id)
    form = request.form
    columns = [form.getlist(name) for name in ("reason", "category", "school_year", "semester", "detail")]
    rows = [dict(zip(("reason", "category", "school_year", "semester", "detail"), values)) for values in zip(*columns)]
    included = {int(value) for value in form.getlist("include") if value.isdigit()}

    chosen = [(index, row) for index, row in enumerate(rows) if index in included and row["reason"].strip()]
    if not chosen:
        return _render_review(user, document, rows, [], error="請至少勾選一列要匯入的紀錄。", status=400)
    for index, row in chosen:
        if row["category"] not in EXPERIENCE_CATEGORIES:
            return _render_review(user, document, rows, [], error=f"第 {index + 1} 列請選擇類別。", status=400)

    profile = user.student_profile
    admission_year = profile.admission_year if profile else None
    added = 0
    for _, row in chosen:
        title = row["reason"].strip()[:150]
        exists = Portfolio.query.filter_by(student_id=user.id, source="award_record", title=title).first()
        if exists:
            continue
        year = int(row["school_year"]) if row["school_year"].strip().isdigit() else None
        # 知道入學年度就換成年級（專一～專五），「我的五年」才放得進對的資料夾
        year = grade_for(year, admission_year) or year
        db.session.add(Portfolio(
            student_id=user.id, title=title, category=row["category"], description=row["detail"].strip() or None,
            school_year=year,
            semester=int(row["semester"]) if row["semester"].strip() in ("1", "2") else None,
            source="award_record", source_document_id=document.id,
            status="confirmed",  # 學生在上一頁已逐列勾選確認
        ))
        added += 1
    document.status = "confirmed"
    db.session.commit()
    return redirect(url_for("student.portfolio_list", imported=added))
