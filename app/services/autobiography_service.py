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

from app.extensions import db
from app.models import CredentialRecord, LearningCourseRecord, LearningProfileOutput, Portfolio
from app.services.gap_service import ALL_LABELS
from app.services.gemini_client import AIUnavailable, ai_ready, generate_json
from app.services.journey_service import CATEGORY_LABELS

OUTPUT_TYPE = "autobiography_ai"

# 學生按過「確認」的經歷；submitted 是舊的專題送審流程，也代表學生確認過
CONFIRMED_PORTFOLIO_STATUSES = ("confirmed", "submitted")

# 問題（key, 題目, 提示）。要改題目只要改這裡。
QUESTIONS = [
    ("motivation", "為什麼想繼續讀資管，或特別想讀這個系？", "例如：哪一門課、哪一次經驗讓你確定方向"),
    ("proud", "五年中最有成就感的一件事是什麼？你負責做了什麼？", "寫你自己做的部分，越具體越好"),
    ("challenge", "遇過最大的困難是什麼？你怎麼解決？", "可以是課業、專題或團隊合作"),
    ("future", "進二技後想學什麼？之後想做什麼工作？", "和這個系的課程或特色連起來會更好"),
]

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
    """
    lines = []
    for course in (LearningCourseRecord.query.filter_by(student_id=student.id, confirmation_status="confirmed")
                   .order_by(LearningCourseRecord.id)):
        score = f"{course.score} 分" if course.score is not None else (course.status_mark or "")
        lines.append({
            "text": f"成績：{course.course_name}（{course.year_for_placement or '?'} 年級，{score}）",
            "evidence_id": f"course:{course.id}",
            "evidence_type": "course",
        })
    for credential in (CredentialRecord.query.filter_by(student_id=student.id, confirmation_status="confirmed")
                       .order_by(CredentialRecord.id)):
        lines.append({
            "text": f"證照：{credential.credential_name}" + (f"（{credential.level}）" if credential.level else ""),
            "evidence_id": f"credential:{credential.id}",
            "evidence_type": "credential",
        })
    for record in (Portfolio.query.filter_by(student_id=student.id)
                   .filter(Portfolio.status.in_(CONFIRMED_PORTFOLIO_STATUSES)).order_by(Portfolio.id)):
        label = CATEGORY_LABELS.get(record.category)
        if label:
            source = "" if record.source == "student" else f"（來源：{record.source_label}）"
            lines.append({
                "text": f"{label}：{record.title}" + (f"—{record.description}" if record.description else "") + source,
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


def build_evidence_package(student, program):
    """為指定校系整理學生已確認、可追溯來源的最小證據包。"""
    facts = build_facts(student, program)
    return {"version": 1, "program_id": program.id, "items": facts["items"]}


def _prompt(student, program, facts, answers):
    fact_lines = "\n".join(f"{fact['id']}. {fact['text']}" for fact in facts["items"]) or "（沒有資料）"
    weight_lines = "\n".join(f"- {w['name']}：{w['weight']}%（{w['categories']}）" for w in facts["weights"])
    answer_lines = "\n".join(f"- {question}\n  回答：{answers.get(key) or '（未回答）'}" for key, question, _ in QUESTIONS)
    return f"""你是五專資管科學生的自傳寫作助手。請幫學生寫申請「{program.school_name} {program.department_name}」的自傳草稿。

規則：
1. 使用繁體中文、第一人稱，語氣真誠自然，像高職／五專學生寫的，不要浮誇或使用空泛形容詞。
2. 只能使用下面的「學生資料」和「學生回答」，不得編造任何獎項、分數、證照、職位或經歷。資料不足就少寫，不要補。
3. 學生沒回答的題目，那一段的 text 只寫「（請補上：題目內容）」，sources 給空陣列；不要從其他資料推想他的感受、心得或經過。
4. 依校系加權，把加權高的項目相關經驗寫得比較完整。
5. 分成 4 段：學習動機、學習歷程與具體經驗、困難與成長、未來規劃。總長約 600～900 字。
6. 每段的 sources 列出這段用到的學生資料編號（例如 F2）；只用到學生回答就給空陣列。

學生資料（只能引用這些）：
{fact_lines}

目標校系的評分項目與加權：
{weight_lines}

學生回答：
{answer_lines}
"""


def _demo_paragraphs(facts, answers):
    """沒有接上 AI 時的示範草稿：只把學生的回答和資料排好，明白標示不是 AI 寫的。"""
    experience = [f for f in facts["items"] if f["text"].split("：", 1)[0] in ("競賽", "活動", "幹部經歷")][:3]
    titles = "、".join(f["text"].split("：", 1)[1].split("—")[0] for f in experience)
    proud = answers.get("proud") or "（請補上你最有成就感的經驗）"
    return [
        {"title": "學習動機", "text": answers.get("motivation") or "（請補上你想讀這個系的原因）", "sources": []},
        {"title": "學習歷程與具體經驗", "text": proud + (f"另外，我也參與了{titles}。" if titles else ""),
         "sources": [f["id"] for f in experience]},
        {"title": "困難與成長", "text": answers.get("challenge") or "（請補上你遇過的困難與解決方式）", "sources": []},
        {"title": "未來規劃", "text": answers.get("future") or "（請補上進二技後的學習計畫）", "sources": []},
    ]


def generate_draft(student, program, answers, generate=None, api_key=None):
    """產生並儲存草稿。generate 是呼叫 AI 的函式（測試時可以換成假的）。

    api_key：學生自己的 Gemini 金鑰，只在這次呼叫用，**不會**寫進資料庫或任何紀錄。
    """
    facts = build_facts(student, program)
    evidence_package = {"version": 1, "program_id": program.id, "items": facts["items"]}
    previous = latest_draft(student, program)
    known = {fact["id"] for fact in facts["items"]}
    answers = {key: (answers.get(key) or "").strip()[:1000] for key, _, _ in QUESTIONS}
    if generate is None and not api_key and not ai_ready():
        paragraphs, provider = _demo_paragraphs(facts, answers), "demo"
    else:
        prompt = _prompt(student, program, facts, answers)
        result = generate(prompt, PARAGRAPH_SCHEMA) if generate else generate_json(prompt, PARAGRAPH_SCHEMA, api_key=api_key)
        paragraphs = [{
            "title": str(p.get("title", "")).strip()[:30],
            "text": str(p.get("text", "")).strip(),
            "sources": [s for s in p.get("sources", []) if s in known],
        } for p in result.get("paragraphs", []) if str(p.get("text", "")).strip()]
        if not paragraphs:
            raise AIUnavailable("AI 沒有產生內容，請再試一次。")
        provider = "gemini"
    output = LearningProfileOutput(
        student_id=student.id,
        output_type=OUTPUT_TYPE,
        content_json={
            "program_id": program.id,
            "answers": answers,
            "paragraphs": paragraphs,
            "facts": facts["items"],
            "provider": provider,
            "edited": False,
            "version": _next_version(student.id, program.id),
            "editor_id": student.id,
            "editor_role": "ai",
            "based_on": previous.id if previous else None,
        },
    source_snapshot_json={"program_id": program.id, "fact_count": len(facts["items"]),
                          "evidence_package": evidence_package,
                              "generated_at": datetime.now(timezone.utc).isoformat()},
    )
    db.session.add(output)
    db.session.commit()
    return output


def versions(student, program):
    """同一位學生、同一個校系的所有自傳版本（舊到新）。"""
    outputs = (LearningProfileOutput.query.filter_by(student_id=student.id, output_type=OUTPUT_TYPE)
               .order_by(LearningProfileOutput.id).all())
    return [o for o in outputs if o.content_json.get("program_id") == program.id]


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


def save_edits(output, texts, editor, comments=None):
    """逐段修改後儲存成**新的一版**，回傳新版本；舊版不動。

    texts：每一段的新文字（順序和原本一樣）。
    editor：按儲存的人（學生本人或導師）。
    comments：導師的段落意見；None 表示沿用上一版的意見（學生儲存時）。
    要存的不是最新版時丟 StaleVersion，避免舊頁面蓋掉別人剛存的版本。
    """
    latest = _latest_for(output.student_id, output.content_json.get("program_id"))
    if latest and latest.id != output.id:
        role = {"teacher": "導師", "student": "學生", "ai": "AI"}.get(latest.content_json.get("editor_role"), "其他人")
        raise StaleVersion(f"你的修改還沒存：這段期間{role}已經存了第 {version_of(latest)} 版。"
                           "下面是最新版，你剛才打的字列在最上方，請對照後再存一次。")
    content = dict(output.content_json)
    paragraphs = [dict(p) for p in content["paragraphs"]]
    for paragraph, text in zip(paragraphs, texts):
        paragraph["text"] = text.strip()
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
    new_version = LearningProfileOutput(
        student_id=output.student_id,
        output_type=OUTPUT_TYPE,
        content_json=content,
        source_snapshot_json={**(output.source_snapshot_json or {}),
                              "saved_at": datetime.now(timezone.utc).isoformat()},
    )
    db.session.add(new_version)
    db.session.commit()
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
    new_version = LearningProfileOutput(
        student_id=output.student_id,
        output_type=OUTPUT_TYPE,
        content_json=content,
        source_snapshot_json={**(output.source_snapshot_json or {}),
                              "saved_at": datetime.now(timezone.utc).isoformat(), "origin": origin},
    )
    db.session.add(new_version)
    db.session.commit()
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
