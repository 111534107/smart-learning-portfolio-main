from app import create_app
from app.extensions import db
from app.models import Portfolio, PortfolioSubmission, SubmissionAssignment, User


def work_app():
    app = create_app(
        {
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
        }
    )
    with app.app_context():
        db.create_all()
        student = User(username="work-student", display_name="Work Student", role="student")
        teacher = User(username="work-teacher", display_name="Work Teacher", role="teacher")
        staff = User(username="work-staff", display_name="Work Staff", role="staff")
        admin = User(username="work-admin", display_name="Work Admin", role="admin")
        for user in (student, teacher, staff, admin):
            user.set_password("test-password")
            db.session.add(user)
        db.session.flush()

        portfolio = Portfolio(
            student_id=student.id,
            title="Work layer submission",
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


def test_teacher_dashboard_exposes_assigned_review_work():
    client = work_app().test_client()
    login(client, "work-teacher")

    response = client.get("/teacher/dashboard")

    assert response.status_code == 200
    assert b'data-page="work-dashboard"' in response.data
    assert b'data-work-role="teacher"' in response.data
    assert b'href="/teacher/reviews"' in response.data


def test_staff_dashboard_shows_only_staff_work_not_portfolio_submissions():
    # 2026-10-10 定案：科辦不看備審，「待處理送件／登錄共同結論」從畫面拿掉（舊資料保留）
    client = work_app().test_client()
    login(client, "work-staff")

    response = client.get("/staff/dashboard")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'data-work-role="staff"' in page
    assert 'data-work-queue' in page
    assert "科辦工作台" in page
    assert 'href="#staff-certificates"' in page and 'href="#staff-graduation"' in page
    assert "Work layer submission" not in page
    assert "待處理送件" not in page and "共同結論" not in page


def test_admin_dashboard_exposes_system_overview():
    client = work_app().test_client()
    login(client, "work-admin")

    response = client.get("/admin/dashboard")

    assert response.status_code == 200
    assert b'data-page="admin-dashboard"' in response.data
    assert b'data-work-role="admin"' in response.data
    assert b'data-system-overview' in response.data


def test_staff_nav_has_workbench_and_certificates_only():
    client = work_app().test_client()
    login(client, 'work-staff')
    page = client.get('/staff/dashboard').get_data(as_text=True)
    assert '>工作台</a>' in page and '>電子獎狀</a>' in page
    assert '登錄結果' not in page
