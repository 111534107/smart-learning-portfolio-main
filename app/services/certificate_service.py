"""科辦電子獎狀：外框固定，內文由系統先帶入、科辦核准前可以修改。

規則（寫在這裡，方便報告時說明）：
- 只有從「學校獎懲記錄」匯入的紀錄可以申請，科辦只開自己開得出來的兩種證明：
  - 服務證明：類別是服務學習（也就是科上派的服務）。
  - TA 證明：獎懲事由寫到「TA」「助教」或「教學助理」。
  事由以匯入時的原文為準（學生之後改了經歷標題也不影響）。同一筆符合多種時由學生選一種，
  科辦審核時還能再改標題。（2026-11-08 判斷：規格只寫「加 TA 證明、社團證明」，沒寫條件，
  先用獎懲事由關鍵字，因為 TA 與社團在學校系統也都記成嘉獎。）
- 科學會證明 2026-11-09 起不再由科辦開（規格原寫「社團證明」，指的是科學會）：訪談時科長說明
  科學會歸類在社團，幹部證明走學務處的表格，學生填好、社團指導老師蓋章後交回學務處蓋章。
  經歷寫到科學會、社團、學生會時改成提醒學生到學務處辦（club_reminder）。
  之前已申請或已核准的（代碼仍是 club）照樣顯示、照樣能審，所以 KINDS 仍保留 club。
- 電子獎狀是補充個別證明，不取代學校的獎懲記錄。
- 核准時才產生 8 碼驗證碼；任何人可在 /verify 用驗證碼查到獎狀是否由本系統核發，姓名只顯示遮蔽後的樣子。
- 核准或退回時寄站內通知給學生，連到獎狀或修改頁。
- 活動證明（activity）2026-11-12 新增：只有科辦批量開立會用到（見 certificate_batch_service.py），學生不能自己申請。
- 新增其他證明類別時，在 KINDS、CLOSINGS 與 eligible_kinds 各加一種；外框共用 templates/certificate.html。
"""

import re
import secrets

from app.models import AwardCertificate, SchoolAwardRecord

KINDS = {"service": "服務證明", "ta": "TA 證明", "club": "科學會證明", "activity": "活動證明"}
KIND_HINTS = {"service": "科上派的服務", "ta": "擔任課程 TA（教學助理）", "club": "科學會幹部或活動"}
CLOSINGS = {"service": "熱心服務、表現認真", "ta": "協助課程教學、認真負責", "club": "積極參與科學會、表現優良"}
TA_PATTERN = re.compile(r"(?<![A-Za-z])TA(?![A-Za-z])|助教|教學助理", re.IGNORECASE)
CLUB_WORDS = ("科學會", "社團", "社長", "學生會")
STUDENT_AFFAIRS_NOTE = ("科學會歸類在社團，科學會（含幹部）與其他社團的證明由學務處辦理，科辦不開："
                        "到學務處拿表格填寫經歷，請社團指導老師蓋章，再交回學務處蓋章才算完整。蓋好章的證明可以拍照上傳到下面的「佐證」。")
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
    return kinds


def club_reminder(record):
    """經歷寫到科學會、社團、學生會時，回傳「到學務處辦證明」的提醒；其他回傳 None。"""
    if record.deleted_at:
        return None
    text = f"{original_reason(record) if record.source == 'award_record' else ''} {record.title or ''}"
    return STUDENT_AFFAIRS_NOTE if any(word in text for word in CLUB_WORDS) else None


def can_apply(record, kind=None):
    kinds = eligible_kinds(record)
    return bool(kinds) if kind is None else kind in kinds


def _content(title):
    """拿掉事由開頭的「1141學期」，其他照原文。"""
    return re.sub(r"^\s*\d{3}[12]\s*學期", "", title).strip() or title


TA_COURSE_PATTERN = re.compile(r"擔任\s*「?([^「」]{1,30}?)」?\s*(?:課程)?\s*(?:TA|助教|教學助理)", re.IGNORECASE)


def ta_course(reason):
    """從獎懲事由找出 TA 協助的課名（「擔任資料庫系統課程TA」→ 資料庫系統）；看不出來回傳 None。"""
    match = TA_COURSE_PATTERN.search(_content(reason or ""))
    course = match.group(1).strip() if match else ""
    return course or None


def default_body(record, kind="service"):
    student = record.student
    profile = student.student_profile
    student_no = f"（學號：{profile.student_no}）" if profile and profile.student_no else ""
    year = record.school_year
    if year and year <= 5 and profile and profile.admission_year:
        year = profile.admission_year + year - 1  # 年級換回民國學年度
    when = f"於 {year} 學年度{SEMESTER_NAMES.get(record.semester, '')}" if year and year > 5 else ""
    course = ta_course(original_reason(record) or "") if kind == "ta" else None
    if course:
        # 11-09 科長訪談：TA 證明寫誰、哪一學期、協助哪一門課；不寫時數（公文核給時數和實際不同）
        return (f"茲證明 本校五專資訊管理科 {student.display_name}{student_no} 同學，"
                f"{when}擔任「{course}」課程 TA（教學助理），{CLOSINGS['ta']}，特此證明。")
    return (f"茲證明 本校五專資訊管理科 {student.display_name}{student_no} 同學，"
            f"{when}參與「{_content(record.title)}」，{CLOSINGS.get(kind, CLOSINGS['service'])}，特此證明。")


ISSUE_KINDS = ("service", "ta")  # 科辦直接開立只開這兩種；科學會證明由學務處辦


# 電子獎狀核准、開立只限主任、副主任（2026-11-13 使用者決定）；科助與其他行政人員可以審內容、建立，
# 建立的獎狀先是「待核准」，等主任或副主任按核准才有驗證碼、通知學生
APPROVER_TITLES = ("主任", "副主任")


def can_approve(user):
    from app.services import staff_roles
    return staff_roles.is_chief(user)


def approval_fields(staff):
    """建立獎狀時的狀態欄位：主任、副主任直接核准；其他人建立成待核准。"""
    from datetime import date, datetime, timezone

    if can_approve(staff):
        return {"status": "approved", "issued_on": date.today(), "verify_code": new_verify_code(),
                "reviewed_by_id": staff.id, "reviewed_at": datetime.now(timezone.utc)}
    return {"status": "pending"}


def staff_issue(staff, student, kind, event, school_year, semester, course=None, body=None):
    """科辦直接開立（2026-11-09 使用者決定）：不等學生申請。主任、副主任開的直接核准、給驗證碼；科助開的先待核准。
    同時在學生的經歷新增一筆來源「科辦電子獎狀」的紀錄，證明有地方掛、學生的五年裡也看得到。
    school_year 是民國學年度；經歷裡和匯入的資料一樣換成年級。輸入錯誤丟 ValueError（訊息給科辦看）。"""
    from app.extensions import db
    from app.models import Portfolio
    from app.services.journey_service import grade_for

    if kind not in ISSUE_KINDS:
        raise ValueError("科辦只開服務證明與 TA 證明；科學會證明請學生到學務處辦理。")
    event = (event or "").strip()
    course = (course or "").strip()
    if kind == "service" and not event:
        raise ValueError("請填寫服務事由，例如「協助資管科課輔班擔任小老師」。")
    if kind == "ta" and not course:
        raise ValueError("TA 證明請填寫協助的課名。")
    profile = student.student_profile
    title = f"擔任「{course}」課程TA" if kind == "ta" else event
    record = Portfolio(
        student_id=student.id, title=title[:150], category="service", course_name=course or None,
        school_year=grade_for(school_year, profile.admission_year if profile else None) or school_year,
        semester=semester, source="department_certificate", status="confirmed",
    )
    db.session.add(record)
    db.session.flush()
    cert = AwardCertificate(
        portfolio=record, kind=kind, title=KINDS[kind], issuer=DEFAULT_ISSUER,
        body=(body or "").strip() or default_body(record, kind), **approval_fields(staff),
    )
    db.session.add(cert)
    db.session.flush()
    return cert


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


def roc_year(day):
    """今天屬於哪個民國學年度（8 月起算新學年）。"""
    return day.year - 1911 - (0 if day.month >= 8 else 1)


def roc_date(day):
    return f"中華民國 {day.year - 1911} 年 {day.month} 月 {day.day} 日"
