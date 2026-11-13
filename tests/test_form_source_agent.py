"""表單代理（2026-11-13）：從學校網站抓表單 → 待核准 → 主任、副主任核准上架；只連學校網域。

網頁內容是照 2026-11-13 實際看到的學校網站結構簡化的假資料，測試不連網路。
"""
import pytest

from app import create_app
from app.extensions import db
from app.models import FormItem, User
from app.services import form_library_service, form_source_agent as agent

PDF = b"%PDF-1.4 fake form"
PDF2 = b"%PDF-1.4 fake form v2"
DOCX = b"PK\x03\x04 fake docx"

LIST = """<html><head><title>實習表格</title></head><body><ul>
<li><a href="/p/405-1028-7224,c1193.php?Lang=zh-tw">01.學生實習志願序</a></li>
<li><a href="/p/405-1028-7223,c1193.php?Lang=zh-tw">02.學生實習履歷</a></li>
</ul></body></html>"""
ITEM = """<html><head><title>{title}</title></head><body>
<a href="/var/file/28/1028/img/604/{n}.docx">(DOC)</a> <a href="/var/file/28/1028/img/604/{n}.pdf">(PDF)</a>
<a href="https://evil.example.com/x.pdf">外部</a></body></html>"""
TABLE = """<html><head><title>生輔組表單下載</title></head><body><table>
<tr><td>學生公假申請書 (PDF)</td><td><a href="https://ukn05.ukn.edu.tw/var/file/3/1003/img/659882068.pdf">PDF</a></td></tr>
<tr><td>班級座次表 (PDF) (DOC)</td><td><a href="/var/file/3/1003/img/578985912.pdf">PDF</a> <a href="/var/file/3/1003/img/748539750.doc">DOC</a></td></tr>
</table></body></html>"""

SOURCES = [
    agent.Source("im-internship", "資管科", "實習", "https://im.ukn.edu.tw/p/412-1028-1193.php?Lang=zh-tw", "items"),
    agent.Source("sa-life", "學務處生活輔導組", "常用表格", "https://ukn05.ukn.edu.tw/p/412-1003-3494.php?Lang=zh-tw", "table"),
]


def fake_site(files=None):
    files = files or {}
    calls = []

    def fetch(url, limit=None):
        calls.append(url)
        if "evil" in url:
            raise AssertionError("不應該連學校以外的網站")
        if url.endswith("412-1028-1193.php?Lang=zh-tw"):
            return LIST.encode()
        if "405-1028-7224" in url:
            return ITEM.format(title="01.學生實習志願序", n=231303945).encode()
        if "405-1028-7223" in url:
            return ITEM.format(title="02.學生實習履歷", n=176807139).encode()
        if url.endswith("412-1003-3494.php?Lang=zh-tw"):
            return TABLE.encode()
        if url.endswith(".pdf"):
            return files.get(url, PDF)
        if url.endswith((".doc", ".docx")):
            return DOCX
        raise OSError("404")

    fetch.calls = calls
    return fetch


@pytest.fixture()
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        for username, title in (("chief", "主任"), ("assistant", "科助")):
            user = User(username=username, display_name=username, role="staff", job_title=title)
            user.set_password("pw")
            db.session.add(user)
        student = User(username="stu", display_name="stu", role="student")
        student.set_password("pw")
        db.session.add(student)
        db.session.commit()
    yield app


def login(app, username):
    client = app.test_client()
    client.post("/login" if username == "stu" else "/staff/login", data={"username": username, "password": "pw"})
    return client


def test_discover_reads_both_school_layouts_and_prefers_pdf():
    internship = agent.discover(SOURCES[0], fake_site())
    assert [f.title for f in internship] == ["學生實習志願序", "學生實習履歷"]
    assert internship[0].best_file == ("pdf", "https://im.ukn.edu.tw/var/file/28/1028/img/604/231303945.pdf")
    assert all("evil" not in url for form in internship for _, url in form.files)  # 學校以外的連結不收

    life = agent.discover(SOURCES[1], fake_site())
    assert [f.title for f in life] == ["學生公假申請書", "班級座次表"]
    assert life[1].best_file[0] == "pdf" and len(life[1].files) == 2


def test_sync_creates_pending_forms_then_updates_approved_ones(app):
    with app.app_context():
        assistant = User.query.filter_by(username="assistant").one()
        summary = agent.sync(assistant, fake_site(), SOURCES)
        db.session.commit()
        assert sorted(summary["new"]) == sorted(["學生實習志願序", "學生實習履歷", "學生公假申請書", "班級座次表"])
        assert not summary["errors"]
        leave = FormItem.query.filter_by(title="學生公假申請書").one()
        assert leave.origin == "agent" and leave.review_state == "pending" and not leave.is_published
        assert leave.latest_version.original_filename == "學生公假申請書.pdf"
        assert leave.category.name == "常用表格"

        again = agent.sync(assistant, fake_site(), SOURCES)  # 沒變就不會多一版
        assert again["unchanged"] == 4 and not again["new"] and not again["updated"]

        agent.approve(leave, User.query.filter_by(username="chief").one())
        db.session.commit()
        changed = fake_site({"https://ukn05.ukn.edu.tw/var/file/3/1003/img/659882068.pdf": PDF2})
        updated = agent.sync(assistant, changed, SOURCES)
        db.session.commit()
        assert updated["updated"] == ["學生公假申請書"]
        assert [v.version_no for v in leave.versions] == [1, 2] and leave.is_published


def test_one_broken_source_does_not_stop_others(app):
    def flaky(url, limit=None):
        if "1193" in url:
            raise OSError("連不上")
        return fake_site()(url, limit)

    with app.app_context():
        summary = agent.sync(User.query.filter_by(username="assistant").one(), flaky, SOURCES)
        assert len(summary["new"]) == 2 and any("實習" in e for e in summary["errors"])


def test_fetch_refuses_non_school_hosts():
    with pytest.raises(OSError):
        agent.fetch("https://evil.example.com/form.pdf")


def test_only_director_can_approve_and_students_see_only_approved(app, monkeypatch):
    monkeypatch.setattr(agent, "SOURCES", SOURCES)
    monkeypatch.setattr(agent, "fetch", fake_site())
    assistant = login(app, "assistant")
    page = assistant.post("/staff/forms/sync").get_data(as_text=True)
    assert "新抓到 4 份" in page and "上架要由主任或副主任核准" in page
    assert "學生公假申請書" not in login(app, "stu").get("/forms").get_data(as_text=True)

    with app.app_context():
        item_id = FormItem.query.filter_by(title="學生公假申請書").one().id
    assert assistant.post(f"/staff/forms/{item_id}/approve").status_code == 403
    assert assistant.post("/staff/forms/approve-all").status_code == 403
    assert assistant.post(f"/staff/forms/{item_id}/publish", data={"action": "republish"}).status_code == 403

    chief = login(app, "chief")
    assert "全部核准上架" in chief.get("/staff/forms").get_data(as_text=True)
    chief.post(f"/staff/forms/{item_id}/approve")
    assert "學生公假申請書" in login(app, "stu").get("/forms").get_data(as_text=True)
    with app.app_context():
        item = db.session.get(FormItem, item_id)
        assert item.approved_by.username == "chief" and item.review_state == "published"


def test_assistant_manual_upload_waits_for_approval(app):
    from io import BytesIO
    assistant = login(app, "assistant")
    with app.app_context():
        from app.models import FormCategory
        category = FormCategory(name="常用表格", sort_order=1, is_active=True)
        db.session.add(category)
        db.session.commit()
        category_id = category.id
    assistant.post("/staff/forms", data={"category_id": str(category_id), "title": "手動表單", "open_to_students": "1",
                                         "file": (BytesIO(PDF), "手動表單.pdf")}, content_type="multipart/form-data")
    with app.app_context():
        assert FormItem.query.filter_by(title="手動表單").one().review_state == "pending"
        assert form_library_service.can_download(User.query.filter_by(username="stu").one(),
                                                 FormItem.query.filter_by(title="手動表單").one()) is False


def test_paragraph_rows_and_download_script_links():
    """學務處是一段一份（<p>），資管科法規的附件走下載程式、副檔名只在連結文字（2026-11-13 實際網頁）。"""
    paragraph = ('<p><span>學生公假申請書&nbsp; (</span><a href="/var/file/3/1003/img/659882068.pdf">'
                 '<span>PDF</span></a><span>)</span></p>')
    script = ('<a href="/app/index.php?Action=downloadfile&amp;file=abc&amp;cg=1209" title="[下載]">'
              '<img src="/images/icon/pdf.gif">09.資管科學生課業輔導實施辦法(105215).pdf</a>')

    def fetch(url, limit=None):
        if url.endswith("412-1003-3494.php?Lang=zh-tw"):
            return paragraph.encode()
        if url.endswith("412-1028-1209.php?Lang=zh-tw"):
            return '<li><a href="/p/405-1028-36561,c1209.php?Lang=zh-tw">資管科學生課業輔導實施辦法</a></li>'.encode()
        return script.encode()

    life = agent.discover(SOURCES[1], fetch)
    assert [f.title for f in life] == ["學生公假申請書"]
    rules = agent.discover(agent.Source("im-rules", "資管科", "相關法規",
                                        "https://im.ukn.edu.tw/p/412-1028-1209.php?Lang=zh-tw", "items"), fetch)
    assert rules[0].best_file == ("pdf", "https://im.ukn.edu.tw/app/index.php?Action=downloadfile&file=abc&cg=1209")
