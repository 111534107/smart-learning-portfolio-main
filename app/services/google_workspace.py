"""學校 Google Workspace 一鍵登入的規則與設定（2026-11-04 使用者決定，取代 11-03「只限已綁定學生」）。

- 學生（@stu.ukn.edu.tw）：第一次登入自動建立學生帳號。學號＝信箱 @ 前面的 9 碼數字；
  入學學年度＝學號前三碼（例如 111534105 → 111 學年度），不合理就留空給管理員補（10-10 決定由管理者匯入，這裡只是預填，管理員仍可改）。
  已有同學號、沒填信箱的學生帳號：直接綁上，不重複建立。
- 老師、科辦、管理員（預設 @ukn.edu.tw）：不自動建立、不自動給權限，管理員先在帳號管理建好帳號、填好信箱才能登入。
- 學生網域只能登入學生帳號，教職員網域只能登入非學生帳號，避免學生信箱被綁到管理員帳號。
- 設定存在 system_settings（管理員頁面可改，不用重開網站）。
"""

import re
import secrets
from datetime import date

from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import AuditLog, StudentProfile, SystemSetting, User
from app.services.school_google_login import DOMAIN as STUDENT_DOMAIN

ENABLED_KEY = "google_login.enabled"
AUTO_CREATE_KEY = "google_login.auto_create_students"
STAFF_DOMAIN_KEY = "google_login.staff_domain"
DEFAULTS = {ENABLED_KEY: "1", AUTO_CREATE_KEY: "1", STAFF_DOMAIN_KEY: "ukn.edu.tw"}

STUDENT_NO = re.compile(r"\d{9}")
DOMAIN_PATTERN = re.compile(r"(?=.{3,100}$)[a-z0-9-]+(\.[a-z0-9-]+)+")
NOT_BOUND = "學校帳號 {email} 尚未綁定可用的帳號，請洽管理員在「帳號管理」綁定這個信箱。"


def settings():
    """回傳 {"enabled": bool, "auto_create": bool, "staff_domain": str}。資料表不存在時用預設值。"""
    values = dict(DEFAULTS)
    try:
        values.update({row.key: row.value for row in SystemSetting.query.filter(SystemSetting.key.in_(DEFAULTS)).all()})
    except SQLAlchemyError:
        db.session.rollback()
    return {"enabled": values[ENABLED_KEY] == "1", "auto_create": values[AUTO_CREATE_KEY] == "1",
            "staff_domain": values[STAFF_DOMAIN_KEY]}


def save_settings(form, actor):
    """管理員儲存設定；網域不合法時丟 ValueError（訊息給管理員看）。核取方塊沒勾＝關閉。"""
    domain = (form.get("staff_domain") or "").strip().lower()
    if not DOMAIN_PATTERN.fullmatch(domain):
        raise ValueError("教職員網域格式不正確，例如 ukn.edu.tw。")
    if domain == STUDENT_DOMAIN:
        raise ValueError(f"教職員網域不能和學生網域（{STUDENT_DOMAIN}）相同，否則學生信箱也能登入教職員帳號。")
    previous = settings()
    new = {ENABLED_KEY: "1" if form.get("enabled") else "0",
           AUTO_CREATE_KEY: "1" if form.get("auto_create") else "0",
           STAFF_DOMAIN_KEY: domain}
    for key, value in new.items():
        row = SystemSetting.query.filter_by(key=key).first()
        if row:
            row.value, row.updated_by_id = value, actor.id
        else:
            db.session.add(SystemSetting(key=key, value=value, updated_by_id=actor.id))
    db.session.add(AuditLog(user_id=actor.id, action="system.google_login_settings", target_type="system_setting",
                            detail_json={"from": previous, "to": settings_from(new)}))
    db.session.commit()


def settings_from(raw):
    return {"enabled": raw[ENABLED_KEY] == "1", "auto_create": raw[AUTO_CREATE_KEY] == "1",
            "staff_domain": raw[STAFF_DOMAIN_KEY]}


def identity(claims, staff_domain):
    """驗證 Google 回傳的身分。回傳 (email, sub, kind)；kind 是 "student" 或 "staff"。不是本校帳號回傳 None。"""
    if not isinstance(claims, dict) or claims.get("email_verified") is not True:
        return None
    email, sub = claims.get("email"), claims.get("sub")
    if not isinstance(email, str) or not isinstance(sub, str) or not sub or email.count("@") != 1:
        return None
    email = email.lower()
    domain = email.split("@", 1)[1]
    hosted = claims.get("hd")
    # 學生信箱可能掛在大學主網域的 Workspace 底下（11-03 實測 hd=ukn.edu.tw）
    if domain == STUDENT_DOMAIN and hosted in (STUDENT_DOMAIN, "ukn.edu.tw"):
        return email, sub, "student"
    if domain == staff_domain and hosted == staff_domain:
        return email, sub, "staff"
    return None


def admission_year_from(student_no, today=None):
    """學號前三碼當入學學年度；比 90 學年早或比今年（民國）晚就不採用，留給管理員補。"""
    year = int(student_no[:3])
    this_year = (today or date.today()).year - 1911
    return year if 90 <= year <= this_year else None


def _role_fits(user, kind):
    return (user.role == "student") == (kind == "student")


def _create_student(email, sub, name, student_no):
    user = User(username=student_no, display_name=name or student_no, role="student", email=email, google_sub=sub)
    user.set_password(secrets.token_urlsafe(32))  # 沒有人知道的密碼：這個帳號只能用 Google 登入，之後可由管理員重設
    db.session.add(user)
    db.session.flush()
    db.session.add(StudentProfile(user_id=user.id, student_no=student_no, admission_year=admission_year_from(student_no)))
    db.session.add(AuditLog(user_id=user.id, action="user.google_auto_create", target_type="user", target_id=user.id,
                            detail_json={"email": email, "student_no": student_no}))
    return user


def resolve(claims, name=None):
    """依 Google 身分找出（或建立）要登入的帳號。回傳 (user, None) 或 (None, 給使用者看的錯誤訊息)。

    呼叫端負責 commit。
    """
    config = settings()
    found = identity(claims, config["staff_domain"])
    if found is None:
        return None, (f"請使用學校的 Google 帳號登入（學生 @{STUDENT_DOMAIN}，教職員 @{config['staff_domain']}）。")
    email, sub, kind = found

    user = User.query.filter_by(google_sub=sub).first()
    if user is None:
        matches = User.query.filter(db.func.lower(User.email) == email).all()
        user = matches[0] if len(matches) == 1 and not matches[0].google_sub else None
    if user is not None:
        if not user.is_active:
            return None, "這個帳號已停用，請洽管理員。"
        if (user.email or "").lower() != email or not _role_fits(user, kind):
            return None, NOT_BOUND.format(email=email)
        if not user.google_sub:
            user.google_sub = sub
        return user, None

    if kind == "staff":
        return None, (f"教職員帳號 {email} 還沒有建立。老師、科辦與管理員的帳號要由管理員先在「帳號管理」建立並填好這個信箱，"
                      "系統不會自動給教職員權限。")
    student_no = email.split("@", 1)[0]
    if not config["auto_create"] or not STUDENT_NO.fullmatch(student_no):
        return None, NOT_BOUND.format(email=email)

    existing = User.query.filter_by(username=student_no).first()
    if existing is None and StudentProfile.query.filter_by(student_no=student_no).first():
        return None, NOT_BOUND.format(email=email)  # 學號已被別的帳號用掉，交給管理員處理
    if existing is not None:
        # 管理員事先建好、還沒填信箱的同學號學生帳號：學校信箱就是本人，直接綁上
        if existing.role != "student" or existing.email or existing.google_sub or not existing.is_active:
            return None, NOT_BOUND.format(email=email)
        existing.email, existing.google_sub = email, sub
        return existing, None
    return _create_student(email, sub, name, student_no), None
