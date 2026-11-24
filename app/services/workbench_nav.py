"""備審工作台的導覽模型（純資料，不碰畫面）：

一條路四個階段：① 備齊資料 → ② 寫自傳 → ③ 預覽 A4 → ④ 送審與下載。
每個階段的狀態依實際資料決定：todo（還沒開始）、doing（進行中）、done（完成）、update（資料已更新，建議重新整理）。
"""

from flask import url_for

from app.models import StudentTarget
from app.services import autobiography_service
from app.services.gap_service import analyze_gap
from app.services.package_service import latest_review

STAGES = [("gap", "① 備齊資料"), ("bio", "② 寫自傳"), ("preview", "③ 預覽 A4"), ("send", "④ 送審與下載")]


def schools(student, current_id=None):
    """學生的目標校系（依加入順序），標出目前這一所。"""
    targets = (StudentTarget.query.filter_by(student_id=student.id)
               .order_by(StudentTarget.selected_at, StudentTarget.id).all())
    return [{"program_id": t.program.id, "name": f"{t.program.school_name} {t.program.department_name}",
             "current": t.program.id == current_id,
             "url": url_for("student.target_gap", program_id=t.program.id)} for t in targets]


def stages(student, program):
    """固定四個階段的連結與狀態。"""
    gap = analyze_gap(student, program)
    readiness = gap.get("readiness")
    draft = autobiography_service.latest_draft(student, program)
    review = latest_review(student, program)
    if draft is None:
        bio = "todo"
    elif autobiography_service.new_facts_since(draft, autobiography_service.build_facts(student, program)):
        bio = "update"
    else:
        bio = "doing"
    state = {
        "gap": "done" if readiness == 100 else ("doing" if readiness else "todo"),
        "bio": bio,
        "preview": "doing" if draft else "todo",
        "send": ("done" if review and review.status == "confirmed"
                 else "doing" if review else "todo"),
    }
    urls = {
        "gap": url_for("student.target_gap", program_id=program.id),
        "bio": url_for("student.autobiography", program_id=program.id),
        "preview": url_for("student.portfolio_view", program_id=program.id),
        "send": url_for("student.target_gap", program_id=program.id, _anchor="review"),
    }
    return [{"key": key, "label": label, "url": urls[key], "state": state[key]} for key, label in STAGES]


def next_stage(stage_list, current_key):
    """目前階段之後第一個還沒完成的階段；都完成或已是最後一個回傳 None。"""
    keys = [s["key"] for s in stage_list]
    if current_key not in keys:
        return None
    for stage in stage_list[keys.index(current_key) + 1:]:
        if stage["state"] != "done":
            return stage
    return None
