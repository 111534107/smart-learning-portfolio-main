from app import create_app
from app.extensions import db
from app.models import User


def auth_app():
    app = create_app(
        {
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
        }
    )
    with app.app_context():
        db.create_all()
        for username, role, display_name in (
            ("student001", "student", "測試學生"),
            ("teacher001", "teacher", "測試教師"),
            ("admin", "admin", "測試管理員"),
        ):
            user = User(username=username, role=role, display_name=display_name)
            user.set_password("test-password")
            db.session.add(user)
        db.session.commit()
    return app


def test_login_redirects_student_to_student_dashboard():
    from app.extensions import db
    from app.models import AuditLog, User

    app = auth_app()
    client = app.test_client()
    with app.app_context():
        student = User.query.filter_by(username="student001").one()
        db.session.add(AuditLog(user_id=student.id, action="student.welcome_done"))
        db.session.commit()

    response = client.post(
        "/login",
        data={"username": "student001", "password": "test-password"},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/student/dashboard")


def test_login_rejects_wrong_password_without_creating_session():
    client = auth_app().test_client()

    response = client.post(
        "/login",
        data={"username": "student001", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert "帳號或密碼錯誤".encode("utf-8") in response.data


def test_regular_login_page_has_no_redundant_caption_or_demo_credentials():
    page = auth_app().test_client().get("/login").get_data(as_text=True)

    assert "學生、導師與管理者都從這裡登入" not in page
    assert "student_demo" not in page
    assert "demo2026" not in page


def test_student_cannot_open_admin_dashboard():
    client = auth_app().test_client()
    client.post(
        "/login",
        data={"username": "student001", "password": "test-password"},
    )

    response = client.get("/admin/dashboard")

    assert response.status_code == 403


def test_logout_clears_session():
    client = auth_app().test_client()
    client.post(
        "/login",
        data={"username": "student001", "password": "test-password"},
    )

    response = client.post("/logout")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    assert client.get("/student/dashboard").status_code == 401


def test_admin_navigation_groups_all_management_links_without_losing_access():
    client = auth_app().test_client()
    client.post('/login', data={'username': 'admin', 'password': 'test-password'})
    page = client.get('/admin/dashboard').get_data(as_text=True)
    assert 'aria-label="管理功能分類"' in page
    for label in ('帳號與角色', '課程與招生', '系統設定'):
        assert f'<h2 class="admin-nav-group__title">{label}</h2>' in page  # 2026-11-18 側邊欄：分類常駐展開
    for label in ('帳號管理', '導師班級', '課程規則', '排行篩選選項', '校系資料', '招生資料 Agent', 'OCR 辨識設定', '檔案存放設定', '操作紀錄'):
        assert label in page
    # 規格：專題類型與需求模板先隱藏，只拿掉選單（路由與資料保留）
    assert '專題規則' not in page and '/admin/project-types' not in page
    assert client.get('/admin/project-types').status_code == 200
    assert '系統總覽' in page and '登出' in page
