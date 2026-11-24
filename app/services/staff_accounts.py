"""教職員帳號：管理員新增老師、科辦、管理員帳號，科辦加職稱（2026-11-09 使用者決定，11-10 實作）。

科辦帳號不限人數，像大學系辦一樣，用職稱區分：主任、副主任、科助、其他行政人員（可自填）。
帳號可以設初始密碼（依 app/services/password_policy.py 的規則），也可以只用學校 Google 登入
（密碼設成沒有人知道的亂數，要先填學校信箱）。
"""
import re
import secrets

from app.extensions import db
from app.models import AuditLog, User
from app.services import password_policy

ROLES = {"teacher": "老師", "staff": "科辦", "admin": "管理員"}
STAFF_TITLES = ("主任", "副主任", "科助", "其他行政人員")
USERNAME = re.compile(r"[A-Za-z0-9._-]{3,50}")


def clean_title(role, title, other=""):
    """科辦職稱：選「其他行政人員」時可以自填（例如「行政助理」）；老師與管理員可留空或自填。"""
    title = (title or "").strip()
    other = (other or "").strip()
    if role == "staff":
        if title not in STAFF_TITLES:
            raise ValueError("請選擇科辦職稱：主任、副主任、科助或其他行政人員。")
        if title == "其他行政人員" and other:
            title = other
    elif title == "其他行政人員" and other:
        title = other
    if len(title) > 30:
        raise ValueError("職稱最多 30 個字。")
    return title or None


def create(actor, form, staff_domain):
    """依表單建立教職員帳號；輸入錯誤丟 ValueError（訊息給管理員看）。呼叫端 commit。"""
    role = (form.get("role") or "").strip()
    if role not in ROLES:
        raise ValueError("請選擇身分：老師、科辦或管理員。")
    username = (form.get("username") or "").strip()
    if not USERNAME.fullmatch(username):
        raise ValueError("帳號請用 3～50 個英文字母、數字或 . _ -。")
    if User.query.filter(db.func.lower(User.username) == username.lower()).first():
        raise ValueError("這個帳號已經有人用了。")
    name = (form.get("display_name") or "").strip()
    if not name or len(name) > 100:
        raise ValueError("請填姓名（最多 100 個字）。")
    title = clean_title(role, form.get("job_title"), form.get("job_title_other"))
    email = (form.get("school_email") or "").strip().lower()
    if email:
        if not re.fullmatch(r"[a-z0-9._-]+@" + re.escape(staff_domain), email):
            raise ValueError(f"教職員信箱須為 @{staff_domain}。")
        if User.query.filter(db.func.lower(User.email) == email).first():
            raise ValueError("此學校信箱已綁定其他帳號。")
    google_only = form.get("login") == "google"
    user = User(username=username, display_name=name, role=role, job_title=title, email=email or None)
    if google_only:
        if not email:
            raise ValueError("只用學校 Google 登入時，要填學校信箱。")
        user.set_password(secrets.token_urlsafe(32))
    else:
        password = form.get("password") or ""
        problems = password_policy.check(password, user)
        if problems:
            raise ValueError("初始密碼還不能用：" + "".join(problems))
        user.set_password(password)
    db.session.add(user)
    db.session.flush()
    db.session.add(AuditLog(user_id=actor.id, action="staff.account.create", target_type="user", target_id=user.id,
                            detail_json={"role": role, "job_title": title, "google_only": google_only}))
    return user


def set_title(actor, account, title, other=""):
    if account.role not in ROLES:
        raise ValueError("學生帳號沒有職稱。")
    new = clean_title(account.role, title, other) if (title or account.role == "staff") else None
    if new != account.job_title:
        db.session.add(AuditLog(user_id=actor.id, action="staff.job_title.update", target_type="user",
                                target_id=account.id, detail_json={"from": account.job_title, "to": new}))
        account.job_title = new
