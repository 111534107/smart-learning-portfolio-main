"""畢業門檻工作台的呈現資料（2026-11-16）。

只把 graduation_check_service 已經算好的結果整理成工作台要的形狀：
哪些課已算進必修／選修、科目表上還沒修過的必修、對不到科目表待人工確認的課、
還在辨識或等確認的檔案，以及每個缺口的「下一步」。
不改任何學分或證照的計算規則；學分數字一律沿用 credit_status()。
"""

from app.models import SourceDocument
from app.services import graduation_check_service as check
from app.services.eligibility_service import normalize_course_name

# 科目表上「一定要修」的類別。進階分類通識、通識選修是從清單裡挑幾門，不能整份列成「還缺」。
MUST_TAKE_CATEGORIES = ("校定必修", "院定必修", "一般科目必修", "專業必修")
ITEM_NAMES = {"certificates": "專業證照", "required_credits": "必修學分",
              "elective_credits": "選修學分", "total_credits": "總學分"}


def _pending_documents(student):
    rows = (SourceDocument.query
            .filter(SourceDocument.owner_id == student.id,
                    SourceDocument.status.in_(check.PENDING_DOCUMENT_STATUSES))
            .order_by(SourceDocument.id).all())
    return {"transcript": [row for row in rows if row.document_type == "transcript"],
            "credential": [row for row in rows if row.document_type == "credential"]}


def course_lists(student, curriculum):
    """已算進必修、已算進選修、還沒修過的必修、待人工確認的課。科目表沒核對過的屆別回傳 None。"""
    profile = student.student_profile
    year = profile.admission_year if profile else None
    table = curriculum.get(year)
    if not table or check.credit_rule(year) is None:
        return None
    courses, _ = check._confirmed_courses(student)
    required, elective, unmatched, failed = [], [], [], []
    passed_keys = set()
    for course in courses:
        key = normalize_course_name(course.course_name)
        entry = table.get(key)
        if course.acquisition_status != "passed":
            if course.acquisition_status == "not_passed":
                failed.append({"name": course.course_name, "score": course.score, "key": key})
            continue
        passed_keys.add(key)
        row = {"name": course.course_name, "credits": course.credits or 0,
               "term": _term_text(course, year)}
        if entry is None:
            unmatched.append(row)
        elif entry["category"] in check.REQUIRED_CATEGORIES:
            required.append(dict(row, category=entry["category"]))
        elif entry["category"] in check.ELECTIVE_CATEGORIES:
            elective.append(dict(row, category=entry["category"]))
    seen, not_taken = set(), []
    for key, entry in table.items():
        if entry["category"] in MUST_TAKE_CATEGORIES and key not in passed_keys and key not in seen:
            seen.add(key)
            not_taken.append({"name": entry["name"], "category": entry["category"]})
    still_failed = [row for row in failed if row["key"] not in passed_keys]
    return {"required": required, "elective": elective, "unmatched": unmatched,
            "not_taken": not_taken, "failed": still_failed}


def _term_text(course, admission_year):
    year = course.year_for_placement
    if year is not None and year > 5 and admission_year:
        year = year - admission_year + 1
    semester = check.normalize_semester(course.semester)
    if year is None or not semester:
        return ""
    return f"專{year}{semester}"


def _pct(have, need):
    if not need:
        return 100
    return round(min(have / need * 100, 100), 1)


def meters(result):
    """頂端四條量表：證照、必修、選修、總學分（數字沿用 evaluate()）。"""
    cert, credits = result["certificates"], result["credits"]
    rows = [{"item": "certificates", "have": cert["counted_count"], "need": cert["needed"],
             "short": cert["missing"], "unit": "張", "pct": _pct(cert["counted_count"], cert["needed"])}]
    for item, key in (("required_credits", "required"), ("elective_credits", "elective"),
                      ("total_credits", "total")):
        if credits.get("earned") is None:
            rows.append({"item": item, "have": None, "need": None, "short": None, "unit": "學分", "pct": 0})
        else:
            have, need = credits["earned"][key], credits["needed"][key]
            rows.append({"item": item, "have": have, "need": need, "short": credits["gaps"][key],
                         "unit": "學分", "pct": _pct(have, need)})
    for row in rows:
        row["name"] = ITEM_NAMES[row["item"]]
    return rows


def next_steps(assessment, result, lists, pending, warnings):
    """把所有缺口整理成一張待辦清單；每一項都有要去的頁面（kind 決定按鈕連到哪裡）。"""
    steps = []
    items = assessment["items"]
    if pending["transcript"]:
        steps.append({"kind": "files", "item": "required_credits",
                      "text": f"有 {len(pending['transcript'])} 份成績單還在辨識或等你確認",
                      "action": "去確認成績單"})
    if pending["credential"]:
        steps.append({"kind": "files", "item": "certificates",
                      "text": f"有 {len(pending['credential'])} 份證照還在辨識或等你確認",
                      "action": "去確認證照"})
    missing_terms = []
    for data in items.values():
        for term in data.get("missing_terms") or []:
            if term not in missing_terms:
                missing_terms.append(term)
    if missing_terms:
        admission = assessment["stage"]["ended_terms"][0][0] if assessment["stage"]["ended_terms"] else None
        labels = "、".join(f"專{y - admission + 1}{s}" if admission else f"{y}{s}" for y, s in missing_terms)
        steps.append({"kind": "transcript", "item": "required_credits",
                      "text": f"這些學期還沒有已確認的成績：{labels}", "action": "上傳成績單"})
    cert = items["certificates"]
    if cert["result"] in ("gap", "progress") and cert["amount"]:
        steps.append({"kind": "credential", "item": "certificates",
                      "text": f"還差 {cert['amount']} 張可採計的證照", "action": "上傳證照"})
    credit_gaps = [(name, items[name]["amount"]) for name in ("required_credits", "elective_credits", "total_credits")
                   if items[name]["result"] == "gap" and items[name]["amount"]]
    if credit_gaps:
        text = "、".join(f"{ITEM_NAMES[name]}還差 {amount} 學分" for name, amount in credit_gaps)
        steps.append({"kind": "ask", "item": credit_gaps[0][0],
                      "text": f"{text}，已列為缺口", "action": "問導師補修方式",
                      "prefill": f"畢業門檻顯示{text}，想請問要怎麼補修。"})
    if lists and lists["failed"]:
        names = "、".join(row["name"] for row in lists["failed"][:4])
        more = f"等 {len(lists['failed'])} 門" if len(lists["failed"]) > 4 else ""
        steps.append({"kind": "ask", "item": "required_credits",
                      "text": f"不及格還沒補：{names}{more}，要排重修",
                      "action": "問導師怎麼重修",
                      "prefill": f"我有這些課還沒補及格：{'、'.join(r['name'] for r in lists['failed'])}，想請問重修怎麼安排。"})
    if lists and lists["unmatched"]:
        names = "、".join(row["name"] for row in lists["unmatched"])
        steps.append({"kind": "ask", "item": "total_credits",
                      "text": f"{len(lists['unmatched'])} 門課對不到科目表，學分還沒算進去",
                      "action": "請科辦確認",
                      "prefill": f"這些課在畢業門檻對不到科目表，請幫我確認學分怎麼算：{names}。"})
    if any(data["result"] == "transfer_pending" for data in items.values()):
        steps.append({"kind": "ask", "item": "total_credits", "text": "有抵免還沒完成，學分先不算",
                      "action": "問抵免進度", "prefill": "想請問我的抵免目前處理到哪裡。"})
    high = [term for term in (warnings.get("terms") or []) if term["level"] == "high"]
    if high:
        steps.append({"kind": "ask", "item": "required_credits",
                      "text": f"{'、'.join(t['label'] for t in high)} 不及格學分達一半",
                      "action": "找導師討論", "prefill": f"{high[0]['label']} 不及格比較多，想找導師討論接下來怎麼補。"})
    return steps


def build(student, assessment, result, curriculum, warnings):
    lists = course_lists(student, curriculum)
    pending = _pending_documents(student)
    return {"meters": meters(result), "lists": lists, "pending": pending,
            "steps": next_steps(assessment, result, lists, pending, warnings)}
