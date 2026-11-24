import pytest

from app import create_app
from app.extensions import db
from app.models import (
    AdmissionProgram,
    LearningCourseRecord,
    PackageReview,
    SourceDocument,
    StudentProfile,
    StudentTarget,
    User,
)
from app.services.admission_service import import_seed_programs
from app.services.student_progress import student_progress


@pytest.fixture()
def student():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context(), app.test_request_context():
        db.create_all()
        import_seed_programs()
        user = User(username="s", display_name="s", role="student")
        user.set_password("pw")
        db.session.add(user)
        db.session.flush()
        db.session.add(StudentProfile(user_id=user.id, student_no="s", class_name="甲", admission_year=113))
        db.session.commit()
        yield user


def states(progress):
    return [step["state"] for step in progress["steps"]]


def test_new_student_starts_by_uploading_transcript(student):
    progress = student_progress(student)

    assert states(progress) == ["current", "todo", "todo", "todo"]
    assert "成績單" in progress["next"]["text"]


def test_unconfirmed_upload_is_the_next_action(student):
    db.session.add(SourceDocument(owner_id=student.id, document_type="transcript", display_name="t.pdf",
                                  file_path="x", sha256="0" * 64, status="extracted"))
    db.session.commit()

    assert "確認" in student_progress(student)["next"]["text"]


def test_after_grades_next_step_is_choosing_target(student):
    db.session.add(LearningCourseRecord(student_id=student.id, school_year=1, course_name="程式",
                                        normalized_course_name="程式", score=90))
    db.session.commit()

    progress = student_progress(student)

    assert states(progress) == ["done", "current", "todo", "todo"]
    assert "目標校系" in progress["next"]["text"]


def test_with_target_next_action_points_to_heaviest_missing_item(student):
    db.session.add(LearningCourseRecord(student_id=student.id, school_year=1, course_name="程式",
                                        normalized_course_name="程式", score=90))
    program = AdmissionProgram.query.filter_by(program_code="208003").one()
    db.session.add(StudentTarget(student_id=student.id, rule_version_id=program.id))
    db.session.commit()

    progress = student_progress(student)

    assert states(progress)[:3] == ["done", "done", "current"]
    # 北商資管加權最高且還沒資料的項目之一：證照證明（30%）或專業成果（30%）
    assert "30%" in progress["next"]["text"]


def test_confirmed_review_marks_last_step_done(student):
    program = AdmissionProgram.query.filter_by(program_code="208003").one()
    db.session.add(LearningCourseRecord(student_id=student.id, school_year=1, course_name="程式",
                                        normalized_course_name="程式", score=90))
    db.session.add(StudentTarget(student_id=student.id, rule_version_id=program.id))
    db.session.add(PackageReview(student_id=student.id, rule_version_id=program.id, status="confirmed"))
    db.session.commit()

    progress = student_progress(student)

    assert progress["steps"][3]["state"] == "done"
