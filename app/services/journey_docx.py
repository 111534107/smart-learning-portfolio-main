"""把學生的五年資料匯出成可以修改的 Word（11-05 評審意見 7，2026-11-10）。

內容：基本資料、各學年成績（表格）、證照、經歷（活動、競賽、服務、幹部，含負責內容、成果、學到什麼）。
只放已確認的成績與證照、沒被刪除的經歷；放不進年級的資料列在「未分年級」。
匯出後學生可以在 Word 裡自由修改，再拿去做書面報告或備審資料。
"""
from collections import defaultdict
from datetime import date
from io import BytesIO

from docx import Document
from docx.shared import Pt

from app.models import CredentialRecord, LearningCourseRecord, Portfolio
from app.services.journey_service import (CATEGORY_LABELS, EXPERIENCE_CATEGORIES, GRADE_LABELS, academic_year_of,
                                         grade_for)

UNSORTED = "未分年級"


def _grade_label(grade):
    return GRADE_LABELS.get(grade, UNSORTED)


def _set_font(document):
    style = document.styles["Normal"]
    style.font.name = "Microsoft JhengHei"
    style.font.size = Pt(11)
    style.element.rPr.rFonts.set("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia",
                                 "Microsoft JhengHei")


def build(student, today=None):
    profile = student.student_profile
    admission = profile.admission_year if profile else None
    document = Document()
    _set_font(document)
    document.add_heading(f"{student.display_name} 的五年學習歷程", level=0)
    info = [f"學號：{profile.student_no}" if profile else "",
            f"班級：{profile.class_name}" if profile and profile.class_name else "",
            f"入學學年度：{admission}" if admission else "",
            f"匯出日期：{(today or date.today()).isoformat()}"]
    document.add_paragraph("　".join(part for part in info if part))
    document.add_paragraph("這份文件由學習歷程系統匯出，只包含已確認的成績與證照，以及你的經歷。可以直接在 Word 裡修改。")

    courses = (LearningCourseRecord.query.filter_by(student_id=student.id, confirmation_status="confirmed")
               .order_by(LearningCourseRecord.school_year, LearningCourseRecord.semester, LearningCourseRecord.id).all())
    by_grade = defaultdict(list)
    for course in courses:
        by_grade[grade_for(course.year_for_placement, admission)].append(course)
    document.add_heading("一、成績", level=1)
    if not courses:
        document.add_paragraph("還沒有已確認的成績。")
    for grade in sorted(by_grade, key=lambda value: value or 99):
        rows = by_grade[grade]
        passed = sum(course.credits or 0 for course in rows if course.acquisition_status == "passed")
        scores = [course.score for course in rows if course.score is not None]
        average = f"，平均 {sum(scores) / len(scores):.1f} 分" if scores else ""
        document.add_heading(f"{_grade_label(grade)}（及格 {passed} 學分{average}）", level=2)
        table = document.add_table(rows=1, cols=4)
        table.style = "Table Grid"
        for cell, text in zip(table.rows[0].cells, ("學期", "科目", "學分", "成績")):
            cell.text = text
        for course in rows:
            cells = table.add_row().cells
            cells[0].text = str(course.semester or "")
            cells[1].text = course.course_name
            cells[2].text = "" if course.credits is None else str(course.credits)
            cells[3].text = str(course.score) if course.score is not None else (course.status_mark or "")

    document.add_heading("二、證照", level=1)
    credentials = (CredentialRecord.query.filter_by(student_id=student.id, confirmation_status="confirmed")
                   .order_by(CredentialRecord.issue_date, CredentialRecord.id).all())
    if not credentials:
        document.add_paragraph("還沒有已確認的證照。")
    for credential in credentials:
        year = academic_year_of(credential.issue_date) if credential.issue_date else None
        parts = [credential.credential_name, credential.level or "",
                 credential.issue_date.isoformat() if credential.issue_date else "", _grade_label(grade_for(year, admission))]
        document.add_paragraph("　".join(part for part in parts if part), style="List Bullet")

    document.add_heading("三、經歷", level=1)
    records = Portfolio.active().filter_by(student_id=student.id).order_by(Portfolio.school_year, Portfolio.id).all()
    records = [record for record in records if record.category in EXPERIENCE_CATEGORIES]
    if not records:
        document.add_paragraph("還沒有經歷。")
    for category in EXPERIENCE_CATEGORIES:
        items = [record for record in records if record.category == category]
        if not items:
            continue
        document.add_heading(CATEGORY_LABELS[category], level=2)
        for record in items:
            grade = _grade_label(grade_for(record.school_year, admission))
            document.add_paragraph(f"{record.title}（{grade}）", style="List Bullet")
            for label, value in (("內容", record.description), ("我負責的部分", record.role),
                                 ("成果", record.achievement), ("學到什麼", record.learned)):
                if value:
                    document.add_paragraph(f"{label}：{value}")

    stream = BytesIO()
    document.save(stream)
    stream.seek(0)
    return stream
