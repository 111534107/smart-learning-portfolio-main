"""轉學生帳號建置與既有抵免確認的共用服務。

轉科帳號由管理員流程呼叫建立；抵免進度維持獨立處理。
"""

import re
import secrets
from datetime import datetime, timezone

from app.extensions import db
from app.models import AuditLog, StudentProfile, TransferCreditRecord, User
from app.services import password_policy

USERNAME = re.compile(r"[A-Za-z0-9._-]{3,50}")
# 學校學號規則：9 碼數字（前三碼入學年度、第四碼 5 五專部、第五至六碼 34 資管科、第七碼班級、第八至九碼座號）
STUDENT_NO = re.compile(r"\d{9}")
SCHOOL_DOMAIN = "@stu.ukn.edu.tw"


def create(actor, form, create_credit=True):
    """建立轉學生帳號；輸入錯誤丟 ValueError。呼叫端 commit。"""
    student_no = (form.get("student_no") or "").strip()
    name = (form.get("display_name") or "").strip()
    class_name = (form.get("class_name") or "").strip()
    email = (form.get("school_email") or "").strip().lower()
    try:
        admission_year = int(form.get("admission_year") or 0)
    except ValueError:
        admission_year = 0
    if not STUDENT_NO.fullmatch(student_no):
        raise ValueError("學號請填 9 碼數字（例如 113534105）。")
    if User.query.filter(db.func.lower(User.username) == student_no.lower()).first() or \
            StudentProfile.query.filter_by(student_no=student_no).first():
        raise ValueError("這個學號已經有帳號了。")
    if not name or len(name) > 100:
        raise ValueError("請填姓名（最多 100 個字）。")
    if not class_name or len(class_name) > 50:
        raise ValueError("請填班級（最多 50 個字）。")
    if not 90 <= admission_year <= 200:
        raise ValueError("請填入學學年度（例如 113，轉入哪一學年就填哪一學年）。")
    if email:
        if not email.endswith(SCHOOL_DOMAIN):
            raise ValueError(f"學校信箱須為 {SCHOOL_DOMAIN}。")
        if User.query.filter(db.func.lower(User.email) == email).first():
            raise ValueError("此學校信箱已綁定其他帳號。")
    password = form.get("password") or ""
    google_only = not password
    if google_only and not email:
        raise ValueError("只用學校 Google 登入時，要填學校信箱；或填起始密碼。")
    user = User(username=student_no, display_name=name, role="student", email=email or None)
    if google_only:
        user.set_password(secrets.token_urlsafe(32))
    else:
        problems = password_policy.check(password, user)
        if problems:
            raise ValueError("起始密碼還不能用：" + "".join(problems))
        user.set_password(password)
    db.session.add(user)
    db.session.flush()
    db.session.add(StudentProfile(user_id=user.id, student_no=student_no, class_name=class_name, admission_year=admission_year))
    if create_credit:
        db.session.add(TransferCreditRecord(student_id=user.id, status="not_started", note="轉學生帳號建立"))
    db.session.add(AuditLog(user_id=actor.id, action="admin.transfer_student.create", target_type="user", target_id=user.id,
                            detail_json={"class_name": class_name, "admission_year": admission_year, "google_only": google_only}))
    return user


def confirm(actor, student, confirmed):
    """科主任或科辦確認（或取消確認）抵免進度；沒有紀錄回傳 None。呼叫端 commit。"""
    record = TransferCreditRecord.query.filter_by(student_id=student.id).first()
    if record is None:
        return None
    record.teacher_confirmed = bool(confirmed)          # 欄位沿用舊名；現在是「科主任或科辦」確認
    record.teacher_id = actor.id if confirmed else None
    record.teacher_confirmed_at = datetime.now(timezone.utc) if confirmed else None
    db.session.add(AuditLog(user_id=actor.id, action="staff.transfer_credit.confirm", target_type="user", target_id=student.id,
                            detail_json={"confirmed": bool(confirmed)}))
    return record


def rows():
    """所有有轉學抵免紀錄的學生（含科辦剛建立的）。"""
    records = (TransferCreditRecord.query.join(User, User.id == TransferCreditRecord.student_id)
               .filter(User.is_active.is_(True)).order_by(TransferCreditRecord.updated_at.desc()).all())
    return [{"record": record, "student": record.student, "profile": record.student.student_profile,
             "confirmer": record.teacher} for record in records]
