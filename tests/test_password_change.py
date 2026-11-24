"""修改密碼、密碼規則、改密碼後其他裝置登出（11-05 評審意見 1b，2026-11-10）。合成假資料。"""
from app import create_app
from app.extensions import db
from app.models import AuditLog, StudentProfile, User
from app.services import password_policy

OLD = "oldpass1234"
NEW = "Garden2026walk"


def make_app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "WTF_CSRF_ENABLED": False, "TWO_FACTOR_REQUIRED": False})
    with app.app_context():
        db.create_all()
        user = User(username="111534999", display_name="合成學生", role="student")
        user.set_password(OLD)
        db.session.add(user)
        db.session.flush()
        db.session.add(StudentProfile(user_id=user.id, student_no="111534999", class_name="資五甲"))
        teacher = User(username="tea", display_name="合成導師", role="teacher")
        teacher.set_password(OLD)
        db.session.add(teacher)
        db.session.commit()
    return app


def login(app, username="111534999", password=OLD):
    client = app.test_client()
    response = client.post("/login", data={"username": username, "password": password})
    assert response.status_code == 302
    return client


def change(client, current=OLD, new=NEW, confirm=None):
    return client.post("/account/password", data={
        "current_password": current, "new_password": new, "confirm_password": new if confirm is None else confirm})


def test_policy_rules():
    app = make_app()
    with app.app_context():
        user = User.query.filter_by(username="111534999").one()
        assert password_policy.check("short1", user)  # 太短
        assert password_policy.check("onlyletterslong", user)  # 沒數字
        assert password_policy.check("12345678901", user)  # 沒英文
        assert password_policy.check("password123", user)  # 常見密碼
        assert password_policy.check("ab111534999", user)  # 含學號
        assert password_policy.check(OLD, user)  # 和目前相同
        assert password_policy.check(NEW, user) == []


def test_account_menu_links_password_page():
    app = make_app()
    client = login(app)
    page = client.get("/student/dashboard", follow_redirects=True).get_data(as_text=True)
    assert 'href="/account/password"' in page
    form = client.get("/account/password").get_data(as_text=True)
    assert 'name="current_password"' in form and "至少 10 個字元" in form


def test_change_password_success_and_new_password_works():
    app = make_app()
    client = login(app)
    response = change(client)
    assert response.status_code == 200 and "data-password-done" in response.get_data(as_text=True)
    assert client.get("/account/password").status_code == 200  # 這台不用重新登入
    with app.app_context():
        assert AuditLog.query.filter_by(action="user.password_change").count() == 1
    assert app.test_client().post("/login", data={"username": "111534999", "password": OLD}).status_code == 401
    login(app, password=NEW)


def test_other_devices_are_logged_out_after_change():
    app = make_app()
    phone = login(app)
    laptop = login(app)
    assert phone.get("/account/password").status_code == 200
    change(laptop)
    assert phone.get("/account/password").status_code == 401  # 另一台被登出
    assert phone.get("/account/password").status_code == 401  # 而且 session 已清掉
    assert laptop.get("/account/password").status_code == 200


def test_rejects_wrong_current_mismatch_and_weak():
    app = make_app()
    client = login(app)
    assert change(client, current="wrongpass99").status_code == 400
    assert change(client, confirm="Garden2026walX").status_code == 400
    weak = change(client, new="abc")
    assert weak.status_code == 400 and "至少要 10 個字元" in weak.get_data(as_text=True)
    with app.app_context():
        assert User.query.filter_by(username="111534999").one().check_password(OLD)


def test_locks_after_too_many_wrong_current_passwords():
    app = make_app()
    client = login(app)
    for _ in range(5):
        change(client, current="wrongpass99")
    assert change(client).status_code == 429  # 鎖住時連正確密碼也先不收


def test_teacher_can_change_too_and_login_requires_login():
    app = make_app()
    assert app.test_client().get("/account/password").status_code == 401
    client = login(app, "tea")
    assert change(client).status_code == 200


def test_session_without_fingerprint_is_stamped_not_rejected():
    """上線前就登入的人（session 沒有指紋）不會被突然登出，第一次開頁面時補上指紋。"""
    app = make_app()
    client = app.test_client()
    with app.app_context():
        user_id = User.query.filter_by(username="tea").one().id
    with client.session_transaction() as current:
        current["user_id"] = user_id
    assert client.get("/account/password").status_code == 200
    with client.session_transaction() as current:
        assert current.get(password_policy.SESSION_KEY)
