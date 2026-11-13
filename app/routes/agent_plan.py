"""小助手規劃的 GitHub 風格頁面：規劃提案（像 Pull request）、待辦（像 Issues）、行動紀錄（像 Activity）。

後端沿用組員版 assistant_agent_service（同意式計畫，資料存在 AgentTask.result_json）；
這裡只負責整理成頁面。所有查詢都經過 plan_history(目前登入者)，別人的計畫一律 404。
"""

from datetime import datetime, timezone

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.routes.main import get_current_user, role_required
from app.services.assistant_agent_service import decide_plan, plan_history, propose_plan, set_todo_status

agent_plan_bp = Blueprint("agent_plan", __name__)

# 待辦種類 → 標籤（像 GitHub 的 label）
LABELS = {
    "ocr": {"text": "OCR 核對", "tone": "danger"},
    "target": {"text": "目標校系", "tone": "info"},
    "gap": {"text": "補足缺件", "tone": "warn"},
    "data": {"text": "補資料", "tone": "plain"},
    "bio": {"text": "自傳", "tone": "done"},
}
KIND_LABEL = {"confirm_ocr": "ocr", "choose_targets": "target", "target_gap": "gap", "category": "data",
              "experience": "data", "autobiography": "bio"}
PLAN_STATE = {"pending": "等你同意", "succeeded": "已同意執行", "cancelled": "未執行"}


def _when(text):
    """plan_history 給的是 ISO 字串；轉回 datetime 交給 taipei_time 顯示台灣時間。"""
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _plans():
    return plan_history(get_current_user(), limit=None)


def _issues(plans):
    """plans 由新到舊；同一個待辦（key 相同）在好幾份計畫都出現時只列最新那份，避免重複規劃後待辦變兩份。"""
    rows, seen = [], set()
    for plan in plans:
        for index, todo in enumerate(plan["todos"]):
            key = todo.get("key")
            if key and key in seen:
                continue
            seen.add(key)
            rows.append({"plan": plan, "index": index, "todo": todo,
                         "label": KIND_LABEL.get(todo.get("kind"), "data"),
                         "closed": todo.get("status") == "completed",
                         "created_at": _when(plan["executed_at"]), "completed_at": _when(todo.get("completed_at"))})
    return rows


def _render(template, tab, plans, **context):
    rows = _issues(plans)
    done = sum(1 for row in rows if row["closed"])
    pending = next((plan for plan in plans if plan["status"] == "pending"), None)
    counts = {"issues": len(rows) - done, "done": done, "total": len(rows), "proposals": len(plans),
              "percent": round(done / len(rows) * 100) if rows else 0,
              "pending_id": pending["id"] if pending else None}
    return render_template(template, user=get_current_user(), tab=tab, counts=counts, labels=LABELS,
                           kind_label=KIND_LABEL, plan_state=PLAN_STATE, when=_when, **context)


@agent_plan_bp.post("/student/agent/plan")
@role_required("student")
def plan():
    proposal = propose_plan(get_current_user(), "幫我規劃下一步")
    return redirect(url_for("agent_plan.proposal_page", plan_id=proposal["id"]))


@agent_plan_bp.get("/student/agent/issues")
@role_required("student")
def issues():
    plans = _plans()
    state = "closed" if request.args.get("state") == "closed" else "open"
    label = request.args.get("label") if request.args.get("label") in LABELS else None
    rows = [row for row in _issues(plans) if not label or row["label"] == label]
    open_count = sum(1 for row in rows if not row["closed"])
    closed_count = len(rows) - open_count
    rows = [row for row in rows if row["closed"] == (state == "closed")]
    return _render("student_agent_issues.html", "issues", plans, rows=rows, state=state, label=label,
                   open_count=open_count, closed_count=closed_count)


@agent_plan_bp.post("/student/agent/issues/<int:plan_id>/<int:index>/<action>")
@role_required("student")
def issue_action(plan_id, index, action):
    if action not in ("close", "reopen"):
        abort(404)
    todo = set_todo_status(get_current_user(), plan_id, index, "completed" if action == "close" else "open")
    if not todo:
        abort(404)
    flash(f"「{todo['title']}」已{'標記完成' if action == 'close' else '重新開啟'}。")
    target = request.form.get("next") or ""
    # 只接受小助手頁面的相對路徑，避免被帶去外部網站
    if not target.startswith("/student/agent/") or "//" in target or "\\" in target:
        target = url_for("agent_plan.issues")
    return redirect(target)


@agent_plan_bp.get("/student/agent/proposals")
@role_required("student")
def proposals():
    plans = _plans()
    return _render("student_agent_proposals.html", "proposals", plans, rows=plans)


@agent_plan_bp.get("/student/agent/proposals/<int:plan_id>")
@role_required("student")
def proposal_page(plan_id):
    plans = _plans()
    proposal = next((plan for plan in plans if plan["id"] == plan_id), None)
    if proposal is None:
        abort(404)
    return _render("student_agent_proposal.html", "proposals", plans, proposal=proposal,
                   issues=[row for row in _issues([proposal])])


@agent_plan_bp.post("/student/agent/proposals/<int:plan_id>/<decision>")
@role_required("student")
def proposal_action(plan_id, decision):
    if decision not in ("approve", "reject"):
        abort(404)
    result = decide_plan(get_current_user(), plan_id, decision)
    if not result:
        abort(404)
    flash(result.get("message") or "")
    if result["status"] == "succeeded":
        return redirect(url_for("agent_plan.issues"))
    return redirect(url_for("agent_plan.proposal_page", plan_id=plan_id))


@agent_plan_bp.get("/student/agent/activity")
@role_required("student")
def activity():
    """行動紀錄：由計畫與待辦的時間整理出來；只有動作，沒有任何聊天內容。"""
    plans = _plans()
    events = []
    for plan in plans:
        events.append({"at": _when(plan["created_at"]), "icon": "⇄", "kind": "plan", "text": "小助手提出規劃提案",
                       "plan": plan})
        if plan["status"] == "succeeded":
            events.append({"at": _when(plan["executed_at"]) or _when(plan["finished_at"]), "icon": "✓", "kind": "merged",
                           "text": f"你同意執行，建立了 {len(plan['todos'])} 項待辦", "plan": plan})
        elif plan["status"] == "cancelled":
            events.append({"at": _when(plan["finished_at"]), "icon": "✕", "kind": "closed",
                           "text": "提案沒有執行（不採用或逾時）", "plan": plan})
        for todo in plan["todos"]:
            for entry in todo.get("history") or []:
                closed = entry.get("action") == "completed"
                events.append({"at": _when(entry.get("at")), "icon": "☑" if closed else "↺", "plan": plan,
                               "kind": "done" if closed else "reopen",
                               "text": f"你把「{todo['title']}」標記完成" if closed else f"你重新開啟「{todo['title']}」"})
    events = [event for event in events if event["at"]]
    # 資料庫讀回的時間沒有時區（UTC），JSON 裡的有 +00:00；統一成 UTC 再排序
    events.sort(key=lambda event: event["at"] if event["at"].tzinfo else event["at"].replace(tzinfo=timezone.utc),
                reverse=True)
    return _render("student_agent_activity.html", "activity", plans, events=events)
