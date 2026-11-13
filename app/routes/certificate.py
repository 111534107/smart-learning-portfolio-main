"""科辦電子獎狀：學生申請 → 科辦編輯內文、核准或退回 → 產出獎狀與驗證頁。規則見 services/certificate_service.py。"""

from datetime import date, datetime, timezone

from flask import Blueprint, abort, redirect, render_template, request, url_for

from app.extensions import db
from app.models import AwardCertificate, Notification, Portfolio
from app.routes.main import get_current_user, role_required
from app.services import certificate_service as service
from app.services.file_preview import inline_file, preview_kind
from app.services.teacher_scope import can_view_student

certificate_bp = Blueprint("certificate", __name__)


@certificate_bp.app_template_global()
def certificate_kinds(record):
    """學生經歷頁用：這筆紀錄可以申請哪幾種電子獎狀（[(kind, 標題, 說明), ...]）。"""
    return [(kind, service.KINDS[kind], service.KIND_HINTS[kind]) for kind in service.eligible_kinds(record)]


@certificate_bp.app_template_global()
def certificate_club_reminder(record):
    """學生經歷頁用：寫到科學會、社團的紀錄，提醒到學務處辦證明（科辦不開科學會證明）。"""
    return service.club_reminder(record)


@certificate_bp.post("/student/portfolio/<int:portfolio_id>/certificate")
@role_required("student")
def certificate_apply(portfolio_id):
    user = get_current_user()
    record = db.session.get(Portfolio, portfolio_id)
    if not record or record.student_id != user.id or record.deleted_at:
        abort(404)
    kinds = service.eligible_kinds(record)
    kind = request.form.get("kind") or (kinds[0] if kinds else "")
    if kind not in kinds:
        return ("只有從學校獎懲記錄匯入的紀錄可以申請電子獎狀：服務學習可申請服務證明，"
                "事由寫到 TA、助教可申請 TA 證明。科學會（社團）證明請到學務處辦理。"), 400
    cert = record.certificate
    if cert and cert.status in ("pending", "approved"):
        return redirect(url_for("student.portfolio_edit", portfolio_id=record.id))
    body = service.default_body(record, kind)  # 先算好內文，再加進 session，避免查詢時先存進一筆空白的
    if not cert:
        cert = AwardCertificate(portfolio=record)
    cert.status = "pending"
    cert.kind = kind
    cert.title = service.KINDS[kind]
    cert.issuer = service.DEFAULT_ISSUER
    cert.body = body
    cert.return_reason = None
    db.session.add(cert)
    db.session.commit()
    return redirect(url_for("student.portfolio_edit", portfolio_id=record.id))


def _cert_or_404(cert_id):
    cert = db.session.get(AwardCertificate, cert_id)
    if not cert:
        abort(404)
    return cert


@certificate_bp.get("/staff/certificates")
@role_required("staff")
def staff_list():
    pending = AwardCertificate.query.filter_by(status="pending").order_by(AwardCertificate.created_at).all()
    done = (AwardCertificate.query.filter(AwardCertificate.status != "pending")
            .order_by(AwardCertificate.reviewed_at.desc()).limit(20).all())
    return render_template("staff_certificates.html", user=get_current_user(), pending=pending, done=done)


@certificate_bp.get("/staff/certificates/new")
@certificate_bp.post("/staff/certificates/new")
@role_required("staff")
def staff_issue():
    """科辦直接開立：選學生、類別、事由（TA 填課名），送出就核准，轉到獎狀頁可以列印。"""
    from app.models import StudentProfile, User
    from app.services import audit_service
    user = get_current_user()
    students = (User.query.join(StudentProfile, StudentProfile.user_id == User.id)
                .filter(User.role == "student", User.is_active.is_(True))
                .order_by(StudentProfile.student_no).all())
    form = request.form if request.method == "POST" else {}
    this_year = service.roc_year(date.today())

    def render(error=None, status=200):
        return render_template("staff_certificate_issue.html", user=user, students=students, form=form,
                               this_year=this_year, error=error), status

    if request.method == "GET":
        return render()
    student_no = form.get("student_no", "").strip()
    profile = StudentProfile.query.filter_by(student_no=student_no).first() if student_no else None
    if not profile or not profile.user or profile.user.role != "student":
        return render("找不到這個學號的學生，請從清單選擇。", 400)
    year = form.get("school_year", "").strip()
    semester = form.get("semester", "").strip()
    try:
        cert = service.staff_issue(
            user, profile.user, form.get("kind", ""), form.get("event"),
            int(year) if year.isdigit() else None, int(semester) if semester in ("1", "2") else None,
            course=form.get("course"), body=form.get("body"))
    except ValueError as error:
        db.session.rollback()
        return render(str(error), 400)
    _notify_student(cert)
    audit_service.record(user, "certificate.issue", "award_certificate", cert.id,
                         f"{profile.student_no} {cert.title}")
    db.session.commit()
    return redirect(url_for("certificate.certificate_view", cert_id=cert.id))


@certificate_bp.get("/staff/certificates/batch")
@certificate_bp.post("/staff/certificates/batch")
@role_required("staff")
def staff_batch():
    """科辦批量開立：貼上或上傳名單 → 預覽（含錯誤列）→ 確認後一次建立。規則見 services/certificate_batch_service.py。"""
    from app.services import audit_service
    from app.services import certificate_batch_service as batch
    user = get_current_user()
    default_title = service.KINDS[batch.KIND]

    def render(status=200, **context):
        context.setdefault("text", "")
        context.setdefault("title", default_title)
        return render_template("staff_certificate_batch.html", user=user, sample=batch.SAMPLE,
                               max_rows=batch.MAX_ROWS, **context), status

    if request.method == "GET":
        return render()
    text = request.form.get("rows", "")
    title = request.form.get("title", "").strip()[:50] or default_title
    uploaded = request.files.get("file")
    try:
        if uploaded and uploaded.filename:
            text = batch.decode_upload(uploaded.read(1024 * 1024 + 1)[:1024 * 1024])
        rows = batch.parse_rows(text)
    except batch.BatchRejected as error:
        return render(400, error=str(error), text=text, title=title)
    good = [row for row in rows if row.ok]
    bad = [row for row in rows if not row.ok]
    if request.form.get("action") != "confirm":
        return render(rows=rows, good=good, bad=bad, text=text, title=title)
    if not good:
        return render(400, rows=rows, good=good, bad=bad, text=text, title=title,
                      error="名單裡沒有可以建立的列，請修正後再試。")
    certs = batch.issue_rows(user, rows, title)
    for cert in certs:
        _notify_student(cert)
        audit_service.record(user, "certificate.issue", "award_certificate", cert.id)
    audit_service.record(user, "certificate.batch_issue", detail={"count": len(certs), "skipped": len(bad)})
    db.session.commit()
    return render(created=certs, bad=bad, title=title,
                  print_ids=",".join(str(cert.id) for cert in certs))


@certificate_bp.get("/staff/certificates/print")
@role_required("staff")
def staff_print():
    """整批列印：一次開啟多張已核准的獎狀，一張一頁。"""
    raw = request.args.get("ids", "")
    ids = [int(part) for part in raw.split(",") if part.strip().isdigit()][:300]
    certs = (AwardCertificate.query.filter(AwardCertificate.id.in_(ids), AwardCertificate.status == "approved")
             .order_by(AwardCertificate.id).all()) if ids else []
    if not certs:
        abort(404)
    return render_template("certificate.html", cert=certs[0], certs=certs, roc_date=service.roc_date,
                           today=date.today(), verify_url=url_for("certificate.verify", _external=True))


@certificate_bp.get("/staff/certificates/<int:cert_id>")
@certificate_bp.post("/staff/certificates/<int:cert_id>")
@role_required("staff")
def staff_review(cert_id):
    user = get_current_user()
    cert = _cert_or_404(cert_id)
    if request.method == "GET":
        return _render_review(user, cert)

    if cert.status != "pending":
        return _render_review(user, cert, error="這筆申請已處理，不能重複審核。"), 409

    action = request.form.get("action")
    cert.title = request.form.get("title", cert.title).strip()[:50] or cert.title
    cert.issuer = request.form.get("issuer", cert.issuer).strip()[:100] or cert.issuer
    cert.body = request.form.get("body", cert.body).strip() or cert.body
    if action == "return":
        reason = request.form.get("return_reason", "").strip()
        if not reason:
            return _render_review(user, cert, error="退回時請寫原因，學生才知道要補什麼。"), 400
        cert.status, cert.return_reason = "returned", reason[:500]
    elif action == "approve":
        cert.status, cert.return_reason = "approved", None
        cert.issued_on = date.today()
        cert.verify_code = cert.verify_code or service.new_verify_code()
    else:
        abort(400)
    cert.reviewed_by_id, cert.reviewed_at = user.id, datetime.now(timezone.utc)
    _notify_student(cert)
    db.session.commit()
    return redirect(url_for("certificate.staff_list"))


def _render_review(user, cert, error=None):
    """審核頁：直接附上獎懲記錄原文與學生上傳的原始檔，科助不必離開頁面就能對照。"""
    document = cert.portfolio.source_document
    return render_template(
        "staff_certificate_review.html", user=user, cert=cert, error=error,
        award_row=service.award_row(cert.portfolio), kind_label=service.KINDS.get(cert.kind, cert.kind),
        source_kind=preview_kind(document.display_name) if document else None,
    )


def _notify_student(cert):
    """核准或退回時寄站內通知給學生：核准連到獎狀，退回連到修改頁。"""
    if cert.status == "approved":
        verb = "開立" if cert.portfolio.source == "department_certificate" else "核准"
        message = f"科辦已{verb}你的電子獎狀「{cert.title}」，可以查看與列印。"
        link = url_for("certificate.certificate_view", cert_id=cert.id)
    else:
        message = f"科辦退回你的電子獎狀申請「{cert.title}」：{cert.return_reason}"
        link = url_for("student.portfolio_edit", portfolio_id=cert.portfolio_id)
    if len(message) > 255:
        message = message[:254] + "…"
    db.session.add(Notification(recipient_id=cert.student_id, message=message, link=link))


@certificate_bp.get("/staff/certificates/<int:cert_id>/source")
@role_required("staff")
def staff_source(cert_id):
    """科辦核准前對照學生上傳的獎懲記錄原始檔。"""
    document = _cert_or_404(cert_id).portfolio.source_document
    if not document:
        abort(404)
    return inline_file(document.file_path, document.display_name)


@certificate_bp.get("/certificates/<int:cert_id>")
@role_required("student", "teacher", "staff", "admin")
def certificate_view(cert_id):
    user = get_current_user()
    cert = _cert_or_404(cert_id)
    allowed = (user.role in ("staff", "admin") or user.id == cert.student_id
               or (user.role == "teacher" and can_view_student(user, cert.student)))
    if not allowed:
        abort(403)
    if cert.status != "approved" and user.role not in ("staff", "admin"):
        abort(404)
    return render_template("certificate.html", cert=cert, certs=[cert], roc_date=service.roc_date,
                           today=date.today(), verify_url=url_for("certificate.verify", _external=True))


@certificate_bp.get("/verify")
def verify():
    """公開的驗證頁：輸入驗證碼，確認獎狀是否由本系統核發。不顯示學號，姓名遮蔽。"""
    code = request.args.get("code", "").strip().upper()
    cert = AwardCertificate.query.filter_by(verify_code=code, status="approved").first() if code else None
    return render_template("certificate_verify.html", code=code, cert=cert,
                           masked_name=service.mask_name(cert.student.display_name) if cert else "",
                           issued=service.roc_date(cert.issued_on) if cert else "")
