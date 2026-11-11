"""學生、教職員、管理員登入頁與雙重驗證的錯誤次數限制（2026-11-12）。次數記在資料庫，清 Cookie 也繞不過。"""
import pyotp
import pytest

from app.extensions import db
from app.models import AuditLog, User
from tests.test_login_portals import logged_in_role, make_app, post_login

pytestmark = pytest.mark.real_login_routes

PAGES = [("/login", "stu"), ("/staff/login", "teacher"), ("/admin/login", "admin")]


def age_failures(app):
    """把錯誤紀錄調到一年前，模擬 15 分鐘已過。"""
    with app.app_context():
        for row in AuditLog.query.filter(AuditLog.action.like("%failed")).all():
            row.created_at = row.created_at.replace(year=row.created_at.year - 1)
        db.session.commit()


@pytest.mark.parametrize("path,username", PAGES)
def test_each_login_page_locks_after_five_wrong_passwords(path, username):
    app = make_app(ADMIN_TWO_FACTOR_REQUIRED=False)
    client = app.test_client()
    for left in (4, 3, 2, 1):
        response = post_login(client, path, username, "wrong")
        assert response.status_code == 401
        assert f"還可以再試 {left} 次" in response.get_data(as_text=True)
    fifth = post_login(client, path, username, "wrong")
    assert fifth.status_code == 429 and "15 分鐘後再試" in fifth.get_data(as_text=True)
    # 清 Cookie（換一個新的瀏覽器）也一樣鎖著，密碼對了也不行
    fresh = app.test_client()
    assert post_login(fresh, path, username).status_code == 429
    with app.app_context():
        assert logged_in_role(fresh) is None
        assert AuditLog.query.filter_by(action="account.locked").count() == 1
    age_failures(app)
    post_login(fresh, path, username)
    with app.app_context():
        assert logged_in_role(fresh) is not None


def test_success_resets_the_count():
    app = make_app()
    client = app.test_client()
    for _ in range(4):
        post_login(client, "/login", "stu", "wrong")
    post_login(client, "/login", "stu")
    response = post_login(app.test_client(), "/login", "stu", "wrong")
    assert response.status_code == 401 and "還可以再試 4 次" in response.get_data(as_text=True)


def test_other_accounts_are_not_locked_by_one_students_mistakes():
    app = make_app()
    with app.app_context():
        other = User(username="stu2", display_name="合成學生二", role="student")
        other.set_password("pw")
        db.session.add(other)
        db.session.commit()
    client = app.test_client()
    for _ in range(5):
        post_login(client, "/login", "stu", "wrong")
    post_login(client, "/login", "stu2")
    with app.app_context():
        assert logged_in_role(client) == "student"


def test_admin_can_unlock_and_it_is_logged():
    app = make_app(ADMIN_TWO_FACTOR_REQUIRED=False)
    for _ in range(5):
        post_login(app.test_client(), "/login", "stu", "wrong")
    admin = app.test_client()
    post_login(admin, "/admin/login", "admin")
    page = admin.get("/admin/accounts").get_data(as_text=True)
    assert "登入已鎖定" in page and "解除鎖定" in page
    with app.app_context():
        stu_id = User.query.filter_by(username="stu").one().id
    assert admin.post(f"/admin/accounts/{stu_id}/unlock-login").status_code == 302
    assert "登入已鎖定" not in admin.get("/admin/accounts").get_data(as_text=True)
    with app.app_context():
        row = AuditLog.query.filter_by(action="account.unlocked").one()
        assert row.target_id == stu_id
    student = app.test_client()
    post_login(student, "/login", "stu")
    with app.app_context():
        assert logged_in_role(student) == "student"


def test_non_admin_cannot_unlock():
    app = make_app()
    client = app.test_client()
    post_login(client, "/login", "stu")
    assert client.post("/admin/accounts/1/unlock-login").status_code in (302, 401, 403)
    with app.app_context():
        assert AuditLog.query.filter_by(action="account.unlocked").count() == 0


# ---------- 雙重驗證 ----------

def enroll(app, username="stu"):
    from app.services import two_factor
    with app.app_context():
        user = User.query.filter_by(username=username).one()
        secret = two_factor.new_secret()
        two_factor.enable(user, secret, pyotp.TOTP(secret).now())
        db.session.commit()
    return pyotp.TOTP(secret)


def test_two_factor_lock_survives_clearing_cookies():
    app = make_app(TWO_FACTOR_REQUIRED=True)
    enroll(app)
    client = app.test_client()
    post_login(client, "/login", "stu")
    for left in (4, 3, 2, 1):
        response = client.post("/login/two-factor", data={"code": "000000"})
        assert response.status_code == 400 and f"還可以試 {left} 次" in response.get_data(as_text=True)
    assert client.post("/login/two-factor", data={"code": "000000"}).status_code == 429
    # 新瀏覽器重新輸入密碼：直接顯示鎖定，連正確的碼也不收
    fresh = app.test_client()
    post_login(fresh, "/login", "stu")
    response = fresh.get("/login/two-factor")
    assert response.status_code == 429 and "驗證碼錯太多次" in response.get_data(as_text=True)
    with app.app_context():
        assert AuditLog.query.filter_by(action="account.locked").count() == 1
    age_failures(app)
    assert fresh.get("/login/two-factor").status_code == 200
