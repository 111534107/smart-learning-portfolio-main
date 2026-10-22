"""科辦電子獎狀：外框固定，內文由系統先帶入、科辦核准前可以修改。

規則（寫在這裡，方便報告時說明）：
- 只有從「學校獎懲記錄」匯入、類別是服務學習的紀錄可以申請（也就是科上派的服務）。
- 電子獎狀是補充個別證明，不取代學校的獎懲記錄。
- 核准時才產生 8 碼驗證碼；任何人可在 /verify 用驗證碼查到獎狀是否由本系統核發，姓名只顯示遮蔽後的樣子。
- 新增其他證明類別（例如幹部證明）時，在 KINDS 多加一種預設標題即可；外框共用 templates/certificate.html。
"""

import re
import secrets

from app.models import AwardCertificate

KINDS = {"service": "服務證明"}
DEFAULT_ISSUER = "資訊管理科"
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 不用 0、O、1、I，避免看錯
SEMESTER_NAMES = {1: "第一學期", 2: "第二學期"}


def can_apply(record):
    return record.source == "award_record" and record.category in KINDS


def _content(title):
    """拿掉事由開頭的「1141學期」，其他照原文。"""
    return re.sub(r"^\s*\d{3}[12]\s*學期", "", title).strip() or title


def default_body(record):
    student = record.student
    profile = student.student_profile
    student_no = f"（學號：{profile.student_no}）" if profile and profile.student_no else ""
    year = record.school_year
    if year and year <= 5 and profile and profile.admission_year:
        year = profile.admission_year + year - 1  # 年級換回民國學年度
    when = f"於 {year} 學年度{SEMESTER_NAMES.get(record.semester, '')}" if year and year > 5 else ""
    return (f"茲證明 本校五專資訊管理科 {student.display_name}{student_no} 同學，"
            f"{when}參與「{_content(record.title)}」，熱心服務、表現認真，特此證明。")


def new_verify_code():
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
        if not AwardCertificate.query.filter_by(verify_code=code).first():
            return code


def mask_name(name):
    """王小明 → 王○明；兩個字的名字 → 王○。"""
    if len(name) <= 1:
        return name
    if len(name) == 2:
        return name[0] + "○"
    return name[0] + "○" * (len(name) - 2) + name[-1]


def roc_date(day):
    return f"中華民國 {day.year - 1911} 年 {day.month} 月 {day.day} 日"
