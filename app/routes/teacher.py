"""導師：查看本班學生資料，確認備審內容或留下修改建議。"""

from flask import Blueprint, abort, redirect, render_template, request, url_for

from app.extensions import db
from app.models import (
    AdmissionProgram,
    AutobiographyComment,
    LearningProfileOutput,
    Notification,
    PackageReview,
    Portfolio,
    PortfolioEvidence,
    SourceDocument,
    StudentTarget,
    TransferCreditRecord,
    TransferPlan,
    User,
)
from app.routes.main import get_current_user, role_required
from app.services.gap_service import ALL_LABELS, analyze_gap
from app.services.journey_service import CATEGORY_KEYS, CATEGORY_LABELS, build_journey
from app.services.package_service import latest_review
from app.services import audit_service, autobiography_service, review_snapshot_service
from app.services import internship_resume as resume
from app.services import autobiography_comment_service as comment_service
from app.services import transfer_plan as transfer_plan_service
from app.services.autobiography_service import latest_draft, version_of
from app.services.file_preview import inline_file
from app.services.teacher_scope import can_view_student
from app.routes import graduation as graduation_routes
from app.services import graduation_case_service, graduation_check_service
from app.services import check_dates, semester_warning
from app.models import GraduationCase, GraduationCaseEvent

teacher_bp = Blueprint("teacher", __name__)


@teacher_bp.post("/teacher/students/<int:student_id>/summary")
@role_required("teacher")
def student_summary(student_id):
    from app.services.teacher_ai_summary import summarize
    teacher = get_current_user()
    student = db.session.get(User, student_id)
    if not student or not can_view_student(teacher, student):
        abort(403)
    return render_template("teacher_class_summary.html", user=teacher, result=summarize([student]),
                           summary_label="學生資料摘要（僅本機統計）")


@teacher_bp.get("/teacher/students/<int:student_id>/internship-resume")
@role_required("teacher")
def internship_resume(student_id):
    teacher = get_current_user()
    student = _student_or_403(teacher, student_id)
    saved = resume.latest_saved(student)
    contents = saved.content_json if saved else None
    return render_template("teacher_internship_resume.html", user=teacher, student=student, saved=saved,
                           contents=contents, blocks=resume.autobiography_blocks(contents["choices"]) if saved else [],
                           columns=dict(resume.COLUMNS))


@teacher_bp.get("/teacher/students/<int:student_id>")
@role_required("teacher")
def student_detail(student_id):
    teacher = get_current_user()
    student = db.session.get(User, student_id)
    if not student or not can_view_student(teacher, student):
        abort(403)
    journey = build_journey(student)
    record_status = request.args.get("record_status", "all")
    if record_status not in {"all", "draft", "confirmed", "other"}:
        record_status = "all"
    record_counts = {"draft": 0, "confirmed": 0, "other": 0}
    teacher_years = []
    for year in [*journey["years"], {"grade": None, "label": "尚未歸入年級", "categories": journey["unsorted"]}]:
        categories = {}
        for key in CATEGORY_KEYS:
            categories[key] = []
            for item in year["categories"][key]:
                status = item.get("confirmation_status")
                group = status if status in {"draft", "confirmed"} else "other"
                record_counts[group] += 1
                if record_status in {"all", group}:
                    categories[key].append(item)
        count = sum(len(items) for items in categories.values())
        if count:
            teacher_years.append({"grade": year["grade"], "label": year["label"], "categories": categories, "count": count})
    current_grade = journey["current_grade"] or 1
    journey_stops = [
        {
            "grade": year["grade"],
            "label": year["label"],
            "count": year["count"],
            "state": (
                "past"
                if year["grade"] < current_grade
                else "now" if year["grade"] == current_grade else "future"
            ),
        }
        for year in journey["years"]
    ]
    programs = [t.program for t in StudentTarget.query.filter_by(student_id=student.id).order_by(StudentTarget.selected_at)]
    chosen = {program.id for program in programs}
    # 學生取消的目標：送審紀錄與快照保留，導師仍看得到（規格 10.4）
    cancelled = [r.program for r in PackageReview.query.filter_by(student_id=student.id).order_by(PackageReview.id)
                 if r.rule_version_id not in chosen]
    targets = []
    for program in programs + list(dict.fromkeys(cancelled)):
        review = latest_review(student, program)
        previous = review_snapshot_service.previous_confirmed(review) if review else None
        draft = latest_draft(student, program)
        gap = analyze_gap(student, program, journey)
        targets.append({
            "program": program,
            "cancelled": program.id not in chosen,
            "gap": gap,
            "reminder_suggestion": reminder_suggestion(gap),
            "submitted_autobiography": _submitted_autobiography(review, student),
            # 送審後自傳又存了新版：導師不能確認舊的那份，要請學生重新送審（組員 46531f2）
            "autobiography_changed": bool(review and review.status == "pending"
                                          and review_snapshot_service.autobiography_changed(review)),
            "open_comments": comment_service.open_count(student, program) if draft else 0,
            "review": review,
            "previous": previous,
            "diff": (review_snapshot_service.snapshot_diff(review.snapshot_json, previous.snapshot_json)
                     if review and previous and review.id != previous.id else None),
            "autobiography": draft,
            "current_version": version_of(draft) if draft else None,
        })
    assessment = graduation_check_service.assess(student)
    grad_cases = (GraduationCase.query.filter_by(student_id=student.id)
                  .order_by(GraduationCase.id.desc()).all())
    return render_template(
        "teacher_student.html",
        grad_assessment=assessment,
        grad_cases=[{"case": case, "events": case.events.order_by(GraduationCaseEvent.id.desc()).limit(5).all()}
                    for case in grad_cases],
        grad_next_check=graduation_case_service.next_check_text(assessment["stage"]),
        grad_countdown=check_dates.countdown(assessment["stage"]),
        semester_warnings=semester_warning.build(student),
        warning_labels=semester_warning.LEVEL_LABELS,
        grad_item_labels=graduation_case_service.ITEM_LABELS,
        grad_event_labels=graduation_routes.EVENT_LABELS,
        grad_result_labels=graduation_check_service.RESULT_LABELS,
        grad_disclaimer=graduation_check_service.DISCLAIMER,
        review_notices=review_snapshot_service.NOTICES,
        user=teacher,
        student=student,
        journey=journey,
        teacher_years=teacher_years,
        record_status=record_status,
        record_counts=record_counts,
        journey_stops=journey_stops,
        targets=targets,
        transfer_credit=TransferCreditRecord.query.filter_by(student_id=student.id).first(),
        transfer_plans=[{"plan": plan, "ready": transfer_plan_service.readiness(plan)}
                        for plan in TransferPlan.query.filter_by(student_id=student.id, archived=False)
                        .order_by(TransferPlan.id)],
        documents=SourceDocument.query.filter_by(owner_id=student.id, status="confirmed")
                                      .order_by(SourceDocument.created_at).all(),
        records_with_evidence=[r for r in Portfolio.active().filter_by(student_id=student.id).order_by(Portfolio.id).all()
                               if r.evidence_items],
        category_keys=CATEGORY_KEYS,
        category_labels=CATEGORY_LABELS,
        labels=ALL_LABELS,
        error=request.args.get("error"),
        reminded=request.args.get("reminded", type=int),
    )


def _submitted_autobiography(review, student):
    """送審快照記的那一版自傳（導師要看的是送審時的內容，不是學生之後改的）。"""
    info = (review.snapshot_json or {}).get("autobiography") if review else None
    output = db.session.get(LearningProfileOutput, info.get("output_id")) if info else None
    if not output or output.student_id != student.id or output.output_type != autobiography_service.OUTPUT_TYPE:
        return None
    return output


def gap_needs(gap):
    """缺件分析裡還沒備齊的資料類別（中文名稱，不重複）。"""
    return list(dict.fromkeys(ALL_LABELS.get(key, key) for item in gap["items"]
                              for key, level in item["levels"].items() if level < 1))


def reminder_suggestion(gap):
    """提醒內容的預設文字：列出還沒備齊的類別；導師送出前可以改。"""
    needs = gap_needs(gap)
    if needs:
        return ("請查看這個校系的備審資料，建議優先準備：" + "、".join(needs) + "。")[:180]
    return "請查看這個校系的備審要求，確認資料是否準備完整。"


@teacher_bp.post("/teacher/students/<int:student_id>/targets/<int:program_id>/remind")
@role_required("teacher")
def remind_target(student_id, program_id):
    """導師看完校系明細後，改好提醒文字送站內通知；學生點通知直接到該校系的備審頁。"""
    teacher = get_current_user()
    student = _student_or_403(teacher, student_id)
    if not StudentTarget.query.filter_by(student_id=student.id, rule_version_id=program_id).first():
        abort(404)
    message = (request.form.get("message") or "").strip()
    if not message or len(message) > 180:
        abort(400, description="提醒內容請寫 1 到 180 字。")
    note = Notification(recipient_id=student.id, message=f"{teacher.display_name[:40]}老師提醒：{message}"[:255],
                        link=url_for("student.target_gap", program_id=program_id))
    db.session.add(note)
    db.session.flush()
    audit_service.record(teacher, "target.teacher_reminder", "notification", note.id,
                         detail={"student_id": student.id, "program_id": program_id})
    db.session.commit()
    return redirect(url_for("teacher.student_detail", student_id=student.id, reminded=program_id,
                            _anchor=f"teacher-target-{program_id}"))


@teacher_bp.get("/teacher/evidence/<int:evidence_id>/view")
@role_required("teacher")
def evidence_view(evidence_id):
    """導師看本班學生的佐證照片；不是自己班的學生就 403。"""
    evidence = db.session.get(PortfolioEvidence, evidence_id)
    if not evidence or evidence.deleted_at:
        abort(404)
    if not can_view_student(get_current_user(), evidence.portfolio.student):
        abort(403)
    return inline_file(evidence.file_path, evidence.display_name)


@teacher_bp.get("/teacher/documents/<int:document_id>/view")
@role_required("teacher")
def document_view(document_id):
    """導師看本班學生上傳的成績單、證照原始檔（只限學生已確認的）。"""
    document = db.session.get(SourceDocument, document_id)
    if not document or document.status != "confirmed":
        abort(404)
    if not can_view_student(get_current_user(), document.owner):
        abort(403)
    return inline_file(document.file_path, document.display_name)


@teacher_bp.post("/teacher/package-reviews/<int:review_id>")
@role_required("teacher")
def decide_review(review_id):
    teacher, review = _reviewable_or_abort(review_id)
    decision = request.form.get("decision", "")
    comment = request.form.get("comment", "").strip()
    if decision not in {"confirmed", "needs_revision"}:
        abort(400, description="請選擇「確認」或「需要修改」")
    if decision == "needs_revision" and not comment:
        abort(400, description="需要修改時，請寫下給學生的建議")
    try:
        review_snapshot_service.decide(review, teacher, decision, comment, request.form.get("taken_at", ""),
                                      autobiography_viewed=request.form.get("autobiography_viewed") == "1")
    except review_snapshot_service.ReviewChanged as exc:
        return redirect(url_for("teacher.student_detail", student_id=review.student_id, notice=exc.code))
    return redirect(url_for("teacher.student_detail", student_id=review.student_id))


def _reviewable_or_abort(review_id):
    teacher = get_current_user()
    review = db.session.get(PackageReview, review_id)
    if not review:
        abort(404)
    if not can_view_student(teacher, review.student):
        abort(403)
    return teacher, review


@teacher_bp.post("/teacher/package-reviews/<int:review_id>/withdraw")
@role_required("teacher")
def withdraw_review(review_id):
    """導師按錯時撤回確認；要寫原因，原本的確認紀錄保留。"""
    teacher, review = _reviewable_or_abort(review_id)
    try:
        review_snapshot_service.withdraw(review, teacher, request.form.get("reason", "").strip())
    except ValueError as exc:
        abort(400, description=str(exc))
    return redirect(url_for("teacher.student_detail", student_id=review.student_id))


@teacher_bp.get("/teacher/students/<int:student_id>/autobiography/<int:output_id>/edit")
@teacher_bp.post("/teacher/students/<int:student_id>/autobiography/<int:output_id>/edit")
@role_required("teacher")
def autobiography_edit(student_id, output_id):
    """導師直接修改學生自傳、留段落意見；每次儲存都是新的一版，學生看得到改了哪裡。"""
    teacher = get_current_user()
    student = db.session.get(User, student_id)
    if not student or not can_view_student(teacher, student):
        abort(403)
    output = db.session.get(LearningProfileOutput, output_id)
    if not output or output.output_type != autobiography_service.OUTPUT_TYPE or output.student_id != student.id:
        abort(404)
    program = db.session.get(AdmissionProgram, output.content_json.get("program_id"))
    if request.method == "POST":
        count = len(output.content_json.get("paragraphs", []))
        texts = [request.form.get(f"paragraph_{i}", "") for i in range(count)]
        # 11-18 起段落意見改用下方的段落註解；舊表單（有 comment_ 欄位）仍照舊存進段落意見
        comments = ([request.form.get(f"comment_{i}", "") for i in range(count)]
                    if any(f"comment_{i}" in request.form for i in range(count)) else None)
        try:
            saved = autobiography_service.save_edits(output, texts, teacher, comments=comments)
            db.session.add(Notification(
                recipient_id=student.id,
                message=f"{teacher.display_name}老師修改了你的自傳，請查看改了哪裡。"[:255],
                link=url_for("student.autobiography_versions", program_id=program.id, v=saved.id),
            ))
            audit_service.record(teacher, "autobiography.teacher_edit", "learning_profile_output", saved.id,
                                 detail={"student_id": student.id}, commit=True)
        except autobiography_service.StaleVersion as exc:
            latest = latest_draft(student, program)
            return _render_edit(teacher, student, program, latest,
                                stale={"message": str(exc), "texts": texts, "comments": comments or [""] * count,
                                       "paragraphs": output.content_json["paragraphs"]}), 409
        return redirect(url_for("teacher.student_detail", student_id=student.id, saved=1))
    return _render_edit(teacher, student, program, output)


def _render_edit(teacher, student, program, output, stale=None, comment_error=None):
    by_paragraph, orphans = comment_service.threads(student, program, output.content_json.get("paragraphs", []))
    latest = latest_draft(student, program)
    return render_template("teacher_autobiography_edit.html", user=teacher, student=student, program=program,
                           output=output, version=version_of(output), stale=stale,
                           threads=by_paragraph, orphan_threads=orphans, comment_error=comment_error,
                           is_latest=bool(latest and latest.id == output.id))


def _student_or_403(teacher, student_id):
    student = db.session.get(User, student_id)
    if not student or not can_view_student(teacher, student):
        abort(403)
    return student


@teacher_bp.get("/teacher/students/<int:student_id>/autobiography/program/<int:program_id>")
@role_required("teacher")
def autobiography_latest(student_id, program_id):
    """通知連結用：一律打開這個校系最新一版的自傳（通知寄出後學生可能又存了新版）。"""
    student = _student_or_403(get_current_user(), student_id)
    program = db.session.get(AdmissionProgram, program_id)
    draft = latest_draft(student, program) if program else None
    if not draft:
        abort(404)
    return redirect(url_for("teacher.autobiography_edit", student_id=student.id, output_id=draft.id))


@teacher_bp.get("/teacher/students/<int:student_id>/autobiography/versions/<int:program_id>")
@role_required("teacher")
def autobiography_versions(student_id, program_id):
    """導師看學生自傳的所有版本與差異（組員 0837903）；只限自己班的學生。"""
    from app.routes.student import _version_view
    teacher = get_current_user()
    student = _student_or_403(teacher, student_id)
    program = db.session.get(AdmissionProgram, program_id)
    if not program or not autobiography_service.versions(student, program):
        abort(404)
    return render_template("autobiography_versions.html", user=teacher, student=student, program=program,
                           teacher_view=True, cancelled=False,
                           **_version_view(student, program, request.args.get("v", type=int)))


@teacher_bp.post("/teacher/students/<int:student_id>/autobiography/<int:output_id>/comments")
@role_required("teacher")
def autobiography_comment(student_id, output_id):
    """導師在某一段新增註解；同一段可以有很多則。"""
    teacher = get_current_user()
    student = _student_or_403(teacher, student_id)
    output = db.session.get(LearningProfileOutput, output_id)
    if not output or output.output_type != autobiography_service.OUTPUT_TYPE or output.student_id != student.id:
        abort(404)
    paragraph = request.form.get("paragraph", type=int)
    try:
        comment_service.add_comment(teacher, student, output, paragraph, request.form.get("text"))
    except comment_service.CommentError as exc:
        program = db.session.get(AdmissionProgram, output.content_json.get("program_id"))
        return _render_edit(teacher, student, program, output, comment_error=str(exc)), 400
    return redirect(url_for("teacher.autobiography_latest", student_id=student.id,
                            program_id=output.content_json.get("program_id"), _anchor=f"paragraph-{paragraph}"))


@teacher_bp.post("/teacher/autobiography-comments/<int:comment_id>/<action>")
@role_required("teacher")
def autobiography_comment_action(comment_id, action):
    """導師回覆、標記已處理或改回待處理。"""
    teacher = get_current_user()
    comment = db.session.get(AutobiographyComment, comment_id)
    if not comment or comment.parent_id or action not in {"reply", "resolve", "reopen"}:
        abort(404)
    student = _student_or_403(teacher, comment.student_id)
    try:
        if action == "reply":
            comment_service.reply(teacher, comment, request.form.get("text"))
        else:
            comment_service.set_resolved(teacher, comment, action == "resolve")
    except comment_service.CommentError as exc:
        abort(400, description=str(exc))
    return redirect(url_for("teacher.autobiography_latest", student_id=student.id, program_id=comment.program_id,
                            _anchor=f"paragraph-{comment.paragraph}"))


@teacher_bp.post("/teacher/students/<int:student_id>/transfer-plans/<int:plan_id>")
@role_required("teacher")
def transfer_plan_update(student_id, plan_id):
    """B18：導師修正學生的插大目標（日期、考科打錯）並留言；不蓋掉學生備註，修改寫進操作紀錄。"""
    teacher = get_current_user()
    student = db.session.get(User, student_id)
    plan = db.session.get(TransferPlan, plan_id)
    if not student or not can_view_student(teacher, student) or not plan or plan.student_id != student.id:
        abort(403)
    try:
        fields, names = transfer_plan_service.parse_plan_form(request.form)
    except transfer_plan_service.PlanFormError as exc:
        abort(400, description=str(exc))
    fields.pop("note", None)
    before = {"exam_date": str(plan.exam_date), "subjects": [s.name for s in plan.subjects]}
    for key, value in fields.items():
        setattr(plan, key, value)
    transfer_plan_service.apply_subjects(plan, names)
    plan.teacher_note = (request.form.get("teacher_note") or "").strip()[:2000] or None
    plan.updated_by_id = teacher.id
    audit_service.record(teacher, "transfer_plan.teacher_update", "transfer_plan", plan.id,
                         detail={"before": before, "after": {"exam_date": str(plan.exam_date), "subjects": names}})
    db.session.commit()
    return redirect(url_for("teacher.student_detail", student_id=student.id, _anchor=f"transfer-plan-{plan.id}"))
