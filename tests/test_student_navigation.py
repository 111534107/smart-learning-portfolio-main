"""學生動線：清單頁只放資料，按「＋新增」才到表單頁；「下一步」只出現在首頁。"""
import io

from app.extensions import db
from app.models import Portfolio
from tests.test_student_records import login, records_app


def test_portfolio_list_has_add_button_but_no_form(tmp_path):
    client = records_app(tmp_path).test_client()
    login(client)

    html = client.get("/student/portfolio").get_data(as_text=True)

    assert "/student/portfolio/new" in html
    assert 'name="title"' not in html


def test_new_record_page_preselects_category(tmp_path):
    client = records_app(tmp_path).test_client()
    login(client)

    response = client.get("/student/portfolio/new?category=service")

    assert response.status_code == 200
    assert 'value="service" required checked' in response.get_data(as_text=True)


def test_invalid_record_shows_form_page_with_error(tmp_path):
    client = records_app(tmp_path).test_client()
    login(client)

    response = client.post("/student/portfolio", data={"title": "", "category": "activity"})

    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert "請填寫名稱" in html
    assert 'name="title"' in html


def test_upload_has_its_own_page(tmp_path):
    client = records_app(tmp_path).test_client()
    login(client)

    list_html = client.get("/student/learning-profile").get_data(as_text=True)
    upload = client.get("/student/learning-profile/upload")

    assert 'type="file"' not in list_html
    assert "/student/learning-profile/upload" in list_html
    assert upload.status_code == 200
    assert 'type="file"' in upload.get_data(as_text=True)


def test_next_step_only_on_home(tmp_path):
    client = records_app(tmp_path).test_client()
    login(client)

    assert "data-guide-card" in client.get("/student/dashboard").get_data(as_text=True)
    assert "data-guide-card" not in client.get("/student/portfolio").get_data(as_text=True)
    assert "next-line" not in client.get("/student/portfolio").get_data(as_text=True)


def test_home_explains_upload_review_recommendation_order(tmp_path):
    client = records_app(tmp_path).test_client()
    login(client)
    html = client.get("/student/dashboard").get_data(as_text=True)
    assert "先新增或上傳" in html
    assert "核對辨識內容" in html
    assert "查看校系建議" in html
    assert "可繼續新增或重複上傳" in html


def test_evidence_upload_returns_to_edit_page(tmp_path):
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    client.post("/student/portfolio", data={"title": "迎新", "category": "activity"})
    with app.app_context():
        record_id = Portfolio.query.one().id

    response = client.post(f"/student/portfolio/{record_id}/evidence", data={
        "file": (io.BytesIO(b"demo"), "photo.png"),
    }, content_type="multipart/form-data")

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/student/portfolio/{record_id}/edit")
    edit_html = client.get(f"/student/portfolio/{record_id}/edit").get_data(as_text=True)
    assert "photo.png" in edit_html


def test_login_page_lists_demo_accounts_only_when_configured(tmp_path):
    from app.demo import DEMO_ACCOUNTS

    app = records_app(tmp_path)
    regular_page = app.test_client().get("/login").get_data(as_text=True)
    assert "Demo 快速登入" not in regular_page
    assert "demo2026" not in regular_page

    app.config["DEMO_ACCOUNTS"] = DEMO_ACCOUNTS
    demo_page = app.test_client().get("/login").get_data(as_text=True)
    assert "Demo 快速登入" in demo_page
    assert "teacher_demo" in demo_page
    assert "demo2026" in demo_page

    app.config["FLASK_ENV"] = "production"
    production_page = app.test_client().get("/login").get_data(as_text=True)
    assert "Demo 快速登入" not in production_page


def test_demo_quick_login_button_signs_in_with_listed_account(tmp_path):
    app = records_app(tmp_path)
    app.config["DEMO_ACCOUNTS"] = [{"role": "student", "label": "學生", "username": "stu",
                                    "password": "pw", "name": "測試學生"}]
    client = app.test_client()
    page = client.get("/login").get_data(as_text=True)
    assert 'name="username" value="stu"' in page
    assert 'name="password" value="pw"' in page

    # 按鈕送出的就是表單裡的帳密
    response = client.post("/login", data={"username": "stu", "password": "pw"})
    assert response.status_code == 302


def _record_with_evidence(app, client, filename, content=b"\x89PNG\r\n\x1a\nfake"):
    client.post("/student/portfolio", data={"title": "迎新", "category": "activity"})
    with app.app_context():
        record_id = Portfolio.query.one().id
    client.post(f"/student/portfolio/{record_id}/evidence", data={
        "file": (io.BytesIO(content), filename),
    }, content_type="multipart/form-data")
    with app.app_context():
        evidence = Portfolio.query.one().evidence_items[0]
        return record_id, evidence.id


def test_image_evidence_can_be_viewed_inline(tmp_path):
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    record_id, evidence_id = _record_with_evidence(app, client, "photo.png")

    response = client.get(f"/student/evidence/{evidence_id}/view")

    assert response.status_code == 200
    assert response.mimetype == "image/png"
    assert "attachment" not in response.headers.get("Content-Disposition", "")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    edit_html = client.get(f"/student/portfolio/{record_id}/edit").get_data(as_text=True)
    assert f'src="/student/evidence/{evidence_id}/view"' in edit_html


def test_non_image_evidence_is_not_served_inline(tmp_path):
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    _, evidence_id = _record_with_evidence(app, client, "note.txt", b"<script>alert(1)</script>")

    assert client.get(f"/student/evidence/{evidence_id}/view").status_code == 404


def test_other_student_cannot_view_evidence(tmp_path):
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    _, evidence_id = _record_with_evidence(app, client, "photo.png")
    with app.app_context():
        from app.models import User
        other = User(username="other", display_name="別人", role="student")
        other.set_password("pw")
        db.session.add(other)
        db.session.commit()
    other_client = app.test_client()
    other_client.post("/login", data={"username": "other", "password": "pw"})

    assert other_client.get(f"/student/evidence/{evidence_id}/view").status_code in (403, 404)


def test_evidence_can_be_deleted(tmp_path):
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    record_id, evidence_id = _record_with_evidence(app, client, "photo.png")

    response = client.post(f"/student/evidence/{evidence_id}/delete")

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/student/portfolio/{record_id}/edit")
    with app.app_context():
        assert Portfolio.query.one().evidence_items == []
