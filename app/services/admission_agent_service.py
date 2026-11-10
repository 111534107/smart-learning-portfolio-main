"""招生資料 Agent（系統亮點第一、二、三階段）。

第一階段：上網找來源（2026-11-04 使用者：Agent 要自己上網找，不是人工登記網址）
    Agent 用 Gemini 內建的 Google 搜尋找招生簡章與備審資料準備指引 → 只收學校（.edu.tw）與政府（.gov.tw）網域 →
    自動登記成來源。搜尋只會新增「要監看的來源」，不會發布任何招生資料。
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
import ssl
import urllib.request
from urllib.parse import urlsplit
from datetime import date, datetime, timezone
from pathlib import Path

from flask import current_app

from app.extensions import db
from app.models import (
    AdmissionEligibilityRule,
    AdmissionProgram,
    AdmissionRequirementItem,
    AdmissionScheduleEvent,
    AgentTask,
    PublicSource,
    PublicSourceChange,
    PublicSourceSnapshot,
)
from app.services.gap_service import ALL_LABELS
from app.services.gemini_client import AIUnavailable, generate_json, search_web

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


def _ssl_context():
    """照常驗證憑證與網域；只關掉 Python 3.13 新增的嚴格 X.509 檢查。

    部分學校與政府網站（例如技專校院招生委員會聯合會）的憑證缺少 Subject Key Identifier，
    瀏覽器可以開，但嚴格檢查會拒絕連線。
    """
    context = ssl.create_default_context()
    context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return context


def fetch_url(url):
    """下載官方網頁或 PDF，回傳 (內容, Content-Type)。"""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30, context=_ssl_context()) as response:
        content = response.read(MAX_DOWNLOAD + 1)
        if len(content) > MAX_DOWNLOAD:
            raise ValueError("檔案超過 30MB，請改用手動上傳")
        return content, response.headers.get_content_type()


def _extension(content_type, url):
    content_type = (content_type or "").split(";")[0].strip().lower()  # 「text/html; charset=utf-8」也認得
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


# ---------- 第一階段：上網找來源 ----------

OFFICIAL_SUFFIXES = (".edu.tw", ".gov.tw")
AGENT_SOURCE_PREFIX = "Agent 找到："


def official_url(url):
    """只有學校（.edu.tw）與政府（.gov.tw）網站算官方來源；看主機名稱結尾，不看網址裡有沒有出現這些字。"""
    parts = urlsplit(url or "")
    host = (parts.hostname or "").lower()
    return parts.scheme in ("http", "https") and host.endswith(OFFICIAL_SUFFIXES)


def resolve_url(uri):
    """搜尋結果多半是 Google 的轉址連結：追到最後的真正網址。先只讀標頭（HEAD）；
    有些學校網站不接受 HEAD（實測 11-04），再改用一般請求（GET，不讀內容）。都失敗回傳 None。"""
    for method in ("HEAD", "GET"):
        try:
            request = urllib.request.Request(uri, headers={"User-Agent": USER_AGENT}, method=method)
            with urllib.request.urlopen(request, timeout=15, context=_ssl_context()) as response:
                return response.geturl()
        except Exception:  # 轉址失效、對方拒絕：換下一種方法，最後就跳過這筆
            continue
    return None


def default_search_queries(roc_year=None):
    """預設搜尋：今年與明年的二技技優甄審、日間部申請入學簡章，以及資管系的備審資料準備指引。"""
    year = roc_year or date.today().year - 1911
    queries = []
    for y in (year, year + 1):
        queries += [
            f"{y} 學年度 二技技優甄審 招生簡章 技專校院招生委員會聯合會",
            f"{y} 學年度 日間部二技申請入學 招生簡章 資訊管理系",
            f"{y} 學年度 二技 資訊管理系 備審資料準備指引",
        ]
    return queries


def discover_sources(requester, queries=None, search=None, resolve=None):
    """讓 Agent 自己上網找官方來源並登記；回傳這次的 agent_task。search／resolve 測試時換成假的。"""
    search = search or search_web
    resolve = resolve or resolve_url
    queries = queries or default_search_queries()
    task = _start_task("admission_source_search", requester, None, None)
    known = {source.url for source in PublicSource.query.all()}
    added, already, unofficial = [], 0, 0
    try:
        for query in queries:
            for found in search(query).get("sources", []):
                url = resolve(found["uri"])
                if not url or not official_url(url):
                    unofficial += 1
                    continue
                if url in known:
                    already += 1
                    continue
                title = (found.get("title") or urlsplit(url).hostname or url).strip()
                add_source(AGENT_SOURCE_PREFIX + title, url=url)
                known.add(url)
                added.append(url)
    except AIUnavailable as exc:
        db.session.rollback()
        db.session.add(task)
        return _finish(task, "failed", {"queries": queries, "added": added}, error=f"上網搜尋失敗：{exc}")
    return _finish(task, "succeeded", {"queries": queries, "added": added, "already_known": already,
                                       "skipped_unofficial": unofficial})


# ---------- 第二階段：偵測更新 ----------

def check_source(source, requester, fetch=fetch_url, content=None, content_type="application/pdf"):
    """抓一次來源並和上次比對。content 有值時（手動上傳）就不連網路。"""
    task = _start_task("admission_source_check", requester, "public_source", source.id)
    try:
        if content is None:
            content, content_type = fetch(source.url)
        digest = _fingerprint(content, content_type)
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
        linked = []
        if extension == "html" and official_url(source.url):
            linked = follow_brochure_links(source, content)
        return _finish(task, "succeeded", {"changed": True, "hash": digest, "first": previous is None,
                                           "linked_sources": linked})
    except Exception as exc:  # 失敗也要留下紀錄，管理者才知道
        db.session.rollback()
        db.session.add(task)
        return _finish(task, "failed", error=f"抓取失敗：{exc}")


LINK = re.compile(r"""<a\b[^>]*?href\s*=\s*["']([^"'#]+)["'][^>]*>(.*?)</a>""", re.I | re.S)
BROCHURE_WORDS = re.compile(r"簡章|甄審|招生|備審|日程")
MAX_LINKED = 10
LINKED_PREFIX = "Agent 從頁面找到："


def follow_brochure_links(source, content):
    """官方網頁更新時，把頁面上的簡章 PDF 連結登記成新來源（2026-11-10）。

    只收：.pdf 結尾、連結文字或檔名有「簡章／甄審／招生／備審／日程」、而且是學校或政府網站；
    已經登記過的不重複，一次最多 MAX_LINKED 個。登記的來源一樣要經過檢查、擷取、管理員核准。
    """
    from urllib.parse import urljoin
    known = {item.url for item in PublicSource.query.all()}
    added = []
    for href, label in LINK.findall(_decode(content)):
        url = urljoin(source.url, href.strip())
        text = " ".join(re.sub(r"<[^>]+>", " ", label).split())
        if (not urlsplit(url).path.lower().endswith(".pdf") or not official_url(url)
                or not BROCHURE_WORDS.search(text + url) or url in known):
            continue
        add_source((LINKED_PREFIX + (text or url.rsplit("/", 1)[-1]))[:150], url=url)
        known.add(url)
        added.append(url)
        if len(added) >= MAX_LINKED:
            break
    return added


def check_all(requester, fetch=fetch_url):
    """排程用：檢查所有啟用中的網址來源（flask agent-check、升學 Agent 巡查）。fetch 可換成假的（測試用）。"""
    sources = PublicSource.query.filter_by(is_active=True, source_type="url").all()
    return [check_source(source, requester, fetch=fetch) for source in sources]


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
                                "requirement": {"type": "STRING"},
                                "source_page": {"type": "STRING"},
                            },
                            "required": ["name", "weight", "categories"],
                        },
                    },
                    "highlights": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {"text": {"type": "STRING"}, "source_page": {"type": "STRING"}},
                            "required": ["text"],
                        },
                    },
                },
                "required": ["program_code", "admission_year", "school_name", "department_name", "items",
                             "eligibility_rules"],
            },
        },
        "schedule": {
            "type": "OBJECT",
            "properties": {
                "channel": {"type": "STRING"},
                "admission_year": {"type": "INTEGER"},
                "events": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "name": {"type": "STRING"},
                            "start": {"type": "STRING"},
                            "end": {"type": "STRING"},
                            "note": {"type": "STRING"},
                        },
                        "required": ["name", "start"],
                    },
                },
            },
        },
    },
    "required": ["programs"],
}

SCHEDULE_CHANNELS = {"skill_review"}


def _extract_prompt(keywords, page_text=None):
    categories = "、".join(f"{key}（{label}）" for key, label in ALL_LABELS.items())
    max_highlights = MAX_HIGHLIGHTS
    prompt = f"""以下是臺灣「二技技優甄審」的招生簡章或其附錄。請擷取科系名稱包含「{'、'.join(keywords)}」的每一個志願：
- program_code：志願代碼（6 位數字）
- admission_year：學年度（民國年，例如 116）
- school_name、department_name、admission_category（招生類別，例如「管理類四」）
- items：備審資料（第二階段）的每個評分項目名稱與加權百分比（整數，照原文）
- categories：建議這個項目對應的資料類別，只能從這些代碼選：{categories}
- requirement：這個評分項目要繳什麼、怎麼評（照簡章的「繳交資料」與「評分標準」整理成一兩句，不要加自己的建議）；簡章沒寫就留空
- source_page：這個項目在簡章的頁碼（照頁面上印的頁碼）
- highlights：學生準備備審時最容易漏掉的重點，最多 {max_highlights} 條，每條一句話、附 source_page 頁碼。只收簡章明確寫的：
  要另外下載或親簽的表格、字數或頁數上限、必繳與選繳的分別、缺件以零分計、報名前要具備的檢定程度、入學後的畢業門檻。
  一般說明（例如「資料不退還」）不要列。
- eligibility_rules：只擷取簡章明確寫出的第一階段報名資格；每筆包含 rule_group（同組條件必須同時符合，不同組是替代資格）、condition_type（student_status、credential、competition）、operator、value_json、description（保留簡章原意）及 source_location（頁碼／章節）。
- value_json 只使用可直接對照學生結構化資料的欄位：學籍可用 field（class_name 或 admission_year）及 values；證照可用 name、min_level、issuer、issue_date_from、issue_date_to；競賽只可表達是否有已確認競賽經歷。

規則：只擷取文件裡真的有寫的內容，看不清楚或沒有寫的不要猜；不符合關鍵字的科系不要列出。獎項、名次或日期等缺少學生欄位的條件，不得自動判斷；保留原文和頁碼供管理者核對。

另外，如果文件有「重要日程表」，請填 schedule：
- channel：二技技優保送／技優甄審的日程填 skill_review；其他招生管道填 other
- admission_year：學年度（民國年，例如 116）
- events：考生要注意的每一個日程，只取【技優甄審】欄或兩欄共用的項目；學校之間的行政作業（例如寄送錄取名單）不要列
  - 只出現在【技優保送】欄的項目（例如網路查詢成績排名、成績排名複查、網路選填志願）不要列；日期請對準【技優甄審】欄那一列
  - name：項目名稱，20 個字以內（例如「網路報名」「登記就讀志願序」）；說明、電話、注意事項一律放 note，不要放進 name
  - start、end：轉成西元「YYYY-MM-DD HH:MM」（民國年加 1911，例如 115.4.9 → 2026-04-09）；沒寫時間的開始用 00:00、結束用 23:59
  - 「…前」「…止」這種截止時間只有一個時間點：start 填那個時間、end 留空
  - note：注意事項（例如「當日只到 17:00」），沒有就留空
沒有日程表就不要填 schedule。"""
    if page_text:
        prompt += "\n\n文件內容：\n" + page_text[:200000]
    return prompt


# 網頁上每次都會變、但和招生內容無關的計數器，比對前先拿掉（例如「網站人次：1666538」）
COUNTER = re.compile(r"(網站|瀏覽|訪客|參觀|累計|今日|本日)?(人次|人數|點閱數|點閱率|瀏覽數)\s*[:：]?\s*[\d,]+")


def _decode(content):
    """學校網站常是 Big5：先試 UTF-8，不行再用 cp950（Big5 的 Windows 版）。"""
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("cp950", errors="ignore")


def _fingerprint(content, content_type):
    """判斷來源有沒有更新用的雜湊：PDF 比原始檔；網頁比去掉標籤與計數器後的文字。"""
    if content_type == "text/html":
        text = COUNTER.sub(" ", _html_to_text(content))
        return hashlib.sha256(re.sub(r"\s+", " ", text).strip().encode("utf-8")).hexdigest()
    return hashlib.sha256(content).hexdigest()


def _html_to_text(content):
    text = _decode(content)
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
                requirement=_requirement_text(item),
            ))
        program.highlights = _highlights(raw.get("highlights"))
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
    schedule_created, schedule_skipped = _save_schedule(result.get("schedule") or {}, change, source)
    change.status = "extracted"
    return _finish(task, "succeeded", {"created": created, "skipped": skipped,
                                       "schedule_created": schedule_created, "schedule_skipped": schedule_skipped})


def _parse_time(text):
    try:
        return datetime.strptime(str(text or "").strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def _save_schedule(schedule, change, source):
    """把擷取到的日程存成候選；日期看不懂、結束比開始早的項目略過。回傳 (新增數, 略過數)。"""
    if schedule.get("channel") not in SCHEDULE_CHANNELS:
        return 0, 0
    try:
        year = int(schedule.get("admission_year"))
    except (TypeError, ValueError):
        return 0, len(schedule.get("events") or [])
    if not 100 <= year <= 200:
        return 0, len(schedule.get("events") or [])
    created = skipped = 0
    for raw in schedule.get("events") or []:
        name = str(raw.get("name", "")).strip()[:100]
        start, end = _parse_time(raw.get("start")), _parse_time(raw.get("end")) if str(raw.get("end") or "").strip() else None
        bad_end = str(raw.get("end") or "").strip() and end is None
        if not name or start is None or bad_end or (end and end < start) or not 2000 <= start.year <= 2100:
            skipped += 1
            continue
        duplicate = AdmissionScheduleEvent.query.filter(
            AdmissionScheduleEvent.channel == schedule["channel"], AdmissionScheduleEvent.admission_year == year,
            AdmissionScheduleEvent.name == name, AdmissionScheduleEvent.start_at == start,
            AdmissionScheduleEvent.end_at.is_(end) if end is None else AdmissionScheduleEvent.end_at == end,
            AdmissionScheduleEvent.status.in_(["candidate", "published"])).first()
        if duplicate:
            continue
        db.session.add(AdmissionScheduleEvent(
            channel=schedule["channel"], admission_year=year, name=name, start_at=start, end_at=end,
            note=str(raw.get("note") or "").strip()[:255] or None,
            source_url=None if source.url.startswith("upload://") else source.url,
            status="candidate", data_origin="agent", change_id=change.id,
        ))
        created += 1
    return created, skipped


MAX_HIGHLIGHTS = 8


def _page_label(page):
    page = str(page or "").strip()
    if not page:
        return ""
    return f"第{page}頁" if page.isdigit() else page


def _requirement_text(item):
    """評分項目的「要繳什麼」，後面附頁碼，方便管理員回簡章核對。沒寫就是 None。"""
    text = " ".join(str(item.get("requirement") or "").split())[:500]
    if not text:
        return None
    page = _page_label(item.get("source_page"))
    return f"{text}（{page}）" if page else text


def _highlights(raw):
    """重點提醒：去掉空白、重複，最多 MAX_HIGHLIGHTS 條。"""
    result, seen = [], set()
    for entry in raw if isinstance(raw, list) else []:
        if not isinstance(entry, dict):
            continue
        text = " ".join(str(entry.get("text") or "").split())[:200]
        if not text or text in seen:
            continue
        seen.add(text)
        result.append({"text": text, "page": _page_label(entry.get("source_page"))})
        if len(result) >= MAX_HIGHLIGHTS:
            break
    return result or None


def compare_with_published(program):
    """和同一志願代碼「最近一年的正式版」比對加權，給管理者核准前看。"""
    previous = (AdmissionProgram.query.filter(
        AdmissionProgram.program_code == program.program_code,
        AdmissionProgram.status == "published",
        AdmissionProgram.id != program.id,
    ).order_by(AdmissionProgram.admission_year.desc()).first())
    old_items = {item.source_item_name: item for item in previous.items} if previous else {}
    new_items = {item.source_item_name: item for item in program.items}
    rows = []
    for name in list(new_items) + [n for n in old_items if n not in new_items]:
        old, new = old_items.get(name), new_items.get(name)
        row = {"name": name, "old": old.weight_percent if old else None, "new": new.weight_percent if new else None,
               "old_requirement": old.requirement if old else None,
               "new_requirement": new.requirement if new else None}
        row["changed"] = row["old"] != row["new"]
        # 要繳的資料改了也要讓管理員看到（只比對字，不比對頁碼括號）
        row["requirement_changed"] = bool(old and new and _strip_page(old.requirement) != _strip_page(new.requirement))
        rows.append(row)
    return {"previous": previous, "rows": rows}


def _strip_page(text):
    return re.sub(r"（第[^）]*頁）$", "", (text or "").strip())
