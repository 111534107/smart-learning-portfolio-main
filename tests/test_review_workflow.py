import pytest

from app import create_app
from app.extensions import db
from app.models import Portfolio, PortfolioSubmission, User
from app.services.review_service import assign_submission, create_revision, record_review_result


def review_app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        student = User(username="student", display_name="學生", role="student")
        teacher = User(username="teacher", display_name="教師", role="teacher")
        other_teacher = User(username="other-teacher", display_name="其他教師", role="teacher")
        staff = User(username="staff", display_name="科辦", role="staff")
        for user in (student, teacher, other_teacher, staff):
            user.set_password("pw")
            db.session.add(user)
        db.session.flush()
        portfolio = Portfolio(student_id=student.id, title="作品", category="其他")
        db.session.add(portfolio)
        db.session.flush()
        submission = PortfolioSubmission(portfolio_id=portfolio.id, version_no=1, status="submitted")
        db.session.add(submission)
        db.session.commit()
    return app


def test_only_assigned_teacher_can_view_submission():
    app = review_app()
    with app.app_context():
        submission = PortfolioSubmission.query.one()
        teacher = User.query.filter_by(username="teacher").one()
        other = User.query.filter_by(username="other-teacher").one()
        assignment = assign_submission(submission, teacher)
        db.session.commit()
        assert assignment.teacher_id == teacher.id
        assert submission.id in [item.submission_id for item in teacher.review_assignments]
        assert submission.id not in [item.submission_id for item in other.review_assignments]


def test_staff_can_record_common_result_and_teacher_cannot():
    app = review_app()
    with app.app_context():
        submission = PortfolioSubmission.query.one()
        teacher = User.query.filter_by(username="teacher").one()
        staff = User.query.filter_by(username="staff").one()
        with pytest.raises(PermissionError):
            record_review_result(submission, teacher, "approved", "no")
        result = record_review_result(submission, staff, "needs_revision", "請補件")
        db.session.commit()
        assert result.decision == "needs_revision"
        assert submission.status == "needs_revision"


def test_new_revision_preserves_v1():
    app = review_app()
    with app.app_context():
        submission = PortfolioSubmission.query.one()
        submission.status = "needs_revision"
        v2 = create_revision(submission)
        db.session.commit()
        assert v2.version_no == 2
        assert v2.previous_submission_id == submission.id
        assert submission.status == "needs_revision"
