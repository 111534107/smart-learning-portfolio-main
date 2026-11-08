"""科辦電子獎狀：外框固定，內文由系統先帶入、科辦核准前可以修改。

規則（寫在這裡，方便報告時說明）：
- 只有從「學校獎懲記錄」匯入的紀錄可以申請，科辦只開自己開得出來的三種證明：
  - 服務證明：類別是服務學習（也就是科上派的服務）。
  - TA 證明：獎懲事由寫到「TA」「助教」或「教學助理」。
  - 社團證明：獎懲事由寫到「社團」或「社長」。
  事由以匯入時的原文為準（學生之後改了經歷標題也不影響）。同一筆符合多種時由學生選一種，
  科辦審核時還能再改標題。（2026-11-08 判斷：規格只寫「加 TA 證明、社團證明」，沒寫條件，
  先用獎懲事由關鍵字，因為 TA 與社團在學校系統也都記成嘉獎。）
- 電子獎狀是補充個別證明，不取代學校的獎懲記錄。
- 核准時才產生 8 碼驗證碼；任何人可在 /verify 用驗證碼查到獎狀是否由本系統核發，姓名只顯示遮蔽後的樣子。
- 核准或退回時寄站內通知給學生，連到獎狀或修改頁。
- 新增其他證明類別（例如幹部證明）時，在 KINDS、CLOSINGS 與 eligible_kinds 各加一種；外框共用 templates/certificate.html。
"""

import re
import secrets

from app.models import AwardCertificate, SchoolAwardRecord

KINDS = {"service": "服務證明", "ta": "TA 證明", "club": "社團證明"}
KIND_HINTS = {"service": "科上派的服務", "ta": "擔任課程 TA（教學助理）", "club": "社團活動或社團幹部"}
CLOSINGS = {"service": "熱心服務、表現認真", "ta": "協助課程教學、認真負責", "club": "積極參與社團、表現優良"}
TA_PATTERN = re.compile(r"(?<![A-Za-z])TA(?![A-Za-z])|助教|教學助理", re.IGNORECASE)
CLUB_WORDS = ("社團", "社長")
DEFAULT_ISSUER = "資訊管理科"
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 不用 0、O、1、I，避免看錯
SEMESTER_NAMES = {1: "第一學期", 2: "第二學期"}


def award_row(record):
    """這筆經歷匯入時對應的獎懲記錄列（有原文、日期、獎懲名稱）；手動新增或舊資料可能沒有。"""
    return (SchoolAwardRecord.query.filter_by(portfolio_id=record.id, record_type="reward")
            .order_by(SchoolAwardRecord.id).first())


def original_reason(record):
    row = award_row(record)
    return row.reason if row else record.title


def eligible_kinds(record):
    """這筆經歷可以申請哪幾種證明，依 KINDS 的順序。"""
    if record.source != "award_record" or record.deleted_at:
        return []
    reason = original_reason(record) or ""
    kinds = []
    if record.category == "service":
        kinds.append("service")
    if TA_PATTERN.search(reason):
        kinds.append("ta")
    if any(word in reason for word in CLUB_WORDS):
        kinds.append("club")
    return kinds


def can_apply(record, kind=None):
    kinds = eligible_kinds(record)
    return bool(kinds) if kind is None else kind in kinds


def _content(title):
    """拿掉事由開頭的「1141學期」，其他照原文。"""
    return re.sub(r"^\s*\d{3}[12]\s*學期", "", title).strip() or title


def default_body(record, kind="service"):
    student = record.student
    profile = student.student_profile
    student_no = f"（學號：{profile.student_no}）" if profile and profile.student_no else ""
    year = record.school_year
    if year and year <= 5 and profile and profile.admission_year:
        year = profile.admission_year + year - 1  # 年級換回民國學年度
    when = f"於 {year} 學年度{SEMESTER_NAMES.get(record.semester, '')}" if year and year > 5 else ""
    return (f"茲證明 本校五專資訊管理科 {student.display_name}{student_no} 同學，"
            f"{when}參與「{_content(record.title)}」，{CLOSINGS.get(kind, CLOSINGS['service'])}，特此證明。")


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
