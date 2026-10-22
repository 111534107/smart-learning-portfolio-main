"""組員確認頁把年級存在 grade_level（例如「三年級」）；列表與「我的五年」也要讀得到（合成資料）。"""
from app import create_app
from app.extensions import db
from app.models import LearningCourseRecord, StudentProfile, User


def course(**fields):
    return LearningCourseRecord(course_name="模擬課程", normalized_course_name="模擬課程", **fields)


def test_year_for_placement_reads_teammate_grade_level_text():
    assert course(grade_level="三年級").year_for_placement == 3
    assert course(grade_level="5年級").year_for_placement == 5
    assert course(grade_level="一年級").year_for_placement == 1


def test_year_for_placement_prefers_school_year_and_ignores_unknown_text():
    assert course(school_year=2, grade_level="三年級").year_for_placement == 2
    assert course(school_year=113).year_for_placement == 113
    assert course(grade_level="不明").year_for_placement is None
    assert course().year_for_placement is None


def grade_app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        student = User(username="stu", display_name="合成學生", role="student")
        student.set_password("pw")
        db.session.add(student)
        db.session.flush()
        db.session.add(StudentProfile(user_id=student.id, student_no="SYN0001", admission_year=113))
        db.session.add(LearningCourseRecord(
            student_id=student.id, course_name="模擬資料結構", normalized_course_name="模擬資料結構",
            grade_level="三年級", semester="1", credits=3, score=88, confirmation_status="confirmed",
        ))
        db.session.commit()
    client = app.test_client()
    client.post("/login", data={"username": "stu", "password": "pw"})
    return client


def test_my_five_years_places_course_with_only_grade_level_into_that_grade(tmp_path):
    html = grade_app(tmp_path).get("/student/dashboard").get_data(as_text=True)

    folder = html.split('data-year-folder="3"', 1)[1].split("data-year-folder=", 1)[0]
    assert "模擬資料結構" in folder


def test_learning_profile_list_shows_grade_level_when_school_year_missing(tmp_path):
    html = grade_app(tmp_path).get("/student/learning-profile").get_data(as_text=True)

    row = html.split("模擬資料結構", 1)[0].rsplit("<tr>", 1)[1]
    assert "三年級" in row


def test_confirm_rejects_grade_level_above_students_current_grade(tmp_path):
    import io
    import json
    from datetime import date

    from app.models import SourceDocument
    from app.services.journey_service import academic_year_of

    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        student = User(username="stu1", display_name="合成一年級學生", role="student")
        student.set_password("pw")
        db.session.add(student)
        db.session.flush()
        # 今年入學＝一年級
        db.session.add(StudentProfile(user_id=student.id, student_no="SYN0002",
                                      admission_year=academic_year_of(date.today())))
        db.session.commit()
    client = app.test_client()
    client.post("/login", data={"username": "stu1", "password": "pw"})
    client.post("/student/learning-profile/documents", data={
        "document_type": "transcript", "file": (io.BytesIO(b"synthetic"), "synthetic.pdf"),
    }, content_type="multipart/form-data")
    with app.app_context():
        document = SourceDocument.query.one()
        document_id, revision = document.id, document.extraction.result_json["draft_revision"]

    response = client.post(f"/student/learning-profile/documents/{document_id}/review/confirm", data={
        "draft_revision": revision,
        "courses_json": json.dumps([{"course_name": "模擬專題", "credits": "3", "grade_level": "五年級"}]),
        "credentials_json": "[]",
    })

    assert response.status_code == 400
    with app.app_context():
        assert LearningCourseRecord.query.count() == 0
