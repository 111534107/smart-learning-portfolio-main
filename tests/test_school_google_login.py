from urllib.parse import parse_qs, urlparse
from html.parser import HTMLParser

from app import create_app
from app.extensions import db
from app.models import User, StudentProfile


SCHOOL_EMAIL = "111534107@stu.ukn.edu.tw"


class FakeGoogleLogin:
    def __init__(self, claims=None):
        self.claims = claims or {
            "sub": "google-student-107",
            "email": SCHOOL_EMAIL,
            "email_verified": True,
            "hd": "stu.ukn.edu.tw",
        }
        self.codes = []

    def verify_code(self, code):
        self.codes.append(code)
        return self.claims


def school_app(google=None):
    google = google or FakeGoogleLogin()
    app = create_app({
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "TESTING": True,
        "GOOGLE_OAUTH_CLIENT_ID": "test-client.apps.googleusercontent.com",
        "GOOGLE_OAUTH_CLIENT_SECRET": "test-secret",
        "GOOGLE_LOGIN_REDIRECT_URI": "http://localhost/auth/google/callback",
        "GOOGLE_LOGIN_CLIENT": google,
    })
    with app.app_context():
        db.create_all()
        for username, role, email, active in (
            ("111534107", "student", SCHOOL_EMAIL, True),
            ("teacher", "teacher", "teacher@stu.ukn.edu.tw", True),
            ("disabled", "student", "disabled@stu.ukn.edu.tw", False),
        ):
            user = User(username=username, display_name=username, role=role, email=email, is_active=active)
            user.set_password("pw")
            db.session.add(user)
        db.session.commit()
    return app, google


def start(client):
    response = client.get('/auth/google')
    assert response.status_code == 302
    assert urlparse(response.location).hostname == "accounts.google.com"
    return parse_qs(urlparse(response.location).query)["state"][0]


def test_google_login_uses_existing_student_and_binds_stable_subject():
    app, google = school_app()
    client = app.test_client()
    state = start(client)
    response = client.get(f"/auth/google/callback?state={state}&code=test-code")
    assert response.status_code == 302
    assert google.codes == ["test-code"]
    with client.session_transaction() as login_session:
        assert login_session["user_id"]
    with app.app_context():
        assert User.query.count() == 3
        assert User.query.filter_by(username="111534107").one().google_sub == "google-student-107"


def test_first_school_google_login_creates_student_visible_to_admin():
    claims = {'sub': 'new-google-student', 'email': '111534108@stu.ukn.edu.tw',
              'email_verified': True, 'hd': 'stu.ukn.edu.tw', 'name': '新學生'}
    app, _ = school_app(FakeGoogleLogin(claims))
    client = app.test_client()
    state = start(client)
    response = client.get(f'/auth/google/callback?state={state}&code=first')
    assert response.status_code == 302
    with app.app_context():
        user = User.query.filter_by(username='111534108').one()
        assert (user.role, user.email, user.google_sub, user.display_name) == ('student', claims['email'], claims['sub'], '新學生')
        assert user.student_profile.student_no == '111534108'
        assert user.student_profile.admission_year is None
    dashboard = client.get('/student/dashboard').get_data(as_text=True)
    assert '年級待確認' in dashboard
    assert '專一，你在這裡' not in dashboard
    state = start(client)
    assert client.get(f'/auth/google/callback?state={state}&code=second').status_code == 302
    with app.app_context():
        assert User.query.filter_by(username='111534108').count() == 1


def test_first_google_login_links_matching_existing_unbound_student():
    app, _ = school_app()
    with app.app_context():
        user = User.query.filter_by(username='111534107').one()
        user.email = None
        db.session.commit()
    client = app.test_client()
    state = start(client)
    assert client.get(f'/auth/google/callback?state={state}&code=first').status_code == 302
    with app.app_context():
        assert User.query.filter_by(username='111534107').one().email == SCHOOL_EMAIL


def test_google_login_updates_display_name_from_verified_profile():
    claims = {"sub": "google-student-107", "email": SCHOOL_EMAIL,
              "email_verified": True, "hd": "stu.ukn.edu.tw", "name": "真實姓名"}
    app, _ = school_app(FakeGoogleLogin(claims))
    client = app.test_client()
    response = client.get('/auth/google')
    params = parse_qs(urlparse(response.location).query)
    assert "profile" in params["scope"][0].split()
    client.get(f"/auth/google/callback?state={params['state'][0]}&code=test-code")
    with app.app_context():
        assert User.query.filter_by(username="111534107").one().display_name == "真實姓名"
    assert "真實姓名" in client.get('/student/dashboard').get_data(as_text=True)


def test_google_login_rejects_invalid_state_without_exchanging_code():
    app, google = school_app()
    client = app.test_client()
    start(client)
    response = client.get("/auth/google/callback?state=wrong&code=test-code")
    assert response.status_code == 400
    assert google.codes == []


def test_correct_new_student_login_creates_separate_account():
    claims = {'sub': 'other-google-user', 'email': '111534124@stu.ukn.edu.tw',
              'email_verified': True, 'hd': 'stu.ukn.edu.tw', 'name': '另一位學生'}
    app, _ = school_app(FakeGoogleLogin(claims))
    client = app.test_client()
    response = client.get('/auth/google')
    params = parse_qs(urlparse(response.location).query)
    assert params['prompt'] == ['select_account']
    assert client.get(f"/auth/google/callback?state={params['state'][0]}&code=ok").status_code == 302
    with client.session_transaction() as session:
        user_id = session['user_id']
    with app.app_context():
        assert db.session.get(User, user_id).username == '111534124'
        assert User.query.filter_by(username='111534107').one().id != user_id


def test_opening_google_callback_directly_shows_help_on_login_page():
    app, google = school_app()
    client = app.test_client()

    response = client.get("/auth/google/callback")

    assert response.status_code == 400
    assert "登入系統" in response.get_data(as_text=True)
    assert "請從登入頁" in response.get_data(as_text=True)
    assert google.codes == []


def test_callback_without_google_configuration_explains_setup():
    app, _ = school_app()
    app.config["GOOGLE_OAUTH_CLIENT_ID"] = ""
    response = app.test_client().get("/auth/google/callback")
    assert response.status_code == 400
    assert "Google 登入尚未設定" in response.get_data(as_text=True)


def test_teacher_can_login_from_google_callback_error_page():
    class Forms(HTMLParser):
        def __init__(self):
            super().__init__()
            self.actions = []

        def handle_starttag(self, tag, attrs):
            if tag == "form":
                self.actions.append(dict(attrs).get("action"))

    app, _ = school_app()
    app.config["DEMO_ACCOUNTS"] = [{"username": "teacher", "password": "pw",
                                    "name": "Teacher", "role": "teacher", "label": "導師"}]
    client = app.test_client()
    page = client.get('/auth/google/callback')
    forms = Forms()
    forms.feed(page.get_data(as_text=True))
    assert forms.actions == ['/login', '/login']
    response = client.post(forms.actions[-1], data={'username': 'teacher', 'password': 'pw'})
    assert response.status_code == 302
    assert client.get(response.location).status_code == 200


def test_google_login_rejects_unverified_wrong_domain_and_unbound_accounts():
    for claims in (
        {"sub": "x", "email": SCHOOL_EMAIL, "email_verified": False, "hd": "stu.ukn.edu.tw"},
        {"sub": "x", "email": "111534107@stu.ukn.edu.tw.evil.test", "email_verified": True, "hd": "stu.ukn.edu.tw"},
        {"sub": "x", "email": SCHOOL_EMAIL, "email_verified": True, "hd": "evil.test"},
        {"sub": "x", "email": "unknown@stu.ukn.edu.tw", "email_verified": True, "hd": "stu.ukn.edu.tw"},
        {"sub": "x", "email": "teacher@stu.ukn.edu.tw", "email_verified": True, "hd": "stu.ukn.edu.tw"},
        {"sub": "x", "email": "disabled@stu.ukn.edu.tw", "email_verified": True, "hd": "stu.ukn.edu.tw"},
    ):
        app, _ = school_app(FakeGoogleLogin(claims))
        client = app.test_client()
        state = start(client)
        response = client.get(f"/auth/google/callback?state={state}&code=test-code")
        assert response.status_code in (302, 403)
        with client.session_transaction() as login_session:
            assert "user_id" not in login_session


def test_admin_can_bind_unique_school_email_only_to_student():
    app, _ = school_app()
    client = app.test_client()
    with app.app_context():
        admin = User(username="admin", display_name="Admin", role="admin")
        admin.set_password("pw")
        db.session.add(admin)
        db.session.commit()
        student_id = User.query.filter_by(username="111534107").one().id
        teacher_id = User.query.filter_by(username="teacher").one().id
    client.post("/login", data={"username": "admin", "password": "pw"})
    assert client.post(f"/admin/accounts/{student_id}/school-email", data={"school_account": "111534107"}).status_code == 302
    with app.app_context():
        assert db.session.get(User, student_id).email == SCHOOL_EMAIL
    assert client.post(f"/admin/accounts/{student_id}/school-email", data={"school_account": "wrong"}).status_code == 400
    assert client.post(f"/admin/accounts/{student_id}/school-email", data={"school_account": "111534107@stu.ukn.edu.tw.evil.test"}).status_code == 400
    assert client.post(f"/admin/accounts/{teacher_id}/school-email", data={"school_account": "teacher"}).status_code == 400


def test_google_login_rejects_changed_subject_for_bound_account_and_replay():
    app, _ = school_app()
    client = app.test_client()
    state = start(client)
    assert client.get(f"/auth/google/callback?state={state}&code=first").status_code == 302
    assert client.get(f"/auth/google/callback?state={state}&code=first").status_code == 400
    client.post("/logout")
    other = FakeGoogleLogin({"sub": "different-google-user", "email": SCHOOL_EMAIL,
                             "email_verified": True, "hd": "stu.ukn.edu.tw"})
    app.config["GOOGLE_LOGIN_CLIENT"] = other
    state = start(client)
    assert client.get(f"/auth/google/callback?state={state}&code=other").status_code == 403
    with client.session_transaction() as login_session:
        assert "user_id" not in login_session


def test_school_email_can_be_on_university_primary_workspace_domain():
    from app.services.school_google_login import school_identity

    assert school_identity({"sub": "google-student-107", "email": SCHOOL_EMAIL,
                            "email_verified": True, "hd": "ukn.edu.tw"}) == (SCHOOL_EMAIL, "google-student-107")


def test_admin_rejects_duplicate_email_and_clearing_binding_removes_google_subject():
    app, _ = school_app()
    with app.app_context():
        admin = User(username="admin", display_name="Admin", role="admin")
        admin.set_password("pw")
        student = User.query.filter_by(username="111534107").one()
        student.google_sub = "old-google-subject"
        student_id = student.id
        db.session.add(admin)
        db.session.commit()
    client = app.test_client()
    client.post("/login", data={"username": "admin", "password": "pw"})
    with app.app_context():
        student = db.session.get(User, student_id)
        student.email = None
        teacher = User.query.filter_by(username="teacher").one()
        teacher.email = SCHOOL_EMAIL
        db.session.commit()
    assert client.post(f"/admin/accounts/{student_id}/school-email",
                       data={"school_account": "111534107"}).status_code == 400
    with app.app_context():
        User.query.filter_by(username="teacher").one().email = "teacher@stu.ukn.edu.tw"
        student = db.session.get(User, student_id)
        student.email = SCHOOL_EMAIL
        db.session.commit()
    assert client.post(f"/admin/accounts/{student_id}/school-email",
                       data={"school_account": ""}).status_code == 302
    with app.app_context():
        student = db.session.get(User, student_id)
        assert student.email is None
        assert student.google_sub is None


def test_login_button_hidden_when_not_configured():
    app, _ = school_app()
    client = app.test_client()
    assert "/auth/google" in client.get("/login").get_data(as_text=True)
    app.config["GOOGLE_LOGIN_REDIRECT_URI"] = ""
    assert "/auth/google" not in client.get("/login").get_data(as_text=True)


def test_google_button_stays_visible_after_wrong_password():
    app, _ = school_app()
    response = app.test_client().post("/login", data={"username": "unknown", "password": "wrong"})
    assert response.status_code == 401
    assert "/auth/google" in response.get_data(as_text=True)
