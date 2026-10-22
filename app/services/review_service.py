from flask import abort

from app.extensions import db
from app.models import ProjectReviewResult, ProjectRevisionRecord, SubmissionAssignment, TeacherReviewFeedback, PortfolioSubmission


def assign_submission(submission, teacher):
    if teacher.role != "teacher":
        raise PermissionError("only teachers can receive review assignments")
    assignment = SubmissionAssignment(submission=submission, teacher=teacher)
    db.session.add(assignment)
    return assignment


def can_teacher_review(submission, teacher):
    return any(item.teacher_id == teacher.id for item in submission.assignments)


def record_teacher_feedback(submission, teacher, comment):
    if teacher.role != "teacher" or not can_teacher_review(submission, teacher):
        raise PermissionError("only an assigned teacher can submit feedback")
    comment = (comment or "").strip()
    if not comment:
        raise ValueError("feedback comment is required")
    feedback = TeacherReviewFeedback(
        submission_id=submission.id,
        teacher_id=teacher.id,
        comment=comment,
    )
    db.session.add(feedback)
    return feedback


def record_review_result(submission, actor, decision, comment=None, revision_items=None):
    if actor.role not in {"staff", "admin"}:
        raise PermissionError("only staff or admin can record the common result")
    if decision not in {"approved", "needs_revision", "rejected"}:
        raise ValueError("invalid review decision")
    result = ProjectReviewResult(submission=submission, recorded_by=actor, decision=decision, comment=comment)
    db.session.add(result)
    submission.status = decision
    for issue in revision_items or []:
        result.revision_records.append(ProjectRevisionRecord(submission=submission, issue=issue))
    return result


def create_revision(submission):
    revision = PortfolioSubmission(
        portfolio_id=submission.portfolio_id,
        version_no=submission.version_no + 1,
        previous_submission=submission,
        status="draft",
    )
    db.session.add(revision)
    return revision
