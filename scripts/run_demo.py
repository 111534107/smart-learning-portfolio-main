"""用測試資料啟動展示版網站（SQLite，不會連到 MySQL）。

用法（在專案根目錄）：
    .venv\\Scripts\\python.exe scripts\\run_demo.py
然後打開 http://127.0.0.1:5000

展示帳號（皆為假資料）：
    學生  111534105 / demo1234（王小明，還沒選目標校系）
    學生  111534107 / demo1234（林小美，已送導師確認）
    導師  teacher01 / demo1234（負責資管科三甲）
    科辦  staff01   / demo1234（林科助，核准電子獎狀）
    管理者 admin     / demo1234
每次啟動都會重建 instance/demo.db。
"""

import os
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from app import create_app  # noqa: E402
from real_ocr import real_ocr_provider  # noqa: E402
from app.extensions import db  # noqa: E402
from app.services.admission_service import import_seed_programs  # noqa: E402
from app.services.transfer_exam import import_transfer_programs  # noqa: E402
from app.services import certificate_service, review_snapshot_service  # noqa: E402
from app.models import (  # noqa: E402
    AdmissionProgram,
    AwardCertificate,
    ClassAdvisor,
    CredentialRecord,
    StudentTarget,
    LearningCourseRecord,
    Portfolio,
    StudentProfile,
    User,
)

DEMO_PASSWORD = "demo1234"

# 登入頁「Demo 快速登入」列出的帳號，和 seed() 建立的帳號一致
DEMO_ACCOUNTS = [
    {"role": "student", "label": "學生", "username": "111534105", "password": DEMO_PASSWORD,
     "name": "王小明", "note": "還沒選目標校系"},
    {"role": "student", "label": "學生", "username": "111534107", "password": DEMO_PASSWORD,
     "name": "林小美", "note": "已送導師確認"},
    {"role": "teacher", "label": "導師", "username": "teacher01", "password": DEMO_PASSWORD,
     "name": "陳導師", "note": "負責資管科三甲"},
    {"role": "staff", "label": "科辦", "username": "staff01", "password": DEMO_PASSWORD,
     "name": "林科助", "note": "核准電子獎狀"},
    {"role": "admin", "label": "管理者", "username": "admin", "password": DEMO_PASSWORD, "name": "系統管理者"},
]


def seed():
    student = User(username="111534105", display_name="王小明", role="student")
    teacher = User(username="teacher01", display_name="陳導師", role="teacher")
    admin = User(username="admin", display_name="系統管理者", role="admin")
    staff = User(username="staff01", display_name="林科助", role="staff")
    for user in (student, teacher, admin, staff):
        user.set_password(DEMO_PASSWORD)
        db.session.add(user)
    db.session.flush()
    db.session.add(StudentProfile(user_id=student.id, student_no="111534105", class_name="資管科三甲", admission_year=113))

    courses = [
        (1, "上", "計算機概論", 3, 88), (1, "下", "程式設計（一）", 3, 91), (1, "下", "國文", 2, 82),
        (2, "上", "資料庫管理實務(SQL)", 3, 85), (2, "下", "網頁設計", 3, 93), (3, "上", "系統分析與設計", 3, 79),
    ]
    for year, semester, name, credits, score in courses:
        db.session.add(LearningCourseRecord(
            student_id=student.id, school_year=year, semester=semester, course_name=name,
            normalized_course_name="".join(name.split()), credits=credits, score=score,
        ))
    db.session.add(CredentialRecord(student_id=student.id, credential_name="電腦軟體應用丙級", level="丙級",
                                    issuing_organization="勞動部", issue_date=date(2025, 5, 20)))
    db.session.add(CredentialRecord(student_id=student.id, credential_name="網頁設計乙級", level="乙級",
                                    issuing_organization="勞動部", issue_date=date(2025, 11, 2)))
    # 最後一筆還沒確認：展示「確認過的經歷才會被 AI 寫進自傳」
    records = [
        ("activity", 1, 1, "資管科迎新宿營", "擔任小隊輔，帶領新生認識校園。", "confirmed"),
        ("service", 2, 1, "資訊週志工", "協助活動報到與場地引導。", "confirmed"),
        ("leadership", 2, 2, "班級學藝股長", "負責班級公告與學習資料整理。", "confirmed"),
        ("activity", 3, 1, "校園黑客松", "三人一組，兩天內完成活動報名網站。", "draft"),
    ]
    for category, year, semester, title, description, status in records:
        db.session.add(Portfolio(student_id=student.id, category=category, school_year=year, semester=semester,
                                 title=title, description=description, status=status))
    db.session.commit()

    # 主線後半：校系資料、導師班級，以及一位已送導師確認的同學
    import_seed_programs()
    # 展示用：再補上 PDF 裡所有國立校系，讓「選很多校系」的畫面有足夠的資料
    import_seed_programs(PROJECT_ROOT / "app" / "content" / "admission_demo_national_116.csv")
    import_seed_programs(PROJECT_ROOT / "app" / "content" / "admission_demo_dayapply_115.csv")
    # 插大（轉學考）：北中南資訊相關科系的示範資料（官方簡章，見 CSV 的出處欄）
    import_transfer_programs()
    db.session.add(ClassAdvisor(teacher_id=teacher.id, class_name="資管科三甲", school_year=115))
    classmate = User(username="111534107", display_name="林小美", role="student")
    classmate.set_password(DEMO_PASSWORD)
    db.session.add(classmate)
    db.session.flush()
    db.session.add(StudentProfile(user_id=classmate.id, student_no="111534107", class_name="資管科三甲", admission_year=113))
    db.session.add(LearningCourseRecord(student_id=classmate.id, school_year=1, semester="上", course_name="計算機概論",
                                        normalized_course_name="計算機概論", credits=3, score=90))
    # 113 學年度課綱的資訊類專業科目各一門，學群才判斷得出來（只有計算機概論時對不到課綱，推薦排序會亂）
    for year, semester, name, score in ((1, "下", "程式設計", 88), (2, "上", "網頁設計", 85), (2, "下", "管理資訊系統", 82)):
        db.session.add(LearningCourseRecord(student_id=classmate.id, school_year=year, semester=semester, course_name=name,
                                            normalized_course_name=name, credits=3, score=score))
    db.session.add(CredentialRecord(student_id=classmate.id, credential_name="電腦軟體應用丙級", level="丙級",
                                    issuing_organization="勞動部", issue_date=date(2025, 4, 12)))
    db.session.add(Portfolio(student_id=classmate.id, category="competition", school_year=2, semester=2,
                             title="全國商業類技藝競賽 佳作", description="電腦軟體應用組。", status="confirmed"))
    # 從學校獎懲記錄匯入的科上派服務，已申請電子獎狀，等科辦核准
    service_record = Portfolio(student_id=classmate.id, category="service", school_year=2, semester=1,
                               title="1141學期協助資管科麗山國中社團活動共1次", description="2025/12/30 嘉獎1次",
                               source="award_record", status="confirmed")
    db.session.add(service_record)
    db.session.flush()
    db.session.add(AwardCertificate(student_id=classmate.id, portfolio=service_record, status="pending",
                                    title=certificate_service.KINDS["service"], issuer=certificate_service.DEFAULT_ISSUER,
                                    body=certificate_service.default_body(service_record)))
    program = AdmissionProgram.query.filter_by(program_code="208003").one()
    db.session.add(StudentTarget(student_id=classmate.id, rule_version_id=program.id))
    db.session.flush()
    db.session.commit()
    review_snapshot_service.request_review(classmate, program)  # 送審時存快照


def main():
    port = int(os.getenv("DEMO_PORT", "5000"))
    # 不同埠號用不同資料庫檔，可以同時開兩個展示網站
    demo_db = PROJECT_ROOT / "instance" / ("demo.db" if port == 5000 else f"demo-{port}.db")
    demo_db.parent.mkdir(parents=True, exist_ok=True)
    try:
        demo_db.unlink(missing_ok=True)
    except PermissionError:
        print(f"展示網站好像已經在執行了（{demo_db.name} 正在使用中）。")
        print(f"請直接打開 http://127.0.0.1:{port} ，或先關掉另一個視窗的展示網站（按 Ctrl+C）再重新啟動。")
        print("想同時開兩個，可以換埠號：$env:DEMO_PORT=5001 再執行一次。")
        sys.exit(1)
    app = create_app({
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{demo_db.as_posix()}",
        "UPLOAD_FOLDER": str(PROJECT_ROOT / "instance" / "demo-uploads"),
        "DEMO_ACCOUNTS": DEMO_ACCOUNTS,  # 登入頁顯示展示帳號；正式環境不要設定
        # 瀏覽器的 cookie 只分主機、不分埠：同時開 5020、5021 會互相蓋掉登入（10-27 實測問題 6）
        "SESSION_COOKIE_NAME": f"demo_session_{port}",
    })
    app.config["DOCUMENT_ANALYSIS_PROVIDER"] = real_ocr_provider(app.config["DOCUMENT_ANALYSIS_PROVIDER"])
    print(f"OCR 模式：{app.config['DOCUMENT_ANALYSIS_PROVIDER']}")
    with app.app_context():
        db.create_all()
        seed()
    print(f"展示網站：http://127.0.0.1:{port}")
    print(f"帳號（密碼都是 {DEMO_PASSWORD}）：學生 111534105、111534107｜導師 teacher01｜科辦 staff01｜管理者 admin")
    app.run(port=port, debug=False)


if __name__ == "__main__":
    main()
