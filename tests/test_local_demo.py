import re

from app.demo import create_local_demo_app
from app.extensions import db
from app.models import AdmissionProgram, StudentTarget, User


def test_local_demo_app_uses_isolated_synthetic_data_and_demo_ocr():
    app = create_local_demo_app()

    assert app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite://"
    assert app.config["DOCUMENT_ANALYSIS_PROVIDER"] == "demo"
    assert app.config["GOOGLE_DRIVE_PREVIEW_ENABLED"] is False
    client = app.test_client()
    response = client.get("/proposal-preview")

    assert response.status_code == 200
    assert "Drive 尚未設定" in response.get_data(as_text=True)


def test_local_demo_forces_external_ai_off_even_if_local_environment_enables_it(monkeypatch):
    from app.config import Config

    monkeypatch.setattr(Config, "AI_ENABLED", True)
    monkeypatch.setattr(Config, "AI_API_KEY", "local-env-key-must-not-be-used")

    app = create_local_demo_app()

    assert app.config["LOCAL_DEMO_MODE"] is True
    assert app.config["AI_ENABLED"] is False
    assert app.config["AI_API_KEY"] == ""


def test_local_demo_accounts_open_only_their_role_workspaces():
    app = create_local_demo_app()
    client = app.test_client()

    for role, path in (
        ("student", "/student/dashboard"),
        ("teacher", "/teacher/dashboard"),
        ("staff", "/staff/dashboard"),
        ("admin", "/admin/dashboard"),
    ):
        login_page = client.get("/login").get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', login_page).group(1)
        response = client.post("/login", data={"csrf_token": token,
                                               "username": f"{role}_demo", "password": "demo2026"})
        assert response.status_code == 302
        assert response.headers["Location"].endswith(path)
        assert client.get(path).status_code == 200
        client.post("/logout")


def test_local_demo_login_page_shows_the_current_synthetic_credentials():
    client = create_local_demo_app().test_client()

    page = client.get("/login").get_data(as_text=True)

    for username in ("student_demo", "teacher_demo", "staff_demo", "admin_demo"):
        assert username in page
    assert "demo2026" in page
    assert "demo1234" not in page
    assert "111534105" not in page


def test_local_demo_login_page_hides_credentials_in_production():
    app = create_local_demo_app()
    app.config["FLASK_ENV"] = "production"

    page = app.test_client().get("/login").get_data(as_text=True)

    assert "student_demo" not in page
    assert "demo2026" not in page


def test_local_autobiography_page_labels_the_draft_as_local_simulation():
    app = create_local_demo_app()
    with app.app_context():
        student = User.query.filter_by(username="student_demo").one()
        program = AdmissionProgram.query.filter_by(program_code="208003").one()
        db.session.add(StudentTarget(student_id=student.id, rule_version_id=program.id))
        db.session.commit()
    client = app.test_client()
    login_page = client.get("/login").get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', login_page).group(1)
    client.post("/login", data={"csrf_token": token, "username": "student_demo", "password": "demo2026"})

    page = client.get("/student/autobiography").get_data(as_text=True)

    assert "本機展示模式不呼叫外部 AI" in page
    assert 'name="own_api_key"' not in page
    assert "產生示範草稿" in page


def test_demo_app_handles_one_request_at_a_time():
    # 展示站把資料庫放在記憶體、所有執行緒共用同一條連線；同時處理多個請求時，
    # 實測 36 個同時請求有 1 個被誤判為未登入、3 個被誤回 404。請求必須一次處理一個。
    import threading
    import time

    from app.demo import SerializedWSGI

    active, peak, lock = [0], [0], threading.Lock()

    def slow_app(environ, start_response):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(0.02)
        with lock:
            active[0] -= 1
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"ok"]

    wrapped = SerializedWSGI(slow_app)
    threads = [threading.Thread(target=lambda: list(wrapped({}, lambda *args: None))) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert peak[0] == 1


def test_local_demo_app_is_wrapped_to_serialize_requests():
    from app.demo import SerializedWSGI, create_local_demo_app

    assert isinstance(create_local_demo_app().wsgi_app, SerializedWSGI)
