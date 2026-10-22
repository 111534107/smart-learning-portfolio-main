"""只供本機展示使用的合成資料應用程式。"""

from datetime import date

from sqlalchemy.pool import StaticPool

from app import create_app
from app.extensions import db
from app.models import AuditLog, ClassAdvisor, StudentProfile, User
from app.services.admission_service import import_seed_programs
from app.services.journey_service import academic_year_of


DEMO_PASSWORD = "demo2026"


class SerializedWSGI:
    """讓展示站一次只處理一個請求（網站仍可同時接受多條連線）。

    展示站的資料庫在記憶體中，所有執行緒共用同一條 SQLite 連線（StaticPool）；
    同時處理多個請求時查詢會互相干擾，實測會把已登入的人誤判為未登入、或誤回 404。
    正式環境使用 MySQL 連線池，不需要這一層。
    """

    def __init__(self, app):
        import threading

        self.app = app
        self.lock = threading.Lock()

    def __call__(self, environ, start_response):
        with self.lock:
            response = self.app(environ, start_response)
            try:
                return list(response)  # 在鎖內讀完整個回應（含檔案下載）
            finally:
                if hasattr(response, "close"):
                    response.close()


def create_local_demo_app():
    """建立只在記憶體 SQLite 運作的合成資料展示站，絕不連到 .env 資料庫。"""
    app = create_app({
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "SQLALCHEMY_ENGINE_OPTIONS": {
            "poolclass": StaticPool,
            "connect_args": {"check_same_thread": False},
        },
        "TESTING": False,
        "SECRET_KEY": "local-demo-only-not-for-production",
        "LOCAL_DEMO_MODE": True,
        "AI_ENABLED": False,
        "AI_PROVIDER": "none",
        "AI_API_KEY": "",
        "DOCUMENT_ANALYSIS_PROVIDER": "demo",
        "GOOGLE_DRIVE_PREVIEW_ENABLED": False,
        "GOOGLE_OAUTH_CLIENT_ID": "",
        "GOOGLE_PICKER_API_KEY": "",
        "GOOGLE_CLOUD_PROJECT_NUMBER": "",
    })
    with app.app_context():
        db.create_all()
        users = {}
        for role in ("student", "teacher", "staff", "admin"):
            user = User(username=f"{role}_demo", display_name=f"合成{role}帳號", role=role)
            user.set_password(DEMO_PASSWORD)
            db.session.add(user)
            users[role] = user
        db.session.flush()
        current_year = academic_year_of(date.today())
        db.session.add(StudentProfile(
            user_id=users["student"].id,
            student_no="DEMO-0001",
            class_name="資管科測試班",
            admission_year=current_year - 4,
        ))
        db.session.add(ClassAdvisor(
            teacher_id=users["teacher"].id,
            class_name="資管科測試班",
            school_year=current_year,
        ))
        db.session.add(AuditLog(user_id=users["student"].id, action="student.welcome_done"))
        import_seed_programs()
        db.session.commit()
    app.wsgi_app = SerializedWSGI(app.wsgi_app)
    return app
