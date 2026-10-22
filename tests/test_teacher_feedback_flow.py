from app import create_app
from app.extensions import db
from app.models import Portfolio, PortfolioSubmission, SubmissionAssignment, User


def feedback_app():
    app = create_app(
        {
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
        }
    )
    with app.app_context():
        db.create_all()
        student = User(username="feedback-student", display_name="Feedback Student", role="student")
        teacher = User(username="feedback-teacher", display_name="Feedback Teacher", role="teacher")
        other_teacher = User(username="feedback-other", display_name="Other Teacher", role="teacher")
        staff = User(username="feedback-staff", display_name="Feedback Staff", role="staff")
        for user in (student, teacher, other_teacher, staff):
            user.set_password("test-password")
            db.session.add(user)
        db.session.flush()
        portfolio = Portfolio(
            student_id=student.id,
            title="Feedback workflow item",
            category="project",
        )
        db.session.add(portfolio)
        db.session.flush()
        submission = PortfolioSubmission(
            portfolio_id=portfolio.id,
            version_no=1,
            status="submitted",
        )
        db.session.add(submission)
        db.session.flush()
        db.session.add(SubmissionAssignment(submission_id=submission.id, teacher_id=teacher.id))
        db.session.commit()
    return app


def login(client, username):
    return client.post(
        "/login",
        data={"username": username, "password": "test-password"},
    )


def submission_id(app):
    with app.app_context():
        return PortfolioSubmission.query.one().id


def test_assigned_teacher_feedback_is_visible_before_staff_records_a_result():
    app = feedback_app()
    client = app.test_client()
    item_id = submission_id(app)

    login(client, "feedback-teacher")
    feedback_response = client.post(
        f"/teacher/reviews/{item_id}/feedback",
        data={"comment": "Please add the data model diagram."},
    )

    assert feedback_response.status_code == 302
    client.post("/logout")
    login(client, "feedback-staff")
    queue_response = client.get("/staff/dashboard")

    assert queue_response.status_code == 200
    assert b"Please add the data model diagram." in queue_response.data


def test_unassigned_teacher_cannot_submit_feedback_for_someone_elses_assignment():
    app = feedback_app()
    client = app.test_client()

    login(client, "feedback-other")
    response = client.post(
        f"/teacher/reviews/{submission_id(app)}/feedback",
        data={"comment": "I should not be able to submit this."},
    )

    assert response.status_code == 403


def test_teacher_feedback_rejects_an_empty_comment():
    app = feedback_app()
    client = app.test_client()

    login(client, "feedback-teacher")
    response = client.post(
        f"/teacher/reviews/{submission_id(app)}/feedback",
        data={"comment": "   "},
    )

    assert response.status_code == 400


def test_staff_can_record_common_result_after_teacher_feedback():
    app = feedback_app()
    client = app.test_client()
    item_id = submission_id(app)

    login(client, "feedback-teacher")
    feedback_response = client.post(
        f"/teacher/reviews/{item_id}/feedback",
        data={"comment": "The project scope is clear."},
    )
    assert feedback_response.status_code == 302
    client.post("/logout")
    login(client, "feedback-staff")
    response = client.post(
        f"/staff/reviews/{item_id}/result",
        data={"decision": "approved", "comment": "Common decision recorded."},
    )

    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(PortfolioSubmission, item_id).status == "approved"
