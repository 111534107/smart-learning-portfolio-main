"""重複上傳成績單：同一學年（年級）、同一學期、同一門課只存一筆，畢業門檻也只算一次。（僅為測試資料）"""
import json

from app.extensions import db
from app.models import DocumentExtraction, LearningCourseRecord, SourceDocument, StudentProfile, User
from app.services import graduation_check_service as svc
from tests.test_learning_profile_confirmation import learning_profile_app, login


def _second_document(app, tmp_path):
    with app.app_context():
        owner = User.query.filter_by(username="student_demo").one()
        document = SourceDocument(owner_id=owner.id, document_type="transcript", display_name="transcript-2.pdf",
                                  file_path=str(tmp_path / "transcript-2.pdf"), sha256="d" * 64, status="extracted")
        db.session.add(document)
        db.session.flush()
        db.session.add(DocumentExtraction(source_document_id=document.id, provider="fake", status="extracted",
                                          result_json={"courses": []}))
        db.session.commit()
        return document.id


def _confirm(client, document_id, courses):
    return client.post(f"/student/learning-profile/documents/{document_id}/review/confirm", data={
        "scores_unlocked": "1", "courses_json": json.dumps(courses), "credentials_json": "[]"})


def test_reuploading_same_course_and_term_keeps_one_record(tmp_path):
    app, first = learning_profile_app(tmp_path)
    second = _second_document(app, tmp_path)
    client = app.test_client()
    login(client)

    assert _confirm(client, first, [
        {"course_name": "國文", "credits": 2, "score": 70, "grade_level": "一年級", "semester": "上"},
    ]).status_code == 302
    # 專四時上傳的歷年成績單又列出同一門課，並多了新學期的課
    assert _confirm(client, second, [
        {"course_name": "國文", "credits": 2, "score": 75, "grade_level": "一年級", "semester": "上"},
        {"course_name": "國文", "credits": 2, "score": 80, "grade_level": "一年級", "semester": "下"},
    ]).status_code == 302

    with app.app_context():
        rows = LearningCourseRecord.query.order_by(LearningCourseRecord.id).all()
        assert [(r.course_name, r.grade_level, r.semester, r.score) for r in rows] == [
            ("國文", "一年級", "上", 75),   # 以後上傳的那份為準
            ("國文", "一年級", "下", 80),
        ]


def test_courses_without_term_are_not_merged(tmp_path):
    app, first = learning_profile_app(tmp_path)
    second = _second_document(app, tmp_path)
    client = app.test_client()
    login(client)

    _confirm(client, first, [{"course_name": "程式設計", "credits": 3, "score": 90}])
    _confirm(client, second, [{"course_name": "程式設計", "credits": 3, "score": 90}])

    with app.app_context():
        assert LearningCourseRecord.query.count() == 2   # 沒有年級與學期，無法判斷是不是同一門課


def test_credit_status_counts_existing_duplicates_once(tmp_path):
    app, _ = learning_profile_app(tmp_path)
    with app.app_context():
        student = User.query.filter_by(username="student_demo").one()
        db.session.add(StudentProfile(user_id=student.id, student_no="s1", class_name="資管科五甲", admission_year=111))
        for _ in range(2):   # 舊資料：同一門課存了兩筆
            db.session.add(LearningCourseRecord(student_id=student.id, course_name="國文", normalized_course_name="國文",
                                                school_year=1, semester="上", credits=8, score=80,
                                                confirmation_status="confirmed"))
        db.session.add(LearningCourseRecord(student_id=student.id, course_name="國文", normalized_course_name="國文",
                                            school_year=1, semester="下", credits=8, score=80,
                                            confirmation_status="confirmed"))
        db.session.flush()

        credits = svc.credit_status(student)

        assert credits["earned"]["required"] == 16
        assert credits["duplicates"] == ["國文"]
        db.session.commit()

    client = app.test_client()
    login(client)
    html = client.get("/student/graduation-check").get_data(as_text=True)
    assert "同一學期只計算一次：國文" in html
