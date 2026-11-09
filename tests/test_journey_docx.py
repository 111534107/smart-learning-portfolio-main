"""五年資料匯出成可修改的 Word（評審意見 7，2026-11-10）。合成假資料。"""
import io
from datetime import date

from docx import Document

from app import create_app
from app.extensions import db
from app.models import AuditLog, CredentialRecord, LearningCourseRecord, Portfolio, StudentProfile, User


def make_app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "WTF_CSRF_ENABLED": False, "TWO_FACTOR_REQUIRED": False})
    with app.app_context():
        db.create_all()
        user = User(username="stu", display_name="合成學生", role="student")
        user.set_password("pw")
        db.session.add(user)
        db.session.flush()
        db.session.add(StudentProfile(user_id=user.id, student_no="111000001", class_name="資五甲", admission_year=111))
        db.session.add(LearningCourseRecord(student_id=user.id, course_name="資料庫系統", normalized_course_name="資料庫系統",
                                            credits=3, score=88, school_year=113, semester=1, confirmation_status="confirmed"))
        db.session.add(LearningCourseRecord(student_id=user.id, course_name="草稿課程", normalized_course_name="草稿課程",
                                            credits=2, score=70, school_year=113, semester=1, confirmation_status="draft"))
        db.session.add(CredentialRecord(student_id=user.id, credential_name="電腦軟體應用丙級", issue_date=date(2024, 5, 1),
                                        confirmation_status="confirmed"))
        db.session.add(Portfolio(student_id=user.id, title="資訊競賽佳作", category="competition", status="confirmed",
                                 school_year=3, role="負責資料庫設計", learned="學會分工"))
        db.session.commit()
    return app


def test_student_downloads_editable_word():
    app = make_app()
    client = app.test_client()
    client.post("/login", data={"username": "stu", "password": "pw"})
    menu = client.get("/student/learning-profile", follow_redirects=True).get_data(as_text=True)
    assert 'href="/student/journey.docx"' in menu
    response = client.get("/student/journey.docx")
    assert response.status_code == 200 and "wordprocessingml" in response.mimetype
    text = "\n".join(p.text for p in Document(io.BytesIO(response.data)).paragraphs)
    tables = Document(io.BytesIO(response.data)).tables
    cells = [cell.text for table in tables for row in table.rows for cell in row.cells]
    assert "合成學生 的五年學習歷程" in text and "111000001" in text
    assert "資料庫系統" in cells and "88" in cells and "草稿課程" not in cells  # 只放已確認
    assert "電腦軟體應用丙級" in text and "資訊競賽佳作（專三）" in text and "我負責的部分：負責資料庫設計" in text
    with app.app_context():
        assert AuditLog.query.filter_by(action="student.journey_docx").count() == 1


def test_only_students_can_export():
    app = make_app()
    assert app.test_client().get("/student/journey.docx").status_code == 401
