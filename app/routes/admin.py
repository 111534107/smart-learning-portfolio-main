from datetime import date, datetime, timezone

from flask import Blueprint, abort, current_app, redirect, render_template, request, session, url_for

from app.extensions import db
from app.security import validate_upload_filename
from app.models import (
    AdmissionProgram,
    AgentTask,
    AuditLog,
    PublicSource,
    PublicSourceChange,
    PublicSourceSnapshot,
    AdmissionRequirementItem,
    ClassAdvisor,
    CourseRule,
    MatchFilterOption,
    ProjectType,
    RequirementItem,
    RequirementTemplate,
    StudentProfile,
    User,
)
from app.services import admission_agent_service as agent
from app.services.admission_service import import_seed_programs, published_programs
from app.services.gemini_client import ai_ready
from app.services.gap_service import ALL_LABELS
from app.services.journey_service import academic_year_of
from app.models.match_filter import MATCH_FILTER_CATEGORIES
from app.routes.main import get_current_user, role_required


admin_bp = Blueprint("admin", __name__)


def _normalise_course_name(value):
    return "".join(value.split())


@admin_bp.route("/admin/course-rules", methods=["GET", "POST"])
@role_required("admin")
def course_rules():
    if request.method == "POST":
        course_name = request.form.get("course_name", "").strip()
        normalized_course_name = _normalise_course_name(course_name)
        category = request.form.get("category", "").strip()
        requirement_type = request.form.get("requirement_type", "").strip()
        try:
            school_year = int(request.form.get("school_year", ""))
            credits_value = request.form.get("credits", "").strip()
            credits = int(credits_value) if credits_value else None
        except ValueError:
            abort(400, description="School year and credits must be numbers")
        if not normalized_course_name or not category or requirement_type not in {"required", "elective"}:
            abort(400, description="Course name, category, and requirement type are required")
        if CourseRule.query.filter_by(
            school_year=school_year, normalized_course_name=normalized_course_name
        ).first():
            abort(400, description="A rule for this school year and course already exists")
        db.session.add(CourseRule(
            school_year=school_year,
            course_name=course_name,
            normalized_course_name=normalized_course_name,
            category=category,
            requirement_type=requirement_type,
            credits=credits,
            ability_domain=request.form.get("ability_domain", "").strip() or None,
            is_active=True,
        ))
        db.session.commit()
        return redirect(url_for("admin.course_rules"))
    return render_template(
        "admin_course_rules.html",
        user=get_current_user(),
        course_rules=CourseRule.query.order_by(CourseRule.school_year.desc(), CourseRule.course_name.asc()).all(),
    )


@admin_bp.post("/admin/course-rules/<int:rule_id>/toggle-active")
@role_required("admin")
def toggle_course_rule_active(rule_id):
    rule = db.session.get(CourseRule, rule_id)
    if not rule:
        abort(404)
    rule.is_active = not rule.is_active
    db.session.commit()
    return redirect(url_for("admin.course_rules"))


MATCH_FILTER_CATEGORY_LABELS = {"department": "科系", "region": "地區（尚未啟用）", "level": "學制", "eligible": "是否可報"}


MATCH_FILTER_ELIGIBLE_VALUES = {"eligible": "可報", "needs_check": "需確認", "ineligible": "不可報"}


def _check_match_filter_label(label):
    limit = MatchFilterOption.label.type.length
    if len(label) > limit:
        abort(400, description=f"顯示名稱不可超過 {limit} 個字")


@admin_bp.route("/admin/match-filters", methods=["GET", "POST"])
@role_required("admin")
def match_filters():
    if request.method == "POST":
        category = request.form.get("category", "").strip()
        label = request.form.get("label", "").strip()
        value = request.form.get("value", "").strip()
        try:
            sort_order = int(request.form.get("sort_order", "").strip() or 0)
        except ValueError:
            abort(400, description="Sort order must be a number")
        if category not in MATCH_FILTER_CATEGORIES or not label or not value:
            abort(400, description="Category, label, and value are required")
        _check_match_filter_label(label)
        if len(value) > MatchFilterOption.value.type.length:
            abort(400, description=f"值不可超過 {MatchFilterOption.value.type.length} 個字")
        if category == "eligible" and value not in MATCH_FILTER_ELIGIBLE_VALUES:
            abort(400, description="「是否可報」的值只能是 eligible、needs_check、ineligible")
        if MatchFilterOption.query.filter_by(category=category, value=value).first():
            abort(400, description="This filter option already exists")
        db.session.add(MatchFilterOption(
            category=category, label=label, value=value, sort_order=sort_order, is_active=True,
        ))
        db.session.commit()
        return redirect(url_for("admin.match_filters"))
    return render_template(
        "admin_match_filters.html",
        user=get_current_user(),
        options=MatchFilterOption.query.order_by(
            MatchFilterOption.category.asc(), MatchFilterOption.sort_order.asc(), MatchFilterOption.id.asc()
        ).all(),
        category_labels=MATCH_FILTER_CATEGORY_LABELS,
        eligible_values=MATCH_FILTER_ELIGIBLE_VALUES,
        level_values=sorted({p.admission_category for p in published_programs() if p.admission_category}),
    )


@admin_bp.post("/admin/match-filters/<int:option_id>/edit")
@role_required("admin")
def edit_match_filter(option_id):
    option = db.session.get(MatchFilterOption, option_id)
    if not option:
        abort(404)
    label = request.form.get("label", "").strip()
    if not label:
        abort(400, description="顯示名稱不可空白")
    _check_match_filter_label(label)
    try:
        sort_order = int(request.form.get("sort_order", "").strip() or 0)
    except ValueError:
        abort(400, description="Sort order must be a number")
    option.label = label
    option.sort_order = sort_order
    db.session.commit()
    return redirect(url_for("admin.match_filters"))


@admin_bp.post("/admin/match-filters/<int:option_id>/toggle-active")
@role_required("admin")
def toggle_match_filter(option_id):
    option = db.session.get(MatchFilterOption, option_id)
    if not option:
        abort(404)
    option.is_active = not option.is_active
    db.session.commit()
    return redirect(url_for("admin.match_filters"))


@admin_bp.get("/admin/accounts")
@role_required("admin")
def accounts():
    return render_template(
        "admin_accounts.html",
        user=get_current_user(),
        accounts=User.query.order_by(User.role.asc(), User.username.asc()).all(),
        admission_import=session.pop("admission_import", None),
    )


@admin_bp.post("/admin/accounts/admission-years")
@role_required("admin")
def import_admission_years():
    """管理者匯入入學學年度：每行「學號,入學學年度」（逗號或空白分隔）。學生不能自己填（主持人 2026-10-10）。"""
    actor = get_current_user()
    current = academic_year_of(date.today())
    updated, problems = 0, []
    for number, line in enumerate(request.form.get("rows", "").splitlines(), start=1):
        parts = line.replace(",", " ").replace("，", " ").split()
        if not parts:
            continue
        if len(parts) != 2 or not parts[1].isdigit():
            problems.append(f"第 {number} 行看不懂：{line.strip()[:40]}")
            continue
        student_no, year = parts[0], int(parts[1])
        profile = StudentProfile.query.filter_by(student_no=student_no).first()
        if not profile:
            problems.append(f"第 {number} 行找不到學號 {student_no[:20]}")
            continue
        if not current - 7 <= year <= current:
            problems.append(f"第 {number} 行入學學年度 {year} 不在最近 8 個學年度內")
            continue
        if profile.admission_year != year:
            db.session.add(AuditLog(user_id=actor.id, action="student_profile.admission_year",
                                    target_type="student_profile", target_id=profile.id,
                                    detail_json={"from": profile.admission_year, "to": year}))
            profile.admission_year = year
            updated += 1
    db.session.commit()
    session["admission_import"] = {"updated": updated, "problems": problems[:50]}
    return redirect(url_for("admin.accounts"))


@admin_bp.post("/admin/accounts/<int:user_id>/toggle-active")
@role_required("admin")
def toggle_account_active(user_id):
    actor = get_current_user()
    account = db.session.get(User, user_id)
    if not account:
        abort(404)
    if account.id == actor.id:
        abort(400, description="Administrators cannot disable their own account")
    account.is_active = not account.is_active
    db.session.commit()
    return redirect(url_for("admin.accounts"))


@admin_bp.route("/admin/project-types", methods=["GET", "POST"])
@role_required("admin")
def project_types():
    if request.method == "POST":
        code = request.form.get("code", "").strip().lower()
        name = request.form.get("name", "").strip()
        try:
            school_year = int(request.form.get("school_year", ""))
        except ValueError:
            abort(400, description="School year must be a number")
        if not code or not name or ProjectType.query.filter_by(code=code).first():
            abort(400, description="Project type code and name must be unique and complete")
        db.session.add(
            ProjectType(code=code, name=name, school_year=school_year, is_active=True)
        )
        db.session.commit()
        return redirect(url_for("admin.project_types"))
    return render_template(
        "admin_rules.html",
        user=get_current_user(),
        project_types=ProjectType.query.order_by(ProjectType.school_year.desc(), ProjectType.name.asc()).all(),
    )


@admin_bp.post("/admin/project-types/<int:project_type_id>/toggle-active")
@role_required("admin")
def toggle_project_type_active(project_type_id):
    project_type = db.session.get(ProjectType, project_type_id)
    if not project_type:
        abort(404)
    project_type.is_active = not project_type.is_active
    db.session.commit()
    return redirect(url_for("admin.project_types"))


@admin_bp.post("/admin/project-types/<int:project_type_id>/templates")
@role_required("admin")
def create_requirement_template(project_type_id):
    project_type = db.session.get(ProjectType, project_type_id)
    if not project_type:
        abort(404)
    name = request.form.get("name", "").strip()
    version = request.form.get("version", "").strip()
    if not name or not version:
        abort(400, description="Template name and version are required")
    db.session.add(
        RequirementTemplate(
            project_type_id=project_type.id,
            name=name,
            version=version,
            is_active=True,
        )
    )
    db.session.commit()
    return redirect(url_for("admin.project_types"))


@admin_bp.post("/admin/templates/<int:template_id>/toggle-active")
@role_required("admin")
def toggle_template_active(template_id):
    template = db.session.get(RequirementTemplate, template_id)
    if not template:
        abort(404)
    template.is_active = not template.is_active
    db.session.commit()
    return redirect(url_for("admin.project_types"))


@admin_bp.post("/admin/templates/<int:template_id>/items")
@role_required("admin")
def create_requirement_item(template_id):
    template = db.session.get(RequirementTemplate, template_id)
    if not template:
        abort(404)
    title = request.form.get("title", "").strip()
    if not title:
        abort(400, description="Requirement title is required")
    try:
        sort_order = int(request.form.get("sort_order", "0"))
    except ValueError:
        abort(400, description="Sort order must be a number")
    db.session.add(
        RequirementItem(
            template_id=template.id,
            title=title,
            description=request.form.get("description", "").strip() or None,
            stage=request.form.get("stage", "midterm").strip() or "midterm",
            is_required=request.form.get("is_required", "on") == "on",
            sort_order=sort_order,
        )
    )
    db.session.commit()
    return redirect(url_for("admin.project_types"))


# ---------- 校系備審要求（二技招生資料 Agent 第一階段：管理者維護） ----------

@admin_bp.get("/admin/programs")
@role_required("admin")
def programs():
    return render_template(
        "admin_programs.html",
        user=get_current_user(),
        programs=AdmissionProgram.query.order_by(
            AdmissionProgram.status, AdmissionProgram.admission_year.desc(), AdmissionProgram.program_code).all(),
        mappable=list(ALL_LABELS.items()),
        message=request.args.get("message"),
        compare=agent.compare_with_published,
    )


@admin_bp.post("/admin/programs/import-seed")
@role_required("admin")
def programs_import_seed():
    created = import_seed_programs()
    return redirect(url_for("admin.programs", message=f"已匯入 {created} 個志願" if created else "種子資料都已存在，沒有新增"))


@admin_bp.post("/admin/programs/<int:program_id>/toggle-status")
@role_required("admin")
def program_toggle_status(program_id):
    program = db.session.get(AdmissionProgram, program_id)
    if not program:
        abort(404)
    program.status = "candidate" if program.status == "published" else "published"
    db.session.commit()
    return redirect(url_for("admin.programs"))


@admin_bp.post("/admin/program-items/<int:item_id>")
@role_required("admin")
def program_item_update(item_id):
    item = db.session.get(AdmissionRequirementItem, item_id)
    if not item:
        abort(404)
    categories = [key for key in request.form.getlist("categories") if key in ALL_LABELS]
    if not categories:
        abort(400, description="至少要對應一個資料類別")
    status = request.form.get("mapping_status", "pending")
    item.mapped_categories = ",".join(categories)
    item.mapping_status = status if status in {"confirmed", "pending"} else "pending"
    db.session.commit()
    return redirect(url_for("admin.programs") + f"#program-{item.rule_version_id}")


# ---------- 招生資料 Agent（系統亮點第二、三階段） ----------

@admin_bp.get("/admin/agent")
@role_required("admin")
def agent_home():
    sources = PublicSource.query.order_by(PublicSource.id).all()
    latest = {}
    for source in sources:
        latest[source.id] = (PublicSourceSnapshot.query.filter_by(source_id=source.id)
                             .order_by(PublicSourceSnapshot.id.desc()).first())
    changes = (db.session.query(PublicSourceChange, PublicSourceSnapshot, PublicSource)
               .join(PublicSourceSnapshot, PublicSourceChange.snapshot_id == PublicSourceSnapshot.id)
               .join(PublicSource, PublicSourceSnapshot.source_id == PublicSource.id)
               .order_by(PublicSourceChange.id.desc()).limit(20).all())
    tasks = (AgentTask.query.filter(AgentTask.task_type.in_(["admission_source_check", "admission_extract", "agent_patrol"]))
             .order_by(AgentTask.id.desc()).limit(15).all())
    from app.services.admission_schedule import schedule_groups
    return render_template(
        "admin_agent.html",
        schedule_groups=schedule_groups(),
        user=get_current_user(),
        sources=sources,
        latest=latest,
        changes=changes,
        tasks=tasks,
        ai_ready=ai_ready(),
        keywords=current_app.config["AGENT_PROGRAM_KEYWORDS"],
        message=request.args.get("message"),
        error=request.args.get("error"),
    )


@admin_bp.post("/admin/agent/sources")
@role_required("admin")
def agent_add_source():
    uploaded = request.files.get("file")
    try:
        if uploaded and uploaded.filename:
            safe_name = validate_upload_filename(uploaded.filename, {"pdf", "html", "htm"})
            content = uploaded.read()
            if not content:
                raise ValueError("檔案是空的")
            source = agent.add_source(request.form.get("name"), upload_name=safe_name)
            content_type = "application/pdf" if safe_name.lower().endswith(".pdf") else "text/html"
            agent.check_source(source, get_current_user(), content=content, content_type=content_type)
            return redirect(url_for("admin.agent_home", message=f"已上傳「{source.name}」，可以按「擷取加權」"))
        source = agent.add_source(request.form.get("name"), url=request.form.get("url", "").strip())
    except ValueError as exc:
        return redirect(url_for("admin.agent_home", error=str(exc)))
    return redirect(url_for("admin.agent_home", message=f"已新增來源「{source.name}」，按「立即檢查」抓第一次"))


@admin_bp.post("/admin/agent/sources/<int:source_id>/check")
@role_required("admin")
def agent_check_source(source_id):
    source = db.session.get(PublicSource, source_id)
    if not source or source.source_type != "url":
        abort(404)
    task = agent.check_source(source, get_current_user())
    if task.status != "succeeded":
        return redirect(url_for("admin.agent_home", error=task.error_message))
    text = "內容有更新，已建立變更，可以擷取加權" if task.result_json["changed"] else "內容和上次一樣，沒有更新"
    return redirect(url_for("admin.agent_home", message=f"「{source.name}」：{text}"))


@admin_bp.post("/admin/agent/patrol")
@role_required("admin")
def agent_patrol():
    from app.services.agent_patrol import run_patrol
    result = run_patrol(get_current_user())
    return redirect(url_for("admin.agent_home", message=result["summary"]))


@admin_bp.post("/admin/agent/schedule/<channel>/<int:year>/<decision>")
@role_required("admin")
def agent_schedule_decide(channel, year, decision):
    """候選日程整組核准（取代目前的日程）或退回。"""
    from app.models import AdmissionScheduleEvent
    if decision not in ("approve", "reject"):
        abort(404)
    candidates = AdmissionScheduleEvent.query.filter_by(channel=channel, admission_year=year, status="candidate").all()
    if not candidates:
        abort(404)
    actor, now = get_current_user(), datetime.now(timezone.utc)
    if decision == "approve":
        retired = AdmissionScheduleEvent.query.filter_by(channel=channel, admission_year=year, status="published").all()
        for event in retired:
            event.status = "retired"
    for event in candidates:
        event.status = "published" if decision == "approve" else "rejected"
        event.reviewed_by, event.reviewed_at = actor.id, now
    db.session.add(AuditLog(user_id=actor.id, action=f"admission_schedule.{decision}", target_type="admission_schedule",
                            target_id=year, detail_json={"channel": channel, "year": year, "count": len(candidates)}))
    db.session.commit()
    text = "已核准，招生時程頁改用這一組日程" if decision == "approve" else "已退回這一組候選日程"
    return redirect(url_for("admin.agent_home", message=f"{year} 學年度：{text}（{len(candidates)} 項）。"))


@admin_bp.post("/admin/agent/changes/<int:change_id>/extract")
@role_required("admin")
def agent_extract(change_id):
    change = db.session.get(PublicSourceChange, change_id)
    if not change:
        abort(404)
    task = agent.extract_programs(change, get_current_user())
    if task.status != "succeeded":
        return redirect(url_for("admin.agent_home", error=task.error_message))
    created = task.result_json["created"]
    if not created:
        return redirect(url_for("admin.agent_home", message="沒有新的校系（可能已擷取過，或沒有符合關鍵字的科系）"))
    return redirect(url_for("admin.programs", message=f"Agent 建立了 {len(created)} 個候選校系，請核對加權與對應後再核准"))


# ---------- 導師班級 ----------

@admin_bp.get("/admin/classes")
@admin_bp.post("/admin/classes")
@role_required("admin")
def classes():
    error = None
    if request.method == "POST":
        teacher = db.session.get(User, request.form.get("teacher_id", type=int) or 0)
        class_name = request.form.get("class_name", "").strip()
        school_year = request.form.get("school_year", type=int)
        if not teacher or teacher.role != "teacher":
            error = "請選擇導師帳號"
        elif not class_name or not school_year:
            error = "請填寫班級與學年度"
        elif ClassAdvisor.query.filter_by(teacher_id=teacher.id, class_name=class_name, school_year=school_year).first():
            error = "這位導師已經負責這個班級"
        else:
            db.session.add(ClassAdvisor(teacher_id=teacher.id, class_name=class_name, school_year=school_year))
            db.session.commit()
            return redirect(url_for("admin.classes"))
    class_names = sorted({p.class_name for p in StudentProfile.query.all() if p.class_name})
    return render_template(
        "admin_classes.html",
        user=get_current_user(),
        advisors=ClassAdvisor.query.order_by(ClassAdvisor.school_year.desc(), ClassAdvisor.class_name).all(),
        teachers=User.query.filter_by(role="teacher", is_active=True).order_by(User.display_name).all(),
        class_names=class_names,
        error=error,
    ), (400 if error else 200)


@admin_bp.post("/admin/classes/<int:advisor_id>/delete")
@role_required("admin")
def class_delete(advisor_id):
    advisor = db.session.get(ClassAdvisor, advisor_id)
    if advisor:
        db.session.delete(advisor)
        db.session.commit()
    return redirect(url_for("admin.classes"))


@admin_bp.get("/admin/ocr")
@admin_bp.post("/admin/ocr")
@role_required("admin")
def ocr_settings_page():
    """切換 OCR 用 CPU 或顯示卡（DirectML）辨識；設定存在資料庫，切換後不用重開網站。"""
    from app.services import ocr_settings

    error = None
    if request.method == "POST":
        try:
            ocr_settings.save_device(request.form.get("device", ""),
                                     request.form.get("dml_device_id", type=int, default=-1),
                                     get_current_user())
            return redirect(url_for("admin.ocr_settings_page", saved=1))
        except ValueError as exc:
            error = str(exc)
    device, dml_device_id = ocr_settings.current_device()
    return render_template(
        "admin_ocr.html",
        user=get_current_user(),
        device=device,
        dml_device_id=dml_device_id,
        device_labels=ocr_settings.DEVICE_LABELS,
        gpu_available=ocr_settings.directml_available(),
        provider=current_app.config.get("DOCUMENT_ANALYSIS_PROVIDER"),
        error=error,
    ), (400 if error else 200)


@admin_bp.get("/admin/audit-logs")
@role_required("admin")
def audit_logs():
    """操作紀錄（規格 M11）：最近 200 筆，可依動作篩選。只顯示角色與使用者編號，不顯示姓名與學號。"""
    from app.services import audit_service

    action = request.args.get("action", "").strip()
    query = AuditLog.query
    if action:
        query = query.filter_by(action=action)
    logs = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(200).all()
    known = {row[0] for row in db.session.query(AuditLog.action).distinct()}
    return render_template(
        "admin_audit_logs.html",
        user=get_current_user(),
        logs=logs,
        action=action,
        actions=sorted(known | set(audit_service.ACTION_LABELS)),
        label=audit_service.label,
    )
