from app import create_app
from app.extensions import db
from app.models import CourseRule, LearningCourseRecord, User


def learning_profile_app(tmp_path):
    app = create_app({
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "TESTING": True,
        "UPLOAD_FOLDER": str(tmp_path),
    })
    with app.app_context():
        db.create_all()
        student = User(username="student_demo", display_name="測試學生甲", role="student")
        student.set_password("pw")
        db.session.add(student)
        db.session.flush()
        db.session.add_all([
            CourseRule(school_year=115, course_name="程式設計", normalized_course_name="程式設計", category="專業課程", requirement_type="required", credits=3, ability_domain="程式智能開發"),
            LearningCourseRecord(student_id=student.id, course_name="程式設計", normalized_course_name="程式設計", credits=3, score=92),
        ])
        db.session.commit()
    return app


def test_student_can_generate_and_download_own_word_output(tmp_path):
    app = learning_profile_app(tmp_path)
    client = app.test_client()
    client.post("/login", data={"username": "student_demo", "password": "pw"})

    generate_response = client.post("/student/learning-profile/generate", data={"school_year": "115"})
    assert generate_response.status_code == 302

    with app.app_context():
        from app.models import LearningProfileOutput
        output_id = LearningProfileOutput.query.filter_by(output_type="profile_summary").one().id

    download_response = client.get(f"/student/learning-profile/outputs/{output_id}/docx")
    assert download_response.status_code == 200
    assert download_response.headers["Content-Type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert download_response.data.startswith(b"PK")
