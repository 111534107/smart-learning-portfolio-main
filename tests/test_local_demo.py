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


def test_local_demo_uses_its_own_upload_folder():
    # 示範學生編號固定是 1；共用 instance/uploads 會拿到磁碟上別人留下的照片（10-29 瀏覽器驗收發現）
    from pathlib import Path

    first, second = create_local_demo_app(), create_local_demo_app()

    assert Path(first.config["UPLOAD_FOLDER"]).resolve() != Path("instance/uploads").resolve()
    assert first.config["UPLOAD_FOLDER"] != second.config["UPLOAD_FOLDER"]


def test_local_demo_student_can_generate_autobiography_right_away():
    from app.services import student_rules
    from app.services.journey_home import board_progress
    from app.services.journey_service import build_journey

    app = create_local_demo_app()
    with app.app_context():
        student = User.query.filter_by(username="student_demo").one()
        total, filled = board_progress(build_journey(student))

        assert total == filled == 30
        assert student_rules.autobiography_block_reason(student) is None
        assert StudentTarget.query.filter_by(student_id=student.id).count() == 1


def test_local_demo_staff_has_submissions_and_a_certificate_to_review():
    # 10-29 驗收：科辦兩頁原本都是 0 件，展示時沒東西可審
    client = create_local_demo_app().test_client()
    client.post("/login", data={"username": "staff_demo", "password": "demo2026"})

    dashboard = client.get("/staff/dashboard").get_data(as_text=True)
    certificates = client.get("/staff/certificates").get_data(as_text=True)

    # 11-08：科辦首頁直接列出待核准的電子獎狀；送件（備審）2026-10-10 起科辦不看
    assert "【測試】服務4" in dashboard and "/staff/certificates/" in dashboard
    assert "【測試】競賽5" not in dashboard and "【測試】活動5" not in dashboard
    assert "【測試】服務4" in certificates
    assert "目前沒有待核准的申請" not in certificates


def test_local_demo_has_no_synthetic_forms_and_points_to_paper_copies():
    # 2026-11-13 使用者決定：展示資料不放合成表單；表單由科辦從學校網站抓，沒有的請學生到科辦拿紙本
    app = create_local_demo_app()
    student = app.test_client()
    student.post("/login", data={"username": "student_demo", "password": "demo2026"})
    page = student.get("/forms").get_data(as_text=True)
    assert "學生請假單" not in page and "請到科辦拿紙本填寫" in page
    staff = app.test_client()
    staff.post("/login", data={"username": "staff_demo", "password": "demo2026"})
    assert "從學校網站更新表單" in staff.get("/staff/forms").get_data(as_text=True)


def test_local_demo_follows_environment_ai_setting(monkeypatch):
    # 10-30 起展示站的 AI 與 Google 沿用 .env（每個版本功能都要真的能用），不再強制關閉
    from app.config import Config

    monkeypatch.setattr(Config, "AI_ENABLED", True)
    monkeypatch.setattr(Config, "AI_API_KEY", "fake-key-for-test")

    app = create_local_demo_app()

    assert app.config["LOCAL_DEMO_MODE"] is True
    assert app.config["AI_ENABLED"] is True
    assert app.config["AI_API_KEY"] == "fake-key-for-test"


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

    # 11-10 登入頁分開：各角色的示範帳號列在自己的登入頁
    page = "".join(client.get(path).get_data(as_text=True) for path in ("/login", "/staff/login", "/admin/login"))

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

    assert "本機展示站目前沒有設定 AI 金鑰" in page  # 測試環境 AI 關閉時才顯示（11-02 起 AI 開啟時不再誤稱不呼叫）
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


def test_local_demo_loads_both_two_year_and_transfer_sample_programs():
    app = create_local_demo_app()
    with app.app_context():
        programs = AdmissionProgram.query.filter_by(status="published").all()
        assert len(programs) > 30
        assert any(p.admission_category == "插大（轉學考）" for p in programs)
        assert any(p.admission_category == "日間部申請入學" for p in programs)


def test_demo_experiences_have_labelled_specific_facts_for_autobiography():
    from app.models import Portfolio
    from app.services.autobiography_service import build_facts

    app = create_local_demo_app()
    with app.app_context():
        student = User.query.filter_by(username="student_demo").one()
        records = Portfolio.query.filter_by(student_id=student.id, status="confirmed").all()
        assert records
        assert all(record.description and "僅為測試資料" in record.description for record in records)
        assert all(record.role and record.achievement and record.learned and record.domain_tags for record in records)
        assert len({record.description for record in records}) >= 4
        program = StudentTarget.query.filter_by(student_id=student.id).first().program
        facts = build_facts(student, program)
        assert any("我負責" in str(fact) and "學到" in str(fact) for fact in facts["items"])
