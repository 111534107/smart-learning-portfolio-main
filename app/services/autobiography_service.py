"""AI 自傳小幫手：學生先回答幾題，AI 再用「回答＋已確認的六類資料＋目標校系加權」寫草稿。

防止 AI 亂寫的做法：
1. 把學生資料整理成有編號的事實（F1、F2…），AI 只能引用這些事實和學生的回答。
2. 每一段都要列出用到的事實編號，不存在的編號會被濾掉。
3. 草稿一定要學生自己看過、修改、儲存，才會放進備審 Word。

草稿存在 learning_profile_outputs（output_type="autobiography_ai"），不需要新資料表。

版本紀錄（規格 10.3-4、10.3-5）：AI 產生、學生儲存、導師修改，每一次都**新增一筆**，舊版不動也不能刪。
content_json 記錄 version（第幾版）、editor_id、editor_role（ai／student／teacher）、based_on（從哪一版改的）。
"""

import difflib
from datetime import datetime, timezone

from markupsafe import Markup, escape
from flask import current_app

from app.extensions import db
from app.models import AdmissionProgram, CredentialRecord, LearningCourseRecord, LearningProfileOutput, Portfolio, User
from app.services import autobiography_backup, package_exclusion
from app.services.gap_service import ALL_LABELS
from app.services.gemini_client import AIUnavailable, ai_ready, generate_json
from app.services.journey_service import CATEGORY_LABELS

OUTPUT_TYPE = "autobiography_ai"

# 舊 submitted 可能由草稿直接送出，無法證明學生已確認；需重新確認。
CONFIRMED_PORTFOLIO_STATUSES = ("confirmed",)

# 問題（key, 題目, 提示）。要改題目只要改這裡。
QUESTIONS = [
    ("motivation", "為什麼想繼續讀資管，或特別想讀這個系？", "例如：哪一門課、哪一次經驗讓你確定方向"),
    ("proud", "五年中最有成就感的一件事是什麼？你負責做了什麼？", "寫你自己做的部分，越具體越好"),
    ("challenge", "遇過最大的困難是什麼？你怎麼解決？", "可以是課業、專題或團隊合作"),
    ("future", "進二技後想學什麼？之後想做什麼工作？", "和這個系的課程或特色連起來會更好"),
]

# 依簡章比重引導（導師 2026-11-12）：比重高的項目一定要學生自己寫到，AI 只整理。
# 每個資料類別的提示；題目本身用簡章的項目名稱與比重，沒有比重資料的校系不加題目。
FOCUS_HINTS = {
    "grades": "哪一門課學得最好、你怎麼學的",
    "credential": "為什麼考這張證照、準備過程學到什麼",
    "competition": "哪一個比賽、你負責什麼、結果如何",
    "project": "專題題目、你負責的部分、做出什麼成果",
    "activity": "參加過的社團或活動、你做了什麼",
    "leadership": "擔任過的幹部、處理過的事情",
    "service": "服務的對象與內容、你的體會",
}
VALUED_LABEL = "這所校系很看重"
VALUED_WEIGHT = 30  # 比重最高的項目，以及比重達到這個百分比的項目，標示「這所校系很看重」
MIN_OWN_CHARS = 10  # 少於這個字數不算「用自己的話寫過」


def guided_questions(program):
    """自傳引導題目：先列簡章評分項目（比重高到低），再列原本的共通題。

    回傳 [{key, text, hint, weight, item, important}]。校系沒有比重資料時只有原本的題目，不自己編比重。
    同一組資料類別只出一題（取比重最高的項目），key 用類別組成，換校系時回答可以沿用。
    """
    focus = {}
    for item in (program.items if program else []):
        keys = sorted(key for key in item.category_keys if key in FOCUS_HINTS)
        if not keys or not item.weight_percent:
            continue
        key = "focus_" + "_".join(keys)
        if key not in focus or item.weight_percent > focus[key]["weight"]:
            focus[key] = {
                "key": key,
                "text": f"簡章評分項目「{item.source_item_name}」占 {item.weight_percent}%："
                        "你有哪些相關經驗？你自己做了什麼、結果如何？",
                "hint": "可以寫：" + "；".join(FOCUS_HINTS[k] for k in keys),
                "weight": item.weight_percent,
                "item": item.source_item_name,
                "important": False,
            }
    ordered = sorted(focus.values(), key=lambda question: -question["weight"])  # 穩定排序，同比重維持簡章順序
    for question in ordered:
        question["important"] = question["weight"] == ordered[0]["weight"] or question["weight"] >= VALUED_WEIGHT
    base = [{"key": key, "text": text, "hint": hint, "weight": None, "item": None, "important": False}
            for key, text, hint in QUESTIONS]
    return ordered + base


def own_words_problem(program, answers):
    """學生還沒用自己的話寫夠就回傳提示文字（不能產生草稿）；可以產生時回傳 None。"""
    questions = guided_questions(program)

    def written(key):
        return len((answers.get(key) or "").strip()) >= MIN_OWN_CHARS

    missing = [question["item"] for question in questions if question["important"] and not written(question["key"])]
    if missing:
        return (f"{VALUED_LABEL}「{'、'.join(missing)}」，請先用自己的話寫幾句（每題至少 {MIN_OWN_CHARS} 個字；"
                "還沒有相關經驗，也可以寫你打算怎麼準備）。AI 只幫你整理文字，不會替你寫。")
    if not any(written(question["key"]) for question in questions):
        return f"請先用自己的話寫幾句（至少回答一題、{MIN_OWN_CHARS} 個字以上）。AI 只幫你整理文字，不會替你寫。"
    return None


PARAGRAPH_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "paragraphs": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "title": {"type": "STRING"},
                    "text": {"type": "STRING"},
                    "sources": {"type": "ARRAY", "items": {"type": "STRING"}},
                },
                "required": ["title", "text", "sources"],
            },
        },
    },
    "required": ["paragraphs"],
}


def build_facts(student, program):
    """把學生已確認的資料整理成編號事實，並附上目標校系的評分項目與加權。

    只收學生確認過的資料：成績與證照要 confirmation_status 是 confirmed，經歷要學生按過「確認」。
    學生標成「不放進備審」的資料不收；這個校系簡章規定必備的類別除外。
    """
    required = package_exclusion.required_keys(program)
    lines = []
    for course in package_exclusion.keep_courses(
            LearningCourseRecord.query.filter_by(student_id=student.id, confirmation_status="confirmed")
            .order_by(LearningCourseRecord.id), required):
        score = f"{course.score} 分" if course.score is not None else (course.status_mark or "")
        lines.append({
            "text": f"成績：{course.course_name}（{course.year_for_placement or '?'} 年級，{score}）",
            "evidence_id": f"course:{course.id}",
            "evidence_type": "course",
        })
    for credential in package_exclusion.keep_credentials(
            CredentialRecord.query.filter_by(student_id=student.id, confirmation_status="confirmed")
            .order_by(CredentialRecord.id), required):
        lines.append({
            "text": f"證照：{credential.credential_name}" + (f"（{credential.level}）" if credential.level else ""),
            "evidence_id": f"credential:{credential.id}",
            "evidence_type": "credential",
        })
    for record in package_exclusion.keep_portfolios(
            Portfolio.active().filter_by(student_id=student.id)
            .filter(Portfolio.status.in_(CONFIRMED_PORTFOLIO_STATUSES)).order_by(Portfolio.id), required):
        label = CATEGORY_LABELS.get(record.category)
        if label:
            source = "" if record.source == "student" else f"（來源：{record.source_label}）"
            details = "；".join(f"{name}：{value}" for name, value in (
                ("我負責", record.role), ("成果", record.achievement), ("學到", record.learned), ("領域", record.domain_tags))
                if value)
            lines.append({
                "text": f"{label}：{record.title}" + (f"—{record.description}" if record.description else "")
                        + (f"（{details}）" if details else "") + source,
                "evidence_id": f"portfolio:{record.id}",
                "evidence_type": "portfolio",
            })
    items = [{"id": f"F{index}", **item} for index, item in enumerate(lines, start=1)]
    weights = [{
        "name": item.source_item_name,
        "weight": item.weight_percent,
        "categories": "、".join(ALL_LABELS.get(key, key) for key in item.category_keys),
    } for item in sorted(program.items, key=lambda i: -i.weight_percent)]
    return {"items": items, "weights": weights}


def strength_inventory(student, program=None):
    """按現有類別盤點已確認資料；數量並非能力評分。有指定校系時，不列學生選擇不放進備審的資料。"""
    required = package_exclusion.required_keys(program) if program else None
    groups = {}
    def add(label, name, evidence_id):
        groups.setdefault(label, []).append({"name": name, "evidence_id": evidence_id})
    courses = LearningCourseRecord.query.filter_by(student_id=student.id, confirmation_status="confirmed").all()
    credentials = CredentialRecord.query.filter_by(student_id=student.id, confirmation_status="confirmed").all()
    records = Portfolio.active().filter_by(student_id=student.id, status="confirmed").all()
    if required is not None:
        courses = package_exclusion.keep_courses(courses, required)
        credentials = package_exclusion.keep_credentials(credentials, required)
        records = package_exclusion.keep_portfolios(records, required)
    for item in courses:
        add("已確認課程", item.course_name, f"course:{item.id}")
    for item in credentials:
        add("證照：" + (item.category or "未分類"), credential_label(item), f"credential:{item.id}")
    for item in records:
        if item.category in CATEGORY_LABELS:
            add(CATEGORY_LABELS[item.category], item.title, f"portfolio:{item.id}")
    return [{"label": label, "count": len(items), "evidence": items} for label, items in groups.items()]

# 備審目錄不列的共同課程（不是專業能力的證明）：勞作教育、體育、班會等
GENERAL_COURSE_WORDS = ("勞作", "體育", "班會", "週會", "周會", "團體活動", "全民國防", "軍訓", "健康與護理", "生涯規劃")
TOP_COURSES = 5


def credential_label(credential):
    """證照名稱加上級別（同名證照才分得出來），名稱已含級別就不重複。"""
    name = credential.credential_name
    level = (credential.level or "").strip()
    return f"{name}（{level}）" if level and level not in name else name


def _course_summary(courses):
    """成績不逐門列出（11-04 實測：85 門課全列，連勞作教育、體育都在）：
    一行總覽＋分數最高的幾門專業科目。"""
    if not courses:
        return []
    scored = [c for c in courses if c.score is not None]
    summary = f"歷年成績單：已確認 {len(courses)} 門課"
    if scored:
        summary += f"，平均 {round(sum(c.score for c in scored) / len(scored), 1)} 分"
    items = [{"name": summary, "evidence_id": "course:all"}]
    professional = [c for c in scored if not any(word in c.course_name for word in GENERAL_COURSE_WORDS)]
    seen = set()
    for course in sorted(professional, key=lambda c: c.score, reverse=True):
        if course.course_name in seen:
            continue
        seen.add(course.course_name)
        items.append({"name": f"表現較好的科目：{course.course_name} {course.score:g} 分", "evidence_id": f"course:{course.id}"})
        if len(seen) >= TOP_COURSES:
            break
    return items


def custom_contents(student, program):
    """依加權列出已確認的具體佐證；保留資料來源供學生核對。"""
    from app.services.gap_service import chapter_order

    courses = LearningCourseRecord.query.filter_by(student_id=student.id, confirmation_status="confirmed").all()
    credentials = CredentialRecord.query.filter_by(student_id=student.id, confirmation_status="confirmed").all()
    records = Portfolio.active().filter_by(student_id=student.id, status="confirmed").all()
    required = package_exclusion.required_keys(program)
    courses = package_exclusion.keep_courses(courses, required)
    credentials = package_exclusion.keep_credentials(credentials, required)
    records = package_exclusion.keep_portfolios(records, required)
    chapters = chapter_order(program)
    for chapter in chapters:
        evidence = []
        if "grades" in chapter["keys"]:
            evidence.extend(_course_summary(courses))
        if "credential" in chapter["keys"]:
            evidence.extend({"name": credential_label(c), "evidence_id": f"credential:{c.id}"} for c in credentials)
        for record in records:
            if record.category in chapter["keys"] or ("project" in chapter["keys"] and
                    ("專題" in record.title or "作品" in record.title)):
                evidence.append({"name": record.title, "evidence_id": f"portfolio:{record.id}"})
        chapter["evidence"] = evidence
    return chapters

def build_evidence_package(student, program):
    """為指定校系整理學生已確認、可追溯來源的最小證據包。"""
    facts = build_facts(student, program)
    return {"version": 1, "program_id": program.id, "items": facts["items"]}


def _prompt(student, program, facts, answers, questions=None):
    questions = questions or guided_questions(program)
    fact_lines = "\n".join(f"{fact['id']}. {fact['text']}" for fact in facts["items"]) or "（沒有資料）"
    weight_lines = "\n".join(f"- {w['name']}：{w['weight']}%（{w['categories']}）" for w in facts["weights"])
    budgets = paragraph_budgets(program, questions)
    outline = "→".join(f"{title}（約{budgets.get(title, 200)}字內）" for title in outline_titles(program, questions))
    answer_lines = "\n".join(f"- {question['text']}\n  回答：{answers.get(question['key']) or '（未回答）'}"
                             for question in questions)
    return f"""你是五專資管科學生的自傳寫作助手。請幫學生寫申請「{program.school_name} {program.department_name}」的自傳草稿。

規則：
1. 使用繁體中文、第一人稱，語氣真誠自然，像高職／五專學生寫的，不要浮誇或使用空泛形容詞。
2. 只能使用下面的「學生資料」和「學生回答」，不得編造任何獎項、分數、證照、職位或經歷。資料不足就少寫，不要補。
3. 學生沒回答的題目，那一段的 text 只寫「（請補上：題目內容）」，sources 給空陣列；不要從其他資料推想他的感受、心得或經過。
4. 依校系加權，把加權高的項目相關經驗寫得比較完整。
5. 段落（目錄）請照這個大綱的順序，段落數量與順序不要增減：{outline}。每段的 title 請寫成「有主張的小標題」，格式像「從電腦興趣，走進資訊管理」「在社團中，學會負責與合作」（約 8 到 16 字，點出這段的成長主軸，不要只寫類別名稱）；括號裡的名稱只是這段的主題，不是標題。
5-1. 每段內文寫 3 到 5 句：先講一件具體的事（用學生資料或回答），再講做了什麼、得到什麼，最後用一兩句寫自己的體會，像學生自己說話，不要口號。
長度依簡章規定；沒有規定時以約 1500～2500 字為目標，資料不足時寧可較短，不得為湊字數編造。
6. 每段的 sources 列出這段用到的學生資料編號（例如 F2）；只用到學生回答就給空陣列。
7. 學生回答是自傳的主體：你只整理語句、順序與段落，不替學生新增他沒寫的經歷、感受或結論。

學生資料（只能引用這些）：
{fact_lines}

目標校系的評分項目與加權：
{weight_lines}

學生回答：
{answer_lines}
"""


MAX_FOCUS_SECTIONS = 4  # 自傳大綱最多放幾個「依簡章項目」的段落


def outline_titles(program, questions=None):
    """自傳大綱（目錄）：學習動機 → 依簡章比重由高到低的項目 → 困難與成長 → 未來規劃。

    沒有比重資料的校系沒有項目段落，改用「學習歷程與具體經驗」。標題用簡章的項目名稱，所以換校系目錄就會跟著變。
    """
    questions = questions if questions is not None else guided_questions(program)
    focus = [q["item"][:30] for q in questions if q.get("weight")][:MAX_FOCUS_SECTIONS]
    middle = [*focus, "學習歷程與具體經驗"]
    return ["學習動機", *middle, "困難與成長", "未來規劃"]


TOTAL_CHAR_BUDGET = 2200  # 一所校系自傳加讀書計畫的總字數目標（評審不會有耐心看萬字）
_FIXED_BUDGET = {"學習動機": 250, "學習歷程與具體經驗": 250, "困難與成長": 200, "未來規劃": 300}


def paragraph_budgets(program, questions=None):
    """每一段的字數上限：固定段落給固定字數，剩下的依簡章比重分給各項目（每項 150～450 字），總量約 2200 字。"""
    questions = questions if questions is not None else guided_questions(program)
    focus = [q for q in questions if q.get("weight")][:MAX_FOCUS_SECTIONS]
    left = max(TOTAL_CHAR_BUDGET - sum(_FIXED_BUDGET.values()), 150 * len(focus))
    total_weight = sum(q["weight"] for q in focus) or 1
    budgets = dict(_FIXED_BUDGET)
    for q in focus:
        budgets[q["item"][:30]] = max(150, min(450, round(left * q["weight"] / total_weight / 10) * 10))
    return budgets


def _demo_paragraphs(facts, answers, questions=()):
    """沒有接上 AI 時的示範草稿：只把學生的回答和資料排好，明白標示不是 AI 寫的。

    段落順序跟著校系的簡章比重（outline_titles）：比重高的項目排在前面，各自放學生對那一題的回答。
    """
    experience = [f for f in facts["items"] if f["text"].split("：", 1)[0] in ("競賽", "活動", "幹部經歷")][:3]
    titles = "、".join(f["text"].split("：", 1)[1].split("—")[0] for f in experience)
    proud = answers.get("proud") or "（請補上你最有成就感的經驗）"
    focus = [q for q in questions if q.get("weight")][:MAX_FOCUS_SECTIONS]
    middle = [{"title": q["item"][:30], "text": answers.get(q["key"]) or f"（請補上你在「{q['item']}」的相關經驗）",
               "sources": []} for q in focus]
    if not focus or answers.get("proud"):  # 學生回答了「最有成就感的事」就保留成一段，不因為有簡章項目而消失
        middle.append({"title": "學習歷程與具體經驗", "text": proud + (f"另外，我也參與了{titles}。" if titles else ""),
                       "sources": [f["id"] for f in experience]})
    return [
        {"title": "學習動機", "text": answers.get("motivation") or "（請補上你想讀這個系的原因）", "sources": []},
        *middle,
        {"title": "困難與成長", "text": answers.get("challenge") or "（請補上你遇過的困難與解決方式）", "sources": []},
        {"title": "未來規劃", "text": answers.get("future") or "（請補上進二技後的學習計畫）", "sources": []},
    ]


def new_facts_since(draft, current_facts):
    """草稿產生後新增的已確認資料（比對草稿存的資料清單）；用來提示「資料已更新，可重新產生」。"""
    old = {(f.get("text") or "") for f in ((draft.content_json or {}).get("facts") or [])}
    return [f["text"] for f in current_facts.get("items", []) if f.get("text") and f["text"] not in old]


def generate_draft(student, program, answers, generate=None, api_key=None):
    """產生並儲存草稿。generate 是呼叫 AI 的函式（測試時可以換成假的）。

    api_key：學生自己的 Gemini 金鑰，只在這次呼叫用，**不會**寫進資料庫或任何紀錄。
    """
    facts = build_facts(student, program)
    evidence_package = {"version": 1, "program_id": program.id, "items": facts["items"]}
    previous = latest_draft(student, program)
    known = {fact["id"] for fact in facts["items"]}
    questions = guided_questions(program)
    answers = {question["key"]: (answers.get(question["key"]) or "").strip()[:1000] for question in questions}
    use_ollama = not api_key and ollama_ready()
    if generate is None and not api_key and not ai_ready() and not use_ollama:
        paragraphs, provider = _demo_paragraphs(facts, answers, questions), "demo"
    else:
        prompt = _prompt(student, program, facts, answers, questions)
        if generate:
            result = generate(prompt, PARAGRAPH_SCHEMA)
        elif use_ollama:
            from app.services import ollama_client
            result = ollama_client.generate_json(prompt, PARAGRAPH_SCHEMA)
        else:
            result = generate_json(prompt, PARAGRAPH_SCHEMA, api_key=api_key)
        paragraphs = [{
            "title": str(p.get("title", "")).strip()[:30],
            "text": str(p.get("text", "")).strip(),
            "sources": [s for s in p.get("sources", []) if s in known],
        } for p in result.get("paragraphs", []) if str(p.get("text", "")).strip()]
        if not paragraphs:
            raise AIUnavailable("AI 沒有產生內容，請再試一次。")
        provider = "ollama" if use_ollama and generate is None else "gemini"
    content = {
        "program_id": program.id,
        "answers": answers,
        # 重新產生草稿時，上一版學生（或導師）自己改過的段落不能被 AI 蓋掉不見：留在這裡，頁面上可拖回去用
        "kept_paragraphs": _kept_paragraphs(previous),
        "paragraphs": paragraphs,
        "facts": facts["items"],
        "provider": provider,
        "edited": False,
        "version": _next_version(student.id, program.id),
        "editor_id": student.id,
        "editor_role": "ai",
        "based_on": previous.id if previous else None,
    }
    autobiography_backup.mark_pending(content)
    output = LearningProfileOutput(
        student_id=student.id,
        output_type=OUTPUT_TYPE,
        content_json=content,
        source_snapshot_json={"program_id": program.id, "fact_count": len(facts["items"]),
                              "evidence_package": evidence_package,
                              "generated_at": datetime.now(timezone.utc).isoformat()},
    )
    db.session.add(output)
    db.session.commit()
    autobiography_backup.schedule_after_save(current_app._get_current_object(), output)
    return output


def _kept_paragraphs(previous):
    """上一版若是人改過的，把有內容的段落留下（AI 重寫後學生自己打的字還在）；上一版是 AI 原稿就沿用它留下的。"""
    if not previous:
        return []
    content = previous.content_json
    if not content.get("edited"):
        return content.get("kept_paragraphs", [])
    return [{"title": p.get("title", ""), "text": p["text"]} for p in content.get("paragraphs", [])
            if p.get("text", "").strip() and not p["text"].startswith("（請補上")]


def own_words(content, questions):
    """自傳頁「你自己寫的文字」：學生的回答原文＋上一版自己改過的段落。回傳 [{label, text}]，AI 不會動這些字。"""
    answers = content.get("answers", {})
    items = [{"label": q["text"], "text": answers[q["key"]]} for q in questions if answers.get(q["key"], "").strip()]
    items += [{"label": f"上一版你改過的：{p['title']}", "text": p["text"]} for p in content.get("kept_paragraphs", [])]
    return items


def bio_pieces(student, program, draft=None):
    """自傳頁可拖放的素材（B1）。facts：已確認資料，插入「內容（F 編號）」讓依據檢查對得到；own：學生自己寫的原文。
    有草稿時用草稿存的資料（和段落引用的編號一致），沒有就用目前已確認的資料。"""
    items = draft.content_json.get("facts", []) if draft else build_facts(student, program)["items"]
    facts = [{"tag": f["id"], "text": f["text"], "insert": f"{f['text'].split('：', 1)[-1]}（{f['id']}）"} for f in items]
    own = ([{"tag": "", "text": f"{w['label']}：{w['text']}", "insert": w["text"]}
            for w in own_words(draft.content_json, guided_questions(program))] if draft else [])
    return {"facts": facts, "own": own}


def ollama_ready():
    return bool(current_app.config.get("AI_ENABLED") and
                current_app.config.get("AUTOBIOGRAPHY_AI_PROVIDER", "gemini") == "ollama")


def carried_answers(student):
    """新校系還沒有草稿時，帶入學生最近一份草稿存的回答；沒有就回傳空字典。

    回答只打一次：第二所學校不用重打，學生再依該校系修改。依簡章項目寫的回答（focus_ 開頭）也一起帶。
    """
    outputs = (LearningProfileOutput.query.filter_by(student_id=student.id, output_type=OUTPUT_TYPE)
               .order_by(LearningProfileOutput.id.desc()).all())
    for output in outputs:
        answers = output.content_json.get("answers") or {}
        if any(answers.values()):
            return {**{key: value for key, value in answers.items() if key.startswith("focus_") and value},
                    **{key: answers.get(key, "") for key, _, _ in QUESTIONS}}
    return {}


def versions(student, program):
    """同一位學生、同一個校系的所有自傳版本（舊到新）。"""
    outputs = (LearningProfileOutput.query.filter_by(student_id=student.id, output_type=OUTPUT_TYPE)
               .order_by(LearningProfileOutput.id).all())
    return [o for o in outputs if o.content_json.get("program_id") == program.id]


def never_submitted(student, program):
    """這份自傳從沒送過導師（沒有任何送審紀錄、也沒有導師留言）才能整份刪除（2026-11-19 使用者決定）。"""
    from app.models import AutobiographyComment, PackageReview
    if PackageReview.query.filter_by(student_id=student.id, rule_version_id=program.id).first():
        return False
    return AutobiographyComment.query.filter_by(student_id=student.id, program_id=program.id).first() is None


def delete_unsubmitted(student, program):
    """整份刪除從沒送審過的自傳草稿（所有版本與本系統記的 Google 文件連結）；送審過的回傳 None、不刪。

    學生雲端硬碟裡的 Google 文件本身不動（那是學生自己的檔案）。呼叫端 commit。"""
    from app.models import AutobiographyGoogleDoc
    if not never_submitted(student, program):
        return None
    drafts = versions(student, program)
    AutobiographyGoogleDoc.query.filter_by(student_id=student.id, program_id=program.id).delete()
    for draft in drafts:
        db.session.delete(draft)
    return len(drafts)


def version_of(output):
    """這一版是第幾版。新資料存在 content_json["version"]；舊資料依建立順序推算。"""
    if output.content_json.get("version"):
        return output.content_json["version"]
    earlier = (LearningProfileOutput.query.filter(
        LearningProfileOutput.student_id == output.student_id,
        LearningProfileOutput.output_type == OUTPUT_TYPE,
        LearningProfileOutput.id <= output.id,
    ).all())
    return sum(1 for o in earlier if o.content_json.get("program_id") == output.content_json.get("program_id"))


def latest_draft(student, program):
    outputs = (LearningProfileOutput.query.filter_by(student_id=student.id, output_type=OUTPUT_TYPE)
               .order_by(LearningProfileOutput.id.desc()).all())
    return next((o for o in outputs if o.content_json.get("program_id") == program.id), None)


class StaleVersion(RuntimeError):
    """要存的不是最新版（這段期間別人存了新版）。訊息是給使用者看的中文。"""


def _latest_for(student_id, program_id):
    outputs = (LearningProfileOutput.query.filter_by(student_id=student_id, output_type=OUTPUT_TYPE)
               .order_by(LearningProfileOutput.id.desc()).all())
    return next((o for o in outputs if o.content_json.get("program_id") == program_id), None)


def _next_version(student_id, program_id):
    outputs = LearningProfileOutput.query.filter_by(student_id=student_id, output_type=OUTPUT_TYPE).all()
    return 1 + max((version_of(o) for o in outputs if o.content_json.get("program_id") == program_id), default=0)


def _backup_existing(student_id, content):
    """存修改／取回的新版本也要備份到學校端：先標成待備份，commit 後交給背景佇列。"""
    autobiography_backup.mark_pending(content)


def save_edits(output, texts, editor, comments=None, images=None, titles=None):
    """逐段修改後儲存成**新的一版**，回傳新版本；舊版不動。

    texts：每一段的新文字（順序和原本一樣）。
    editor：按儲存的人（學生本人或導師）。
    comments：導師的段落意見；None 表示沿用上一版的意見（學生儲存時）。
    titles：各段標題（選填，若有新增段落或修改標題時使用）。
    要存的不是最新版時丟 StaleVersion，避免舊頁面蓋掉別人剛存的版本。
    """
    latest = _latest_for(output.student_id, output.content_json.get("program_id"))
    if latest and latest.id != output.id:
        role = {"teacher": "導師", "student": "學生", "ai": "AI"}.get(latest.content_json.get("editor_role"), "其他人")
        raise StaleVersion(f"你的修改還沒存：這段期間{role}已經存了第 {version_of(latest)} 版。"
                           "下面是最新版，你剛才打的字列在最上方，請對照後再存一次。")
    content = dict(output.content_json)
    paragraphs = [dict(p) for p in content["paragraphs"]]
    for i, (paragraph, text) in enumerate(zip(paragraphs, texts)):
        paragraph["text"] = text.strip()
        if titles and i < len(titles) and titles[i]:
            paragraph["title"] = str(titles[i]).strip()
    if len(texts) > len(paragraphs):
        for i in range(len(paragraphs), len(texts)):
            t = (str(titles[i]).strip() if titles and i < len(titles) and titles[i] else f"第 {i + 1} 段")
            paragraphs.append({"title": t, "text": texts[i].strip(), "sources": []})
    if images is not None:  # 只有學生儲存時傳入；導師修改文字不動學生貼的圖
        for paragraph, ids in zip(paragraphs, images):
            if ids:
                paragraph["images"] = list(ids)
            else:
                paragraph.pop("images", None)
    if comments is not None:
        for paragraph, comment in zip(paragraphs, comments):
            comment = comment.strip()[:500]
            if comment:
                paragraph["teacher_comment"] = comment
            else:
                paragraph.pop("teacher_comment", None)
    content.update({
        "paragraphs": paragraphs,
        "edited": True,
        "version": _next_version(output.student_id, content["program_id"]),
        "editor_id": editor.id,
        "editor_role": editor.role,
        "based_on": output.id,
    })
    _backup_existing(output.student_id, content)
    new_version = LearningProfileOutput(
        student_id=output.student_id,
        output_type=OUTPUT_TYPE,
        content_json=content,
        source_snapshot_json={**(output.source_snapshot_json or {}),
                              "saved_at": datetime.now(timezone.utc).isoformat()},
    )
    db.session.add(new_version)
    db.session.commit()
    autobiography_backup.schedule_after_save(current_app._get_current_object(), new_version)
    return new_version


def save_imported(output, paragraphs, editor, origin):
    """從外部編輯工具（例如 Google 文件）取回的段落存成**新的一版**，回傳新版本；舊版不動。

    paragraphs：已檢查過來源的段落（title、text、sources，可能有 unknown_sources）。
    導師意見依段落順序沿用上一版。
    """
    content = dict(output.content_json)
    old = content.get("paragraphs", [])
    new_paragraphs = []
    for index, paragraph in enumerate(paragraphs):
        item = dict(paragraph)
        if index < len(old) and old[index].get("teacher_comment"):
            item["teacher_comment"] = old[index]["teacher_comment"]
        new_paragraphs.append(item)
    content.update({
        "paragraphs": new_paragraphs,
        "edited": True,
        "version": _next_version(output.student_id, content["program_id"]),
        "editor_id": editor.id,
        "editor_role": editor.role,
        "based_on": output.id,
        "origin": origin,
    })
    _backup_existing(output.student_id, content)
    new_version = LearningProfileOutput(
        student_id=output.student_id,
        output_type=OUTPUT_TYPE,
        content_json=content,
        source_snapshot_json={**(output.source_snapshot_json or {}),
                              "saved_at": datetime.now(timezone.utc).isoformat(), "origin": origin},
    )
    db.session.add(new_version)
    db.session.commit()
    autobiography_backup.schedule_after_save(current_app._get_current_object(), new_version)
    return new_version


def _diff_html(old, new):
    """逐字比較，刪掉的用 <del>、新增的用 <ins>。"""
    parts = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag == "equal":
            parts.append(escape(new[j1:j2]))
            continue
        if i2 > i1:
            parts.append(Markup("<del>%s</del>") % old[i1:i2])
        if j2 > j1:
            parts.append(Markup("<ins>%s</ins>") % new[j1:j2])
    return Markup("").join(parts)


def version_diff(output, previous):
    """這一版和上一版逐段比較。沒有上一版時，每段都當作沒變動。"""
    old_paragraphs = previous.content_json.get("paragraphs", []) if previous else []
    result = []
    for index, paragraph in enumerate(output.content_json.get("paragraphs", [])):
        old_text = old_paragraphs[index]["text"] if index < len(old_paragraphs) else ""
        changed = previous is not None and old_text != paragraph["text"]
        result.append({
            "title": paragraph.get("title", ""),
            "changed": changed,
            "html": _diff_html(old_text, paragraph["text"]) if changed else escape(paragraph["text"]),
            "comment": paragraph.get("teacher_comment"),
        })
    return result
