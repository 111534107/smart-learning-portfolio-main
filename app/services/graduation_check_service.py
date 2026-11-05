"""畢業門檻檢核（只提醒，不自動判定畢業）。

依據（來源見 app/content/knowledge/graduation-requirements.md）：
- 證照：資訊管理科學生畢業門檻實施要點（113.03.27 修訂，109 學年度（含）以後入學適用）。
  至少 3 張專業證照；中文或英文輸入證照至多採計 1 張。
- 學分：各屆五專修業科目表的「總畢業學分數需修滿 220 學分（必修 181 分，選修 39 學分）」。
  目前只核對過 111、113 學年度入學；其他屆別標「待確認」，不硬判。

只用學生已確認、而且及格的成績與證照；草稿與未確認的資料不算。
"""

from datetime import date

from app.models import (CredentialRecord, LearningCourseRecord, SourceDocument, SystemSetting,
                        TransferCreditRecord)
from app.services.eligibility_service import load_curriculum, normalize_course_name

CERTIFICATE_MINIMUM = 3
INPUT_CERTIFICATE_LIMIT = 1
NEEDS_CHECK = "needs_check"

# 實施要點第五點：丙級、乙級可採計的證照（名稱用字串比對，先去掉空白與括號）。
PROFICIENCY_CERTIFICATES = {
    "丙級": ("電腦軟體應用", "網頁設計", "電腦硬體裝修", "電腦軟體設計", "會計事務-資訊項", "會計事務-人工項"),
    "乙級": ("軟體應用", "軟體設計", "會計事務"),
}
INPUT_CERTIFICATE_WORDS = ("中文輸入", "英文輸入")

# 各屆總學分（總學分, 必修, 選修）。只列已核對過修業科目表的屆別。
CREDIT_RULES = {
    111: {"total": 220, "required": 181, "elective": 39, "source": "111 學年度入學五專修業科目表"},
    113: {"total": 220, "required": 181, "elective": 39, "source": "113 學年度入學五專修業科目表"},
}

# 修業科目表的「科目類別」歸為必修或選修。校外實習、微學分歸入選修，這是依科目表排列的判斷，待科辦確認。
REQUIRED_CATEGORIES = ("校定必修", "院定必修", "一般科目必修", "進階分類通識", "專業必修")
ELECTIVE_CATEGORIES = ("專業選修", "校外實習", "微學分")


def _squash(text):
    return (text or "").replace(" ", "").replace("　", "").replace("－", "-").replace("(", "（").replace(")", "）")


def classify_credential(record):
    """回傳 "輸入"、"丙級"、"乙級" 或 None（不在實施要點採計範圍）。"""
    name = _squash(record.credential_name)
    level = _squash(record.level)
    if any(word in name for word in INPUT_CERTIFICATE_WORDS):
        return "輸入"
    if "丙級" in level or "丙級" in name:
        levels = ("丙級",)
    elif "乙級" in level or "乙級" in name:
        levels = ("乙級",)
    else:
        return None
    for lvl in levels:
        if any(item in name for item in PROFICIENCY_CERTIFICATES[lvl]):
            return lvl
    return None


def certificate_status(student):
    records = (CredentialRecord.query
               .filter_by(student_id=student.id, confirmation_status="confirmed")
               .order_by(CredentialRecord.id).all())
    counted, unmatched, input_count = [], [], 0
    for record in records:
        kind = classify_credential(record)
        if kind is None:
            unmatched.append(record.credential_name)
        elif kind == "輸入":
            input_count += 1
            if input_count <= INPUT_CERTIFICATE_LIMIT:
                counted.append(record.credential_name)
        else:
            counted.append(record.credential_name)
    notes = []
    if input_count > INPUT_CERTIFICATE_LIMIT:
        notes.append(f"中（英）文輸入證照至多採計 {INPUT_CERTIFICATE_LIMIT} 張，其餘不計入。")
    if unmatched:
        notes.append(f"這些證照不在實施要點採計範圍，請科辦確認：{'、'.join(unmatched)}。")
    missing = max(CERTIFICATE_MINIMUM - len(counted), 0)
    status = "ok" if missing == 0 else "short"
    return {"status": status, "counted": counted, "counted_count": len(counted),
            "needed": CERTIFICATE_MINIMUM, "missing": missing, "notes": notes}


def credit_status(student, curriculum=None):
    profile = student.student_profile
    year = profile.admission_year if profile else None
    rule = CREDIT_RULES.get(year)
    curriculum = load_curriculum() if curriculum is None else curriculum
    table = curriculum.get(year)
    if rule is None or table is None:
        return {"status": NEEDS_CHECK, "admission_year": year, "earned": None,
                "reason": f"尚未核對 {year} 學年度入學的修業科目表，總學分與必修、選修學分待確認。"}

    courses = (LearningCourseRecord.query
               .filter_by(student_id=student.id, confirmation_status="confirmed")
               .order_by(LearningCourseRecord.id).all())
    required = elective = 0
    unmatched = []
    for course in courses:
        if course.acquisition_status != "passed":
            continue
        entry = table.get(normalize_course_name(course.course_name))
        credits = course.credits or 0
        if entry is None:
            unmatched.append(course.course_name)
        elif entry["category"] in REQUIRED_CATEGORIES:
            required += credits
        elif entry["category"] in ELECTIVE_CATEGORIES:
            elective += credits
    total = required + elective
    short_required = max(rule["required"] - required, 0)
    short_elective = max(rule["elective"] - elective, 0)
    short_total = max(rule["total"] - total, 0)
    earned = {"required": required, "elective": elective, "total": total}
    gaps = {"required": short_required, "elective": short_elective, "total": short_total}
    if unmatched:
        status = NEEDS_CHECK
        reason = f"有 {len(unmatched)} 門課對不到科目表，請科辦確認：{'、'.join(unmatched)}。"
    elif short_required == 0 and short_elective == 0:
        status, reason = "ok", ""
    else:
        status, reason = "short", "尚未達到科目表規定的學分。"
    return {"status": status, "admission_year": year, "source": rule["source"],
            "earned": earned, "needed": {"required": rule["required"], "elective": rule["elective"],
                                         "total": rule["total"]},
            "gaps": gaps, "unmatched": unmatched, "reason": reason}


def evaluate(student, curriculum=None):
    """畢業門檻提醒：證照與學分兩部分；任一部分待確認或不足，整體就不是通過。"""
    certificates = certificate_status(student)
    credits = credit_status(student, curriculum=curriculum)
    if credits["status"] == NEEDS_CHECK:
        overall = NEEDS_CHECK
    elif certificates["status"] == "ok" and credits["status"] == "ok":
        overall = "ok"
    else:
        overall = "short"
    return {"status": overall, "certificates": certificates, "credits": credits,
            "note": "僅供提醒，正式畢業資格以學校學生畢業門檻審核委員會的審核結果為準。"}


# ---- 判斷結果：階段、資料是否足夠、規則（spec 4.2、5.2）----
MAX_CREDITS_PER_TERM_SENIOR = 28  # 專五每學期最高修習學分
TOTAL_TERMS = 10
TODAY_SETTING_KEY = "graduation_check_today"
ITEMS = ("certificates", "required_credits", "elective_credits", "total_credits")
RESULTS = ("met", "gap", "insufficient_data", "transfer_pending", "rule_unverified", "progress")
CERTIFICATE_BASIS = "資訊管理科學生畢業門檻實施要點（113.03.27 修訂）第五點"
_CREDIT_ITEM_KEYS = {"required_credits": "required", "elective_credits": "elective", "total_credits": "total"}


def academic_term(today):
    """回傳（民國學年度, "上"|"下"）。8/1 起是新學年上學期，2/1 起是下學期。"""
    if today.month >= 8:
        return today.year - 1911, "上"
    return today.year - 1912, "上" if today.month == 1 else "下"


def check_today():
    """檢核用的「今天」：系統設定有 graduation_check_today（ISO 日期）就用它，否則用今天。"""
    setting = SystemSetting.query.filter_by(key=TODAY_SETTING_KEY).first()
    if setting and setting.value:
        try:
            return date.fromisoformat(setting.value.strip())
        except ValueError:
            pass
    return date.today()


def student_stage(admission_year, today):
    """學生目前的階段。formal 為專四下（含）以後；ended_terms 是入學後、目前學期之前的所有學期。"""
    year, semester = academic_term(today)
    if admission_year is None or year < admission_year:
        return {"grade": None, "semester": semester, "formal": False, "ended_terms": [],
                "remaining_terms": TOTAL_TERMS}
    index = (year - admission_year) * 2 + (0 if semester == "上" else 1)
    ended = [(admission_year + i // 2, "上" if i % 2 == 0 else "下") for i in range(index)]
    grade = year - admission_year + 1
    formal = grade > 4 or (grade == 4 and semester == "下")
    return {"grade": grade, "semester": semester, "formal": formal, "ended_terms": ended,
            "remaining_terms": max(TOTAL_TERMS - len(ended), 0)}


def _item(result, amount=None, unit="學分", detail="", basis="", failed_required=None, missing_terms=None):
    return {"result": result, "amount": amount, "unit": unit, "detail": detail, "basis": basis,
            "failed_required": failed_required or [], "missing_terms": missing_terms or []}


def _certificate_item(student, stage):
    unconfirmed = (SourceDocument.query
                   .filter(SourceDocument.owner_id == student.id, SourceDocument.document_type == "credential",
                           SourceDocument.status != "confirmed").first())
    if unconfirmed is not None:
        return _item("insufficient_data", unit="張", basis=CERTIFICATE_BASIS,
                     detail="有證照文件尚未確認，確認後才能判斷。")
    status = certificate_status(student)
    if status["missing"] == 0:
        return _item("met", unit="張", basis=CERTIFICATE_BASIS,
                     detail=f"已採計 {status['counted_count']} 張。")
    result = "gap" if stage["formal"] else "progress"
    return _item(result, status["missing"], "張", f"已採計 {status['counted_count']} 張，還差 {status['missing']} 張。",
                 CERTIFICATE_BASIS)


def _missing_terms(student, admission_year, ended_terms):
    """已結束、但沒有已確認課程紀錄的學期；school_year 可能存民國學年度，也可能存年級。"""
    courses = (LearningCourseRecord.query
               .filter_by(student_id=student.id, confirmation_status="confirmed").all())
    have = {(course.school_year, course.semester) for course in courses}
    return [(year, semester) for year, semester in ended_terms
            if (year, semester) not in have and (year - admission_year + 1, semester) not in have]


def _failed_required(student, table):
    """必修類別、已確認不及格，而且沒有同課名已確認及格的課程名稱。"""
    courses = (LearningCourseRecord.query
               .filter_by(student_id=student.id, confirmation_status="confirmed")
               .order_by(LearningCourseRecord.id).all())
    passed = {normalize_course_name(c.course_name) for c in courses if c.acquisition_status == "passed"}
    failed = []
    for course in courses:
        key = normalize_course_name(course.course_name)
        entry = table.get(key)
        if (course.acquisition_status == "not_passed" and entry and entry["category"] in REQUIRED_CATEGORIES
                and key not in passed and course.course_name not in failed):
            failed.append(course.course_name)
    return failed


def _credit_items(student, stage, curriculum):
    profile = student.student_profile
    year = profile.admission_year if profile else None
    credits = credit_status(student, curriculum=curriculum)
    if credits["earned"] is None:
        return {name: _item("rule_unverified", detail=credits["reason"]) for name in _CREDIT_ITEM_KEYS}
    basis = credits["source"]
    missing = _missing_terms(student, year, stage["ended_terms"])
    if missing:
        text = "、".join(f"{y}{s}" for y, s in missing)
        return {name: _item("insufficient_data", basis=basis, missing_terms=missing,
                            detail=f"這些學期還沒有已確認的成績單：{text}。")
                for name in _CREDIT_ITEM_KEYS}
    pending = TransferCreditRecord.query.filter(TransferCreditRecord.student_id == student.id,
                                                TransferCreditRecord.status != "completed").first()
    capacity = stage["remaining_terms"] * MAX_CREDITS_PER_TERM_SENIOR
    failed = _failed_required(student, curriculum[year]) if stage["formal"] else []
    items = {}
    for name, key in _CREDIT_ITEM_KEYS.items():
        short = credits["gaps"][key]
        detail = f"已修 {credits['earned'][key]} 學分，規定 {credits['needed'][key]} 學分。"
        if pending is not None:
            items[name] = _item("transfer_pending", short, detail=detail + "抵免尚未完成。", basis=basis)
        elif short == 0:
            items[name] = _item("met", detail=detail, basis=basis)
        elif not stage["formal"]:
            items[name] = _item("progress", short, detail=detail, basis=basis)
        elif (name == "required_credits" and failed) or short > capacity:
            items[name] = _item("gap", short, detail=detail, basis=basis,
                                failed_required=failed if name == "required_credits" else [])
        else:
            items[name] = _item("progress", short, detail=detail, basis=basis)
    return items


def assess(student, today=None, curriculum=None):
    """四個項目的判斷結果。load_curriculum() 只讀一次；既有 evaluate 不受影響。"""
    today = check_today() if today is None else today
    curriculum = load_curriculum() if curriculum is None else curriculum
    profile = student.student_profile
    stage = student_stage(profile.admission_year if profile else None, today)
    items = {"certificates": _certificate_item(student, stage)}
    items.update(_credit_items(student, stage, curriculum))
    return {"stage": stage, "items": items}


# ---- 補救方式文字（只引用實施要點，不替學科辦決定）----
CERTIFICATE_REMEDY = (
    f"依據：{CERTIFICATE_BASIS}。適用 109 學年度（含）以後入學的日間部五年制學生。"
    "未能通過證照門檻者，可擇一補救："
    "（1）修畢額外加選六學分專業選修；"
    "（2）修畢且取得微學分學程或學分學程並加選三學分專業選修；"
    "（3）採計輔導課程及服務時數：缺三張須報考任三張證照、完成 12 小時輔導課程與 24 小時資訊技術實作，"
    "缺二張須報考任二張並完成 24 小時資訊技術實作，缺一張須報考任一張並完成 12 小時資訊技術實作"
    "（除打字證照外，各類證照須報考並到考但未通過者適用，需檢附未通過紀錄文件）；"
    "（4）獲得校內外資訊相關競賽前三名；"
    "（5）取得國立大專院校入學資格；"
    "（6）其他特殊狀況，經科務會議同意者。")
CREDIT_REMEDY = "請洽科辦確認補修方式。"
REMEDY_TEXT = {
    "certificates": CERTIFICATE_REMEDY,
    "required_credits": CREDIT_REMEDY,
    "elective_credits": CREDIT_REMEDY,
    "total_credits": CREDIT_REMEDY,
}
RESULT_LABELS = {
    "met": ("已達成", "tag--ok"), "gap": ("有缺口", "tag--danger"),
    "insufficient_data": ("資料不足", "tag--warn"), "transfer_pending": ("抵免待核對", "tag--warn"),
    "rule_unverified": ("待人工確認", "tag--warn"), "progress": ("修課中", "tag--warn"),
}
DISCLAIMER = "僅供提醒，正式畢業資格以學校學生畢業門檻審核委員會的審核結果為準。"
