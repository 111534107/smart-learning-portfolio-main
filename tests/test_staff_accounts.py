"""管理員新增教職員帳號、科辦不限人數、職稱（2026-11-09 使用者決定，11-10）。合成假資料。"""
from app import create_app
from app.extensions import db
from app.models import AuditLog, User

PASSWORD = "Maple2026river"


def make_app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "WTF_CSRF_ENABLED": False, "TWO_FACTOR_REQUIRED": False})
    with app.app_context():
        db.create_all()
        admin = User(username="adm", display_name="合成管理員", role="admin")
        admin.set_password("pw")
        db.session.add(admin)
        db.session.commit()
    return app


def admin_client(app):
    client = app.test_client()
    client.post("/login", data={"username": "adm", "password": "pw"})
    return client


def create(client, **form):
    data = {"role": "staff", "job_title": "科助", "display_name": "合成科助", "username": "office1",
            "login": "password", "password": PASSWORD}
    data.update(form)
    return client.post("/admin/accounts/staff", data=data)


def test_accounts_page_has_create_form():
    app = make_app()
    page = admin_client(app).get("/admin/accounts").get_data(as_text=True)
    assert "新增教職員帳號" in page and "data-staff-create" in page
    for title in ("主任", "副主任", "科助", "其他行政人員"):
        assert title in page


def test_create_many_staff_with_titles():
    app = make_app()
    client = admin_client(app)
    for index, title in enumerate(("主任", "副主任", "科助", "科助", "其他行政人員")):
        assert create(client, username=f"office{index}", job_title=title, display_name=f"科辦{index}").status_code == 302
    create(client, username="office9", job_title="其他行政人員", job_title_other="行政助理")
    with app.app_context():
        staff = User.query.filter_by(role="staff").all()
        assert len(staff) == 6  # 不限人數
        assert sorted(user.job_title for user in staff) == sorted(["主任", "副主任", "科助", "科助", "其他行政人員", "行政助理"])
        assert AuditLog.query.filter_by(action="staff.account.create").count() == 6
    page = client.get("/admin/accounts").get_data(as_text=True)
    assert "已建立 科辦9（行政助理）" in page or "行政助理" in page


def test_new_staff_can_log_in_and_menu_shows_title():
    app = make_app()
    create(admin_client(app), job_title="副主任")
    client = app.test_client()
    assert client.post("/login", data={"username": "office1", "password": PASSWORD}).status_code == 302
    page = client.get("/staff/dashboard", follow_redirects=True).get_data(as_text=True)
    assert "科主任（副主任）" in page


def test_create_validates_input():
    app = make_app()
    client = admin_client(app)
    create(client, job_title="")  # 科辦一定要選職稱
    create(client, password="short")  # 密碼規則
    create(client, username="a")  # 帳號太短
    create(client, login="google", school_email="")  # 只用 Google 要填信箱
    create(client, school_email="someone@gmail.com")  # 只收教職員網域
    with app.app_context():
        assert User.query.filter_by(role="staff").count() == 0
    page = client.get("/admin/accounts").get_data(as_text=True)
    assert 'role="alert"' in page
    create(client)
    create(client, display_name="重複帳號")
    with app.app_context():
        assert User.query.filter_by(role="staff").count() == 1


def test_google_only_staff_account():
    app = make_app()
    create(admin_client(app), login="google", school_email="office@ukn.edu.tw", password="")
    with app.app_context():
        user = User.query.filter_by(username="office1").one()
        assert user.email == "office@ukn.edu.tw" and not user.check_password("")


def test_admin_can_change_title_and_only_admin_can_create():
    app = make_app()
    client = admin_client(app)
    create(client)
    with app.app_context():
        user_id = User.query.filter_by(username="office1").one().id
    assert client.post(f"/admin/accounts/{user_id}/job-title", data={"job_title": "主任"}).status_code == 302
    with app.app_context():
        assert db.session.get(User, user_id).job_title == "主任"
        assert AuditLog.query.filter_by(action="staff.job_title.update").count() == 1
    staff = app.test_client()
    staff.post("/login", data={"username": "office1", "password": PASSWORD})
    assert create(staff, username="office2").status_code == 403
