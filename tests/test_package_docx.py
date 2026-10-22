from datetime import date

from docx import Document

from app import create_app
from app.extensions import db
from app.models import AdmissionProgram, CredentialRecord, LearningCourseRecord, PackageReview, Portfolio, StudentProfile, User
from app.services.admission_service import import_seed_programs
from app.services.package_service import build_package_docx


def test_package_follows_weighted_chapter_order_and_lists_records():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        import_seed_programs()
        student = User(username="111534105", display_name="王小明", role="student")
        student.set_password("pw")
        db.session.add(student)
        db.session.flush()
        db.session.add(StudentProfile(user_id=student.id, student_no="111534105", class_name="資管科三甲", admission_year=113))
        db.session.add(CredentialRecord(student_id=student.id, credential_name="網頁設計乙級", level="乙級", issue_date=date(2025, 11, 2)))
        db.session.add(LearningCourseRecord(student_id=student.id, course_name="已確認課程", normalized_course_name="已確認課程",
                                            score=90, confirmation_status="confirmed"))
        db.session.add(LearningCourseRecord(student_id=student.id, course_name="不可引用的草稿課程", normalized_course_name="不可引用的草稿課程",
                                            score=100, confirmation_status="draft"))
        db.session.add(CredentialRecord(student_id=student.id, credential_name="不可引用的草稿證照", confirmation_status="draft"))
        db.session.add(Portfolio(student_id=student.id, title="班級學藝股長", category="leadership", school_year=2, status="confirmed"))
        program = AdmissionProgram.query.filter_by(program_code="208003").one()
        db.session.add(PackageReview(student_id=student.id, rule_version_id=program.id, status="confirmed"))
        db.session.commit()

        stream = build_package_docx(student, program)

    package = Document(stream)
    text = [paragraph.text for paragraph in package.paragraphs]
    text.extend(cell.text for table in package.tables for row in table.rows for cell in row.cells)
    joined = "\n".join(text)
    assert "國立臺北商業大學" in joined
    assert "導師已確認" in joined
    assert "網頁設計乙級" in joined
    assert "已確認課程" in joined
    assert "不可引用的草稿" not in joined
    assert "班級學藝股長" in joined
    headings = [line for line in text if line[:2].isdigit() and "　" in line]
    assert [line[:2] for line in headings] == [f"{n:02d}" for n in range(1, 11)]
    # 北商資管：成績、證照、競賽、專題各 30%；活動／服務 10%；自傳、讀書計畫不在加權項目中
    assert [line[3:] for line in headings] == [
        "封面與目錄", "報名資格證明", "歷年成績單與排名", "證照證明", "競賽成果",
        "專題／作品集", "社團與幹部經歷", "其他有利審查資料", "自傳", "讀書計畫",
    ]
