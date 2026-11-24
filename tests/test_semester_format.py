"""B25（2026-11-14 假學生實測）：辨識送來「第一學期／第二學期」，系統統一存「上／下」。（僅為測試資料）

之前原字存進資料庫，畢業門檻只認「上／下」：有成績的學期被判沒有資料、同一門課「上」與「第一學期」變兩筆。
"""
import json
from datetime import date

import pytest
from sqlalchemy import text

from app import create_app
from app.extensions import db
from app.models import DocumentExtraction, LearningCourseRecord, SourceDocument, StudentProfile, User
from app.services import graduation_check_service as svc


def make_app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        user = User(username="sem_student", display_name="sem_student", role="student")
        user.set_password("pw")
        db.session.add(user)
        db.session.flush()
        db.session.add(StudentProfile(user_id=user.id, student_no="sem_student", class_name="資管科三甲",
                                      admission_year=113))
        document = SourceDocument(owner_id=user.id, document_type="transcript", display_name="t.png",
                                  file_path=str(tmp_path / "t.png"), sha256="d" * 64, status="extracted")
        db.session.add(document)
        db.session.flush()
        db.session.add(DocumentExtraction(source_document_id=document.id, provider="fake", status="extracted",
                                          result_json={"courses": []}))
        db.session.commit()
        return app, user.id, document.id


def confirm(app, document_id, courses):
    client = app.test_client()
    client.post("/login", data={"username": "sem_student", "password": "pw"})
    response = client.post(f"/student/learning-profile/documents/{document_id}/review/confirm", data={
        "scores_unlocked": "1", "courses_json": json.dumps(courses), "credentials_json": "[]"})
    assert response.status_code == 302


@pytest.mark.parametrize("raw, stored", [
    ("第一學期", "上"), ("第二學期", "下"), ("上學期", "上"), ("下學期", "下"),
    ("上", "上"), ("下", "下"), ("1", "上"), ("二", "下"),
])
def test_normalize_semester(raw, stored):
    assert svc.normalize_semester(raw) == stored


def test_ocr_semester_words_are_stored_as_up_down(tmp_path):
    app, _, document_id = make_app(tmp_path)
    confirm(app, document_id, [
        {"course_name": "程式設計", "credits": 3, "score": 91, "grade_level": "一年級", "semester": "第一學期"},
        {"course_name": "網頁設計", "credits": 3, "score": 93, "grade_level": "一年級", "semester": "第二學期"},
    ])
    with app.app_context():
        assert [c.semester for c in LearningCourseRecord.query.order_by(LearningCourseRecord.id)] == ["上", "下"]


def test_ocr_upload_updates_existing_up_down_course_instead_of_adding(tmp_path):
    app, user_id, document_id = make_app(tmp_path)
    with app.app_context():
        db.session.add(LearningCourseRecord(student_id=user_id, school_year=1, semester="上", course_name="計算機概論",
                                            normalized_course_name="計算機概論", credits=3, score=88,
                                            confirmation_status="confirmed"))
        db.session.commit()
    confirm(app, document_id, [
        {"course_name": "計算機概論", "credits": 3, "score": 86, "grade_level": "一年級", "semester": "第一學期"}])
    with app.app_context():
        courses = LearningCourseRecord.query.all()
        assert [(c.course_name, c.semester, c.score) for c in courses] == [("計算機概論", "上", 86)]


def test_terms_with_ocr_courses_are_not_reported_missing(tmp_path):
    app, user_id, document_id = make_app(tmp_path)
    confirm(app, document_id, [
        {"course_name": "程式設計", "credits": 3, "score": 91, "grade_level": "一年級", "semester": "第一學期"},
        {"course_name": "網頁設計", "credits": 3, "score": 93, "grade_level": "一年級", "semester": "第二學期"},
    ])
    with app.app_context():
        student = db.session.get(User, user_id)
        assert svc._missing_terms(student, 113, [(113, "上"), (113, "下")]) == []


def test_old_rows_saved_as_first_semester_still_match(tmp_path):
    """遷移前留下的「第一學期」舊資料，去重與學期判斷也要認得。"""
    a = LearningCourseRecord(school_year=1, semester="上", course_name="程式設計")
    b = LearningCourseRecord(school_year=1, semester="第一學期", course_name="程式設計")
    assert svc.course_term_key(a, 113) == svc.course_term_key(b, 113)


def test_migration_rewrites_old_semester_words(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'sem.db'}", "TESTING": True})
    runner = app.test_cli_runner()
    with app.app_context():
        db.session.execute(text("CREATE TABLE learning_course_records "
                                "(id INTEGER PRIMARY KEY, course_name VARCHAR(150) NOT NULL, semester VARCHAR(20))"))
        db.session.execute(text("INSERT INTO learning_course_records (id, course_name, semester) VALUES "
                                "(1, 'a', '第一學期'), (2, 'b', '第二學期'), (3, 'c', '上學期'), (4, 'd', '下'), "
                                "(5, 'e', NULL), (6, 'f', '寒修')"))
        db.session.commit()
    assert runner.invoke(args=["db", "stamp", "b20261114p01"]).exit_code == 0
    result = runner.invoke(args=["db", "upgrade"])
    assert result.exit_code == 0, result.output
    with app.app_context():
        rows = db.session.execute(text("SELECT semester FROM learning_course_records ORDER BY id")).scalars().all()
        assert rows == ["上", "下", "上", "下", None, "寒修"]
