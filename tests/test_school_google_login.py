from urllib.parse import parse_qs, urlparse

from app import create_app
from app.extensions import db
from app.models import User


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
    response = client.get("/auth/google")
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


def test_google_login_updates_display_name_from_verified_profile():
    claims = {"sub": "google-student-107", "email": SCHOOL_EMAIL,
              "email_verified": True, "hd": "stu.ukn.edu.tw", "name": "真實姓名"}
    app, _ = school_app(FakeGoogleLogin(claims))
    client = app.test_client()
    response = client.get("/auth/google")
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


def test_real_client_allows_small_clock_skew_and_keeps_cause(monkeypatch):
    """2026-11-03 實測：電腦時間比 Google 慢 5 秒，預設 0 秒誤差就被拒絕（Token used too early）。"""
    import io
    import json
    from google.oauth2 import id_token
    from app.services import school_google_login as g_login

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(g_login, "urlopen", lambda request, timeout: Response(json.dumps({"id_token": "t"}).encode()))
    seen = {}

    def fake_verify(token, request, audience, clock_skew_in_seconds=0):
        seen["skew"] = clock_skew_in_seconds
        if clock_skew_in_seconds < 5:
            raise ValueError("Token used too early")
        return {"sub": "1", "email": SCHOOL_EMAIL, "email_verified": True, "hd": "stu.ukn.edu.tw"}

    monkeypatch.setattr(id_token, "verify_oauth2_token", fake_verify)
    client = g_login.HttpGoogleLoginClient({"GOOGLE_OAUTH_CLIENT_ID": "id", "GOOGLE_OAUTH_CLIENT_SECRET": "s",
                                            "GOOGLE_LOGIN_REDIRECT_URI": "http://localhost:5013/auth/google/callback"})

    assert client.verify_code("code")["email"] == SCHOOL_EMAIL
    assert seen["skew"] >= 10


def test_google_login_control_visible_and_explains_unconfigured_state():
    app, _ = school_app()
    client = app.test_client()
    page = client.get('/login').get_data(as_text=True)
    assert '使用學校 Google Workspace 帳號登入' in page
    assert 'class="google-login' in page and 'href="/auth/google' in page
    app.config['GOOGLE_LOGIN_REDIRECT_URI'] = ''
    page = client.get('/login').get_data(as_text=True)
    assert '使用學校 Google Workspace 帳號登入' in page
    assert 'Google 登入尚未設定' in page
    assert 'disabled' in page and 'href="/auth/google' not in page


def test_student_button_asks_google_for_student_domain_so_only_student_no_is_typed():
    """2026-11-09 使用者：學校其他系統的 Google 登入只要打帳號，網域會直接顯示在框後面（Google 的 hd 參數）。"""
    app, _ = school_app()
    client = app.test_client()
    params = parse_qs(urlparse(client.get("/auth/google").location).query)
    assert params["hd"] == ["stu.ukn.edu.tw"]
    staff = parse_qs(urlparse(client.get("/auth/google?who=staff").location).query)
    assert staff["hd"] == ["ukn.edu.tw"]
    page = client.get("/login").get_data(as_text=True)
    assert 'href="/auth/google?who=staff"' in page and "只要輸入學號" in page


def test_hd_is_only_a_hint_other_domains_are_still_rejected():
    claims = {"sub": "outsider", "email": "someone@gmail.com", "email_verified": True}
    app, _ = school_app(FakeGoogleLogin(claims))
    client = app.test_client()
    state = start(client)
    response = client.get(f"/auth/google/callback?state={state}&code=c")
    assert response.status_code in (400, 403)
    with client.session_transaction() as current:
        assert current.get("user_id") is None
