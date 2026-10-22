"""導師：查看本班學生資料，確認備審內容或留下修改建議。"""

from flask import Blueprint, abort, redirect, render_template, request, url_for

from app.extensions import db
from app.models import (
    AdmissionProgram,
    LearningProfileOutput,
    PackageReview,
    Portfolio,
    PortfolioEvidence,
    SourceDocument,
    StudentTarget,
    TransferCreditRecord,
    User,
)
from app.routes.main import get_current_user, role_required
from app.services.gap_service import ALL_LABELS, analyze_gap
from app.services.journey_service import CATEGORY_KEYS, CATEGORY_LABELS, build_journey
from app.services.package_service import latest_review
from app.services import autobiography_service, review_snapshot_service
from app.services.autobiography_service import latest_draft, version_of
from app.services.file_preview import inline_file
from app.services.teacher_scope import can_view_student

teacher_bp = Blueprint("teacher", __name__)


@teacher_bp.get("/teacher/students/<int:student_id>")
@role_required("teacher")
def student_detail(student_id):
    teacher = get_current_user()
    student = db.session.get(User, student_id)
    if not student or not can_view_student(teacher, student):
        abort(403)
    journey = build_journey(student)
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
        targets.append({
            "program": program,
            "cancelled": program.id not in chosen,
            "gap": analyze_gap(student, program, journey),
            "review": review,
            "previous": previous,
            "diff": (review_snapshot_service.snapshot_diff(review.snapshot_json, previous.snapshot_json)
                     if review and previous and review.id != previous.id else None),
            "autobiography": draft,
            "current_version": version_of(draft) if draft else None,
        })
    return render_template(
        "teacher_student.html",
        review_notices=review_snapshot_service.NOTICES,
        user=teacher,
        student=student,
        journey=journey,
        journey_stops=journey_stops,
        targets=targets,
        transfer_credit=TransferCreditRecord.query.filter_by(student_id=student.id).first(),
        documents=SourceDocument.query.filter_by(owner_id=student.id, status="confirmed")
                                      .order_by(SourceDocument.created_at).all(),
        records_with_evidence=[r for r in Portfolio.query.filter_by(student_id=student.id).order_by(Portfolio.id).all()
                               if r.evidence_items],
        category_keys=CATEGORY_KEYS,
        category_labels=CATEGORY_LABELS,
        labels=ALL_LABELS,
        error=request.args.get("error"),
    )


@teacher_bp.get("/teacher/evidence/<int:evidence_id>/view")
@role_required("teacher")
def evidence_view(evidence_id):
    """導師看本班學生的佐證照片；不是自己班的學生就 403。"""
    evidence = db.session.get(PortfolioEvidence, evidence_id)
    if not evidence:
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
        review_snapshot_service.decide(review, teacher, decision, comment, request.form.get("taken_at", ""))
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
        comments = [request.form.get(f"comment_{i}", "") for i in range(count)]
        try:
            autobiography_service.save_edits(output, texts, teacher, comments=comments)
        except autobiography_service.StaleVersion as exc:
            latest = latest_draft(student, program)
            return render_template(
                "teacher_autobiography_edit.html", user=teacher, student=student, program=program, output=latest,
                version=version_of(latest), stale={"message": str(exc), "texts": texts, "comments": comments,
                                                   "paragraphs": output.content_json["paragraphs"]},
            ), 409
        return redirect(url_for("teacher.student_detail", student_id=student.id, saved=1))
    return render_template("teacher_autobiography_edit.html", user=teacher, student=student, program=program,
                           output=output, version=autobiography_service.version_of(output))
