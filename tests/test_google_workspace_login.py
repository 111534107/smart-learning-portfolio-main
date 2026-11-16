"""學校 Google Workspace 一鍵登入（2026-11-04 使用者決定）。

- 學生 @stu.ukn.edu.tw：第一次登入自動建立學生帳號（學號＝信箱 @ 前 9 碼數字，入學學年度＝學號前三碼）。
- 老師、科辦、管理員 @ukn.edu.tw：不自動建立、不自動給權限；管理員先建帳號、填信箱才能登入。
- 管理員在「Google 登入設定」頁可關閉 Google 登入、關閉自動建學生帳號、改教職員網域。
"""
from app.extensions import db
from app.models import AuditLog, StudentProfile, SystemSetting, User
from tests.test_school_google_login import FakeGoogleLogin, school_app, start


def claims(email, sub="sub-new", hd=None, name="田心于"):
    return {"sub": sub, "email": email, "email_verified": True, "hd": hd or email.split("@")[1], "name": name}


def google_callback(app, google_claims):
    app.config["GOOGLE_LOGIN_CLIENT"] = FakeGoogleLogin(google_claims)
    client = app.test_client()
    response = client.get(f"/auth/google/callback?state={start(client)}&code=c")
    with client.session_transaction() as login_session:
        logged_in = login_session.get("user_id")
    return response, logged_in, client


def set_setting(app, key, value):
    with app.app_context():
        db.session.add(SystemSetting(key=key, value=value))
        db.session.commit()


def add_user(app, username, role, email=None, password="pw"):
    with app.app_context():
        user = User(username=username, display_name=username, role=role, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user.id


# ---------- 學生：第一次登入自動建帳號 ----------

def test_new_student_is_created_on_first_google_login():
    app, _ = school_app()

    response, logged_in, _ = google_callback(app, claims("111534188@stu.ukn.edu.tw"))

    assert response.status_code == 302 and logged_in
    with app.app_context():
        user = db.session.get(User, logged_in)
        assert (user.username, user.role, user.email, user.google_sub) == (
            "111534188", "student", "111534188@stu.ukn.edu.tw", "sub-new")
        assert user.display_name == "田心于"
        profile = StudentProfile.query.filter_by(user_id=user.id).one()
        assert (profile.student_no, profile.admission_year, profile.class_name) == ("111534188", 111, None)
        assert AuditLog.query.filter_by(action="user.google_auto_create", target_id=user.id).count() == 1


def test_second_login_reuses_the_created_account():
    app, _ = school_app()
    google_callback(app, claims("111534188@stu.ukn.edu.tw"))

    _, logged_in, _ = google_callback(app, claims("111534188@stu.ukn.edu.tw"))

    with app.app_context():
        assert User.query.filter_by(username="111534188").count() == 1
        assert db.session.get(User, logged_in).username == "111534188"


def test_auto_create_can_be_turned_off():
    app, _ = school_app()
    set_setting(app, "google_login.auto_create_students", "0")

    response, logged_in, _ = google_callback(app, claims("111534188@stu.ukn.edu.tw"))

    assert response.status_code == 403 and not logged_in
    assert "111534188@stu.ukn.edu.tw" in response.get_data(as_text=True)
    with app.app_context():
        assert User.query.filter_by(username="111534188").count() == 0


def test_school_account_that_is_not_a_student_number_is_not_created():
    app, _ = school_app()

    response, logged_in, _ = google_callback(app, claims("club.office@stu.ukn.edu.tw"))

    assert response.status_code == 403 and not logged_in
    with app.app_context():
        assert User.query.filter_by(username="club.office").count() == 0


def test_existing_student_without_email_is_bound_not_duplicated():
    app, _ = school_app()
    existing = add_user(app, "111534177", "student")

    _, logged_in, _ = google_callback(app, claims("111534177@stu.ukn.edu.tw"))

    assert logged_in == existing
    with app.app_context():
        assert db.session.get(User, existing).email == "111534177@stu.ukn.edu.tw"


def test_existing_username_with_other_email_or_role_is_not_taken_over():
    app, _ = school_app()
    add_user(app, "111534166", "student", email="someone@stu.ukn.edu.tw")
    add_user(app, "111534155", "teacher")

    for email in ("111534166@stu.ukn.edu.tw", "111534155@stu.ukn.edu.tw"):
        response, logged_in, _ = google_callback(app, claims(email))
        assert response.status_code == 403 and not logged_in


def test_unrealistic_admission_year_is_left_blank():
    app, _ = school_app()

    _, logged_in, _ = google_callback(app, claims("999534188@stu.ukn.edu.tw"))

    with app.app_context():
        assert StudentProfile.query.filter_by(user_id=logged_in).one().admission_year is None


# ---------- 教職員：只限管理員建好的帳號 ----------

def test_teacher_with_bound_staff_email_can_log_in():
    app, _ = school_app()
    teacher = add_user(app, "t01", "teacher", email="t01@ukn.edu.tw")

    response, logged_in, _ = google_callback(app, claims("t01@ukn.edu.tw", sub="sub-t01"))

    assert response.status_code == 302 and logged_in == teacher


def test_unknown_staff_email_is_rejected_and_never_created():
    app, _ = school_app()

    response, logged_in, _ = google_callback(app, claims("newcomer@ukn.edu.tw"))

    assert response.status_code == 403 and not logged_in
    assert "管理員" in response.get_data(as_text=True)
    with app.app_context():
        assert User.query.filter(User.email == "newcomer@ukn.edu.tw").count() == 0
        assert User.query.filter_by(username="newcomer").count() == 0


def test_student_domain_cannot_open_a_staff_account_and_vice_versa():
    app, _ = school_app()
    add_user(app, "t02", "teacher", email="t02@stu.ukn.edu.tw")
    add_user(app, "111534144", "student", email="111534144@ukn.edu.tw")

    for email in ("t02@stu.ukn.edu.tw", "111534144@ukn.edu.tw"):
        response, logged_in, _ = google_callback(app, claims(email))
        assert response.status_code == 403 and not logged_in


def test_staff_domain_can_be_changed_by_setting():
    app, _ = school_app()
    set_setting(app, "google_login.staff_domain", "staff.ukn.edu.tw")
    teacher = add_user(app, "t03", "teacher", email="t03@staff.ukn.edu.tw")

    _, logged_in, _ = google_callback(app, claims("t03@staff.ukn.edu.tw", sub="sub-t03"))

    assert logged_in == teacher


# ---------- 整個關掉 ----------

def test_google_login_can_be_switched_off():
    app, _ = school_app()
    set_setting(app, "google_login.enabled", "0")
    client = app.test_client()

    page = client.get("/login").get_data(as_text=True)

    assert 'href="/auth/google' not in page
    assert client.get("/auth/google").status_code == 404


# ---------- 管理員設定頁 ----------

def admin_client(app):
    add_user(app, "boss", "admin")
    client = app.test_client()
    client.post("/login", data={"username": "boss", "password": "pw"})
    return client


def test_admin_settings_page_saves_and_audits():
    app, _ = school_app()
    client = admin_client(app)

    page = client.get("/admin/google-workspace").get_data(as_text=True)
    assert "Google 登入設定" in page and "@stu.ukn.edu.tw" in page

    response = client.post("/admin/google-workspace", data={"enabled": "1", "staff_domain": "UKN.edu.tw"})

    assert response.status_code == 302
    with app.app_context():
        stored = {row.key: row.value for row in SystemSetting.query.all()}
        assert stored["google_login.auto_create_students"] == "0"  # 沒勾＝關閉
        assert stored["google_login.staff_domain"] == "ukn.edu.tw"
        assert AuditLog.query.filter_by(action="system.google_login_settings").count() == 1


def test_admin_settings_rejects_bad_domain_and_non_admin():
    app, _ = school_app()
    client = admin_client(app)

    assert client.post("/admin/google-workspace", data={"staff_domain": "evil test"}).status_code == 400
    assert client.post("/admin/google-workspace", data={"staff_domain": "stu.ukn.edu.tw"}).status_code == 400
    student = app.test_client()
    add_user(app, "s9", "student")
    student.post("/login", data={"username": "s9", "password": "pw"})
    assert student.get("/admin/google-workspace").status_code == 403


def test_admin_can_bind_staff_email_only_on_staff_domain():
    app, _ = school_app()
    client = admin_client(app)
    teacher = add_user(app, "t04", "teacher")

    assert client.post(f"/admin/accounts/{teacher}/school-email", data={"school_email": "t04@ukn.edu.tw"}).status_code == 302
    with app.app_context():
        assert db.session.get(User, teacher).email == "t04@ukn.edu.tw"
    assert client.post(f"/admin/accounts/{teacher}/school-email", data={"school_email": "t04@gmail.com"}).status_code == 400
    assert client.post(f"/admin/accounts/{teacher}/school-email", data={"school_email": "t04@stu.ukn.edu.tw"}).status_code == 400


def test_new_google_student_can_open_main_pages():
    app, _ = school_app()
    response, logged_in, client = google_callback(app, claims("111534188@stu.ukn.edu.tw"))

    assert response.headers["Location"].endswith("/student/welcome")
    for path in ("/student/welcome", "/student/dashboard", "/student/learning-profile", "/student/portfolio",
                 "/student/targets", "/student/agent/issues"):
        assert client.get(path).status_code == 200, path
