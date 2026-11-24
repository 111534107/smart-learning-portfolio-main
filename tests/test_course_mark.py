"""成績單「選課別」（必／選）：OCR 抓取、存檔、畢業門檻補算。（僅為測試資料）"""
from pathlib import Path

import pytest

from app import create_app
from app.extensions import db
from app.models import LearningCourseRecord, StudentProfile, User
from app.services import graduation_check_service as check
from app.services.ocr_pipeline import parse_panel_words


def _word(text, x, y):
    return {"text": text, "bbox": [x, y, x + 30, y + 14], "confidence": .99}


def test_parse_panel_reads_course_mark_column():
    size = (1000, 1000)
    edges = [width for width in (60, 650, 735, 820, 900, 1000)]
    edges = [60 * 0, 60, 650, 735, 820, 900, 1000]
    rows = []
    for index, (mark, name) in enumerate((("必", "康寧全人教育"), ("|選", "會計學"), ("|4", "音樂"))):
        y = 200 + index * 40
        rows += [_word(mark, 20, y), _word(name, 100, y), _word("2", 680, y), _word("86", 760, y)]
    courses = parse_panel_words(rows, size, 0, body=(100, 600), columns=edges, layout_verified=True)
    marks = {c["course_name"]: c["course_mark"] for c in courses}
    assert marks == {"康寧全人教育": "必", "會計學": "選", "音樂": None}


@pytest.fixture()
def student_app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite://", "TESTING": True, "SECRET_KEY": "t"})
    with app.app_context():
        db.create_all()
        user = User(username="mark_demo", display_name="選課別測試（僅為測試資料）", role="student")
        user.set_password("demo2026")
        db.session.add(user)
        db.session.flush()
        db.session.add(StudentProfile(user_id=user.id, student_no="113000001", class_name="測試班", admission_year=113))
        db.session.commit()
        yield app, user


def _add(user, name, credits, mark):
    db.session.add(LearningCourseRecord(
        student_id=user.id, school_year=113, semester="第一學期", grade_level="1年級", course_name=name,
        normalized_course_name=name, credits=credits, score=80, course_mark=mark, confirmation_status="confirmed"))


def test_unmatched_course_counts_by_mark(student_app):
    app, user = student_app
    with app.app_context():
        user = db.session.get(User, user.id)
        _add(user, "科目表查不到的必修課", 3, "必")
        _add(user, "科目表查不到的選修課", 2, "選")
        _add(user, "科目表查不到沒標記", 4, None)
        db.session.commit()
        result = check.credit_status(user, curriculum={113: {"某課": {"name": "某課", "category": "專業必修"}}})
        assert result["earned"] == {"required": 3, "elective": 2, "total": 5}
        assert len(result["unmatched"]) == 3  # 仍列待科辦確認，不會悄悄消失
