"""畢業門檻檢核（只提醒，不自動判定畢業）。

依據（來源見 app/content/knowledge/graduation-requirements.md）：
- 證照：資訊管理科學生畢業門檻實施要點（113.03.27 修訂，109 學年度（含）以後入學適用）。
  至少 3 張專業證照；中文或英文輸入證照至多採計 1 張。
- 學分：各屆五專修業科目表的「總畢業學分數需修滿 220 學分（必修 181 分，選修 39 學分）」。
  目前只核對過 111、113 學年度入學；其他屆別標「待確認」，不硬判。

只用學生已確認、而且及格的成績與證照；草稿與未確認的資料不算。
"""

from app.models import CredentialRecord, LearningCourseRecord
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
