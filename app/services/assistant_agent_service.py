"""學生對話 Agent 的安全導引與同意式計畫。

AI 可以閱讀資料、提出下一步；但建立可追蹤的規劃紀錄前，必須由學生按下同意。
站內連結完全由伺服器產生，模型不會提供任意 URL。
"""

from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models import AgentTask, SourceDocument, StudentTarget
from app.services.gap_service import analyze_gap
from app.services.journey_service import CATEGORY_LABELS, build_journey


PLAN_WORDS = ("規劃", "計畫", "待辦", "下一步", "幫我安排", "重新分析", "更新準備度")
PLAN_EXPIRY = timedelta(hours=24)


SAFE_PATHS = {
    "grades": "/student/learning-profile",
    "credentials": "/student/learning-profile/credentials",
    "activities": "/student/portfolio",
    "targets": "/student/targets",
    "autobiography": "/student/autobiography",
    "schedule": "/student/schedule",
    "graduation": "/student/graduation-check",
    "files": "/student/files",
}

CATEGORY_PATHS = {
    "grades": "grades", "credential": "credentials", "activity": "activities",
    "competition": "activities", "service": "activities", "leadership": "activities",
}


def _link(label, path_name):
    """只使用白名單內的站內路徑，服務在背景執行時也能安全回傳連結。"""
    return {"label": label, "url": SAFE_PATHS[path_name]}


FILE_WORDS = ("檔案", "上傳的", "傳上去", "原檔", "佐證")
WHERE_WORDS = ("在哪", "哪裡", "放哪", "去哪", "找不到", "不見")


def is_file_question(message):
    """「我剛剛上傳的成績單在哪裡？」這類找檔案的問題（B27，2026-11-14 假學生實測：沒開 AI 時回了重補修段落）。"""
    text = message or ""
    return "我的檔案" in text or (any(w in text for w in FILE_WORDS + ("上傳",)) and any(w in text for w in WHERE_WORDS))


FILE_ANSWER = ("你上傳過的檔案都在「我的資料 → 我的檔案」：成績單、證照的原始檔，還有每一筆活動與經歷的佐證，"
               "每一筆都寫了存在哪、會不會放進備審。按下面的按鈕就能過去。")


def navigation_links(user, message):
    """依學生的問題回傳最多兩個安全的站內導引連結。"""
    if user.role != "student":
        return []
    text = (message or "").lower()
    links = []
    if is_file_question(message):
        links.append(_link("前往我的檔案", "files"))
    if any(word in text for word in ("畢業", "門檻", "學分")):
        links.append(_link("查看畢業門檻提醒", "graduation"))
    if any(word in text for word in ("ocr", "辨識", "核對", "成績單", "成績", "上傳")):
        links.append(_link("前往成績單與 OCR 核對", "grades"))
    if any(word in text for word in ("證照", "證書", "檢定")):
        links.append(_link("前往證照資料", "credentials"))
    if any(word in text for word in ("活動", "競賽", "服務", "幹部", "經歷")):
        links.append(_link("前往活動與經歷", "activities"))
    if any(word in text for word in ("校系", "志願", "準備度", "缺什麼", "缺件", "二技")):
        links.append(_link("前往目標校系", "targets"))
    if any(word in text for word in ("自傳", "備審", "書審")):
        links.append(_link("前往備審資料與自傳", "autobiography"))
    if any(word in text for word in ("報名", "時程", "日期")):
        links.append(_link("查看招生時程", "schedule"))
    unique = []
    for link in links:
        if link not in unique:
            unique.append(link)
    return unique[:2]


def _plan_payload(task):
    # JSON 欄位不可原地修改；建立新 dict 才能讓 SQLAlchemy 確實寫入待辦與執行結果。
    payload = dict(task.result_json or {})
    return {
        "id": task.id,
        "title": payload.get("title", "整理我的學習歷程計畫"),
        "reason": payload.get("reason", ""),
        "steps": payload.get("steps", []),
        "preview_todos": payload.get("preview_todos", []),
        "status": task.status,
        "action_url": f"/assistant/plans/{task.id}/approve",
        "reject_url": f"/assistant/plans/{task.id}/reject",
    }


def _todo(title, note, path_name, key, **metadata):
    """待辦只連到站內白名單頁面，不能由模型或資料庫任意指定網址。"""
    return {"key": key, "title": title, "note": note, "url": SAFE_PATHS[path_name],
            "status": "open", **metadata}


def _unconfirmed_document_count(user):
    return SourceDocument.query.filter(
        SourceDocument.owner_id == user.id, SourceDocument.status != "confirmed"
    ).count()


def _build_todos(user, journey, targets, unconfirmed):
    """根據已確認資料建立學生自己可追蹤的下一步，不改動任何學習歷程。"""
    todos = []
    if unconfirmed:
        todos.append(_todo("核對 OCR 資料", f"還有 {unconfirmed} 份上傳資料尚未確認；確認前不會納入分析。",
                           "grades", "confirm-ocr", kind="confirm_ocr"))

    if not targets:
        todos.append(_todo("選擇目標校系", "先選擇想申請的校系，Agent 才能依實際加權整理缺件。",
                           "targets", "choose-targets", kind="choose_targets"))
    else:
        target_items = []
        for target in targets:
            gap = analyze_gap(user, target.program, journey)
            for item in gap["items"]:
                if item["status"] not in ("missing", "partial") or not item["missing"]:
                    continue
                target_items.append((item["weight"], target, item))
        # 每個待辦保留校系與原始項目，依真正的簡章加權排序，而不是把所有校系的缺件混在一起。
        for weight, target, item in sorted(target_items, key=lambda row: -row[0])[:3]:
            missing = item["missing"]
            path_name = CATEGORY_PATHS.get(missing[0], "targets")
            labels = "、".join(CATEGORY_LABELS[key] for key in missing)
            school = f"{target.program.school_name}{target.program.department_name}"
            todos.append(_todo(
                f"{school}：補強「{item['name']}」",
                f"此項占 {weight}%；目前缺少：{labels}。",
                path_name, f"target-{target.id}-item-{item['id']}", kind="target_gap",
                target_id=target.id, item_id=item["id"], weight=weight,
            ))

    if journey["totals"]["grades"] == 0:
        todos.append(_todo("補上成績資料", "上傳成績單後，請逐筆核對 OCR 結果。",
                           "grades", "add-grades", kind="category", category="grades"))
    if journey["totals"]["credential"] == 0:
        todos.append(_todo("整理證照資料", "新增或確認已取得的證照，讓準備度分析更完整。",
                           "credentials", "add-credentials", kind="category", category="credential"))
    if not any(journey["totals"][key] for key in ("activity", "competition", "service", "leadership")):
        todos.append(_todo("補充活動與經歷", "填入已確認的活動、競賽、服務或幹部經歷。",
                           "activities", "add-experience", kind="experience"))
    if targets:
        todos.append(_todo("檢查備審與自傳", "依目標校系加權檢查缺件與自傳佐證。",
                           "autobiography", "check-autobiography", kind="autobiography"))
    return todos[:5]


def _todo_state(user, todo, journey=None):
    """待辦一旦因學生補齊真實資料而完成，紀錄頁就自動顯示完成。

    學生自己按過「標記完成／重新開啟」的待辦（manual），以學生的選擇為準，不再自動判斷，
    否則資料已補齊的待辦按「重新開啟」也會立刻被改回完成。
    """
    if todo.get("manual"):
        return todo.get("status", "open")
    kind = todo.get("kind")
    journey = journey or build_journey(user)
    if kind == "confirm_ocr":
        return "completed" if _unconfirmed_document_count(user) == 0 else todo.get("status", "open")
    if kind == "choose_targets":
        return "completed" if StudentTarget.query.filter_by(student_id=user.id).count() else todo.get("status", "open")
    if kind == "category":
        return "completed" if journey["totals"].get(todo.get("category"), 0) else todo.get("status", "open")
    if kind == "experience":
        return "completed" if any(journey["totals"][key] for key in ("activity", "competition", "service", "leadership")) else todo.get("status", "open")
    if kind == "target_gap":
        target = db.session.get(StudentTarget, todo.get("target_id"))
        if target and target.student_id == user.id:
            gap = analyze_gap(user, target.program, journey)
            item = next((row for row in gap["items"] if row["id"] == todo.get("item_id")), None)
            if item and item["status"] == "complete":
                return "completed"
    return todo.get("status", "open")


def plan_history(user, limit=8):
    """學生只讀取自己的 Agent 計畫紀錄；不回傳對話內容。"""
    query = (AgentTask.query.filter_by(task_type="assistant_plan", requester_id=user.id)
             .order_by(AgentTask.created_at.desc(), AgentTask.id.desc()))
    rows = (query.limit(limit) if limit else query).all()
    entries = []
    for task in rows:
        payload = task.result_json or {}
        entries.append({
            "id": task.id,
            "title": payload.get("title", "整理我的下一步計畫"),
            "status": task.status,
            "created_at": task.created_at.isoformat() if task.created_at else "",
            "finished_at": task.finished_at.isoformat() if task.finished_at else "",
            "executed_at": payload.get("executed_at", ""),
            "reason": payload.get("reason", ""),
            "steps": payload.get("steps", []),
            "preview_todos": payload.get("preview_todos", []),
            "todos": [{**todo, "status": _todo_state(user, todo)} for todo in payload.get("todos", [])]
            if task.status == "succeeded" else [],
        })
    return entries


def _expire_if_old(task):
    """未決定超過 24 小時的計畫改成取消；回傳是否已過期。"""
    created_at = task.created_at
    # SQLite 會讀回沒有 tzinfo 的時間；系統所有 Agent 時間都以 UTC 儲存。
    if created_at and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    if created_at and created_at < datetime.now(timezone.utc) - PLAN_EXPIRY:
        task.status = "cancelled"
        task.finished_at = datetime.now(timezone.utc)
        db.session.commit()
        return True
    return False


def propose_plan(user, message):
    """只提出可控計畫；同一位學生先前尚未決定的計畫不重複建立。"""
    if user.role != "student" or not any(word in (message or "") for word in PLAN_WORDS):
        return None
    pending = (AgentTask.query.filter_by(task_type="assistant_plan", requester_id=user.id, status="pending")
               .order_by(AgentTask.id.desc()).first())
    if pending:
        if not _expire_if_old(pending):
            return _plan_payload(pending)

    unconfirmed = _unconfirmed_document_count(user)
    targets = StudentTarget.query.filter_by(student_id=user.id).order_by(StudentTarget.selected_at).all()
    target_count = len(targets)
    # 規格：同意前就要讓學生看到「會產生哪些待辦」；同意時依當下資料重新產生，以免資料已變動。
    preview = _build_todos(user, build_journey(user), targets, unconfirmed)
    steps = ["讀取你的已確認成績、證照與學習歷程資料"]
    if unconfirmed:
        steps.append(f"保留 {unconfirmed} 份尚未確認的 OCR 資料，不納入分析")
    if target_count:
        steps.append("依已選目標校系重新整理準備度與缺件")
    else:
        steps.append("確認你尚未選目標校系，提供選校系導引")
    steps.append("建立這次可回看的 Agent 建議與下一步連結")
    task = AgentTask(
        task_type="assistant_plan", requester_id=user.id, target_type="student", target_id=user.id,
        status="pending", result_json={
            "title": "整理我的下一步計畫",
            "reason": "我會讀取已確認的個人資料、重新整理準備度與缺件；不會新增、修改或刪除你的學習歷程資料。",
            "steps": steps,
            "preview_todos": [{"title": todo["title"], "note": todo["note"], "kind": todo.get("kind")}
                              for todo in preview],
        },
    )
    db.session.add(task)
    db.session.commit()
    return _plan_payload(task)


def decide_plan(user, plan_id, decision):
    task = db.session.get(AgentTask, plan_id)
    if not task or task.task_type != "assistant_plan" or task.requester_id != user.id:
        return None
    if task.status == "pending" and _expire_if_old(task):
        # 過期的計畫不能再同意：資料可能已經變了，請學生重新請 Agent 規劃。
        return {"status": "cancelled", "message": "這份計畫已超過 24 小時，已自動取消；請重新輸入「幫我規劃下一步」。",
                "links": []}
    if task.status != "pending":
        return {"status": task.status, "message": "這份計畫已經處理過了。", "links": []}
    if decision == "reject":
        task.status = "cancelled"
        task.finished_at = datetime.now(timezone.utc)
        db.session.commit()
        return {"status": "cancelled", "message": "好的，這份 Agent 計畫沒有執行。", "links": []}
    if decision != "approve":
        return None

    journey = build_journey(user)
    targets = StudentTarget.query.filter_by(student_id=user.id).order_by(StudentTarget.selected_at).all()
    todos = _build_todos(user, journey, targets, _unconfirmed_document_count(user))
    if targets:
        readiness = [analyze_gap(user, target.program, journey)["readiness"] for target in targets]
        summary = f"已依 {len(targets)} 所目標校系與已確認資料完成本次準備度整理。"
        result = {"target_count": len(targets), "readiness": readiness}
        links = navigation_links(user, "校系 缺件")
    else:
        summary = "已完成資料盤點；你還沒有選目標校系，選定後我才能做個人化準備度分析。"
        result = {"target_count": 0, "readiness": []}
        links = [_link("前往選擇目標校系", "targets")]
    # JSON 欄位不可原地修改；建立新 dict 才能讓 SQLAlchemy 確實寫入待辦與執行結果。
    payload = dict(task.result_json or {})
    payload.update({
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "result": result,
        "todos": todos,
    })
    task.result_json = payload
    task.status = "succeeded"
    task.finished_at = datetime.now(timezone.utc)
    db.session.commit()
    return {"status": "succeeded", "message": summary, "links": links, "todos": todos, "plan_id": task.id}


def set_todo_status(user, plan_id, todo_index, status):
    """學生手動完成或重新開啟自己的 Agent 待辦；不改任何學習歷程資料。"""
    task = db.session.get(AgentTask, plan_id)
    if not task or task.task_type != "assistant_plan" or task.requester_id != user.id or task.status != "succeeded":
        return None
    payload = dict(task.result_json or {})
    todos = list(payload.get("todos") or [])
    if todo_index < 0 or todo_index >= len(todos) or status not in {"open", "completed"}:
        return None
    todo = dict(todos[todo_index])
    now = datetime.now(timezone.utc).isoformat()
    # 行動紀錄用：每次「標記完成／重新開啟」都留一筆動作與時間，不記任何對話內容
    todo["history"] = list(todo.get("history") or []) + [{"action": status, "at": now}]
    todo["status"] = status
    todo["manual"] = True
    todo["completed_at"] = now if status == "completed" else None
    todos[todo_index] = todo
    payload["todos"] = todos
    task.result_json = payload
    db.session.commit()
    return {**todo, "status": _todo_state(user, todo), "plan_id": task.id, "todo_index": todo_index}


def open_todo_count(user):
    """選單上的數字：還沒完成的待辦幾項、有沒有等你同意的計畫。整理資料只做一次，避免每頁都變慢。"""
    rows = (AgentTask.query.filter(AgentTask.task_type == "assistant_plan", AgentTask.requester_id == user.id,
                                   AgentTask.status.in_(("pending", "succeeded")))
            .order_by(AgentTask.created_at.desc(), AgentTask.id.desc()).all())
    pending = any(task.status == "pending" for task in rows)
    # 和待辦頁一致：同一個待辦在好幾份計畫都出現時只算最新那份
    todos, seen = [], set()
    for task in rows:
        for todo in (task.result_json or {}).get("todos", []) if task.status == "succeeded" else []:
            if todo.get("key") in seen:
                continue
            seen.add(todo.get("key"))
            todos.append(todo)
    if not todos:
        return {"open": 0, "pending_plan": pending}
    journey = build_journey(user)
    return {"open": sum(1 for todo in todos if _todo_state(user, todo, journey) != "completed"), "pending_plan": pending}
