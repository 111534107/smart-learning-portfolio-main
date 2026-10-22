"""招生資料 Agent（系統亮點第二、三階段）。

第二階段：偵測更新
    管理者登記官方來源（網址或上傳簡章 PDF）→ Agent 下載並計算內容雜湊（sha256）→
    和上一次比對，內容改變就建立一筆「變更」(public_source_changes) 通知管理者。
第三階段：擷取加權
    管理者在變更上按「擷取」→ Agent 把簡章交給 Gemini，擷取資管相關校系的評分項目與加權 →
    建立 status=candidate、data_origin=agent 的校系版本 → 管理者比對差異、核准後學生才看得到。

每一次執行都記在 agent_tasks，成功、失敗都看得到。Agent 不會自己發布資料。
"""

import hashlib
import re
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

from flask import current_app

from app.extensions import db
from app.models import (
    AdmissionEligibilityRule,
    AdmissionProgram,
    AdmissionRequirementItem,
    AgentTask,
    PublicSource,
    PublicSourceChange,
    PublicSourceSnapshot,
)
from app.services.gap_service import ALL_LABELS
from app.services.gemini_client import AIUnavailable, generate_json

USER_AGENT = "KNU-IM-Portfolio-Agent/1.0 (school project; yearly admission brochure check)"
MAX_DOWNLOAD = 30 * 1024 * 1024
EXTENSIONS = {"application/pdf": "pdf", "text/html": "html"}


def _now():
    return datetime.now(timezone.utc)


# ---------- 來源 ----------

def add_source(name, url=None, upload_name=None):
    """登記官方來源。網址只接受 http／https；上傳的檔案用 upload:// 開頭記錄名稱。"""
    name = (name or "").strip()
    if not name:
        raise ValueError("請填寫來源名稱")
    if upload_name:
        url = f"upload://{upload_name}"
    elif not re.match(r"^https?://[^\s/]+", url or ""):
        raise ValueError("網址必須以 http:// 或 https:// 開頭")
    source = PublicSource(name=name[:150], url=url[:500], source_type="upload" if upload_name else "url")
    db.session.add(source)
    db.session.commit()
    return source


def fetch_url(url):
    """下載官方網頁或 PDF，回傳 (內容, Content-Type)。"""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        content = response.read(MAX_DOWNLOAD + 1)
        if len(content) > MAX_DOWNLOAD:
            raise ValueError("檔案超過 30MB，請改用手動上傳")
        return content, response.headers.get_content_type()


def _extension(content_type, url):
    if content_type in EXTENSIONS:
        return EXTENSIONS[content_type]
    suffix = Path(url.split("?")[0]).suffix.lower().lstrip(".")
    return suffix if suffix in ("pdf", "html", "htm") else "bin"


def _folder():
    folder = Path(current_app.config["AGENT_SOURCE_FOLDER"])
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def snapshot_file(snapshot):
    matches = sorted(_folder().glob(f"{snapshot.content_hash}.*"))
    return matches[0] if matches else None


def _start_task(task_type, requester, target_type, target_id):
    task = AgentTask(task_type=task_type, requester_id=requester.id, target_type=target_type,
                     target_id=target_id, status="running", started_at=_now())
    db.session.add(task)
    db.session.flush()
    return task


def _finish(task, status, result=None, error=None):
    task.status = status
    task.result_json = result
    task.error_message = error
    task.finished_at = _now()
    db.session.commit()
    return task


# ---------- 第二階段：偵測更新 ----------

def check_source(source, requester, fetch=fetch_url, content=None, content_type="application/pdf"):
    """抓一次來源並和上次比對。content 有值時（手動上傳）就不連網路。"""
    task = _start_task("admission_source_check", requester, "public_source", source.id)
    try:
        if content is None:
            content, content_type = fetch(source.url)
        digest = hashlib.sha256(content).hexdigest()
        previous = (PublicSourceSnapshot.query.filter_by(source_id=source.id)
                    .order_by(PublicSourceSnapshot.id.desc()).first())
        if previous and previous.content_hash == digest:
            return _finish(task, "succeeded", {"changed": False, "hash": digest})
        extension = _extension(content_type, source.url)
        (_folder() / f"{digest}.{extension}").write_bytes(content)
        snapshot = PublicSourceSnapshot(source_id=source.id, content_hash=digest)
        db.session.add(snapshot)
        db.session.flush()
        db.session.add(PublicSourceChange(
            snapshot_id=snapshot.id,
            change_type="changed" if previous else "first",
            diff_json={"previous_hash": previous.content_hash if previous else None, "new_hash": digest,
                       "size": len(content), "content_type": content_type, "extension": extension},
            status="candidate",
        ))
        return _finish(task, "succeeded", {"changed": True, "hash": digest, "first": previous is None})
    except Exception as exc:  # 失敗也要留下紀錄，管理者才知道
        db.session.rollback()
        db.session.add(task)
        return _finish(task, "failed", error=f"抓取失敗：{exc}")


def check_all(requester):
    """排程用：檢查所有啟用中的網址來源（flask agent-check）。"""
    sources = PublicSource.query.filter_by(is_active=True, source_type="url").all()
    return [check_source(source, requester) for source in sources]


# ---------- 第三階段：擷取加權 ----------

EXTRACT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "programs": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "program_code": {"type": "STRING"},
                    "admission_year": {"type": "INTEGER"},
                    "school_name": {"type": "STRING"},
                    "department_name": {"type": "STRING"},
                    "admission_category": {"type": "STRING"},
                    "eligibility_rules": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "rule_group": {"type": "INTEGER"},
                                "condition_type": {"type": "STRING"},
                                "operator": {"type": "STRING"},
                                "value_json": {"type": "OBJECT"},
                                "description": {"type": "STRING"},
                                "source_location": {"type": "STRING"},
                                "is_required": {"type": "BOOLEAN"},
                            },
                            "required": ["description", "source_location"],
                        },
                    },
                    "items": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "name": {"type": "STRING"},
                                "weight": {"type": "INTEGER"},
                                "categories": {"type": "ARRAY", "items": {"type": "STRING"}},
                            },
                            "required": ["name", "weight", "categories"],
                        },
                    },
                },
                "required": ["program_code", "admission_year", "school_name", "department_name", "items",
                             "eligibility_rules"],
            },
        },
    },
    "required": ["programs"],
}


def _extract_prompt(keywords, page_text=None):
    categories = "、".join(f"{key}（{label}）" for key, label in ALL_LABELS.items())
    prompt = f"""以下是臺灣「二技技優甄審」的招生簡章或其附錄。請擷取科系名稱包含「{'、'.join(keywords)}」的每一個志願：
- program_code：志願代碼（6 位數字）
- admission_year：學年度（民國年，例如 116）
- school_name、department_name、admission_category（招生類別，例如「管理類四」）
- items：備審資料（第二階段）的每個評分項目名稱與加權百分比（整數，照原文）
- categories：建議這個項目對應的資料類別，只能從這些代碼選：{categories}
- eligibility_rules：只擷取簡章明確寫出的第一階段報名資格；每筆包含 rule_group（同組條件必須同時符合，不同組是替代資格）、condition_type（student_status、credential、competition）、operator、value_json、description（保留簡章原意）及 source_location（頁碼／章節）。
- value_json 只使用可直接對照學生結構化資料的欄位：學籍可用 field（class_name 或 admission_year）及 values；證照可用 name、min_level、issuer、issue_date_from、issue_date_to；競賽只可表達是否有已確認競賽經歷。

規則：只擷取文件裡真的有寫的內容，看不清楚或沒有寫的不要猜；獎項、名次或日期等目前沒有對應學生欄位的條件，不要轉成可自動判斷的 value_json，只保留 description 並讓 condition_type、operator 或 value_json 留空；保留該條原文和頁碼／章節供管理者核對。不符合關鍵字的科系不要列出。"""
    if page_text:
        prompt += "\n\n文件內容：\n" + page_text[:200000]
    return prompt


def _html_to_text(content):
    text = content.decode("utf-8", errors="ignore")
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))


def _eligibility_candidate(raw, source_url, sort_order):
    """只將結構明確的擷取結果留下可比對欄位；其他內容退為待核對原文。"""
    raw = raw if isinstance(raw, dict) else {"description": raw if isinstance(raw, str) else ""}
    description = str(raw.get("description") or "").strip()
    location = str(raw.get("source_location") or "").strip() or None
    condition_type = str(raw.get("condition_type") or "").strip()
    operator = str(raw.get("operator") or "").strip()
    value = raw.get("value_json")
    group_value = raw.get("rule_group")
    group = group_value if isinstance(group_value, int) and not isinstance(group_value, bool) else 0
    supported = {
        ("student_status", "in"),
        ("credential", "has_credential"),
        ("competition", "has_competition"),
    }
    structured = (condition_type, operator) in supported and isinstance(value, dict) and group >= 1
    if not description:
        description = "擷取到資格區塊，但未能可靠整理條件；請管理者回到官方簡章核對。"
    if not structured:
        condition_type = operator = "unresolved"
        value = None
        group = max(group, 1)
    return {
        "rule_group": group,
        "condition_type": condition_type,
        "operator": operator,
        "value_json": value,
        "description": description[:2000],
        "source_url": source_url,
        "source_location": location,
        "mapping_status": "pending",
        "is_required": raw.get("is_required") if isinstance(raw.get("is_required"), bool) else True,
        "sort_order": sort_order,
    }


def extract_programs(change, requester, generate=None):
    """把變更的簡章交給 AI 擷取，建立候選校系版本。generate 可以換成假的（測試用）。"""
    task = _start_task("admission_extract", requester, "public_source_change", change.id)
    snapshot = db.session.get(PublicSourceSnapshot, change.snapshot_id)
    source = db.session.get(PublicSource, snapshot.source_id)
    path = snapshot_file(snapshot)
    if not path:
        return _finish(task, "failed", error="找不到這次抓取的檔案，請重新檢查來源。")
    keywords = current_app.config["AGENT_PROGRAM_KEYWORDS"]
    if path.suffix == ".pdf":
        prompt, files = _extract_prompt(keywords), [("application/pdf", path.read_bytes())]
    else:
        prompt, files = _extract_prompt(keywords, _html_to_text(path.read_bytes())), []
    try:
        result = (generate or generate_json)(prompt, EXTRACT_SCHEMA, files)
    except AIUnavailable as exc:
        return _finish(task, "failed", error=str(exc))

    created, skipped = [], []
    for raw in result.get("programs", []):
        code = str(raw.get("program_code", "")).strip()
        department = str(raw.get("department_name", "")).strip()
        try:
            year = int(raw.get("admission_year"))
        except (TypeError, ValueError):
            year = 0
        if not re.fullmatch(r"\d{6}", code) or not 100 <= year <= 200 or not any(k in department for k in keywords):
            skipped.append(code or department)
            continue
        if AdmissionProgram.query.filter_by(program_code=code, admission_year=year, data_origin="agent").first():
            skipped.append(code)
            continue
        program = AdmissionProgram(
            program_code=code, admission_year=year,
            school_name=str(raw.get("school_name", "")).strip()[:100], department_name=department[:100],
            admission_category=(str(raw.get("admission_category") or "").strip()[:50] or None),
            source_url=None if source.url.startswith("upload://") else source.url,
            source_note=f"Agent 擷取自「{source.name}」（{snapshot.fetched_at:%Y-%m-%d}）"[:255],
            status="candidate", data_origin="agent", checked_at=date.today(),
        )
        db.session.add(program)
        db.session.flush()
        for order, item in enumerate(raw.get("items", []), start=1):
            try:
                weight = max(0, min(100, int(item.get("weight", 0))))
            except (TypeError, ValueError):
                weight = 0
            keys = [k for k in item.get("categories", []) if k in ALL_LABELS]
            db.session.add(AdmissionRequirementItem(
                rule_version_id=program.id, source_item_name=str(item.get("name", "")).strip()[:100] or "（未命名）",
                weight_percent=weight, mapped_categories=",".join(keys), mapping_status="pending", sort_order=order,
            ))
        official_url = None if source.url.startswith("upload://") else source.url
        raw_rules = raw.get("eligibility_rules")
        if not isinstance(raw_rules, list) or not raw_rules:
            raw_rules = [{
                "description": "未能擷取到可核對的報名資格條件；請管理者回到官方簡章確認。",
                "source_location": None,
            }]
        for order, raw_rule in enumerate(raw_rules, start=1):
            db.session.add(AdmissionEligibilityRule(
                rule_version_id=program.id,
                **_eligibility_candidate(raw_rule, official_url, order),
            ))
        created.append(code)
    change.status = "extracted"
    return _finish(task, "succeeded", {"created": created, "skipped": skipped})


def compare_with_published(program):
    """和同一志願代碼「最近一年的正式版」比對加權，給管理者核准前看。"""
    previous = (AdmissionProgram.query.filter(
        AdmissionProgram.program_code == program.program_code,
        AdmissionProgram.status == "published",
        AdmissionProgram.id != program.id,
    ).order_by(AdmissionProgram.admission_year.desc()).first())
    old = {item.source_item_name: item.weight_percent for item in previous.items} if previous else {}
    new = {item.source_item_name: item.weight_percent for item in program.items}
    rows = [{"name": name, "old": old.get(name), "new": new.get(name)}
            for name in list(new) + [n for n in old if n not in new]]
    for row in rows:
        row["changed"] = row["old"] != row["new"]
    return {"previous": previous, "rows": rows}
