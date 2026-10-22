"""自傳可以在 Google 文件中編輯（示範版）：Google API 全部用測試替身，不連網。"""
from urllib.parse import parse_qs, urlparse

import pytest

from app import create_app
from app.extensions import db
from app.models import AdmissionProgram, AutobiographyGoogleDoc, LearningProfileOutput, Portfolio, StudentProfile, User
from app.services import google_docs_service
from app.services.admission_service import import_seed_programs
from app.services.autobiography_service import generate_draft, latest_draft, version_of

GOOGLE_SETTINGS = {
    "GOOGLE_OAUTH_CLIENT_ID": "test-client-id.apps.googleusercontent.com",
    "GOOGLE_OAUTH_CLIENT_SECRET": "test-client-secret",
    "GOOGLE_OAUTH_REDIRECT_URI": "http://localhost:5013/student/google/callback",
}
ANSWERS = {"motivation": "專二做網頁設計時發現自己喜歡把需求變成系統。", "proud": "黑客松時負責後端 API。",
           "challenge": "", "future": "想學資料分析。"}


class FakeGoogle:
    """假的 Google：記錄呼叫，回傳固定結果；fail 設成例外時就丟出來。"""

    def __init__(self):
        self.created = []
        self.exports = {}
        self.fail = None

    def exchange_code(self, code):
        if self.fail:
            raise self.fail
        return {"access_token": f"fake-token-{code}", "expires_in": 3600}

    def create_document(self, access_token, title, text):
        if self.fail:
            raise self.fail
        file_id = f"doc{len(self.created) + 1}"
        self.created.append({"token": access_token, "title": title, "text": text, "id": file_id})
        self.exports[file_id] = text
        return file_id

    def export_text(self, access_token, file_id):
        if self.fail:
            raise self.fail
        return self.exports[file_id]


@pytest.fixture()
def fake_google():
    return FakeGoogle()


def make_app(tmp_path, fake_google, settings=GOOGLE_SETTINGS):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "UPLOAD_FOLDER": str(tmp_path),
                      "GOOGLE_DOCS_CLIENT": fake_google, **settings})
    with app.app_context():
        db.create_all()
        import_seed_programs()
        for username in ("stu", "other"):
            user = User(username=username, display_name=username, role="student")
            user.set_password("pw")
            db.session.add(user)
        db.session.flush()
        stu = User.query.filter_by(username="stu").one()
        db.session.add(StudentProfile(user_id=stu.id, student_no="111534100", class_name="資管科三甲", admission_year=113))
        db.session.add(Portfolio(student_id=stu.id, title="校園黑客松", category="competition", school_year=3,
                                 status="confirmed", description="三人一組完成報名網站"))
        db.session.commit()
    return app


@pytest.fixture()
def app(tmp_path, fake_google):
    return make_app(tmp_path, fake_google)


def program_id(app):
    with app.app_context():
        return AdmissionProgram.query.filter_by(program_code="208003").one().id


def login_with_draft(app, username="stu"):
    """登入、選目標校系、產生一份示範草稿（不連 AI）。回傳 (client, 草稿 id)。"""
    client = app.test_client()
    client.post("/login", data={"username": username, "password": "pw"})
    client.post("/student/targets", data={"program_id": program_id(app)})
    with app.app_context():
        student = User.query.filter_by(username=username).one()
        program = AdmissionProgram.query.filter_by(program_code="208003").one()
        output = generate_draft(student, program, ANSWERS)
        return client, output.id


def csrf(client):
    with client.session_transaction() as session:
        return session.setdefault("csrf_token", "test-csrf")


def authorize(client):
    """走一次 Google 授權：connect 轉到 Google，Google 帶 code 和 state 回到 callback。"""
    response = client.get("/student/google/connect")
    assert response.status_code == 302
    query = parse_qs(urlparse(response.headers["Location"]).query)
    return client.get(f"/student/google/callback?code=abc&state={query['state'][0]}")


def test_without_google_settings_button_says_not_configured_and_page_works(tmp_path, fake_google):
    app = make_app(tmp_path, fake_google, settings={"GOOGLE_OAUTH_CLIENT_ID": "", "GOOGLE_OAUTH_CLIENT_SECRET": "",
                                                    "GOOGLE_OAUTH_REDIRECT_URI": ""})
    client, output_id = login_with_draft(app)

    page = client.get(f"/student/autobiography?program_id={program_id(app)}")
    assert page.status_code == 200
    assert "Google 尚未設定" in page.get_data(as_text=True)

    response = client.post(f"/student/autobiography/{output_id}/google/open", data={"csrf_token": csrf(client)})
    assert response.status_code == 302
    assert "google=unconfigured" in response.headers["Location"]
    assert client.get("/student/google/connect").status_code == 302
    assert fake_google.created == []


def test_connect_asks_google_only_for_drive_file_scope(app):
    client, _ = login_with_draft(app)

    response = client.get("/student/google/connect")
    location = urlparse(response.headers["Location"])
    query = parse_qs(location.query)

    assert location.netloc == "accounts.google.com"
    assert query["scope"] == ["https://www.googleapis.com/auth/drive.file"]
    assert query["response_type"] == ["code"]
    assert query["redirect_uri"] == [GOOGLE_SETTINGS["GOOGLE_OAUTH_REDIRECT_URI"]]
    assert query["access_type"] == ["online"]
    assert query["state"][0]


def test_callback_rejects_wrong_state_and_keeps_token_off_the_cookie(app):
    client, _ = login_with_draft(app)
    client.get("/student/google/connect")

    bad = client.get("/student/google/callback?code=abc&state=forged")
    assert bad.status_code == 400

    good = authorize(client)
    assert good.status_code == 302
    with client.session_transaction() as session:
        assert all("fake-token" not in str(value) for value in session.values())


def test_open_without_authorization_goes_to_google_sign_in_first(app, fake_google):
    client, output_id = login_with_draft(app)

    response = client.post(f"/student/autobiography/{output_id}/google/open", data={"csrf_token": csrf(client)})

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/student/google/connect")
    assert fake_google.created == []


def test_open_creates_doc_with_source_marks_and_records_link(app, fake_google):
    client, output_id = login_with_draft(app)
    authorize(client)

    response = client.post(f"/student/autobiography/{output_id}/google/open", data={"csrf_token": csrf(client)})

    assert response.status_code == 302
    assert response.headers["Location"] == "https://docs.google.com/document/d/doc1/edit"
    created = fake_google.created[0]
    assert created["token"] == "fake-token-abc"
    assert "## 學習歷程與具體經驗 [來源 F1]" in created["text"]
    assert "黑客松時負責後端 API。" in created["text"]
    with app.app_context():
        link = AutobiographyGoogleDoc.query.one()
        assert link.google_file_id == "doc1"
        assert link.web_view_link == "https://docs.google.com/document/d/doc1/edit"
        assert link.based_on_output_id == output_id
        assert link.created_at is not None


def test_second_open_reuses_the_same_doc(app, fake_google):
    client, output_id = login_with_draft(app)
    authorize(client)
    client.post(f"/student/autobiography/{output_id}/google/open", data={"csrf_token": csrf(client)})

    again = client.post(f"/student/autobiography/{output_id}/google/open", data={"csrf_token": csrf(client)})

    assert again.headers["Location"] == "https://docs.google.com/document/d/doc1/edit"
    assert len(fake_google.created) == 1
    with app.app_context():
        assert AutobiographyGoogleDoc.query.count() == 1


def test_pull_saves_new_version_and_flags_unknown_sources(app, fake_google):
    client, output_id = login_with_draft(app)
    authorize(client)
    client.post(f"/student/autobiography/{output_id}/google/open", data={"csrf_token": csrf(client)})
    fake_google.exports["doc1"] = (
        "﻿自傳草稿\r\n說明文字\r\n\r\n"
        "## 學習動機 []\r\n我在 Google 文件裡改寫了動機。\r\n第二行。\r\n\r\n"
        "## 學習歷程與具體經驗 [來源 F1 F9]\r\n黑客松時我負責後端 API。\r\n"
        "## 困難與成長 []\r\n還沒寫完。\r\n"
        "## 未來規劃\r\n想學資料分析。\r\n"
    )

    response = client.post(f"/student/autobiography/{output_id}/google/pull", data={"csrf_token": csrf(client)})

    assert response.status_code == 302
    assert "google=pulled" in response.headers["Location"]
    with app.app_context():
        original = db.session.get(LearningProfileOutput, output_id)
        student = User.query.filter_by(username="stu").one()
        newest = latest_draft(student, AdmissionProgram.query.filter_by(program_code="208003").one())
        assert newest.id != output_id
        assert version_of(newest) == 2
        assert original.content_json["paragraphs"][0]["text"] != "我在 Google 文件裡改寫了動機。\n第二行。"
        paragraphs = newest.content_json["paragraphs"]
        assert paragraphs[0]["text"] == "我在 Google 文件裡改寫了動機。\n第二行。"
        assert paragraphs[1]["sources"] == ["F1"]
        assert paragraphs[1]["unknown_sources"] == ["F9"]
        assert newest.content_json["editor_role"] == "student"
        assert newest.content_json["origin"] == "google_docs"
        assert newest.content_json["based_on"] == output_id

    page = client.get(f"/student/autobiography?program_id={program_id(app)}").get_data(as_text=True)
    assert "F9" in page and "不存在" in page


def test_pull_rejects_text_without_paragraph_titles(app, fake_google):
    client, output_id = login_with_draft(app)
    authorize(client)
    client.post(f"/student/autobiography/{output_id}/google/open", data={"csrf_token": csrf(client)})
    fake_google.exports["doc1"] = "標題都被刪掉了，只剩一段文字。"

    response = client.post(f"/student/autobiography/{output_id}/google/pull", data={"csrf_token": csrf(client)})

    assert "google=no_titles" in response.headers["Location"]
    with app.app_context():
        assert LearningProfileOutput.query.count() == 1


def test_other_student_cannot_open_or_pull_my_draft(app, fake_google):
    _, output_id = login_with_draft(app)
    other, _ = login_with_draft(app, "other")
    authorize(other)

    assert other.post(f"/student/autobiography/{output_id}/google/open", data={"csrf_token": csrf(other)}).status_code == 403
    assert other.post(f"/student/autobiography/{output_id}/google/pull", data={"csrf_token": csrf(other)}).status_code == 403
    assert fake_google.created == []


def test_token_belongs_to_the_session_that_authorized(app, fake_google):
    client, output_id = login_with_draft(app)
    authorize(client)
    fresh = app.test_client()
    fresh.post("/login", data={"username": "stu", "password": "pw"})

    response = fresh.post(f"/student/autobiography/{output_id}/google/open", data={"csrf_token": csrf(fresh)})

    assert response.headers["Location"].endswith("/student/google/connect")


def test_google_failure_falls_back_to_system_editing(app, fake_google):
    client, output_id = login_with_draft(app)
    authorize(client)
    fake_google.fail = google_docs_service.GoogleDocsUnavailable("Google 逾時")

    response = client.post(f"/student/autobiography/{output_id}/google/open", data={"csrf_token": csrf(client)})

    assert response.status_code == 302
    assert "google=unavailable" in response.headers["Location"]
    with app.app_context():
        assert AutobiographyGoogleDoc.query.count() == 0
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "先在系統內編輯" in page
    fake_google.fail = None
    count = 4
    saved = client.post(f"/student/autobiography/{output_id}/save",
                        data={"csrf_token": csrf(client), **{f"paragraph_{i}": f"系統內第 {i} 段" for i in range(count)}})
    assert saved.status_code == 302


def test_expired_authorization_asks_to_sign_in_again(app, fake_google):
    client, output_id = login_with_draft(app)
    authorize(client)
    client.post(f"/student/autobiography/{output_id}/google/open", data={"csrf_token": csrf(client)})
    fake_google.fail = google_docs_service.GoogleDocsAuthExpired("權杖過期")

    response = client.post(f"/student/autobiography/{output_id}/google/pull", data={"csrf_token": csrf(client)})

    assert "google=expired" in response.headers["Location"]
    fake_google.fail = None
    again = client.post(f"/student/autobiography/{output_id}/google/pull", data={"csrf_token": csrf(client)})
    assert again.headers["Location"].endswith("/student/google/connect")


def test_google_sign_in_error_returns_to_autobiography(app):
    client, _ = login_with_draft(app)
    client.get("/student/google/connect")
    with client.session_transaction() as session:
        state = session["google_oauth_state"]

    response = client.get(f"/student/google/callback?error=access_denied&state={state}")

    assert response.status_code == 302
    assert "google=denied" in response.headers["Location"]


def test_document_text_round_trips_through_parser():
    paragraphs = [{"title": "學習動機", "text": "第一行\n第二行", "sources": []},
                  {"title": "未來規劃", "text": "想學資料分析。", "sources": ["F1", "F2"]}]
    text = google_docs_service.document_text("測試校系", 3, paragraphs)

    parsed = google_docs_service.parse_document_text(text)

    assert [(p["title"], p["text"], p["sources"]) for p in parsed] == [
        ("學習動機", "第一行\n第二行", []), ("未來規劃", "想學資料分析。", ["F1", "F2"])]


def test_migration_creates_google_doc_table(tmp_path):
    from sqlalchemy import inspect

    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'gdoc.db'}", "TESTING": True})
    runner = app.test_cli_runner()

    assert runner.invoke(args=["db", "upgrade"]).exit_code == 0
    with app.app_context():
        columns = {c["name"] for c in inspect(db.engine).get_columns("autobiography_google_docs")}
    assert {"student_id", "program_id", "google_file_id", "web_view_link", "based_on_output_id", "created_at"} <= columns
    assert runner.invoke(args=["db", "downgrade", "f3a8c2d61b07"]).exit_code == 0


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body


def test_http_client_creates_google_doc_and_maps_errors(monkeypatch):
    import io
    from urllib.error import HTTPError

    sent = []

    def fake_urlopen(request, timeout):
        sent.append(request)
        if "export" in request.full_url:
            raise HTTPError(request.full_url, 401, "unauthorized", {}, io.BytesIO(b""))
        return FakeResponse(b'{"id": "doc42"}')

    monkeypatch.setattr(google_docs_service, "urlopen", fake_urlopen)
    client = google_docs_service.HttpGoogleDocsClient(GOOGLE_SETTINGS)

    assert client.create_document("token", "自傳草稿", "## 學習動機 []\n內容") == "doc42"
    body = sent[0].data.decode("utf-8")
    assert "application/vnd.google-apps.document" in body and "## 學習動機" in body
    assert sent[0].get_header("Authorization") == "Bearer token"
    with pytest.raises(google_docs_service.GoogleDocsAuthExpired):
        client.export_text("token", "doc42")


def test_http_client_rejects_strange_file_id(monkeypatch):
    monkeypatch.setattr(google_docs_service, "urlopen", lambda request, timeout: FakeResponse(b'{"id": "../evil"}'))
    client = google_docs_service.HttpGoogleDocsClient(GOOGLE_SETTINGS)

    with pytest.raises(google_docs_service.GoogleDocsUnavailable):
        client.create_document("token", "自傳草稿", "內容")


def test_local_demo_keeps_google_off_by_default():
    from app.demo import create_local_demo_app

    assert google_docs_service.configured(create_local_demo_app().config) is False
