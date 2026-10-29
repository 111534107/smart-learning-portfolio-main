"""學生端的使用限制：年級（看得到但不能用）與目標校系上限。規格第 10.4、10.5 節。

- 沒有入學學年度就不知道年級：擋下並請學生先補，不猜年級。
- 不能填寫比目前年級更高的成績或經歷。
- 送審與送審相關的 AI（自傳）要到 MIN_REVIEW_GRADE 年級才能用；更低年級只能看。
- 目標校系：一到四年級不限（找方向用）；五年級準備備審資料時同時最多 TARGET_LIMIT 所（規格 10.7）。
  只算最新學年度的校系；舊學年度的另外列出，可以刪除。
"""

from datetime import date

from flask import current_app

from app.models import StudentTarget
from app.services.admission_service import published_programs
from app.services.journey_service import GRADE_LABELS, academic_year_of, current_grade, grade_for

# 入學學年度由系統管理者匯入（主持人 2026-10-10 決定），學生不能自己填
MISSING_ADMISSION_YEAR = "系統還沒有你的入學學年度，沒辦法判斷你現在幾年級。請聯絡系統管理者補上入學學年度。"


def admission_year_of(student):
    profile = student.student_profile
    return profile.admission_year if profile else None


def grade_of(student, today=None):
    return current_grade(admission_year_of(student), today)


def grade_block_reason(student, today=None):
    """沒有入學學年度時回傳提示文字；可以判斷年級時回傳 None。"""
    return MISSING_ADMISSION_YEAR if grade_of(student, today) is None else None


def review_block_reason(student, today=None):
    """送審、產生自傳前的檢查。回傳提示文字，或 None（可以使用）。"""
    reason = grade_block_reason(student, today)
    if reason:
        return reason
    minimum = current_app.config.get("MIN_REVIEW_GRADE", 2)
    grade = grade_of(student, today)
    if grade < minimum:
        return (f"你現在是{GRADE_LABELS[grade]}，可以先看目標校系的要求和還缺什麼；"
                f"送導師確認和用 AI 寫自傳，要到{GRADE_LABELS[minimum]}才能使用。")
    return None


def autobiography_block_reason(student, today=None):
    """生成自傳前的檢查：年級到 AUTOBIOGRAPHY_OPEN_GRADE 才開放，也要過送審的檢查。回傳提示文字，或 None。"""
    reason = grade_block_reason(student, today)
    if reason:
        return reason
    opening = current_app.config.get("AUTOBIOGRAPHY_OPEN_GRADE", 5)
    grade = grade_of(student, today)
    # 年級不到時先講自傳何時開放；不能用送審的說明，那句寫的是「專二」會誤導（10-28 審查）
    if grade < opening:
        return (f"你現在是{GRADE_LABELS[grade]}，先把五年的拼圖收集起來；"
                f"生成自傳要到{GRADE_LABELS[opening]}才開放。")
    return review_block_reason(student, today)


def review_open_note(student, today=None):
    """生成自傳的年級還沒到時，回傳一句短說明（例如「專五開放生成自傳」）；可以用就回傳 None。"""
    if autobiography_block_reason(student, today) is None:
        return None
    if grade_of(student, today) is None:
        return MISSING_ADMISSION_YEAR
    opening = current_app.config.get("AUTOBIOGRAPHY_OPEN_GRADE", 5)
    return f"{GRADE_LABELS[opening]}開放生成自傳"


def check_record_year(student, school_year, today=None):
    """填成績、經歷時，年級不能比現在高。年級可以是 1～5 或民國學年度；有問題時丟 ValueError。"""
    reason = grade_block_reason(student, today)
    if reason:
        raise ValueError(reason)
    if school_year is None:
        return
    grade = grade_for(school_year, admission_year_of(student))
    now = grade_of(student, today)
    if grade is not None and grade > now:
        raise ValueError(f"你現在是{GRADE_LABELS[now]}，還不能填{GRADE_LABELS[grade]}的資料。"
                         "高年級的內容可以先看，等升上去再填。")
    if grade is None and school_year > 5 and school_year > academic_year_of(today or date.today()):
        raise ValueError(f"{school_year} 學年度還沒到，請確認學年度。")


def over_limit_reason(student):
    """五年級目標超過上限（例如四年級選了 6 所後升上來）：送導師確認前要先縮減。不會自動刪除。"""
    slots = target_slots(student)
    if slots["limit"] is None or slots["used"] <= slots["limit"]:
        return None
    return (f"五年級準備備審資料，目標校系最多 {slots['limit']} 所。你現在有 {slots['used']} 所，"
            f"請先取消 {slots['used'] - slots['limit']} 所，再送導師確認。")


def target_slots(student):
    """目前占名額的目標（最新學年度）與舊學年度的目標。"""
    newest = {program.id for program in published_programs()}
    targets = StudentTarget.query.filter_by(student_id=student.id).order_by(StudentTarget.selected_at).all()
    current = [t for t in targets if t.rule_version_id in newest]
    return {
        # None 代表不限
        "limit": current_app.config.get("TARGET_LIMIT", 5) if grade_of(student) == 5 else None,
        "used": len(current),
        "current": current,
        "old": [t for t in targets if t.rule_version_id not in newest],
    }
