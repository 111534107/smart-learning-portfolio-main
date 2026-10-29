"""升學 Agent 的使用者觸發：學生按「請 Agent 幫我規劃」→ T6 排序校系 → T7 為已選的目標校系準備自傳草稿。

原則：
- Agent 不替學生決定目標校系；只能為學生「已選」的目標校系寫草稿。
- 自傳要有學生自己的反思：學生沒回答過自傳問題就不寫，請學生先去回答（V2 第 9 頁）。
- 草稿和自傳頁產生的一樣：每段標出依據、存成新的一版，學生檢查修改後才算數；學校金鑰照樣計次。
- 送給 AI 的只有校系資料、排序理由與工具結果，不含學生姓名、學號。
"""

import threading

from flask import current_app

from app.extensions import db
from app.models import LearningProfileOutput, StudentTarget, User
from app.services import ai_quota_service, autobiography_service, student_rules
from app.services.agent_file_tool import document_tools
from app.services.admission_service import published_programs
from app.services.agent_engine import AiDecider, Tool, ToolError, fail_task, run, start_task
from app.services.gemini_client import AIUnavailable, ai_ready
from app.services.matching_service import rank_programs

GOAL = ("請依我已確認的資料，推薦適合我的二技或插大校系並說明理由；"
        "如果我已經選了目標校系、也回答過自傳問題，請挑一個最適合的目標校系幫我準備自傳草稿。")

INSTRUCTION = """你是康寧大學資管科學習歷程系統的「升學 Agent」，正在幫一位五專資管科學生規劃升學。
規則：
1. 先用工具排序全部校系，再查學生已選的目標校系；不要自己猜資料。
2. 不可以替學生決定目標校系；自傳草稿只能寫學生「已選」的目標校系，而且學生要先回答過自傳問題。
3. 不可報的學校要說明原因；「需確認」的要提醒學生自己核對簡章。
4. 契合度是依學生資料和簡章加權算的準備程度，不是錄取機率；不可以說學生一定會上或不會上。
   插大（轉學考）只考筆試的校系依考試成績錄取，不算契合度；提到插大時要說插幾年級、考什麼科目，並提醒學生自己核對報考資格。
5. 最後用繁體中文給 3～5 點條列建議：先講最適合的校系與理由，再講還缺什麼、下一步做什麼。每點一行；不要輸出 HTML，也不要用 Markdown 符號（例如 ** 或 #）。"""

AUTO = "auto"
AUTOBIOGRAPHY_LINK = "student.autobiography"

# 畫面上的「分工」：同一個 Agent 依需要呼叫不同工具組（規格第〇節）。一張卡片一個工具組，順序就是畫面上的排列；
# tone 是五年色的編號，tools 是這組包含的工具名稱。
TOOL_LINEUP = [
    {"group": "媒合排序", "label": "排序校系", "tone": 1, "tools": ["rank_programs"],
     "does": "依你的成績、證照、活動和簡章加權，把全部校系分成可報、需確認、不可報"},
    {"group": "學生條件", "label": "查目標校系", "tone": 2, "tools": ["list_my_targets"],
     "does": "看你選了哪些目標校系、有沒有回答自傳問題"},
    {"group": "自傳", "label": "準備自傳草稿", "tone": 3, "tools": ["draft_autobiography"],
     "does": "只為你已選的目標校系、用你的回答寫草稿，每段標出依據"},
    {"group": "雲端檔案", "label": "查檔案、取檔案內容", "tone": 5, "tools": ["list_my_documents", "get_my_document"],
     "does": "依檔案編號讀你自己上傳的檔案，送出前先去掉姓名學號"},
]


def advisor_decider(chat=None):
    return AiDecider(INSTRUCTION, chat=chat)


def _latest_answers(student):
    outputs = (LearningProfileOutput.query.filter_by(student_id=student.id, output_type=autobiography_service.OUTPUT_TYPE)
               .order_by(LearningProfileOutput.id.desc()).all())
    for output in outputs:
        answers = (output.content_json or {}).get("answers") or {}
        if any(str(value).strip() for value in answers.values()):
            return answers
    return None


def _targets(student):
    return [t.program for t in StudentTarget.query.filter_by(student_id=student.id).order_by(StudentTarget.selected_at)]


def _name(program):
    return f"{program.school_name} {program.department_name}"


def _tools(student, generate):
    def rank():
        rows = rank_programs(student, published_programs())
        target_ids = {program.id for program in _targets(student)}
        counts = {label: sum(1 for row in rows if row["status_label"] == label) for label in ("可報", "需確認", "不可報")}
        # 插大排在可報的二技後面，常常不在前 10 名；另外整理一份，AI 才知道有這條路
        transfer = [{"program_id": str(row["program"].id), "school": row["program"].school_name,
                     "department": row["program"].department_name, "grade": row["transfer"]["grade"],
                     "status": row["status_label"], "subjects": row["transfer"]["subjects"],
                     "fit": row["fit"], "fit_note": row["fit_note"]} for row in rows if row["transfer"]]
        return {
            "summary": f"排序 {len(rows)} 個校系：可報 {counts['可報']}、需確認 {counts['需確認']}、不可報 {counts['不可報']}"
                       + (f"；其中插大（轉學考）{len(transfer)} 個。" if transfer else "。"),
            "counts": counts,
            "programs": [{"program_id": str(row["program"].id), "school": row["program"].school_name,
                          "department": row["program"].department_name,
                          "category": row["program"].admission_category or "", "channel": row["channel_label"],
                          "status": row["status_label"], "fit": row["fit"], "fit_note": row["fit_note"],
                          "is_target": row["program"].id in target_ids,
                          "reasons": row["reasons"][:3]} for row in rows[:10]],
            "transfer": transfer,
            "link": {"label": "看完整推薦排序", "endpoint": "student.matching", "params": {}},
        }

    def list_targets():
        targets = _targets(student)
        statuses = {row["program"].id: row["status_label"] for row in rank_programs(student, targets)} if targets else {}
        has_answers = _latest_answers(student) is not None
        if not targets:
            text = "你還沒選目標校系。"
        else:
            text = f"你選了 {len(targets)} 個目標校系，" + ("也回答過自傳問題。" if has_answers else "還沒回答自傳問題。")
        result = {"summary": text, "has_answers": has_answers,
                "targets": [{"program_id": str(p.id), "school": p.school_name, "department": p.department_name,
                             "status": statuses.get(p.id, "")} for p in targets]}
        if targets and not has_answers:  # 給學生一個直接去回答自傳問題的連結
            result["link"] = {"label": "去回答自傳問題", "endpoint": AUTOBIOGRAPHY_LINK,
                              "params": {"program_id": targets[0].id}}
        return result

    def draft(program_id=""):
        reason = student_rules.autobiography_block_reason(student)
        if reason:
            raise ToolError(reason)
        program = next((p for p in _targets(student) if str(p.id) == str(program_id).strip()), None)
        if program is None:
            raise ToolError("只能為你已選的目標校系寫草稿；請先到推薦排序把學校設為目標校系。")
        link = {"label": "打開自傳草稿", "endpoint": AUTOBIOGRAPHY_LINK, "params": {"program_id": program.id}}
        answers = _latest_answers(student)
        if answers is None:
            return {"error": "你還沒回答自傳問題；自傳要用你自己的經驗，請先到自傳頁回答 4 題。", "link": link}
        try:
            if generate is None and ai_ready():
                ai_quota_service.consume(student)  # 和自傳頁一樣計次；AI 失敗時 rollback 退回
            output = autobiography_service.generate_draft(student, program, answers, generate=generate)
        except ai_quota_service.QuotaExceeded as exc:
            raise ToolError(str(exc)) from None
        except AIUnavailable as exc:
            db.session.rollback()
            raise ToolError(str(exc)) from None
        demo = (output.content_json or {}).get("provider") == "demo"
        return {"summary": f"已為「{_name(program)}」產生第 {autobiography_service.version_of(output)} 版自傳草稿"
                           + ("（示範草稿：目前沒有接上 AI）" if demo else "") + "，請到自傳頁檢查、修改後儲存。",
                "link": link}

    return [
        Tool("rank_programs", "排序校系", "依學生已確認的資料，排序全部正式校系（可報／需確認／不可報、契合度、理由）。", rank),
        Tool("list_my_targets", "查目標校系", "列出學生已選的目標校系、各自能不能報，以及是否回答過自傳問題。", list_targets),
        Tool("draft_autobiography", "準備自傳草稿", "為學生已選的一個目標校系產生自傳草稿（每段標出依據）；學生要先回答過自傳問題。",
             draft, params={"program_id": "目標校系的編號（從目標校系清單取得）"}),
        *document_tools(student),  # 依檔案編號取檔：只讀、檢查擁有者、去識別化（T3）
    ]


def _summary(steps):
    lines = []
    rank = next((s for s in steps if s["tool"] == "rank_programs"), None)
    if rank and "programs" in rank["result"]:
        top = [p for p in rank["result"]["programs"] if p["status"] == "可報"][:3]
        if top:
            lines.append("排在前面、可以報的校系：" + "、".join(
                f"{p['school']} {p['department']}" + (f"（準備度 {p['fit']}%）" if p["fit"] is not None else "") for p in top) + "。")
        transfer = rank["result"].get("transfer") or []
        if transfer:
            lines.append("也可以考慮插大（轉學考）：" + "、".join(
                f"{p['school']} {p['department']}（插{p['grade']}，{p['subjects']}）" for p in transfer[:3])
                + "；報考資格請自己核對簡章。")
    listing = next((s for s in steps if s["tool"] == "list_my_targets"), None)
    drafted = next((s for s in steps if s["tool"] == "draft_autobiography"), None)
    if listing and not listing["result"].get("targets"):
        lines.append("你還沒選目標校系：從推薦排序挑你想去的學校按「設為目標校系」，我才能幫你準備自傳。")
    elif listing and not listing["result"].get("has_answers"):
        lines.append("你已經選了目標校系，但還沒回答自傳問題：請先到自傳頁回答 4 題，我才能依你的經驗寫草稿。")
    elif drafted:
        lines.append(drafted["summary"])
    lines.append("準備度是依你的資料和簡章加權算的準備程度，不是錄取機率。")
    return "\n".join(lines)


def _fixed_plan(goal, steps, tools):
    """AI 不能用時的固定流程：排序 → 查目標校系 → 有回答過問題就為第一個能報的目標寫草稿 → 總結。"""
    done = [step["tool"] for step in steps]
    if "rank_programs" not in done:
        return {"tool": "rank_programs", "args": {}}
    if "list_my_targets" not in done:
        return {"tool": "list_my_targets", "args": {}}
    listing = next(s for s in steps if s["tool"] == "list_my_targets")["result"]
    if listing.get("has_answers") and "draft_autobiography" not in done:
        choice = next((t for t in listing.get("targets", []) if t["status"] != "不可報"), None)
        if choice:
            return {"tool": "draft_autobiography", "args": {"program_id": choice["program_id"]}}
    return {"finish": _summary(steps)}


def run_advisor(student, decide=AUTO, generate=None, task_id=None):
    """學生觸發一次升學 Agent。decide=AUTO：有設定 AI 就讓 AI 決定，否則走固定流程。"""
    if decide == AUTO:
        decide = advisor_decider() if ai_ready() else None
    return run(task_type="agent_advisor", goal=GOAL, tools=_tools(student, generate), requester=student,
               decide=decide, fallback=_fixed_plan, max_steps=6, task_id=task_id)


def start_advisor(student, background=False):
    """建立紀錄後開始執行，回傳紀錄編號。background=True 時在背景執行，畫面馬上打開、邊做邊顯示每一步。"""
    task_id = start_task("agent_advisor", student)
    if not background:
        run_advisor(student, task_id=task_id)
        return task_id
    app, student_id = current_app._get_current_object(), student.id

    def work():
        with app.app_context():
            try:
                run_advisor(db.session.get(User, student_id), task_id=task_id)
            except Exception:  # 背景執行沒有人接例外；記下來，畫面才會停在「失敗」而不是一直轉
                db.session.rollback()
                app.logger.exception("升學 Agent 背景執行失敗（紀錄 %s）", task_id)
                fail_task(task_id, "Agent 執行時發生錯誤，請稍後再按一次「再請 Agent 規劃一次」。")

    threading.Thread(target=work, name=f"agent-advisor-{task_id}", daemon=True).start()
    return task_id
