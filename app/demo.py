"""只供本機展示使用的合成資料應用程式。"""

import tempfile
from datetime import date
from pathlib import Path

from sqlalchemy.pool import StaticPool

from app import create_app
from app.extensions import db
from app.models import (AuditLog, AwardCertificate, ClassAdvisor, CredentialRecord, LearningCourseRecord, Portfolio,
                        StudentProfile, StudentTarget, User)
from app.services import certificate_service
from app.services import form_library_service
from app.services.admission_service import import_seed_programs, published_programs
from app.services.transfer_exam import import_transfer_programs
from app.services.journey_service import EXPERIENCE_CATEGORIES, academic_year_of, current_grade
from app.services.portfolio_service import create_submission_snapshot


DEMO_PASSWORD = "demo2026"

# 登入頁「Demo 快速登入」列出的帳號（只有設定 DEMO_ACCOUNTS 的展示站會顯示）
DEMO_ACCOUNTS = [
    {"role": "student", "label": "學生", "username": "student_demo", "password": DEMO_PASSWORD, "name": "合成學生"},
    {"role": "teacher", "label": "導師", "username": "teacher_demo", "password": DEMO_PASSWORD, "name": "合成導師"},
    {"role": "staff", "label": "科辦", "username": "staff_demo", "password": DEMO_PASSWORD, "name": "合成主任"},
    {"role": "admin", "label": "管理者", "username": "admin_demo", "password": DEMO_PASSWORD, "name": "合成管理者"},
]


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


DEMO_CATEGORY_NAMES = {"activity": "活動", "competition": "競賽", "service": "服務", "leadership": "幹部"}


# 以下情節與數字均為虛構，供展示與測試使用。
DEMO_STORIES = {
    "activity": ("數位學習工作坊", "協助同學練習製作簡易網頁", "規劃練習步驟並協助排除錯誤", "協助 12 位同學完成練習", "將複雜步驟拆解成容易理解的說明", "數位學習、網頁開發"),
    "competition": ("校內程式設計挑戰", "與組員設計圖書借閱查詢原型", "負責查詢功能與測試案例", "完成 8 項查詢測試並獲示範組佳作", "透過測試及討論改善程式錯誤", "程式設計、系統開發"),
    "service": ("校園資訊服務", "協助整理教室設備與使用說明", "檢查設備並記錄處理狀況", "整理 15 台設備的檢查紀錄", "遇到問題先記錄現象再逐步排查", "資訊維護、服務學習"),
    "leadership": ("班級活動協調", "與同學共同籌備班級成果分享", "整理工作清單並聯絡各組進度", "協調 4 組完成分享準備", "確認需求和回報進度能減少誤解", "團隊合作、專案管理"),
}

def _seed_journey_board(student_id, admission_year):
    """補滿示範學生的拼圖桌：走過的每一年 × 六類各一筆已確認資料，讓展示時能生成自傳。

    全部是合成測試資料，標題前綴「【測試】」，不是真實成績或證照。回傳 {(類別, 年級): Portfolio}。
    """
    portfolios = {}
    for grade in range(1, current_grade(admission_year) + 1):
        year = admission_year + grade - 1
        db.session.add(LearningCourseRecord(
            student_id=student_id, school_year=grade, course_name=f"【測試】課程{grade}",
            normalized_course_name=f"【測試】課程{grade}", score=80, confirmation_status="confirmed",
        ))
        db.session.add(CredentialRecord(
            student_id=student_id, credential_name=f"【測試】證照{grade}",
            issue_date=date(year + 1911, 10, 1), confirmation_status="confirmed",
        ))
        for category in EXPERIENCE_CATEGORIES:
            title, description, role, achievement, learned, domain_tags = DEMO_STORIES[category]
            portfolio = Portfolio(
                student_id=student_id, title=f"【測試】{DEMO_CATEGORY_NAMES[category]}{grade}：{title}", category=category,
                description=f"僅為測試資料：{description}。", role=role, achievement=achievement,
                learned=learned, domain_tags=domain_tags, school_year=grade, status="confirmed",
            )
            db.session.add(portfolio)
            portfolios[(category, grade)] = portfolio
    return portfolios


def _seed_staff_queue(student, portfolios):
    """讓科辦展示時有東西可處理：兩筆已送審成果、一張待核准的服務電子獎狀。"""
    for key in (("competition", 5), ("activity", 5)):
        portfolio = portfolios.get(key)
        if portfolio:
            db.session.add(create_submission_snapshot(portfolio, student))
    service = portfolios.get(("service", 4))
    if service:
        # 電子獎狀只開給「從學校獎懲記錄匯入」的服務紀錄
        service.source, service.semester = "award_record", 1
        db.session.flush()
        db.session.add(AwardCertificate(
            portfolio=service, status="pending", title=certificate_service.KINDS["service"],
            issuer=certificate_service.DEFAULT_ISSUER, body=certificate_service.default_body(service),
        ))


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
        # 上傳檔另放暫存資料夾：資料庫每次重建、示範學生編號都是 1，
        # 若共用 instance/uploads，會把磁碟上其他人留下的照片或備份當成示範學生的
        "UPLOAD_FOLDER": tempfile.mkdtemp(prefix="ai-local-demo-uploads-"),
        "LOCAL_DEMO_MODE": True,
        "DEMO_ACCOUNTS": DEMO_ACCOUNTS,
        # AI 設定沿用 .env（AI_ENABLED、AI_PROVIDER、AI_API_KEY），不在此覆寫
        "DOCUMENT_ANALYSIS_PROVIDER": "demo",
        # Google 設定沿用 .env（GOOGLE_DRIVE_PREVIEW_ENABLED 與各 OAuth 欄位），不在此覆寫
    })
    with app.app_context():
        db.create_all()
        users = {}
        for role in ("student", "teacher", "staff", "admin"):
            # 本機展示只有一個科辦帳號，設成主任才能示範核准電子獎狀（2026-11-13 核准限主任、副主任）
            user = User(username=f"{role}_demo", display_name=f"合成{role}帳號", role=role,
                        job_title="主任" if role == "staff" else None)
            user.set_password(DEMO_PASSWORD)
            db.session.add(user)
            users[role] = user
        db.session.flush()
        current_year = academic_year_of(date.today())
        admission_year = current_year - 4
        db.session.add(StudentProfile(
            user_id=users["student"].id,
            student_no="DEMO-0001",
            class_name="資管科測試班",
            admission_year=admission_year,
        ))
        portfolios = _seed_journey_board(users["student"].id, admission_year)
        _seed_staff_queue(users["student"], portfolios)
        # 2026-11-13 不放合成表單：表單由科辦按「從學校網站更新表單」抓真的，沒有的請學生到科辦拿紙本
        db.session.add(ClassAdvisor(
            teacher_id=users["teacher"].id,
            class_name="資管科測試班",
            school_year=current_year,
        ))
        db.session.add(AuditLog(user_id=users["student"].id, action="student.welcome_done"))
        import_seed_programs()
        content = Path(__file__).resolve().parent / "content"
        import_seed_programs(content / "admission_demo_national_116.csv")
        import_seed_programs(content / "admission_demo_dayapply_115.csv")
        import_transfer_programs()
        from app.services import school_directory
        school_directory.import_defaults()  # 學校名錄：地區、座標、官網、招生網站
        db.session.flush()
        # 自傳要針對目標校系寫：示範學生先選一個資管相關校系，展示時才能直接生成自傳
        programs = published_programs()
        target = next((p for p in programs if "資訊管理" in p.department_name), programs[0] if programs else None)
        if target:
            db.session.add(StudentTarget(student_id=users["student"].id, rule_version_id=target.id))
        db.session.commit()
    app.wsgi_app = SerializedWSGI(app.wsgi_app)
    return app
