"""成績單與證照分成兩個頁面與兩個導覽項目（合成資料）。"""
import re

import pytest

from app import create_app
from app.extensions import db
from app.models import CredentialRecord, DocumentExtraction, LearningCourseRecord, SourceDocument, User


@pytest.fixture()
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        student = User(username="student_syn", display_name="合成學生", role="student")
        student.set_password("pw")
        db.session.add(student)
        db.session.flush()
        for kind, name in (("transcript", "合成成績單.pdf"), ("credential", "合成證照.png")):
            document = SourceDocument(owner_id=student.id, document_type=kind, display_name=name,
                                      file_path=str(tmp_path / name), sha256="0" * 64, status="extracted")
            db.session.add(document)
            db.session.flush()
            db.session.add(DocumentExtraction(source_document_id=document.id, provider="fake", status="extracted",
                                              result_json={"draft_revision": f"r-{kind}", "courses": [], "credentials": []}))
        db.session.add(LearningCourseRecord(student_id=student.id, course_name="模擬資料結構",
                                            normalized_course_name="模擬資料結構", credits=3, score=88))
        db.session.add(CredentialRecord(student_id=student.id, credential_name="模擬網頁設計丙級"))
        db.session.commit()
    return app


@pytest.fixture()
def client(app):
    client = app.test_client()
    client.post("/login", data={"username": "student_syn", "password": "pw"})
    return client


def nav_html(html):
    return re.search(r'<nav class="mainnav".*?</nav>', html, re.S).group(0)


def test_navigation_has_separate_transcript_and_credential_items(client):
    nav = nav_html(client.get("/student/dashboard").get_data(as_text=True))

    assert ">成績單<" in nav and ">證照<" in nav
    assert "成績與證照" not in nav
    assert 'href="/student/learning-profile/credentials"' in nav


def test_transcript_page_shows_only_transcripts_and_courses(client):
    html = client.get("/student/learning-profile").get_data(as_text=True)

    assert "合成成績單.pdf" in html and "模擬資料結構" in html
    assert "合成證照.png" not in html and "模擬網頁設計丙級" not in html
    assert 'href="/student/learning-profile/upload?type=transcript"' in html


def test_credential_page_shows_only_credentials(client):
    html = client.get("/student/learning-profile/credentials").get_data(as_text=True)

    assert "合成證照.png" in html and "模擬網頁設計丙級" in html
    assert "合成成績單.pdf" not in html and "模擬資料結構" not in html
    assert 'href="/student/learning-profile/upload?type=credential"' in html
    assert re.search(r'<a href="/student/learning-profile/credentials" aria-current="page">證照</a>', nav_html(html))


@pytest.mark.parametrize("kind, label, other", [("transcript", "上傳成績單", "credential"),
                                                ("credential", "上傳證照", "transcript")])
def test_upload_page_is_fixed_to_one_document_type(client, kind, label, other):
    """成績單和證照分開上傳：頁面不給選類型，避免傳錯地方。"""
    html = client.get(f"/student/learning-profile/upload?type={kind}").get_data(as_text=True)

    assert f'<input type="hidden" name="document_type" value="{kind}">' in html
    assert 'type="radio" name="document_type"' not in html
    assert f"<h1>{label}</h1>" in html or f">{label}<" in html
    # 真的傳錯頁時有一條小連結換過去
    assert f'href="/student/learning-profile/upload?type={other}"' in html


def test_upload_page_without_type_is_transcript(client):
    html = client.get("/student/learning-profile/upload").get_data(as_text=True)
    assert '<input type="hidden" name="document_type" value="transcript">' in html


def test_every_upload_link_names_its_document_type(app):
    """首頁、缺件、建議卡等所有「上傳成績／證照」連結都要帶類型，不會開到另一種。"""
    from app.services import focus_service, journey_home, student_progress
    with app.test_request_context():
        for module in (focus_service, journey_home, student_progress):
            assert module._add_link("grades") == "/student/learning-profile/upload?type=transcript"
            assert module._add_link("credential") == "/student/learning-profile/upload?type=credential"
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "app"
    guide = root.joinpath("services", "guide_service.py").read_text(encoding="utf-8")
    assert '"上傳成績單", url_for("student.learning_profile_upload_page", type="transcript")' in guide
    assert guide.count('"上傳證照", url_for("student.learning_profile_upload_page", type="credential")') == 2
    for name in ("student_home.html", "student_gap.html"):
        template = root.joinpath("templates", name).read_text(encoding="utf-8")
        assert 'learning_profile_upload_page", type="transcript"' in template
        assert 'learning_profile_upload_page", type="credential"' in template


def test_folder_tabs_have_no_vertical_scrollbar():
    """首頁年級分頁：分頁往下壓 6 像素蓋住資料夾邊框，不可因此冒出上下捲軸。"""
    from pathlib import Path
    css = (Path(__file__).resolve().parents[1] / "app" / "static" / "css" / "design-system.css").read_text(encoding="utf-8")
    rule = re.search(r"\.folder-tabs \{[^}]*\}", css).group(0)
    assert "overflow-y: hidden" in rule


def test_confirming_without_next_returns_to_the_page_of_that_document_type(client, app):
    with app.app_context():
        ids = {d.document_type: d.id for d in SourceDocument.query.all()}

    credential = client.post(f"/student/learning-profile/documents/{ids['credential']}/review/confirm", data={
        "draft_revision": "r-credential", "courses_json": "[]",
        "credentials_json": '[{"credential_name": "模擬電腦軟體應用丙級"}]',
    })
    transcript = client.post(f"/student/learning-profile/documents/{ids['transcript']}/review/confirm", data={
        "draft_revision": "r-transcript", "credentials_json": "[]",
        "courses_json": '[{"course_name": "模擬網頁設計", "credits": "2", "score": "90"}]',
    })

    assert credential.headers["Location"].endswith("/student/learning-profile/credentials")
    assert transcript.headers["Location"].endswith("/student/learning-profile")
