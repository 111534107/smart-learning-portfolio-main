import re

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


def test_teacher_dashboard_hides_retired_project_review():
    # 2026-10-10 定案：專題共同審查不在本系統範圍。選單「我的審查」與首頁「專題審查指派」拿掉，
    # 舊指派資料與 review 路由保留（只藏畫面）。
    client = work_app().test_client()
    login(client, "work-teacher")

    response = client.get("/teacher/dashboard")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'data-page="work-dashboard"' in page
    assert 'data-work-role="teacher"' in page
    for retired in ('href="/teacher/reviews"', "我的審查", "專題審查指派", "Work layer submission", "給科辦參考的意見"):
        assert retired not in page
    nav = page[page.index('aria-label="主要導覽"'):page.index("</nav>")]
    labels = re.findall(r"<a (?![^>]*masthead__help)[^>]*>([^<]+)", nav)  # 「怎麼操作」說明連結不算功能選單
    assert [label.strip() for label in labels] == ["工作台"]
    # 11-08：通知移到右邊工具列（跟學生同一套頂端列），帳號選單收字體大小、怎麼操作、登出
    assert 'class="snav-bell"' in page and "account-menu__panel" in page
    assert client.get("/teacher/reviews").status_code == 200
    with client.application.app_context():
        assert SubmissionAssignment.query.count() == 1


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
    page = response.get_data(as_text=True)
    assert 'data-admin-todos' in page
    # 舊送審流程（2026-10-10 拿掉）的字樣與英文狀態不能再出現
    for old in ("全部送件", "最近送件動態", "共同審查", "指派的審查", "Work layer submission", ">submitted<"):
        assert old not in page
    assert "科辦" in page and "核准電子獎狀" in page


def test_staff_nav_has_workbench_and_certificates_only():
    client = work_app().test_client()
    login(client, 'work-staff')
    page = client.get('/staff/dashboard').get_data(as_text=True)
    assert '>工作台</a>' in page and '>電子獎狀</a>' in page
    assert '登錄結果' not in page


def test_staff_and_admin_share_the_compact_header():
    # 11-08：老師、科辦、管理員也用學生那套頂端列，視窗變窄不再擠成三、四行
    for username, role in (("work-staff", "staff"), ("work-admin", "admin")):
        client = work_app().test_client()
        login(client, username)
        page = client.get(f"/{role}/dashboard").get_data(as_text=True)
        head = page[page.index("<header"):page.index("</header>")]
        assert f'class="masthead masthead--app masthead--{role}"' in head
        assert 'data-menu-toggle aria-expanded="false" aria-controls="app-mainnav"' in head
        assert 'id="account-menu-panel" hidden' in head and ">登出</button>" in head
