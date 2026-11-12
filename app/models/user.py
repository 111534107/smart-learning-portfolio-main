from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

PASSWORD_MAX_LENGTH = 256


def password_input_ok(password):
    """擋掉看不見的控制字元與超長字串（2026-11-12）。

    密碼雜湊遇到 \x00 會把後面截掉：「pw\x00任意字」會被當成「pw」而登入成功；
    超長字串則會讓伺服器算雜湊算很久。中文、全形、表情符號都是正常字元，照常比對。
    """
    if not isinstance(password, str) or len(password) > PASSWORD_MAX_LENGTH:
        return False
    return not any(ord(ch) < 32 or ord(ch) == 127 for ch in password)

from app.extensions import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(30), nullable=False, default="student", index=True)
    email = db.Column(db.String(120), nullable=True)
    # 電子郵件通知開關（帳號設定可關）；管理員另有全域開關（system_settings.email_notify_enabled）
    # 備審時間線行事曆訂閱的私密網址代碼（app/services/calendar_feed.py）；重設後舊網址失效
    calendar_token = db.Column(db.String(64), unique=True, nullable=True)
    email_notify = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    google_sub = db.Column(db.String(255), unique=True, nullable=True, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    # 教職員職稱（11-10）：科辦可以有很多人，用職稱區分主任、副主任、科助、其他行政人員；學生不用
    job_title = db.Column(db.String(30), nullable=True)
    # 雙重驗證（11-09）：金鑰加密後存放（app/services/two_factor.py），開啟時間、最後用過的時間窗（防止同一組碼重用）
    two_factor_secret = db.Column(db.Text, nullable=True)
    two_factor_enabled_at = db.Column(db.DateTime, nullable=True)
    two_factor_last_counter = db.Column(db.Integer, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    student_profile = db.relationship(
        "StudentProfile", back_populates="user", uselist=False
    )
    portfolios = db.relationship("Portfolio", back_populates="student")
    agent_tasks = db.relationship("AgentTask", back_populates="requester")
    audit_logs = db.relationship("AuditLog", back_populates="user")
    review_assignments = db.relationship("SubmissionAssignment", back_populates="teacher", foreign_keys="SubmissionAssignment.teacher_id")
    source_documents = db.relationship("SourceDocument", back_populates="owner")

    def set_password(self, password):
        if not password_input_ok(password):
            raise ValueError("密碼不能含有看不見的控制字元，長度也不能超過 256 字。")
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not password_input_ok(password):
            return False
        return check_password_hash(self.password_hash, password)

    @property
    def two_factor_enabled(self):
        return bool(self.two_factor_secret and self.two_factor_enabled_at)


class UserBackupCode(db.Model):
    """雙重驗證備用碼：手機遺失時登入用。只存雜湊值，用過就作廢。"""
    __tablename__ = "user_backup_codes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    code_hash = db.Column(db.String(255), nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class StudentProfile(db.Model):
    __tablename__ = "student_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    student_no = db.Column(db.String(20), unique=True, nullable=False, index=True)
    class_name = db.Column(db.String(50), nullable=True)
    admission_year = db.Column(db.Integer, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = db.relationship("User", back_populates="student_profile")
