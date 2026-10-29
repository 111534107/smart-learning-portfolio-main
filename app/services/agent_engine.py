"""升學 Agent 共用引擎：一個引擎、多組工具（規格 AI_設計規格_Agent分工規劃_2026-10-22.md 第〇節）。

流程：決定下一步 → 後端執行工具 → 把結果交回 → 再決定，最多 max_steps 次。
- 決定下一步的有兩種：AiDecider（Gemini 依工具說明自己選）與固定流程（每個工作自己寫的 fallback）。
- AI 沒設定、額度用完或連不上時，自動改走固定流程，結果仍然能用（「AI 失敗要能回到手動流程」）。
- 工具只能讀資料或產生「候選／草稿」；正式資料一律由人確認。
- 每次執行記一筆 agent_tasks：用了哪些工具、每步摘要、最後總結；不記學生的姓名、學號。

工具回傳 dict：summary（給人看的一句話）、error（失敗原因）、link（{label, endpoint, params}，畫面上的連結），
其他欄位會交回給 AI 判斷下一步。
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

from app.extensions import db
from app.models import AgentTask
from app.services import gemini_client
from app.services.gemini_client import AIUnavailable


TAIPEI = timezone(timedelta(hours=8))


def taipei_time(value, pattern="%Y-%m-%d %H:%M"):
    """資料庫存的是 UTC（沒有時區資訊），畫面上改顯示台灣時間。"""
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(TAIPEI).strftime(pattern)


class ToolError(Exception):
    """工具拒絕這次呼叫（參數錯、沒有權限）。訊息是給人看的中文。"""


@dataclass
class Tool:
    name: str
    label: str
    description: str
    run: Callable[..., dict]
    params: dict = field(default_factory=dict)

    def declaration(self):
        declaration = {"name": self.name, "description": self.description}
        if self.params:
            declaration["parameters"] = {
                "type": "OBJECT",
                "properties": {key: {"type": "STRING", "description": text} for key, text in self.params.items()},
                "required": list(self.params),
            }
        return declaration


class AiDecider:
    """請 Gemini 決定下一步：回傳 {"tool", "args"} 或 {"finish": 總結}。chat 可換成假的（測試用）。"""

    def __init__(self, instruction, chat=None):
        self.instruction = instruction
        self.chat = chat

    def __call__(self, goal, steps, tools):
        contents = [{"role": "user", "parts": [{"text": goal}]}]
        for step in steps:
            # Gemini 會在工具呼叫上附 thoughtSignature，下一輪要原封不動送回，否則回 400
            parts = step.get("model_parts") or [{"functionCall": {"name": step["tool"], "args": step["args"]}}]
            contents.append({"role": "model", "parts": parts})
            contents.append({"role": "user", "parts": [
                {"functionResponse": {"name": step["tool"], "response": {"result": step["result"]}}}]})
        chat = self.chat or gemini_client.chat
        content = chat(contents, [tool.declaration() for tool in tools], self.instruction)
        parts = content.get("parts", [])
        calls = [part for part in parts if "functionCall" in part]
        if calls:  # 一次只執行第一個工具，結果交回後再讓 AI 決定；送回時也只留這一個呼叫
            call = calls[0]["functionCall"]
            return {"tool": call.get("name"), "args": call.get("args") or {}, "model_parts": [calls[0]]}
        text = "".join(part.get("text", "") for part in parts).strip()
        if not text:
            raise AIUnavailable("AI 沒有給出下一步。")
        return {"finish": text}


def _plain(text):
    """畫面不轉 Markdown：拿掉 AI 常用的 **粗體** 與 # 標題符號。"""
    text = re.sub(r"(\*\*|__)(.+?)\1", r"\2", text)
    return re.sub(r"(?m)^\s*#{1,6}\s*", "", text).strip()


def _execute(tools, name, args):
    tool = tools.get(name)
    if tool is None:
        return {"error": "沒有這個工具。"}
    clean = {key: str(value) for key, value in (args or {}).items() if key in tool.params}
    try:
        return tool.run(**clean)
    except ToolError as exc:
        return {"error": str(exc)}
    except TypeError:
        return {"error": "工具參數不正確。"}


def start_task(task_type, requester, target_type=None, target_id=None):
    """先建立一筆執行中的紀錄，回傳編號；畫面可以馬上打開，邊執行邊看進度。"""
    task = AgentTask(task_type=task_type, requester_id=requester.id, target_type=target_type, target_id=target_id,
                     status="running", started_at=datetime.now(timezone.utc),
                     result_json={"phase": "starting", "steps": []})
    db.session.add(task)
    db.session.commit()  # 先存起來；工具失敗時會 rollback，不能把這筆紀錄一起退掉
    return task.id


def fail_task(task_id, message):
    """背景執行出錯時記下來，畫面才不會一直顯示「執行中」。"""
    task = db.session.get(AgentTask, task_id)
    task.status = "failed"
    task.error_message = message
    task.result_json = {**(task.result_json or {}), "phase": "done", "summary": message}
    task.finished_at = datetime.now(timezone.utc)
    db.session.commit()


STALE_AFTER = timedelta(minutes=5)  # 一次執行通常 1 分鐘內；超過就當成網站重開或卡住而中斷
INTERRUPTED = "這次執行被中斷了（網站重新啟動或等太久），請再按一次「再請 Agent 規劃一次」。"


def expire_if_stale(task):
    """背景執行的那條執行緒在網站重開時就不見了，紀錄會永遠停在「執行中」；超過時間改記成失敗。"""
    started = task.started_at
    if task.status != "running" or started is None:
        return task
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - started > STALE_AFTER:
        fail_task(task.id, INTERRUPTED)
        task = db.session.get(AgentTask, task.id)
    return task


def progress(task):
    """給畫面輪詢用：目前在做什麼、做完哪些步驟。不含工具交回給 AI 的完整資料。"""
    task = expire_if_stale(task)
    data = task.result_json or {}
    return {"status": task.status, "done": task.status != "running", "mode": data.get("mode"),
            "phase": data.get("phase"), "current_tool": data.get("current_tool"),
            "steps": data.get("steps", []), "summary": data.get("summary")}


def _record(steps):
    return [{"tool": s["tool"], "label": s["label"], "summary": s["summary"], "ok": "error" not in s["result"]}
            for s in steps]


def _save_progress(task_id, mode, steps, phase, current_tool=None):
    task = db.session.get(AgentTask, task_id)
    task.result_json = {"mode": mode, "phase": phase, "current_tool": current_tool, "steps": _record(steps)}
    db.session.commit()


def run(*, task_type, goal, tools, requester, decide, fallback, max_steps=6, target_type=None, target_id=None,
        task_id=None):
    """執行一次 Agent。decide 是 AI（None 表示直接走固定流程）；fallback 是固定流程。

    task_id：已經用 start_task 建好的紀錄（背景執行時用）；沒給就在這裡建立。
    每做完一步就存進紀錄，畫面輪詢 progress() 就能看到 Agent 正在用哪個工具。
    回傳 {task_id, mode, steps, summary, links}；steps 每步含 tool、label、args、result、summary。
    """
    if task_id is None:
        task_id = start_task(task_type, requester, target_type, target_id)

    registry = {tool.name: tool for tool in tools}
    mode, fallback_reason = ("ai" if decide else "rule"), None
    steps, summary = [], None
    for _ in range(max_steps):
        _save_progress(task_id, mode, steps, "deciding")
        try:
            decision = (decide if mode == "ai" else fallback)(goal, steps, tools)
        except AIUnavailable as exc:
            mode, fallback_reason = "rule", str(exc)
            decision = fallback(goal, steps, tools)
        if "finish" in decision:
            summary = _plain(decision["finish"])
            break
        _save_progress(task_id, mode, steps, "running", decision.get("tool"))
        result = _execute(registry, decision.get("tool"), decision.get("args"))
        steps.append({
            "tool": decision.get("tool"),
            "label": registry[decision["tool"]].label if decision.get("tool") in registry else decision.get("tool"),
            "args": decision.get("args") or {},
            "model_parts": decision.get("model_parts"),  # 只在這次執行的記憶體裡，不寫進紀錄
            "result": result,
            "summary": result.get("error") or result.get("summary", ""),
        })

    links = []
    for step in steps:
        link = step["result"].get("link")
        if link and link not in links:
            links.append(link)
    task = db.session.get(AgentTask, task_id)
    task.status = "succeeded" if summary else "stopped"
    task.result_json = {
        "mode": mode,
        "phase": "done",
        "fallback_reason": fallback_reason,
        "steps": _record(steps),
        "summary": summary or f"執行了 {len(steps)} 步還沒有結論，已停止；請稍後再試或改用手動流程。",
        "links": links,
    }
    task.finished_at = datetime.now(timezone.utc)
    db.session.commit()
    return {"task_id": task.id, "mode": mode, "steps": steps, "summary": task.result_json["summary"], "links": links}
