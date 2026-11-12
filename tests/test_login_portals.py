"""三個登入頁分開（2026-11-10 使用者決定）：學生 /login、老師與科辦 /staff/login、管理員 /admin/login。

管理員頁：公開頁不放入口、一定要 Authenticator 六位數驗證碼、密碼錯 5 次鎖 15 分鐘、閒置 15 分鐘登出、
可限定只能從學校網路登入（預設不限制，因為目前沒有學校網路）。
"""
import time

import pytest

from app import create_app
from app.extensions import db
from app.models import AuditLog, SystemSetting, User
from tests.test_school_google_login import FakeGoogleLogin, start

pytestmark = pytest.mark.real_login_routes  # 不讓 conftest 依角色改登入網址

DEMO = [
    {"role": "student", "label": "學生", "username": "stu", "password": "pw", "name": "合成學生"},
    {"role": "teacher", "label": "老師", "username": "teacher", "password": "pw", "name": "合成老師"},
    {"role": "staff", "label": "科辦", "username": "staff", "password": "pw", "name": "合成科辦"},
    {"role": "admin", "label": "管理員", "username": "admin", "password": "pw", "name": "合成管理員"},
]


def make_app(**overrides):
    config = {"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "WTF_CSRF_ENABLED": False,
              "DEMO_ACCOUNTS": DEMO}
    config.update(overrides)
    app = create_app(config)
    with app.app_context():
        db.create_all()
        for account in DEMO:
            user = User(username=account["username"], display_name=account["name"], role=account["role"])
            user.set_password("pw")
            db.session.add(user)
        db.session.commit()
    return app


def post_login(client, path, username, password="pw"):
    return client.post(path, data={"username": username, "password": password})


def logged_in_role(client):
    with client.session_transaction() as sess:
        user_id = sess.get("user_id")
    if not user_id:
        return None
    return db.session.get(User, user_id).role


# ---------- 頁面內容 ----------

def test_student_page_puts_google_first_and_folds_password():
    html = make_app().test_client().get("/login").get_data(as_text=True)
    assert "學生登入" in html
    assert "<details" in html and 'name="password"' in html.split("<details", 1)[1]
    assert 'href="/staff/login"' in html
    assert "/admin/login" not in html
    demo = html.split("demo-login", 1)[1]
    assert "stu" in demo and "teacher" not in demo and "admin" not in demo


def test_staff_page_has_staff_google_and_password_but_no_admin_entry():
    html = make_app().test_client().get("/staff/login").get_data(as_text=True)
    assert "老師與科辦" in html and 'name="password"' in html
    assert "/admin/login" not in html
    demo = html.split("demo-login", 1)[1]
    assert "teacher" in demo and "staff" in demo and "admin" not in demo and ">stu<" not in demo


def test_admin_page_is_separate_and_not_linked_from_home():
    client = make_app().test_client()
    html = client.get("/admin/login").get_data(as_text=True)
    assert "管理員登入" in html and "Google" not in html
    assert "/admin/login" not in client.get("/").get_data(as_text=True)


# ---------- 帳號只能從自己的頁面登入 ----------

def test_each_role_only_logs_in_on_its_own_page():
    app = make_app()
    with app.app_context():
        client = app.test_client()
        response = post_login(client, "/login", "teacher")
        assert "老師與科辦人員請到" in response.get_data(as_text=True) and logged_in_role(client) is None
        response = post_login(client, "/staff/login", "stu")
        assert "學生請到" in response.get_data(as_text=True) and logged_in_role(client) is None
        # 管理員在其他頁一律只說帳號或密碼錯誤，不透露有這個帳號
        for path in ("/login", "/staff/login"):
            response = post_login(client, path, "admin")
            assert response.status_code == 401 and "帳號或密碼錯誤" in response.get_data(as_text=True)
            assert logged_in_role(client) is None
        for path, username, role in (("/login", "stu", "student"), ("/staff/login", "teacher", "teacher"),
                                     ("/staff/login", "staff", "staff"), ("/admin/login", "admin", "admin")):
            client = app.test_client()
            post_login(client, path, username)
            assert logged_in_role(client) == role


def test_admin_login_always_requires_authenticator_when_enabled():
    app = make_app(ADMIN_TWO_FACTOR_REQUIRED=True)
    client = app.test_client()
    response = post_login(client, "/admin/login", "admin")
    assert response.status_code == 302 and "/login/two-factor" in response.location
    with app.app_context():
        assert logged_in_role(client) is None  # 還沒過第二步


def test_admin_cannot_use_google_even_with_staff_email():
    google = FakeGoogleLogin({"sub": "g-admin", "email": "admin@ukn.edu.tw", "email_verified": True, "hd": "ukn.edu.tw"})
    app = make_app(GOOGLE_OAUTH_CLIENT_ID="id", GOOGLE_OAUTH_CLIENT_SECRET="s",
                   GOOGLE_LOGIN_REDIRECT_URI="http://localhost/auth/google/callback", GOOGLE_LOGIN_CLIENT=google)
    with app.app_context():
        User.query.filter_by(username="admin").one().email = "admin@ukn.edu.tw"
        db.session.commit()
        client = app.test_client()
        state = start(client)
        response = client.get(f"/auth/google/callback?state={state}&code=c")
        assert response.status_code == 403 and logged_in_role(client) is None


# ---------- 管理員頁的保護 ----------

def test_admin_password_locks_after_five_failures():
    app = make_app()
    client = app.test_client()
    for _ in range(4):
        assert post_login(client, "/admin/login", "admin", "wrong").status_code == 401
    assert post_login(client, "/admin/login", "admin", "wrong").status_code == 429  # 第 5 次直接告知已鎖
    response = post_login(client, "/admin/login", "admin")  # 密碼對了也不行
    assert response.status_code == 429 and "15 分鐘" in response.get_data(as_text=True)
    with app.app_context():
        assert logged_in_role(client) is None
        assert AuditLog.query.filter_by(action="admin.login_failed").count() == 5
        # 15 分鐘後解鎖
        for row in AuditLog.query.filter_by(action="admin.login_failed"):
            row.created_at = row.created_at.replace(year=row.created_at.year - 1)
        db.session.commit()
    post_login(client, "/admin/login", "admin")
    with app.app_context():
        assert logged_in_role(client) == "admin"


def test_admin_is_logged_out_after_fifteen_idle_minutes():
    app = make_app()
    client = app.test_client()
    post_login(client, "/admin/login", "admin")
    assert client.get("/admin/dashboard").status_code == 200
    with client.session_transaction() as sess:
        sess["admin_last_seen"] = time.time() - 16 * 60
    response = client.get("/admin/dashboard")
    assert response.status_code == 401
    assert "/admin/login" in response.get_data(as_text=True)  # 被登出的管理員知道回哪裡登入


def test_teacher_is_not_affected_by_admin_idle_rule():
    app = make_app()
    client = app.test_client()
    post_login(client, "/staff/login", "teacher")
    with client.session_transaction() as sess:
        sess["admin_last_seen"] = time.time() - 60 * 60
    assert client.get("/teacher/dashboard").status_code == 200


def test_school_network_rule_is_off_by_default_and_blocks_when_set():
    app = make_app()
    client = app.test_client()
    post_login(client, "/admin/login", "admin")
    # 不能存一個把自己擋在外面的設定
    response = client.post("/admin/login-security", data={"networks": "10.0.0.0/8"}, follow_redirects=True)
    assert "你現在的位置" in response.get_data(as_text=True)
    response = client.post("/admin/login-security", data={"networks": "127.0.0.1, 10.0.0.0/8"}, follow_redirects=True)
    assert "已儲存" in response.get_data(as_text=True)
    response = client.post("/admin/login-security", data={"networks": "不是網段"}, follow_redirects=True)
    assert "看不懂" in response.get_data(as_text=True)
    with app.app_context():
        SystemSetting.query.filter_by(key="admin_allowed_networks").one().value = "10.0.0.0/8"
        db.session.commit()
        assert AuditLog.query.filter_by(action="admin.login_security").count() == 1
    # 不在學校網路：登入頁擋住、已登入的也被登出
    assert client.get("/admin/dashboard").status_code == 401
    other = app.test_client()
    response = other.get("/admin/login")
    assert response.status_code == 403 and "學校網路" in response.get_data(as_text=True)
    assert post_login(other, "/admin/login", "admin").status_code == 403


def test_logout_returns_each_role_to_its_own_page():
    app = make_app()
    for path, username in (("/login", "stu"), ("/staff/login", "teacher"), ("/admin/login", "admin")):
        client = app.test_client()
        post_login(client, path, username)
        assert client.post("/logout").location.endswith(path)
