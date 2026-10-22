from app.extensions import db
from app.models import AgentTask, SubmissionAssignment


def _can_run(submission, actor):
    if actor.role in {"student", "staff", "admin"}:
        return actor.role != "student" or submission.portfolio.student_id == actor.id
    if actor.role == "teacher":
        return any(item.teacher_id == actor.id for item in submission.assignments)
    return False


def _default_checker(submission):
    evidence_count = len(submission.portfolio.evidence_items)
    goals = submission.goal_snapshots or []
    if not goals:
        goals = [None]
    findings = []
    for goal in goals:
        title = goal.title if goal else "未指定要求"
        findings.append({
            "goal": title,
            "evidence_count": evidence_count,
            "finding": "需要人工確認" if evidence_count == 0 else "已有佐證，仍需人工確認",
        })
    return {"findings": findings, "automated_decision": None}


def run_evidence_check(submission, actor, checker=None):
    if not _can_run(submission, actor):
        raise PermissionError("actor is not authorized to run evidence check")
    task = AgentTask(
        task_type="evidence_check",
        requester_id=actor.id,
        target_type="portfolio_submission",
        target_id=submission.id,
        status="pending",
    )
    db.session.add(task)
    task.status = "running"
    try:
        task.result_json = (checker or _default_checker)(submission)
        task.status = "succeeded"
    except Exception as exc:  # the failure is part of the persisted workflow
        task.status = "failed"
        task.error_message = str(exc)
    return task
