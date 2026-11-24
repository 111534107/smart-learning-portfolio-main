"""雙重驗證（Authenticator 六位數驗證碼，2026-11-09 使用者決定：所有使用者都要開）。

帳號密碼或學校 Google 登入成功後，還沒真正登入；要再輸入六位數（或先完成設定）才算登入。
全部用合成假資料，不連外部服務。
"""
import time

import pyotp
import pytest
from sqlalchemy import inspect

from app import create_app
from app.extensions import db
from app.models import AuditLog, User, UserBackupCode
from app.services import two_factor


def make_app(required=True):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "WTF_CSRF_ENABLED": False, "TWO_FACTOR_REQUIRED": required})
    with app.app_context():
        db.create_all()
        for username, role in (("adm", "admin"), ("tea", "teacher"), ("stu", "student")):
            # 2026-11-18：只有學校信箱 @stu.ukn.edu.tw 的帳號一定要雙重驗證；原有測試沿用「要開」的情境
            user = User(username=username, display_name=username, role=role, email=f"{username}@stu.ukn.edu.tw")
            user.set_password("pw")
            db.session.add(user)
        db.session.commit()
    return app


@pytest.fixture()
def app():
    return make_app()


def login(client, username="tea"):
    return client.post("/login", data={"username": username, "password": "pw"})


def logged_in(client):
    with client.session_transaction() as current:
        return current.get("user_id")


def enroll(app, username="tea"):
    """幫帳號直接開好雙重驗證，回傳 TOTP 物件。"""
    with app.app_context():
        user = User.query.filter_by(username=username).one()
        secret = pyotp.random_base32()
        codes = two_factor.enable(user, secret, pyotp.TOTP(secret).now())
        db.session.commit()
    return pyotp.TOTP(secret), codes


def next_code(totp):
    """下一個時間窗的驗證碼：同一窗的碼用過就不能再用。"""
    return totp.at(time.time() + 30)


# ---- 一定要開：第一次登入先設定 ----

def test_password_login_without_setup_goes_to_setup_not_logged_in(app):
    client = app.test_client()
    response = login(client)
    assert response.status_code == 302 and response.headers["Location"].endswith("/login/two-factor/setup")
    assert logged_in(client) is None
    assert client.get("/teacher/dashboard").status_code == 401


def test_setup_shows_qr_and_key_then_backup_codes_then_logs_in(app):
    client = app.test_client()
    login(client)
    page = client.get("/login/two-factor/setup").get_data(as_text=True)
    assert "<svg" in page and "Authenticator" in page
    with client.session_transaction() as current:
        secret = current["two_factor_setup_secret"]
    assert secret in page.replace(" ", "")  # 掃不到時可以手動輸入的金鑰
    wrong = client.post("/login/two-factor/setup", data={"code": "000000"})
    assert wrong.status_code == 400 and logged_in(client) is None
    done = client.post("/login/two-factor/setup", data={"code": pyotp.TOTP(secret).now()})
    page = done.get_data(as_text=True)
    assert done.status_code == 200 and page.count('class="backup-code"') == 10
    assert logged_in(client) is not None
    assert client.get("/teacher/dashboard").status_code == 200
    with app.app_context():
        user = User.query.filter_by(username="tea").one()
        assert user.two_factor_enabled and user.two_factor_secret != secret  # 存的是加密後的
        assert two_factor.decrypt_secret(user.two_factor_secret) == secret
        assert UserBackupCode.query.filter_by(user_id=user.id).count() == 10
        assert AuditLog.query.filter_by(user_id=user.id, action="two_factor.enable").count() == 1


# ---- 已開：登入要輸入六位數 ----

def test_enrolled_user_must_enter_code(app):
    totp, _ = enroll(app)
    client = app.test_client()
    response = login(client)
    assert response.headers["Location"].endswith("/login/two-factor")
    assert logged_in(client) is None
    bad = client.post("/login/two-factor", data={"code": "123456"})
    assert bad.status_code == 400 and "驗證碼不正確" in bad.get_data(as_text=True)
    good = client.post("/login/two-factor", data={"code": next_code(totp)})
    assert good.status_code == 302 and good.headers["Location"].endswith("/teacher/dashboard")
    assert logged_in(client) is not None


def test_same_code_cannot_be_used_twice(app):
    totp, _ = enroll(app)
    code = next_code(totp)
    first = app.test_client()
    login(first)
    assert first.post("/login/two-factor", data={"code": code}).status_code == 302
    second = app.test_client()
    login(second)
    assert second.post("/login/two-factor", data={"code": code}).status_code == 400


def test_backup_code_works_once(app):
    _, codes = enroll(app)
    client = app.test_client()
    login(client)
    assert client.post("/login/two-factor", data={"code": codes[0]}).status_code == 302
    again = app.test_client()
    login(again)
    assert again.post("/login/two-factor", data={"code": codes[0]}).status_code == 400


def test_five_wrong_codes_lock_the_login(app):
    totp, _ = enroll(app)
    client = app.test_client()
    login(client)
    for _ in range(5):
        client.post("/login/two-factor", data={"code": "000000"})
    locked = client.post("/login/two-factor", data={"code": next_code(totp)})
    assert locked.status_code == 429 and "15 分鐘" in locked.get_data(as_text=True)
    assert logged_in(client) is None


def test_two_factor_page_needs_password_step_first(app):
    client = app.test_client()
    assert client.get("/login/two-factor").status_code == 302
    assert client.get("/login/two-factor/setup").status_code == 302


# ---- 學校 Google 登入也要 ----

def test_google_login_also_needs_two_factor():
    from tests.test_school_google_login import FakeGoogleLogin, school_app, start
    app, _ = school_app(FakeGoogleLogin())
    app.config["TWO_FACTOR_REQUIRED"] = True
    client = app.test_client()
    response = client.get(f"/auth/google/callback?state={start(client)}&code=c")
    assert response.headers["Location"].endswith("/login/two-factor/setup")
    assert logged_in(client) is None


# ---- 管理員重設、自己管理 ----

def test_admin_can_reset_someone_elses_two_factor(app):
    enroll(app, "tea")
    adm_totp, _ = enroll(app, "adm")
    admin = app.test_client()
    login(admin, "adm")
    admin.post("/login/two-factor", data={"code": next_code(adm_totp)})
    with app.app_context():
        teacher_id = User.query.filter_by(username="tea").one().id
    assert admin.post(f"/admin/accounts/{teacher_id}/reset-two-factor").status_code == 302
    with app.app_context():
        teacher = db.session.get(User, teacher_id)
        assert not teacher.two_factor_enabled and teacher.two_factor_secret is None
        assert UserBackupCode.query.filter_by(user_id=teacher_id).count() == 0
        assert AuditLog.query.filter_by(action="two_factor.reset", target_id=teacher_id).count() == 1
    teacher = app.test_client()
    assert login(teacher).headers["Location"].endswith("/login/two-factor/setup")


def test_non_admin_cannot_reset(app):
    enroll(app, "tea")
    totp, _ = enroll(app, "stu")
    client = app.test_client()
    login(client, "stu")
    client.post("/login/two-factor", data={"code": next_code(totp)})
    with app.app_context():
        teacher_id = User.query.filter_by(username="tea").one().id
    assert client.post(f"/admin/accounts/{teacher_id}/reset-two-factor").status_code == 403


def test_account_menu_links_to_two_factor_page_and_cannot_turn_off_when_required(app):
    totp, _ = enroll(app)
    client = app.test_client()
    login(client)
    client.post("/login/two-factor", data={"code": next_code(totp)})
    dashboard = client.get("/teacher/dashboard").get_data(as_text=True)
    assert 'href="/account/two-factor"' in dashboard
    page = client.get("/account/two-factor").get_data(as_text=True)
    assert "已開啟" in page and "關閉雙重驗證" not in page
    regenerated = client.post("/account/two-factor/backup-codes").get_data(as_text=True)
    assert regenerated.count('class="backup-code"') == 10


def test_cli_reset_for_lost_admin_phone(app):
    enroll(app, "adm")
    result = app.test_cli_runner().invoke(args=["reset-2fa", "adm"])
    assert result.exit_code == 0 and "已重設" in result.output
    with app.app_context():
        assert not User.query.filter_by(username="adm").one().two_factor_enabled


# ---- 不強制時（自動化測試、本機展示站）：可以自己選擇開 ----

def test_optional_mode_logs_in_directly_but_enrolled_users_still_need_code():
    app = make_app(required=False)
    client = app.test_client()
    assert login(client).headers["Location"].endswith("/teacher/dashboard")
    totp, _ = enroll(app, "stu")
    student = app.test_client()
    assert login(student, "stu").headers["Location"].endswith("/login/two-factor")


def test_requirement_defaults():
    plain = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "SECRET_KEY": "x"})
    assert plain.config["TWO_FACTOR_REQUIRED"] is True
    assert create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True}).config["TWO_FACTOR_REQUIRED"] is False
    demo = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "LOCAL_DEMO_MODE": True, "SECRET_KEY": "x"})
    assert demo.config["TWO_FACTOR_REQUIRED"] is False


def test_migration_adds_two_factor_columns(tmp_path):
    migrated = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 't.db'}", "TESTING": True})
    runner = migrated.test_cli_runner()
    assert runner.invoke(args=["db", "upgrade"]).exit_code == 0
    with migrated.app_context():
        inspector = inspect(db.engine)
        assert inspector.has_table("user_backup_codes")
        if inspector.has_table("users"):  # 遷移鏈的測試資料庫不一定有 users（同其他遷移測試）
            columns = {c["name"] for c in inspector.get_columns("users")}
            assert {"two_factor_secret", "two_factor_enabled_at", "two_factor_last_counter"} <= columns
    assert runner.invoke(args=["db", "downgrade", "b20261109c01"]).exit_code == 0
    with migrated.app_context():
        assert not inspect(db.engine).has_table("user_backup_codes")



# ---- 2026-11-18 使用者決定：只有學校信箱要；示範站一律不要 ----

def test_only_school_mailbox_accounts_must_set_up_two_factor():
    app = make_app()
    with app.app_context():
        outside = User(username="out", display_name="out", role="teacher", email="teacher@example.test")
        outside.set_password("pw")
        db.session.add(outside); db.session.commit()
    client = app.test_client()
    response = client.post("/login", data={"username": "out", "password": "pw"})
    assert "/two-factor" not in response.headers.get("Location", "")
    assert logged_in(client)
    client = app.test_client()
    response = login(client, "stu")
    assert "/login/two-factor/setup" in response.headers["Location"]
    assert not logged_in(client)


def test_demo_site_never_asks_for_two_factor_even_for_admin():
    app = make_app()
    app.config["LOCAL_DEMO_MODE"] = True
    app.config["ADMIN_TWO_FACTOR_REQUIRED"] = True
    for username in ("stu", "tea", "adm"):
        client = app.test_client()
        response = login(client, username)
        assert "/two-factor" not in response.headers.get("Location", ""), username
        assert logged_in(client), username


def test_two_factor_pages_have_no_assistant():
    app = make_app()
    client = app.test_client()
    login(client, "stu")
    page = client.get("/login/two-factor/setup").get_data(as_text=True)
    assert "設定雙重驗證" in page
    assert "assistant__toggle" not in page
