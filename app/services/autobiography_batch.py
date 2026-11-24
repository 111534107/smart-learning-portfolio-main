"""批次產生自傳：學生一次替所有目標校系各產生一份草稿，逐校依序跑、可查進度、失敗可單校重試。

進度放在這個程序的記憶體（工作只有幾分鐘壽命，重開機就沒了，草稿本身已存進資料庫）。
每個工作只有建立它的學生查得到。AI 結果只是草稿，學生確認後才算數。
"""

import threading
from time import time
from uuid import uuid4

from app.extensions import db
from app.models import AdmissionProgram, LearningProfileOutput, StudentTarget, User
from app.services import ai_quota_service, audit_service, autobiography_service
from app.services.gemini_client import AIUnavailable, ai_ready

JOB_TTL_SECONDS = 3600
_JOBS = {}
_LOCK = threading.Lock()

PENDING, RUNNING, DONE, FAILED = "pending", "running", "done", "failed"


def _purge():
    cutoff = time() - JOB_TTL_SECONDS
    for job_id in [k for k, v in _JOBS.items() if v["created"] < cutoff]:
        _JOBS.pop(job_id, None)


def collect_answers(student, program):
    """這所校系要用的回答：先用這所校系上次草稿的回答，沒有的題目再用其他校系草稿的回答（題目 key 共通）。"""
    outputs = (LearningProfileOutput.query
               .filter_by(student_id=student.id, output_type=autobiography_service.OUTPUT_TYPE)
               .order_by(LearningProfileOutput.id.desc()).all())
    same = [o for o in outputs if (o.content_json or {}).get("program_id") == program.id]
    other = [o for o in outputs if o not in same]
    answers = {}
    for output in same + other:
        for key, value in ((output.content_json or {}).get("answers") or {}).items():
            if value and not answers.get(key):
                answers[key] = value
    return answers


def _run_one(student, program):
    """產生一所校系的草稿；回傳 (狀態, 訊息)。呼叫端要在 app context 裡。"""
    answers = collect_answers(student, program)
    problem = autobiography_service.own_words_problem(program, answers)
    if problem:
        return FAILED, problem
    try:
        if ai_ready() and not autobiography_service.ollama_ready():
            ai_quota_service.consume(student)
        output = autobiography_service.generate_draft(student, program, answers)
        audit_service.record(student, "autobiography.generate", "learning_profile_output", output.id,
                             detail={"program_id": program.id, "provider": output.content_json.get("provider"),
                                     "batch": True}, commit=True)
        return DONE, ""
    except ai_quota_service.QuotaExceeded as exc:
        db.session.rollback()
        return FAILED, str(exc)
    except AIUnavailable as exc:
        db.session.rollback()
        return FAILED, str(exc)
    except Exception:  # 單一校系失敗不能讓整批停住；細節不給學生看
        db.session.rollback()
        return FAILED, "這所校系產生失敗，請按重試。"


def _work(app, job_id, student_id, program_ids):
    with app.app_context():
        for program_id in program_ids:
            with _LOCK:
                item = next((i for i in _JOBS[job_id]["items"] if i["program_id"] == program_id), None)
                if item is None:
                    continue
                item["status"] = RUNNING
            student = db.session.get(User, student_id)
            program = db.session.get(AdmissionProgram, program_id)
            status, message = _run_one(student, program) if student and program else (FAILED, "找不到校系。")
            with _LOCK:
                item["status"], item["message"] = status, message
            db.session.remove()
        with _LOCK:
            job = _JOBS[job_id]
            job["status"] = DONE if all(i["status"] == DONE for i in job["items"]) else FAILED


def target_programs(student):
    return [t.program for t in StudentTarget.query.filter_by(student_id=student.id)
            .order_by(StudentTarget.selected_at)]


def start(app, student, programs, inline=False):
    """建立工作並開始產生；inline=True（測試用）在同一個執行緒做完。回傳 job_id。"""
    job_id = uuid4().hex
    items = [{"program_id": p.id, "school_name": p.school_name, "department_name": p.department_name,
              "status": PENDING, "message": ""} for p in programs]
    with _LOCK:
        _purge()
        _JOBS[job_id] = {"student_id": student.id, "created": time(), "status": RUNNING, "items": items}
    args = (app, job_id, student.id, [p.id for p in programs])
    if inline:
        _work(*args)
    else:
        threading.Thread(target=_work, args=args, daemon=True).start()
    return job_id


def status(job_id, student):
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None or job["student_id"] != student.id:
            return None
        return {"status": job["status"],
                "items": [{"program_id": i["program_id"], "status": i["status"], "message": i["message"]}
                          for i in job["items"]]}


def retry(app, job_id, student, program_id, inline=False):
    """把某一所失敗的校系重新排進同一個工作；回傳是否接受。"""
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None or job["student_id"] != student.id:
            return False
        item = next((i for i in job["items"] if i["program_id"] == program_id), None)
        if item is None or item["status"] != FAILED:
            return False
        item["status"], item["message"] = PENDING, ""
        job["status"] = RUNNING
    args = (app, job_id, student.id, [program_id])
    if inline:
        _work(*args)
    else:
        threading.Thread(target=_work, args=args, daemon=True).start()
    return True
