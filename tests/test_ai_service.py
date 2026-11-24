import pytest

from app import create_app
from app.extensions import db
from app.models import AgentTask, Portfolio, PortfolioEvidence, PortfolioSubmission, User
from app.services.ai_service import run_evidence_check


def ai_app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        student = User(username="student", display_name="學生", role="student")
        teacher = User(username="teacher", display_name="教師", role="teacher")
        for user in (student, teacher):
            user.set_password("pw")
            db.session.add(user)
        db.session.flush()
        portfolio = Portfolio(student_id=student.id, title="作品", category="其他", status="submitted")
        db.session.add(portfolio)
        db.session.flush()
        submission = PortfolioSubmission(portfolio_id=portfolio.id, version_no=1, status="submitted")
        db.session.add(submission)
        db.session.commit()
    return app


def test_ai_check_creates_candidate_findings_without_approving(tmp_path):
    app = ai_app(tmp_path)
    with app.app_context():
        submission = PortfolioSubmission.query.one()
        student = User.query.filter_by(username="student").one()
        task = run_evidence_check(submission, student)
        db.session.commit()
        assert task.status == "succeeded"
        assert task.result_json["findings"][0]["finding"] == "需要人工確認"
        assert submission.status == "submitted"


def test_ai_check_failure_is_recorded_and_never_approves():
    app = ai_app(None)
    with app.app_context():
        submission = PortfolioSubmission.query.one()
        student = User.query.filter_by(username="student").one()
        submission.status = "needs_revision"
        task = run_evidence_check(submission, student, checker=lambda _: (_ for _ in ()).throw(RuntimeError("checker failed")))
        db.session.commit()
        assert task.status == "failed"
        assert "checker failed" in task.error_message
        assert submission.status == "needs_revision"


def test_unassigned_teacher_cannot_run_ai_check():
    app = ai_app(None)
    with app.app_context():
        submission = PortfolioSubmission.query.one()
        teacher = User.query.filter_by(username="teacher").one()
        with pytest.raises(PermissionError):
            run_evidence_check(submission, teacher)
