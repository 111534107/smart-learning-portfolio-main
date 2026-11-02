from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, send_file, session, url_for
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import AuditLog, AwardCertificate, PortfolioSubmission, SourceDocument, StudentTarget, SubmissionAssignment, TeacherReviewFeedback, User
from app.services.gap_service import analyze_gap
from app.services.admission_schedule import channel_label
from app.services.guide_service import CARD_IDS, guide_cards
from app.services.journey_home import journey_home
from app.services import photo_service, student_rules
from app.services.package_service import latest_review
from app.services.teacher_scope import advised_classes, students_for_teacher
from app.content.five_year_plan import FIVE_YEAR_PLAN, NEXT_STOPS
from app.services.admission_sample import load_sample_programs
from app.services.journey_service import GRADE_LABELS, current_grade, CATEGORY_KEYS, CATEGORY_LABELS, EXPERIENCE_CATEGORIES, build_journey
from app.services import school_google_login as g_login

main_bp = Blueprint("main", __name__)


def get_current_user():
    user_id = session.get("user_id")
    user = db.session.get(User, user_id) if user_id else None
    if not user or not user.is_active:
        return None
    return user


def feedback_by_submission(submission_ids):
    feedback_map = {}
    if not submission_ids:
        return feedback_map
    feedback_items = (
        TeacherReviewFeedback.query.filter(TeacherReviewFeedback.submission_id.in_(submission_ids))
        .order_by(TeacherReviewFeedback.created_at.asc())
        .all()
    )
    for feedback in feedback_items:
        feedback_map.setdefault(feedback.submission_id, []).append(feedback)
    return feedback_map


@main_bp.route("/")
def index():
    return render_template(
        "index.html",
        plan=FIVE_YEAR_PLAN,
        next_stops=NEXT_STOPS,
    )


@main_bp.get("/health")
def health():
    """Expose a minimal readiness check without leaking database details."""
    try:
        db.session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(status="error", database="unavailable"), 503
    return jsonify(status="ok", database="ok")


@main_bp.route("/login", methods=["GET", "POST"])
def login():
    from app.services.flow import safe_next
    next_path = safe_next(request.values.get("next"))
    if request.method == "GET":
        return render_template("login.html", next_path=next_path, google_login_enabled=g_login.configured(current_app.config))

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return render_template("login.html", error="帳號或密碼錯誤", next_path=next_path,
                               google_login_enabled=g_login.configured(current_app.config)), 401
    if not user.is_active:  # 密碼對了才說明已停用，不讓人用來試哪些帳號存在
        return render_template("login.html", error="這個帳號已停用，請洽系統管理員。", next_path=next_path,
                               google_login_enabled=g_login.configured(current_app.config)), 403

    return _finish_login(user, next_path)


def _finish_login(user, next_path=None):
    session.clear()
    session["user_id"] = user.id
    destinations = {
        "student": "main.student_dashboard",
        "teacher": "main.teacher_dashboard",
        "staff": "main.staff_dashboard",
        "admin": "main.admin_dashboard",
    }
    endpoint = destinations.get(user.role)
    if not endpoint:
        session.clear()
        return render_template("login.html", error="此帳號尚未設定可用角色",
                               google_login_enabled=g_login.configured(current_app.config)), 403
    # 每次登入都記（規格 M11）；學生首頁也用 student.login 判斷是不是很久沒來（「好久不見」那一幕）
    action = "student.login" if user.role == "student" else "user.login"
    db.session.add(AuditLog(user_id=user.id, action=action, ip_address=request.remote_addr))
    db.session.commit()
    if user.role == "student" and not _welcome_done(user):
        return redirect(url_for("main.student_welcome"))
    return redirect(next_path or url_for(endpoint))  # 被登出前想看的頁面；權限照樣由那一頁檢查


@main_bp.get("/auth/google")
def google_login():
    from app.services.flow import safe_next
    if not g_login.configured(current_app.config):
        abort(404)
    session.clear()
    session["google_login_state"] = g_login.new_state()
    session["google_login_next"] = safe_next(request.args.get("next"))
    return redirect(g_login.authorization_url(current_app.config, session["google_login_state"]))


@main_bp.get("/auth/google/callback")
def google_login_callback():
    expected = session.pop("google_login_state", None)
    next_path = session.pop("google_login_next", None)
    if not expected or request.args.get("state") != expected:
        enabled = g_login.configured(current_app.config)
        message = ("請從登入頁按「使用學校 Google 帳號登入」重新開始。"
                   if enabled else "學校 Google 登入尚未設定，請先完成 Google Cloud 設定。")
        return render_template("login.html", error=message, google_login_enabled=enabled), 400
    if request.args.get("error") or not request.args.get("code"):
        return render_template("login.html", error="未完成 Google 登入，請重試。",
                               google_login_enabled=g_login.configured(current_app.config)), 403
    try:
        claims = g_login.client_for(current_app).verify_code(request.args["code"])
    except g_login.GoogleLoginError:
        return render_template("login.html", error="Google 登入驗證失敗，請重試。",
                               google_login_enabled=g_login.configured(current_app.config)), 403
    identity = g_login.school_identity(claims)
    if identity is None:
        return render_template("login.html", error="請使用已綁定的學校學生 Google 帳號登入。",
                               google_login_enabled=True), 403
    email, sub = identity
    user = User.query.filter_by(google_sub=sub).first()
    if user is None:
        matches = User.query.filter(db.func.lower(User.email) == email).all()
        if len(matches) != 1 or matches[0].google_sub:
            user = None
        else:
            user = matches[0]
    if not user or not user.is_active or user.role != "student" or (user.email or "").lower() != email:
        return render_template("login.html", error="此學校帳號尚未綁定可用的學生帳號，請洽管理員。",
                               google_login_enabled=True), 403
    if not user.google_sub:
        user.google_sub = sub
    name = claims.get("name")
    if isinstance(name, str):
        name = " ".join(name.split())
        if name and len(name) <= 100 and name.isprintable():
            user.display_name = name
    return _finish_login(user, next_path)


@main_bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.login"))


def role_required(*allowed_roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = get_current_user()
            if not user:
                abort(401)
            if user.role not in allowed_roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


@main_bp.get("/student/dashboard")
@role_required("student")
def student_dashboard():
    user = get_current_user()
    journey = build_journey(user)
    targets = [
        {"program": target.program,
         "readiness": analyze_gap(user, target.program, journey)["readiness"],
         "channel": channel_label(target.program)}
        for target in StudentTarget.query.filter_by(student_id=user.id).order_by(StudentTarget.selected_at).all()
    ]
    class_name = user.student_profile.class_name if user.student_profile else ""
    major_known = any(name in (class_name or "") for name in ("資管科", "資訊管理科"))

    def is_home_major(row):
        department = (row["program"].department_name or "").split("（", 1)[0].split("(", 1)[0].replace(" ", "")
        return major_known and department in {"資管系", "資訊管理系", "資訊管理學系"}

    targets.sort(key=lambda row: (
        not is_home_major(row) if major_known else False,
        row["readiness"] is None,
        -(row["readiness"] or 0),
        row["program"].school_name,
        row["program"].department_name,
        row["program"].id,
    ))
    target_groups = ([
        {"label": "本科系（資訊管理）", "targets": [row for row in targets if is_home_major(row)]},
        {"label": "非本科系", "targets": [row for row in targets if not is_home_major(row)]},
    ] if major_known else [{"label": "已選校系", "targets": targets}])
    target_groups = [group for group in target_groups if group["targets"]]
    home = journey_home(user, journey)
    semester = photo_service.current_semester()
    photo = photo_service.photo_path(user.id, home["grade"], semester)
    photo_url = (url_for("main.semester_photo", grade=home["grade"], semester=semester, v=int(photo.stat().st_mtime))
                 if photo.is_file() else None)
    show_return = bool(home["away_days"]) and not session.get("return_seen")
    if show_return:
        session["return_seen"] = True  # 同一次登入只播一次
    return render_template(
        "student_home.html",
        user=user,
        journey=journey,
        home=home,
        autobiography_note=student_rules.review_open_note(user),
        show_return=show_return,
        photo_url=photo_url,
        semester_label="上學期" if semester == 1 else "下學期",
        targets=targets,
        target_groups=target_groups,
        category_keys=CATEGORY_KEYS,
        category_labels=CATEGORY_LABELS,
        experience_categories=EXPERIENCE_CATEGORIES,
        source_documents=SourceDocument.query.filter_by(owner_id=user.id).all(),
        guide=guide_cards(user, session.get("guide_snooze")),
    )


def _welcome_done(user):
    return AuditLog.query.filter_by(user_id=user.id, action="student.welcome_done").first() is not None


@main_bp.get("/student/welcome")
@role_required("student")
def student_welcome():
    """第一次登入的歡迎流程：一次一個畫面，像手機或電腦的開機設定。"""
    user = get_current_user()
    profile = user.student_profile
    grade = current_grade(profile.admission_year if profile else None)
    return render_template(
        "student_welcome.html",
        user=user,
        grade_label=GRADE_LABELS.get(grade),
        grade=grade,
        schools=load_sample_programs()[:1],
        plan=FIVE_YEAR_PLAN,
    )


@main_bp.post("/student/welcome/done")
@role_required("student")
def student_welcome_done():
    user = get_current_user()
    if not _welcome_done(user):
        db.session.add(AuditLog(user_id=user.id, action="student.welcome_done", ip_address=request.remote_addr))
        db.session.commit()
    destinations = {
        "upload": "student.learning_profile_upload_page",
        "activity": "student.portfolio_new",
        "schools": "student.target_list",
    }
    choice = request.form.get("to", "")
    endpoint = destinations.get(choice, "main.student_dashboard")
    return redirect(url_for(endpoint, category="activity") if choice == "activity" else url_for(endpoint))


@main_bp.get("/ocr/acceptance")
@role_required("student", "teacher", "staff", "admin")
def ocr_acceptance():
    """OCR 實測結果：逐欄對照原圖的驗收紀錄。內容在 app/content/ocr_acceptance.py。"""
    from app.content.ocr_acceptance import ACCEPTANCE
    return render_template("ocr_acceptance.html", user=get_current_user(), data=ACCEPTANCE)


@main_bp.get("/help")
@role_required("student", "teacher", "staff", "admin")
def help_page():
    """❓ 怎麼操作：常見問題（不用 AI、不花額度）。內容在 app/content/help.py。"""
    from app.content.help import HELP
    user = get_current_user()
    tour_routes = {
        "student": ("student-dashboard", "main.student_dashboard"),
        "teacher": ("teacher-dashboard", "main.teacher_dashboard"),
        "staff": ("staff-dashboard", "main.staff_dashboard"),
        "admin": ("admin-dashboard", "main.admin_dashboard"),
    }
    tour_page, tour_endpoint = tour_routes[user.role]
    return render_template("help.html", user=user, sections=HELP.get(user.role, HELP["student"]),
                           tour_page=tour_page, tour_url=url_for(tour_endpoint, tour=1))


@main_bp.post("/student/photo")
@role_required("student")
def semester_photo_upload():
    """上傳這學期最快樂的照片，當成首頁拼圖的圖。只有本人看得到。"""
    user = get_current_user()
    upload = request.files.get("photo")
    if not upload or not upload.filename:
        abort(400)
    from app.services.journey_service import current_grade
    grade = current_grade(user.student_profile.admission_year if user.student_profile else None) or 1
    try:
        photo_service.save_photo(user.id, grade, photo_service.current_semester(), upload.stream)
    except ValueError as error:
        return str(error), 400
    return redirect(url_for("main.student_dashboard") + "#puzzle-title")


@main_bp.get("/student/photo/<int:grade>/<int:semester>")
@role_required("student")
def semester_photo(grade, semester):
    path = photo_service.photo_path(get_current_user().id, grade, semester)
    if semester not in (1, 2) or not path.is_file():
        abort(404)
    response = send_file(path, mimetype="image/jpeg")
    response.headers["Cache-Control"] = "no-store"  # 共用電腦登出後，按上一頁也不會留下照片（會議室 GPT #10）
    return response


@main_bp.post("/student/guide/snooze")
@role_required("student")
def guide_snooze():
    """引導卡片「稍後再說」：記在工作階段裡，隔一天再出現。"""
    card = request.form.get("card", "")
    if card not in CARD_IDS:
        abort(400)
    snoozed = dict(session.get("guide_snooze") or {})
    snoozed[card] = datetime.now(timezone.utc).isoformat()
    session["guide_snooze"] = snoozed
    if request.headers.get("X-Requested-With") == "fetch":
        return "", 204
    return redirect(url_for("main.student_dashboard"))


@main_bp.get("/teacher/dashboard")
@role_required("teacher")
def teacher_dashboard():
    user = get_current_user()
    assignments = (
        SubmissionAssignment.query.filter_by(teacher_id=user.id)
        .order_by(SubmissionAssignment.assigned_at.desc())
        .all()
    )
    students = students_for_teacher(user)
    rows = []
    for student in students:
        journey = build_journey(student)
        targets = StudentTarget.query.filter_by(student_id=student.id).all()
        reviews = [latest_review(student, target.program) for target in targets]
        rows.append({
            "student": student,
            "totals": journey["totals"],
            "missing": len(journey["missing_categories"]),
            "targets": [target.program for target in targets],
            "pending": sum(1 for review in reviews if review and review.status == "pending"),
        })
    return render_template(
        "dashboard.html",
        title="教師工作台",
        user=user,
        teacher_assignments=assignments,
        classes=advised_classes(user),
        class_rows=rows,
        category_keys=CATEGORY_KEYS,
        category_labels=CATEGORY_LABELS,
    )


@main_bp.get("/staff/dashboard")
@role_required("staff")
def staff_dashboard():
    user = get_current_user()
    pending_submissions = (
        PortfolioSubmission.query.filter_by(status="submitted")
        .order_by(PortfolioSubmission.created_at.desc())
        .all()
    )
    return render_template(
        "dashboard.html",
        title="科辦／行政工作台",
        user=user,
        staff_pending_submissions=pending_submissions,
        staff_pending_certificates=AwardCertificate.query.filter_by(status="pending").count(),
        staff_feedback_by_submission=feedback_by_submission(
            [item.id for item in pending_submissions]
        ),
    )


@main_bp.get("/admin/dashboard")
@role_required("admin")
def admin_dashboard():
    user = db.session.get(User, session["user_id"])
    return render_template(
        "admin_dashboard.html",
        user=user,
        student_count=User.query.filter_by(role="student", is_active=True).count(),
        teacher_count=User.query.filter_by(role="teacher", is_active=True).count(),
        staff_count=User.query.filter_by(role="staff", is_active=True).count(),
        submission_count=PortfolioSubmission.query.count(),
        pending_submission_count=PortfolioSubmission.query.filter_by(status="submitted").count(),
        recent_submissions=(
            PortfolioSubmission.query.order_by(PortfolioSubmission.created_at.desc())
            .limit(6)
            .all()
        ),
    )


@main_bp.get("/admin")
def admin_legacy_route():
    return redirect(url_for("main.admin_dashboard"))


@main_bp.get("/dashboard/<role>")
@role_required("student", "teacher", "staff", "admin")
def role_dashboard(role):
    user = db.session.get(User, session["user_id"])
    if role != user.role:
        abort(403)
    destinations = {
        "student": "main.student_dashboard",
        "teacher": "main.teacher_dashboard",
        "staff": "main.staff_dashboard",
        "admin": "main.admin_dashboard",
    }
    endpoint = destinations.get(role)
    if not endpoint:
        abort(403)
    return redirect(url_for(endpoint))


@main_bp.app_context_processor
def inject_student_progress():
    """學生的每一頁都要顯示主線步驟列與「下一步」。"""
    user = get_current_user()
    if user and user.role == "student":
        from app.models.transfer_credit import TransferCreditRecord
        from app.services.student_progress import student_progress
        # 「抵免進度」只給轉學生：目前以「已建立抵免紀錄」判斷，其他學生從「我的五年」的小連結進入
        has_transfer = TransferCreditRecord.query.filter_by(student_id=user.id).first() is not None
        return {"student_progress": student_progress(user), "has_transfer_record": has_transfer}
    return {}
