from app import create_app
from app.extensions import db
from app.models import CourseRule, LearningCourseRecord, User
from app.services.learning_profile_service import generate_learning_profile_outputs


def learning_profile_app(tmp_path):
    app = create_app({
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "TESTING": True,
        "UPLOAD_FOLDER": str(tmp_path),
    })
    with app.app_context():
        db.create_all()
    return app


def test_output_generation_uses_confirmed_data_and_flags_rule_confirmation(tmp_path):
    app = learning_profile_app(tmp_path)
    with app.app_context():
        student = User(username="student_demo", display_name="測試學生甲", role="student")
        student.set_password("pw")
        db.session.add(student)
        db.session.flush()
        db.session.add_all([
            CourseRule(school_year=115, course_name="程式設計", normalized_course_name="程式設計", category="專業課程", requirement_type="required", credits=3, ability_domain="程式智能開發"),
            CourseRule(school_year=115, course_name="資料庫系統", normalized_course_name="資料庫系統", category="專業課程", requirement_type="required", credits=3, ability_domain="程式智能開發"),
            LearningCourseRecord(student_id=student.id, course_name="程式設計", normalized_course_name="程式設計", credits=3, score=92),
            LearningCourseRecord(student_id=student.id, course_name="資訊管理", normalized_course_name="資訊管理", credits=2, status_mark="抵"),
        ])
        db.session.commit()

        outputs = generate_learning_profile_outputs(student, school_year=115)

        assert set(outputs) == {"profile_summary", "curriculum_gap", "autobiography", "study_plan"}
        assert outputs["profile_summary"].content_json["ability_domains"][0]["name"] == "程式智能開發"
        assert outputs["curriculum_gap"].content_json["missing_required_courses"] == ["資料庫系統"]
        assert "測試學生甲" in outputs["autobiography"].content_json["draft"]
        assert "不代表正式畢業審查" in outputs["study_plan"].content_json["disclaimer"]
