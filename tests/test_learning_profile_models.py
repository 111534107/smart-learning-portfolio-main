from app import create_app
from app.extensions import db
from app.models import (
    CourseRule,
    CredentialRecord,
    DocumentExtraction,
    LearningCourseRecord,
    LearningProfileOutput,
    SourceDocument,
    StudentProfile,
    User,
)


def learning_profile_app(tmp_path):
    app = create_app({
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "TESTING": True,
        "UPLOAD_FOLDER": str(tmp_path),
    })
    with app.app_context():
        db.create_all()
    return app


def test_learning_profile_records_are_owned_by_immutable_user_id(tmp_path):
    app = learning_profile_app(tmp_path)
    with app.app_context():
        student = User(username="student_demo", display_name="測試學生甲", role="student")
        student.set_password("pw")
        db.session.add(student)
        db.session.flush()
        profile = StudentProfile(user_id=student.id, student_no="115534001")
        document = SourceDocument(
            owner_id=student.id,
            document_type="transcript",
            display_name="transcript.pdf",
            file_path="/safe/transcript.pdf",
            sha256="a" * 64,
        )
        db.session.add_all([profile, document])
        db.session.flush()
        extraction = DocumentExtraction(
            source_document_id=document.id,
            provider="fake",
            status="extracted",
            result_json={"courses": []},
        )
        db.session.add(extraction)
        db.session.commit()

        original_user_id = document.owner_id
        profile.student_no = "115534099"
        db.session.commit()

        assert document.owner_id == original_user_id == student.id
        assert document.owner.student_profile.student_no == "115534099"
        assert document.extraction.provider == "fake"


def test_confirmed_course_preserves_non_score_status_marks(tmp_path):
    app = learning_profile_app(tmp_path)
    with app.app_context():
        student = User(username="student_demo", display_name="測試學生甲", role="student")
        student.set_password("pw")
        db.session.add(student)
        db.session.flush()
        source_document = SourceDocument(
            owner_id=student.id,
            document_type="transcript",
            display_name="transcript.pdf",
            file_path="/safe/transcript.pdf",
            sha256="b" * 64,
        )
        db.session.add(source_document)
        db.session.flush()
        course = LearningCourseRecord(
            student_id=student.id,
            source_document_id=source_document.id,
            course_name="資訊管理",
            normalized_course_name="資訊管理",
            credits=2,
            status_mark="抵",
            confirmation_status="confirmed",
        )
        db.session.add(course)
        db.session.commit()

        assert course.score is None
        assert course.status_mark == "抵"
        assert course.is_score is False
        assert course.acquisition_status == "pending_rule_confirmation"


def test_course_rules_credentials_and_outputs_keep_auditable_snapshots(tmp_path):
    app = learning_profile_app(tmp_path)
    with app.app_context():
        student = User(username="student_demo", display_name="測試學生甲", role="student")
        student.set_password("pw")
        db.session.add(student)
        db.session.flush()
        rule = CourseRule(
            school_year=115,
            course_name="程式設計",
            normalized_course_name="程式設計",
            category="專業課程",
            requirement_type="required",
            credits=3,
            ability_domain="程式智能開發",
        )
        credential = CredentialRecord(
            student_id=student.id,
            credential_name="資訊技術類測試證照",
            level="丙級",
            issuing_organization="測試發證單位",
            confirmation_status="confirmed",
        )
        db.session.add_all([rule, credential])
        db.session.flush()
        output = LearningProfileOutput(
            student_id=student.id,
            output_type="profile_summary",
            content_json={"summary": "資料已確認"},
            source_snapshot_json={"course_rule_ids": [rule.id], "credential_ids": [credential.id]},
        )
        db.session.add(output)
        db.session.commit()

        assert CourseRule.query.one().ability_domain == "程式智能開發"
        assert CredentialRecord.query.one().confirmation_status == "confirmed"
        assert LearningProfileOutput.query.one().source_snapshot_json["course_rule_ids"] == [rule.id]
