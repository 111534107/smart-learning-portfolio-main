"""升學 Agent 的背景巡查：T1 檢查官方來源有沒有更新 → T2 把更新的簡章擷取成候選校系。

排程（flask agent-patrol）或管理員在「招生資料 Agent」頁按「讓 Agent 巡查一次」時執行。
擷取結果都是候選（status=candidate），管理員核准後學生才看得到；Agent 不會自己發布。
AI 不能用時改走固定流程：照樣檢查來源，擷取（需要 AI）留給管理員之後處理。
"""

from app.extensions import db
from app.models import PublicSource, PublicSourceChange, PublicSourceSnapshot
from app.services import admission_agent_service as admission_agent
from app.services.agent_engine import AiDecider, Tool, ToolError, run
from app.services.gemini_client import ai_ready

GOAL = "請巡查招生資料的官方來源：先檢查有沒有更新，再把等待擷取的簡章擷取成候選校系，最後總結這次做了什麼、管理員要處理什麼。"

INSTRUCTION = """你是康寧大學資管科學習歷程系統的「升學 Agent」，現在做背景巡查。
規則：
1. 先用工具檢查官方來源，再列出等待擷取的變更；只擷取列出來的變更編號，不要自己編號碼。
2. 擷取的結果（候選校系、候選日程）只是「候選」，要等管理員核准；總結時不要說已經發布或學生已經看得到。
3. 工具回傳錯誤時，說明原因，不要一直重試同一個動作。
4. 不要用 Markdown 符號（例如 ** 或 #）。最後用繁體中文、三句話以內總結：檢查了幾個來源、哪些有更新、建立了哪些候選校系、管理員下一步要做什麼。"""

AUTO = "auto"


def patrol_decider(chat=None):
    return AiDecider(INSTRUCTION, chat=chat)


def _tools(requester, fetch, generate):
    def check_sources():
        tasks = admission_agent.check_all(requester, fetch=fetch or admission_agent.fetch_url)
        if not tasks:
            return {"summary": "還沒有登記任何網址來源。", "checked": 0, "changed": [], "failed": []}
        names = {source.id: source.name for source in PublicSource.query.all()}
        changed = [names.get(task.target_id, str(task.target_id)) for task in tasks
                   if task.status == "succeeded" and (task.result_json or {}).get("changed")]
        failed = [names.get(task.target_id, str(task.target_id)) for task in tasks if task.status == "failed"]
        text = f"檢查 {len(tasks)} 個來源，{len(changed)} 個有更新"
        text += f"、{len(failed)} 個抓取失敗。" if failed else "。"
        return {"summary": text, "checked": len(tasks), "changed": changed, "failed": failed}

    def list_pending_changes():
        rows = (PublicSourceChange.query.filter_by(status="candidate")
                .join(PublicSourceSnapshot, PublicSourceChange.snapshot_id == PublicSourceSnapshot.id)
                .join(PublicSource, PublicSourceSnapshot.source_id == PublicSource.id)
                .with_entities(PublicSourceChange, PublicSource).order_by(PublicSourceChange.id).all())
        changes = [{"change_id": str(change.id), "source": source.name, "type": change.change_type,
                    "content_type": (change.diff_json or {}).get("content_type")} for change, source in rows]
        return {"summary": f"有 {len(changes)} 個變更等待擷取。", "changes": changes}

    def extract_change(change_id=""):
        try:
            change = db.session.get(PublicSourceChange, int(change_id))
        except ValueError:
            change = None
        if change is None or change.status != "candidate":
            raise ToolError(f"找不到等待擷取的變更（編號 {change_id}）；請先列出等待擷取的變更。")
        task = admission_agent.extract_programs(change, requester, generate=generate)
        if task.status != "succeeded":
            raise ToolError(task.error_message or "擷取失敗。")
        created = task.result_json.get("created", [])
        schedule = task.result_json.get("schedule_created", 0)
        return {"summary": f"變更 {change_id} 擷取出 {len(created)} 個候選校系"
                           + (f"（{'、'.join(created)}）" if created else "")
                           + (f"、{schedule} 個候選日程" if schedule else "") + "，等管理員核准。",
                "created": created, "schedule_created": schedule,
                "skipped": len(task.result_json.get("skipped", []))}

    return [
        Tool("check_sources", "檢查官方來源", "下載所有登記的招生官方網址，和上次比對有沒有更新。", check_sources),
        Tool("list_pending_changes", "列出待擷取的更新", "列出已偵測到、還沒擷取的來源變更與編號。", list_pending_changes),
        Tool("extract_change", "擷取成候選校系", "把一個變更的簡章交給 AI，擷取資管相關校系的備審加權與重要日程，建立候選版本。",
             extract_change, params={"change_id": "要擷取的變更編號（從待擷取清單取得）"}),
    ]


def _fixed_plan(can_extract):
    """AI 不能用時的固定流程：檢查 → 列出 → 逐一擷取（有 AI 才擷取）→ 總結。"""
    def plan(goal, steps, tools):
        done = [step["tool"] for step in steps]
        if "check_sources" not in done:
            return {"tool": "check_sources", "args": {}}
        if "list_pending_changes" not in done:
            return {"tool": "list_pending_changes", "args": {}}
        pending = [c["change_id"] for c in next(s for s in reversed(steps) if s["tool"] == "list_pending_changes")
                   ["result"].get("changes", [])]
        tried = {step["args"].get("change_id") for step in steps if step["tool"] == "extract_change"}
        if can_extract:
            for change_id in pending:
                if change_id not in tried:
                    return {"tool": "extract_change", "args": {"change_id": change_id}}
        check = next(s for s in steps if s["tool"] == "check_sources")["summary"]
        created = [code for s in steps if s["tool"] == "extract_change" for code in s["result"].get("created", [])]
        schedule = sum(s["result"].get("schedule_created", 0) for s in steps if s["tool"] == "extract_change")
        parts = [f"巡查完成：{check}"]
        if created:
            parts.append(f"建立 {len(created)} 個候選校系（{'、'.join(created)}），請到招生資料 Agent 頁比對後核准。")
        if schedule:
            parts.append(f"建立 {schedule} 個候選日程，請到招生資料 Agent 頁比對後核准。")
        if pending and not can_extract:
            parts.append(f"有 {len(pending)} 個變更等待擷取；擷取需要 AI（尚未設定或暫時不能用），請之後在招生資料 Agent 頁按「擷取加權」。")
        elif not pending and not created and not schedule:
            parts.append("沒有需要擷取的更新。")
        return {"finish": "".join(parts)}
    return plan


def run_patrol(requester, decide=AUTO, fetch=None, generate=None):
    """執行一次巡查。decide=AUTO：有設定 AI 就讓 AI 決定，否則走固定流程。fetch／generate 測試時換成假的。"""
    if decide == AUTO:
        decide = patrol_decider() if ai_ready() else None
    can_extract = generate is not None or ai_ready()
    return run(task_type="agent_patrol", goal=GOAL, tools=_tools(requester, fetch, generate), requester=requester,
               decide=decide, fallback=_fixed_plan(can_extract), max_steps=8)
