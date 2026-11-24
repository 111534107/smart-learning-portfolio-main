"""表單下載區的學校網站連結檢查（2026-11-12 指導老師）：每筆連結記錄最後檢查時間與狀態；
科辦或管理員按「檢查連結」，失效的在清單標示；學生端看到失效連結時提醒洽科辦。
測試不連外網：連線一律用假物件。網址與表單都是合成資料，僅為測試資料。"""
import socket
import urllib.error

import pytest
from sqlalchemy import inspect

from app import create_app
from app.extensions import db
from app.models import AuditLog, FormCategory, FormItem, User
from app.services import form_library_service as forms
from tests.test_form_library_routes import PDF_V1, category_id, forms_app, item_id, login, publish

GOOD = "https://forms.example.edu.tw/leave.pdf"
DEAD = "https://forms.example.edu.tw/old/leave.pdf"


def links_app(tmp_path):
    app = forms_app(tmp_path)
    with app.app_context():
        admin = User(username="admin", display_name="合成管理員", role="admin")
        admin.set_password("pw")
        db.session.add(admin)
        db.session.commit()
    return app


def publish_link(app, client, title, url, with_file=True):
    import io
    form = {"category_id": str(category_id(app)), "title": title, "source_url": url,
            "open_to_students": "1", "open_to_teachers": "1"}
    if with_file:
        form["file"] = (io.BytesIO(PDF_V1), "表單.pdf")
    return client.post("/staff/forms", data=form, content_type="multipart/form-data")


def fake_fetch(statuses):
    """假的連線：依網址回傳狀態碼，或丟出設定好的例外；記下被呼叫的網址與逾時秒數。"""
    calls = []

    def fetch(url, timeout):
        calls.append((url, timeout))
        result = statuses[url]
        if isinstance(result, Exception):
            raise result
        return result
    fetch.calls = calls
    return fetch


# ---------- 規則 ----------

@pytest.mark.parametrize("url", ["ftp://example.edu.tw/a.pdf", "javascript:alert(1)", "file:///etc/passwd",
                                 "example.edu.tw/a.pdf", "https://", "http://exa mple.edu.tw/a",
                                 "https://example.edu.tw/" + "a" * 500])
def test_clean_url_rejects_non_http(url):
    with pytest.raises(forms.LinkRejected):
        forms.clean_url(url)


def test_clean_url_accepts_http_and_https_and_blank():
    assert forms.clean_url(" https://example.edu.tw/表單.pdf ") == "https://example.edu.tw/表單.pdf"
    assert forms.clean_url("HTTP://example.edu.tw/a") == "HTTP://example.edu.tw/a"
    assert forms.clean_url("") is None and forms.clean_url(None) is None


@pytest.mark.parametrize("result,status", [
    (200, "ok"), (204, "ok"), (301, "ok"),
    (404, "broken"), (410, "broken"), (500, "broken"), (503, "broken"),
    (401, "unsure"), (403, "unsure"), (429, "unsure"),
    (socket.timeout("timed out"), "broken"),
    (urllib.error.URLError("no such host"), "broken"),
    (ConnectionResetError("reset"), "broken"),
])
def test_check_link_maps_results(result, status):
    fetch = fake_fetch({GOOD: result})
    got, detail = forms.check_link(GOOD, fetch=fetch)
    assert got == status and detail
    assert fetch.calls == [(GOOD, forms.LINK_TIMEOUT_SECONDS)]


def test_check_link_never_connects_for_non_http():
    fetch = fake_fetch({})
    status, detail = forms.check_link("ftp://example.edu.tw/a.pdf", fetch=fetch)
    assert status == "broken" and fetch.calls == []


def test_default_fetch_uses_timeout_and_falls_back_to_get(monkeypatch):
    """真正連線的那一段：用假的 opener 確認有帶逾時、先 HEAD、網站不收 HEAD 時改 GET。"""
    seen = []

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class FakeOpener:
        def open(self, request, timeout=None):
            seen.append((request.get_method(), request.full_url, timeout))
            if request.get_method() == "HEAD":
                raise urllib.error.HTTPError(request.full_url, 405, "Method Not Allowed", {}, None)
            return FakeResponse()

    monkeypatch.setattr(forms, "_opener", lambda: FakeOpener())
    assert forms.fetch_status(GOOD, 5) == 200
    assert seen == [("HEAD", GOOD, 5), ("GET", GOOD, 5)]

    class NotFoundOpener:
        def open(self, request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(forms, "_opener", lambda: NotFoundOpener())
    assert forms.fetch_status(GOOD, 5) == 404


def test_redirect_to_non_http_is_refused():
    handler = forms.HttpOnlyRedirect()
    with pytest.raises(urllib.error.HTTPError):
        handler.redirect_request(urllib.request.Request(GOOD), None, 302, "Found", {}, "ftp://example.edu.tw/a")


def test_check_all_links_records_status_and_time(tmp_path):
    app = links_app(tmp_path)
    staff = login(app, "staff")
    publish_link(app, staff, "請假單", GOOD)
    publish_link(app, staff, "舊版請假單", DEAD)
    publish(app, staff, title="沒有連結的表單")
    with app.app_context():
        fetch = fake_fetch({GOOD: 200, DEAD: 404})
        summary = forms.check_all_links(fetch=fetch)
        db.session.commit()
        assert summary == {"checked": 2, "ok": 1, "broken": 1, "unsure": 0}
        good = FormItem.query.filter_by(title="請假單").one()
        dead = FormItem.query.filter_by(title="舊版請假單").one()
        plain = FormItem.query.filter_by(title="沒有連結的表單").one()
        assert good.link_status == "ok" and good.link_checked_at is not None
        assert dead.link_status == "broken" and "404" in dead.link_detail and dead.link_checked_at is not None
        assert plain.link_status is None and plain.link_checked_at is None
        assert sorted(url for url, _ in fetch.calls) == sorted([GOOD, DEAD])
        assert forms.broken_link_count() == 1


# ---------- 科辦頁面 ----------

def test_staff_publishes_form_with_link_and_bad_url_is_rejected(tmp_path):
    app = links_app(tmp_path)
    staff = login(app, "staff")
    assert publish_link(app, staff, "請假單", GOOD).status_code == 302
    bad = publish_link(app, staff, "壞連結", "javascript:alert(1)")
    assert bad.status_code == 400 and "http" in bad.get_data(as_text=True)
    with app.app_context():
        assert FormItem.query.filter_by(title="請假單").one().source_url == GOOD
        assert FormItem.query.filter_by(title="壞連結").count() == 0


def test_link_only_form_can_be_published_but_needs_file_or_link(tmp_path):
    app = links_app(tmp_path)
    staff = login(app, "staff")
    assert publish_link(app, staff, "只有連結", GOOD, with_file=False).status_code == 302
    assert publish_link(app, staff, "什麼都沒有", "", with_file=False).status_code == 400
    student = login(app, "stu")
    page = student.get("/forms").get_data(as_text=True)
    assert "只有連結" in page and GOOD in page
    assert student.get(f"/forms/{item_id(app, '只有連結')}/download").status_code == 404
    assert staff.get("/staff/forms").status_code == 200
    assert staff.get(f"/staff/forms/{item_id(app, '只有連結')}").status_code == 200


def test_changing_url_resets_check_status(tmp_path):
    app = links_app(tmp_path)
    staff = login(app, "staff")
    publish_link(app, staff, "請假單", DEAD)
    with app.app_context():
        forms.check_all_links(fetch=fake_fetch({DEAD: 404}))
        db.session.commit()
    form = {"category_id": str(category_id(app)), "title": "請假單", "open_to_students": "1", "source_url": GOOD}
    assert staff.post(f"/staff/forms/{item_id(app, '請假單')}", data=form).status_code == 302
    with app.app_context():
        item = FormItem.query.filter_by(title="請假單").one()
        assert item.source_url == GOOD and item.link_status is None and item.link_checked_at is None
    bad = dict(form, source_url="ftp://example.edu.tw/a")
    assert staff.post(f"/staff/forms/{item_id(app, '請假單')}", data=bad).status_code == 400


def test_check_links_button_marks_broken_for_staff(tmp_path, monkeypatch):
    app = links_app(tmp_path)
    staff = login(app, "staff")
    publish_link(app, staff, "請假單", GOOD)
    publish_link(app, staff, "舊版請假單", DEAD)
    monkeypatch.setattr(forms, "fetch_status", fake_fetch({GOOD: 200, DEAD: socket.timeout("timed out")}))

    before = staff.get("/staff/forms/links").get_data(as_text=True)
    assert "還沒檢查" in before and 'action="/staff/forms/links/check"' in before

    response = staff.post("/staff/forms/links/check")
    assert response.status_code == 302 and response.headers["Location"].endswith("/staff/forms/links")
    page = staff.get("/staff/forms/links").get_data(as_text=True)
    assert "連結失效" in page and "連線逾時" in page and "正常" in page
    assert "請更新成最新的連結" in page
    manage = staff.get("/staff/forms").get_data(as_text=True)
    assert "1 個連結失效" in manage and 'href="/staff/forms/links"' in manage
    with app.app_context():
        log = AuditLog.query.filter_by(action="form.check_links").one()
        assert log.detail_json == {"checked": 2, "ok": 1, "broken": 1, "unsure": 0}


def test_admin_can_check_links_but_students_and_teachers_cannot(tmp_path, monkeypatch):
    app = links_app(tmp_path)
    publish_link(app, login(app, "staff"), "請假單", DEAD)
    monkeypatch.setattr(forms, "fetch_status", fake_fetch({DEAD: 404}))
    for username in ("stu", "tea"):
        client = login(app, username)
        assert client.get("/staff/forms/links").status_code == 403
        assert client.post("/staff/forms/links/check").status_code == 403
    with app.app_context():
        assert FormItem.query.one().link_status is None
    admin = login(app, "admin")
    assert admin.post("/staff/forms/links/check").status_code == 302
    page = admin.get("/staff/forms/links").get_data(as_text=True)
    assert "連結失效" in page and "HTTP 404" in page
    assert "/staff/forms/%d\"" % item_id(app, "請假單") not in page  # 管理員不能進科辦的管理頁，不給連結


# ---------- 學生端 ----------

def test_student_sees_warning_only_for_broken_link(tmp_path):
    app = links_app(tmp_path)
    staff = login(app, "staff")
    publish_link(app, staff, "請假單", GOOD)
    publish_link(app, staff, "舊版請假單", DEAD)
    warning = "連結可能已失效，請洽科辦"
    student = login(app, "stu")
    assert warning not in student.get("/forms").get_data(as_text=True)  # 還沒檢查不提醒
    with app.app_context():
        forms.check_all_links(fetch=fake_fetch({GOOD: 200, DEAD: 404}))
        db.session.commit()
    page = student.get("/forms").get_data(as_text=True)
    assert page.count(warning) == 1
    assert f'href="{GOOD}"' in page and 'rel="noopener noreferrer"' in page
    assert f'href="{DEAD}"' not in page  # 失效的不給點，改顯示提醒
    assert warning in login(app, "tea").get("/forms").get_data(as_text=True)


# ---------- 資料庫與示範資料 ----------

def test_migration_adds_and_drops_link_columns(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'm.db'}", "TESTING": True})
    runner = app.test_cli_runner()
    assert runner.invoke(args=["db", "upgrade"]).exit_code == 0
    wanted = {"source_url", "link_status", "link_detail", "link_checked_at"}
    with app.app_context():
        assert wanted <= {c["name"] for c in inspect(db.engine).get_columns("form_items")}
    assert runner.invoke(args=["db", "downgrade", "b20261110h01"]).exit_code == 0
    with app.app_context():
        assert not wanted & {c["name"] for c in inspect(db.engine).get_columns("form_items")}
    from alembic.script import ScriptDirectory
    assert len(ScriptDirectory("migrations").get_heads()) == 1  # 遷移鏈只有一個 head


def test_demo_forms_have_synthetic_links_with_one_broken(tmp_path):
    from tests.test_form_library import make_app
    app = make_app(tmp_path)
    with app.app_context():
        forms.seed_demo_forms(User.query.filter_by(username="staff").one())
        db.session.commit()
        linked = FormItem.query.filter(FormItem.source_url.isnot(None)).all()
        # 假網址用 example 網域；只有公假申請單是 2026-11-13 查到的學務處正式檔
        assert linked and all(".example." in item.source_url or item.source_url.startswith("https://ukn05.ukn.edu.tw/")
                              for item in linked)
        assert any(item.link_status == "broken" for item in linked)
        assert FormCategory.query.count() == 4
