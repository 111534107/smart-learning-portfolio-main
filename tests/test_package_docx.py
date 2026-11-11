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
    headings = [p.text for p in package.paragraphs if p.style.name == "Heading 1"]
    assert [line[:2] for line in headings] == [f"{n:02d}" for n in range(1, 10)]
    # 北商資管（115 簡章第 70 頁，2026-11-10 核對）：學習能力 30% 含成績、自傳讀書計畫、幹部社團；
    # 專業成果（專題）、證照各 30%；競賽只在「其他」10%。01 封面與目錄改成封面頁＋目錄頁，不再是章節。
    assert [line[3:] for line in headings] == [
        "報名資格證明", "歷年成績單與排名", "自傳", "讀書計畫", "證照證明",
        "專題／作品集", "社團與幹部經歷", "競賽成果", "其他有利審查資料",
    ]


# ---------- 正式排版（2026-11-12）：封面、目錄、課程與證照對照、未確認標示 ----------

def _seed_student(status="confirmed"):
    student = User(username="113534999", display_name="測試學生", role="student")
    student.set_password("pw")
    db.session.add(student)
    db.session.flush()
    db.session.add(StudentProfile(user_id=student.id, student_no="113534999", class_name="資管科三甲", admission_year=113))
    db.session.add(LearningCourseRecord(student_id=student.id, school_year=1, semester="上", course_name="計算機概論",
                                        normalized_course_name="計算機概論", credits=3, score=90))
    db.session.add(LearningCourseRecord(student_id=student.id, school_year=2, semester="上", course_name="國文",
                                        normalized_course_name="國文", credits=2, score=80))
    db.session.add(CredentialRecord(student_id=student.id, credential_name="電腦軟體應用丙級", level="丙級",
                                    issuing_organization="勞動部", issue_date=date(2025, 4, 12)))
    db.session.add(Portfolio(student_id=student.id, category="competition", school_year=2, semester=2,
                             title="商業類技藝競賽 佳作", description="電腦軟體應用組。", status="confirmed"))
    db.session.add(Portfolio(student_id=student.id, category="competition", title="未確認的比賽", status="draft"))
    program = AdmissionProgram.query.filter_by(program_code="208003").one()
    if status:
        db.session.add(PackageReview(student_id=student.id, rule_version_id=program.id, status=status))
    db.session.commit()
    return student, program


def _build(status):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        import_seed_programs()
        student, program = _seed_student(status)
        return Document(build_package_docx(student, program))


def _all_text(package):
    text = [p.text for p in package.paragraphs]
    text.extend(cell.text for table in package.tables for row in table.rows for cell in row.cells)
    return "\n".join(text)


def test_cover_lists_program_and_student_fields_before_toc():
    package = _build("confirmed")
    cover = package.tables[0]
    fields = {row.cells[0].text.rstrip("："): row.cells[1].text for row in cover.rows}
    assert fields["申請校系"].startswith("國立臺北商業大學 資訊管理系")
    assert fields["學生姓名"] == "測試學生"
    assert fields["學　　號"] == "113534999"
    assert fields["班　　級"] == "資管科三甲"
    assert "年" in fields["日　　期"] and "日" in fields["日　　期"]
    texts = [p.text for p in package.paragraphs]
    assert "備 審 資 料" in texts
    assert texts.index("備 審 資 料") < texts.index("目　錄")


def test_toc_lists_every_chapter_with_page_number_field():
    package = _build("confirmed")
    headings = [p.text for p in package.paragraphs if p.style.name == "Heading 1"]
    toc_lines = [p for p in package.paragraphs if "PAGEREF _Toc_ch" in p._p.xml]
    assert [line.text.split("\t")[0] for line in toc_lines] == headings
    body = package.element.body.xml
    for number in range(1, len(headings) + 1):
        assert f'w:name="_Toc_ch{number:02d}"' in body
    assert "updateFields" in package.settings.element.xml
    assert " PAGE " in package.sections[0].footer.paragraphs[0]._p.xml


def test_chapters_follow_program_weight_order():
    package = _build("confirmed")
    headings = [p.text[3:] for p in package.paragraphs if p.style.name == "Heading 1"]
    assert headings[0] == "報名資格證明"  # 固定在最前
    assert headings.index("證照證明") < headings.index("競賽成果")  # 證照 30% 在競賽 10% 前面


def test_course_credential_table_maps_courses_to_credentials_and_results():
    package = _build("confirmed")
    table = next(t for t in package.tables if t.rows[0].cells[0].text == "課程" and t.rows[0].cells[3].text == "對應證照")
    rows = {row.cells[0].text: [cell.text for cell in row.cells] for row in table.rows[1:]}
    assert "國文" not in rows  # 沒有對應的課程不列
    assert rows["計算機概論"][3] == "電腦軟體應用丙級"
    assert "商業類技藝競賽 佳作" in rows["計算機概論"][4]


def test_unconfirmed_package_is_marked_on_cover_header_and_chapters():
    package = _build("pending")
    text = _all_text(package)
    assert "本文件尚未經導師確認" in text
    assert "（本章內容尚未經導師確認）" in text
    assert "尚未經導師確認" in package.sections[0].header.paragraphs[0].text
    assert "未確認的比賽" not in text
    assert "另有 1 筆資料尚未確認" in text


def test_confirmed_package_has_no_unconfirmed_marks():
    package = _build("confirmed")
    assert "尚未經導師確認" not in _all_text(package)
    assert "尚未經導師確認" not in package.sections[0].header.paragraphs[0].text
