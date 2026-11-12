"""科辦批量開立電子獎狀（2026-11-12 指導老師提出）：科上辦活動時，一次匯入名單開多張，不用一張一張開。

規則（寫在這裡，方便報告時說明）：
- 名單一列一位學生，四欄依序是「學號、活動名稱、獎項或服務內容、日期」，用逗號或 Tab 分隔
  （從 Excel 複製貼上就是 Tab）；也可以上傳 CSV 檔。第一列是欄位名稱時自動略過。
- 日期收西元（2026-10-20、2026/10/20）與民國（115/10/20），不能是未來的日期。
- 先預覽：查無學號、欄位缺漏、日期看不懂、名單內重複、以前已經開過同一張，都標成錯誤列，不會建立。
- 確認後只建立沒有問題的列。每一張都和單張開立相同：直接核准、當天為核發日、產生 8 碼驗證碼、
  在學生的經歷新增一筆來源「科辦電子獎狀」的紀錄、寄站內通知、寫一筆 certificate.issue 操作紀錄；
  整批另外寫一筆 certificate.batch_issue（只記張數）。
- 類別是「活動證明」（代碼 activity），只有科辦批量開立會用到，學生不能自己申請。
- 不放科章圖檔（能不能放還沒確認）。
"""
import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone

from app.extensions import db
from app.models import AwardCertificate, Portfolio, StudentProfile
from app.services import certificate_service
from app.services.journey_service import grade_for

KIND = "activity"
MAX_ROWS = 300
COLUMNS = ("學號", "活動名稱", "獎項或服務內容", "日期")
SAMPLE = "學號,活動名稱,獎項或服務內容,日期\n111534105,資管科資訊週程式競賽,榮獲第一名,2026-10-20"
_DATE = re.compile(r"^(\d{2,4})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})\s*日?$")


class BatchRejected(ValueError):
    """整份名單不能用（空的、太多列、檔案讀不懂）；訊息直接顯示給科辦看。"""


@dataclass
class Row:
    line_no: int
    student_no: str = ""
    activity: str = ""
    content: str = ""
    date_text: str = ""
    day: date | None = None
    student: object = None
    error: str = ""

    @property
    def ok(self):
        return not self.error

    @property
    def record_title(self):
        """寫進學生經歷的標題；也用來判斷是不是已經開過同一張。"""
        return f"{self.activity}：{self.content}"[:150]


def decode_upload(data):
    """上傳的 CSV 檔轉成文字：先試 UTF-8（含 Excel 存的 BOM），再試 Big5。"""
    if b"\x00" in data:
        raise BatchRejected("這個檔案不是文字 CSV。Excel 檔請另存成「CSV（逗號分隔）」，或直接複製貼上。")
    for encoding in ("utf-8-sig", "big5"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise BatchRejected("這個檔案不是文字 CSV。Excel 檔請另存成「CSV（逗號分隔）」，或直接複製貼上。")


def parse_date(text):
    match = _DATE.match(text.strip())
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    if year < 1911:
        year += 1911  # 民國年
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _cells(line):
    line = line.replace("，", ",")
    delimiter = "\t" if "\t" in line else ","
    return [cell.strip() for cell in next(csv.reader(io.StringIO(line), delimiter=delimiter), [])]


def parse_rows(text, today=None):
    """把名單文字變成 Row 清單（空白列與欄位名稱列不算）；每列的問題寫在 row.error。"""
    today = today or date.today()
    rows = []
    for line_no, line in enumerate((text or "").splitlines(), start=1):
        cells = _cells(line)
        if not any(cells) or (cells[0] == COLUMNS[0] and not rows):
            continue
        cells += [""] * (4 - len(cells))
        rows.append(Row(line_no, cells[0], cells[1][:60], cells[2][:80], cells[3]))
    if not rows:
        raise BatchRejected("名單是空的。請貼上名單或選擇 CSV 檔，一列一位學生。")
    if len(rows) > MAX_ROWS:
        raise BatchRejected(f"一次最多 {MAX_ROWS} 列，這份名單有 {len(rows)} 列，請分批匯入。")

    profiles = {profile.student_no: profile for profile in
                StudentProfile.query.filter(StudentProfile.student_no.in_({row.student_no for row in rows})).all()}
    seen = {}
    for row in rows:
        missing = [name for name, value in zip(COLUMNS, (row.student_no, row.activity, row.content, row.date_text))
                   if not value]
        if missing:
            row.error = f"缺少{'、'.join(missing)}"
            continue
        profile = profiles.get(row.student_no)
        user = profile.user if profile else None
        if not user or user.role != "student" or not user.is_active:
            row.error = "查無學號（系統裡沒有這位學生，或帳號已停用）"
            continue
        row.student = user
        row.day = parse_date(row.date_text)
        if not row.day:
            row.error = "日期看不懂，請寫成 2026-10-20 或 115/10/20"
            continue
        if row.day > today:
            row.error = "日期在今天之後，活動結束後才能開證明"
            continue
        key = (row.student_no, row.activity, row.content)
        if key in seen:
            row.error = f"和第 {seen[key]} 列重複"
            continue
        seen[key] = row.line_no
        if _already_issued(user, row.record_title):
            row.error = "已經開過同一張（同一位學生、同一個活動與內容）"
    return rows


def _already_issued(student, title):
    return db.session.query(AwardCertificate.id).join(Portfolio, AwardCertificate.portfolio_id == Portfolio.id).filter(
        AwardCertificate.student_id == student.id, AwardCertificate.status == "approved",
        Portfolio.source == "department_certificate", Portfolio.title == title).first() is not None


def body_for(row):
    student = row.student
    profile = student.student_profile
    student_no = f"（學號：{profile.student_no}）" if profile and profile.student_no else ""
    day = row.day
    return (f"茲證明 本校五專資訊管理科 {student.display_name}{student_no} 同學，"
            f"於民國 {day.year - 1911} 年 {day.month} 月 {day.day} 日參加「{row.activity}」，{row.content}，特此證明。")


def issue_rows(staff, rows, title=None):
    """把沒有問題的列各開一張（不 commit、不寄通知、不寫操作紀錄，由路由處理）。回傳建立的獎狀清單。"""
    title = (title or "").strip()[:50] or certificate_service.KINDS[KIND]
    now = datetime.now(timezone.utc)
    certs = []
    for row in rows:
        if not row.ok:
            continue
        profile = row.student.student_profile
        school_year = certificate_service.roc_year(row.day)
        record = Portfolio(
            student_id=row.student.id, title=row.record_title, category="activity",
            school_year=grade_for(school_year, profile.admission_year if profile else None) or school_year,
            semester=1 if row.day.month >= 8 or row.day.month == 1 else 2,
            source="department_certificate", status="confirmed",
        )
        db.session.add(record)
        db.session.flush()
        cert = AwardCertificate(
            student_id=row.student.id, portfolio=record, kind=KIND, title=title,
            issuer=certificate_service.DEFAULT_ISSUER, body=body_for(row), status="approved",
            issued_on=date.today(), verify_code=certificate_service.new_verify_code(),
            reviewed_by_id=staff.id, reviewed_at=now,
        )
        db.session.add(cert)
        db.session.flush()
        certs.append(cert)
    return certs
