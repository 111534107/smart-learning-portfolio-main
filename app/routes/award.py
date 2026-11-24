"""獎懲記錄匯入：上傳 → AI 逐列讀出 → 學生確認 → 獎勵寫進「活動與經歷」、懲處另外保存。規則見 services/award_record_service.py。"""

from hashlib import sha256

from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for

from app.extensions import db
from app.models import DocumentExtraction, Portfolio, SchoolAwardRecord, SourceDocument
from app.routes.attendance import review_pasted_totals
from app.routes.main import get_current_user, role_required
from app.security import validate_upload_filename
from app.services import ai_quota_service, attendance_import, award_record_service, storage_service
from app.services.journey_service import CATEGORY_LABELS, EXPERIENCE_CATEGORIES, grade_for

award_bp = Blueprint("award", __name__)

DOCUMENT_TYPE = "award_record"
REVIEW_COLUMNS = ("reason", "category", "school_year", "semester", "detail", "key")


def _owned_award_document_or_404(document_id):
    document = db.session.get(SourceDocument, document_id)
    if not document or document.document_type != DOCUMENT_TYPE:
        abort(404)
    if document.owner_id != get_current_user().id:
        abort(403)
    return document


def _read_rows(user, stored_path, safe_name):
    """請 AI 逐列讀出；學校金鑰每人每天有次數限制，AI 沒讀出來就退回次數。"""
    from app.services import ai_gateway
    from app.services.deidentify import known_values_for
    known = known_values_for(user)
    if not ai_gateway.ready():
        return award_record_service.extract_rows(stored_path, safe_name, known)
    try:
        ai_quota_service.consume(user)
    except ai_quota_service.QuotaExceeded:
        return [], [f"今天學校 AI 的 {current_app.config.get('SCHOOL_AI_DAILY_LIMIT', 5)} 次已經用完了，"
                    "明天會恢復；現在可以對照上方的原始檔，自己填寫下面的表格。"]
    rows, warnings = award_record_service.extract_rows(stored_path, safe_name, known)
    if not rows:
        ai_quota_service.refund(user)
    return rows, warnings


def _draft_of(document):
    return (document.extraction.result_json or {}) if document.extraction else {}


@award_bp.get("/student/award-records")
@role_required("student")
def award_upload_page():
    user = get_current_user()
    documents = SourceDocument.query.filter_by(owner_id=user.id, document_type=DOCUMENT_TYPE).order_by(
        SourceDocument.created_at.desc()).all()
    return render_template("award_upload.html", user=user, documents=documents)


@award_bp.post("/student/award-records/paste")
@role_required("student")
def award_paste():
    """貼上學校獎懲表格（組員版）：本機解析，不送 AI、不扣學校 AI 次數。"""
    user = get_current_user()
    text = request.form.get("pasted_table", "")
    if attendance_import.looks_like_school_attendance(text):
        return review_pasted_totals(user, text, from_award=True)
    try:
        student_no = user.student_profile.student_no if user.student_profile else None
        rows = award_record_service.parse_pasted_table(text, student_no)
    except ValueError as error:
        documents = SourceDocument.query.filter_by(owner_id=user.id, document_type=DOCUMENT_TYPE).order_by(
            SourceDocument.created_at.desc()).all()
        return render_template("award_upload.html", user=user, documents=documents,
                               paste_error=str(error), pasted_table=text), 400
    file_bytes = text.encode("utf-8")
    name = "貼上的獎懲表格.txt"
    location = storage_service.save(file_bytes, owner_id=user.id, folder="learning-profile", filename=name)
    try:
        document = SourceDocument(owner_id=user.id, document_type=DOCUMENT_TYPE, display_name=name,
                                  file_path=location, sha256=sha256(file_bytes).hexdigest(), status="extracted")
        db.session.add(document)
        db.session.flush()
        draft = award_record_service.build_draft(rows)
        # 貼上的是學校原文，不是 AI 讀的：把「AI 讀的字可能有錯」換成對照來源的提醒
        draft["warnings"] = ["請對照你貼上的原文逐列檢查；類別是建議，可以改。" if "AI 讀的字" in w else w
                             for w in draft.get("warnings", [])]
        draft["pasted_text"] = text
        db.session.add(DocumentExtraction(source_document_id=document.id, provider="paste", status="extracted",
                                          result_json=draft))
        db.session.commit()
    except Exception:
        db.session.rollback()
        storage_service.discard(location)
        raise
    return redirect(url_for("award.award_review", document_id=document.id))


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

    location = storage_service.save(file_bytes, owner_id=user.id, folder="learning-profile", filename=safe_name)
    try:
        rows, warnings = _read_rows(user, storage_service.local_path(location), safe_name)
        document = SourceDocument(owner_id=user.id, document_type=DOCUMENT_TYPE, display_name=safe_name,
                                  file_path=location, sha256=sha256(file_bytes).hexdigest(), status="extracted")
        db.session.add(document)
        db.session.flush()
        db.session.add(DocumentExtraction(
            source_document_id=document.id, provider="gemini" if rows else "manual", status="extracted",
            result_json=award_record_service.build_draft(rows, warnings),
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        storage_service.discard(location)
        raise
    return redirect(url_for("award.award_review", document_id=document.id))


def _render_review(user, document, rows, warnings, punishments, error=None, status=200):
    if not rows:
        rows = [{"reason": "", "category": "", "school_year": "", "semester": "", "detail": "", "key": "", "include": True}
                for _ in range(award_record_service.BLANK_ROWS)]
    return render_template(
        "award_review.html", user=user, document=document, rows=rows, warnings=warnings, error=error,
        punishments=punishments, categories=EXPERIENCE_CATEGORIES, category_labels=CATEGORY_LABELS,
    ), status


@award_bp.get("/student/award-records/<int:document_id>/review")
@role_required("student")
def award_review(document_id):
    document = _owned_award_document_or_404(document_id)
    draft = _draft_of(document)
    return _render_review(get_current_user(), document, draft.get("rows") or [], draft.get("warnings") or [],
                          draft.get("punishments") or [])


def _exists(user, key):
    return db.session.query(SchoolAwardRecord.id).filter_by(student_id=user.id, record_key=key).first() is not None


@award_bp.post("/student/award-records/<int:document_id>/confirm")
@role_required("student")
def award_confirm(document_id):
    user = get_current_user()
    document = _owned_award_document_or_404(document_id)
    draft = _draft_of(document)
    punishments = draft.get("punishments") or []
    form = request.form

    # 表單欄位逐列對齊；缺的欄位補空字串
    count = len(form.getlist("reason"))
    columns = {}
    for name in REVIEW_COLUMNS:
        values = form.getlist(name)
        columns[name] = values + [""] * (count - len(values))
    rows = [{name: columns[name][index] for name in REVIEW_COLUMNS} for index in range(count)]
    included = {int(value) for value in form.getlist("include") if value.isdigit()}
    for index, row in enumerate(rows):
        row["include"] = index in included

    chosen = [(index, row) for index, row in enumerate(rows) if row["include"] and row["reason"].strip()]
    if not chosen and not punishments:
        return _render_review(user, document, rows, [], punishments,
                              error="請至少勾選一列要匯入的紀錄。", status=400)
    for index, row in chosen:
        if row["category"] not in EXPERIENCE_CATEGORIES:
            return _render_review(user, document, rows, [], punishments,
                                  error=f"第 {index + 1} 列請選擇類別。", status=400)

    # 懲處不讓學生勾選，確認時一律保存（不進活動與經歷），同一列只存一次
    for item in punishments:
        if _exists(user, item["key"]):
            continue
        db.session.add(SchoolAwardRecord(
            student_id=user.id, source_document_id=document.id, record_key=item["key"],
            record_type="punishment", date=item.get("date") or None, name=item.get("name") or None,
            count=item.get("count"), reason=item["reason"], revoked=item.get("revoked") or "",
            school_year=item.get("school_year"), semester=item.get("semester"),
        ))

    profile = user.student_profile
    admission_year = profile.admission_year if profile else None
    added = 0
    for _, row in chosen:
        title = row["reason"].strip()[:150]
        key = row["key"].strip() or record_key_for_manual(title, row)
        # 刻意不排除已刪除的：學生刪掉的匯入紀錄，再匯入一次也不要冒回來（靠 record_key 判斷）
        if _exists(user, key):
            continue
        year = int(row["school_year"]) if row["school_year"].strip().isdigit() else None
        # 知道入學年度就換成年級（專一～專五），「我的五年」才放得進對的資料夾
        year = grade_for(year, admission_year) or year
        portfolio = Portfolio(
            student_id=user.id, title=title, category=row["category"], description=row["detail"].strip() or None,
            school_year=year,
            semester=int(row["semester"]) if row["semester"].strip() in ("1", "2") else None,
            source="award_record", source_document_id=document.id,
            status="confirmed",  # 學生在上一頁已逐列勾選確認
        )
        db.session.add(portfolio)
        db.session.flush()
        db.session.add(SchoolAwardRecord(
            student_id=user.id, source_document_id=document.id, portfolio_id=portfolio.id, record_key=key,
            record_type="reward", reason=title,
        ))
        added += 1
    document.status = "confirmed"
    db.session.commit()
    return redirect(url_for("student.portfolio_list", imported=added))


def record_key_for_manual(title, row):
    """學生手動新增的列沒有來源指紋，用事由與填寫內容當作指紋。"""
    return award_record_service.record_key("manual", title, row["school_year"], row["semester"], row["detail"])


@award_bp.get("/student/discipline-records")
@role_required("student")
def discipline_records():
    user = get_current_user()
    records = SchoolAwardRecord.query.filter_by(student_id=user.id, record_type="punishment").order_by(
        SchoolAwardRecord.school_year.desc(), SchoolAwardRecord.id.desc()).all()
    return render_template("award_discipline.html", user=user, records=records)
