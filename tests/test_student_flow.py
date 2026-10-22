"""學生主線動線：做完回原處並顯示更新、上傳後直接確認、首頁下一步在上方、導覽列精簡（合成資料）。"""
import io
import re

import pytest

from app import create_app
from app.extensions import db
from app.models import AdmissionProgram, DocumentExtraction, SourceDocument, StudentProfile, StudentTarget, User
from app.models.transfer_credit import TransferCreditRecord


@pytest.fixture()
def app(tmp_path):
    from app.services.admission_service import import_seed_programs

    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "UPLOAD_FOLDER": str(tmp_path), "DOCUMENT_ANALYSIS_PROVIDER": "fake"})
    with app.app_context():
        db.create_all()
        student = User(username="student_syn", display_name="合成學生", role="student")
        student.set_password("pw")
        db.session.add(student)
        db.session.flush()
        db.session.add(StudentProfile(user_id=student.id, student_no="SYN0001", admission_year=111))
        import_seed_programs()
        program = AdmissionProgram.query.order_by(AdmissionProgram.id).first()
        db.session.add(StudentTarget(student_id=student.id, rule_version_id=program.id))
        db.session.commit()
        app.config["SYN_PROGRAM_ID"] = program.id
    return app


@pytest.fixture()
def client(app):
    client = app.test_client()
    client.post("/login", data={"username": "student_syn", "password": "pw"})
    return client


def target_path(app):
    return f"/student/targets/{app.config['SYN_PROGRAM_ID']}"


def upload(client, next_path=None):
    data = {"document_type": "transcript", "file": (io.BytesIO(b"synthetic"), "synthetic.pdf")}
    if next_path:
        data["next"] = next_path
    return client.post("/student/learning-profile/documents", data=data, content_type="multipart/form-data")


def confirm(client, app, next_path=None):
    with app.app_context():
        document = SourceDocument.query.order_by(SourceDocument.id.desc()).first()
        document_id, revision = document.id, document.extraction.result_json["draft_revision"]
    data = {"draft_revision": revision, "credentials_json": "[]",
            "courses_json": '[{"course_name": "模擬程式設計", "credits": "3", "score": "92", "grade_level": "一年級"}]'}
    if next_path:
        data["next"] = next_path
    return client.post(f"/student/learning-profile/documents/{document_id}/review/confirm", data=data)


def nav_html(html):
    return re.search(r'<nav class="mainnav".*?</nav>', html, re.S).group(0)


# 1. 上傳後先到「辨識中」頁，辨識完成就進確認頁
def test_upload_goes_to_processing_then_review_page(client, app):
    response = upload(client)

    assert response.status_code == 302
    with app.app_context():
        document_id = SourceDocument.query.one().id
    assert response.headers["Location"].endswith(f"/student/learning-profile/documents/{document_id}/processing")
    processing = client.get(response.headers["Location"])
    assert processing.headers["Location"].endswith(f"/student/learning-profile/documents/{document_id}/review")


# 2. 做完回原處並顯示更新
def test_gap_page_add_links_remember_where_the_student_came_from(client, app):
    html = client.get(target_path(app)).get_data(as_text=True)

    assert f"/student/learning-profile/upload?type=transcript&amp;next=/student/targets/{app.config['SYN_PROGRAM_ID']}" in html


def test_upload_and_confirm_return_to_target_with_readiness_update(client, app):
    path = target_path(app)
    upload_page = client.get(f"/student/learning-profile/upload?next={path}").get_data(as_text=True)
    assert f'name="next" value="{path}"' in upload_page

    response = upload(client, path)
    assert "next=/student/targets/" in response.headers["Location"]
    processing = client.get(response.headers["Location"])
    assert "next=/student/targets/" in processing.headers["Location"]
    review = client.get(processing.headers["Location"]).get_data(as_text=True)
    assert f'name="next" value="{path}"' in review

    response = confirm(client, app, path)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(path)
    page = client.get(path).get_data(as_text=True)
    assert "已儲存 1 門課程" in page
    assert re.search(r"準備度 \d+% → \d+%", page)


def test_unsafe_next_is_ignored(client, app):
    upload(client)
    for unsafe in ("https://evil.example/", "//evil.example/", "/\\evil.example"):
        response = confirm(client, app, unsafe)
        assert response.headers["Location"].endswith("/student/learning-profile")
        upload(client)


def test_new_activity_returns_to_target_page(client, app):
    path = target_path(app)
    form = client.get(f"/student/portfolio/new?category=activity&next={path}").get_data(as_text=True)
    assert f'name="next" value="{path}"' in form

    response = client.post("/student/portfolio", data={
        "title": "模擬資訊週志工", "category": "activity", "school_year": "2", "semester": "1", "next": path,
    })

    assert response.headers["Location"].endswith(path)
    assert "已新增「模擬資訊週志工」" in client.get(path).get_data(as_text=True)


# 3. 首頁的下一步在拼圖之前
def test_dashboard_shows_next_steps_before_the_puzzle(client):
    html = client.get("/student/dashboard").get_data(as_text=True)

    assert html.index('class="today"') < html.index('class="year-puzzle"')


# 4. 導覽列：目標校系與備審資料合併；抵免進度只給轉學生
def test_navigation_merges_targets_and_package(client):
    nav = nav_html(client.get("/student/dashboard").get_data(as_text=True))

    assert "目標與備審" in nav
    assert "備審資料" not in nav and ">目標校系<" not in nav


def test_transfer_credit_is_hidden_from_students_without_a_transfer_record(client, app):
    html = client.get("/student/dashboard").get_data(as_text=True)

    assert "抵免進度" not in nav_html(html)
    assert "轉學生？填寫抵免進度" in html
    with app.app_context():
        student = User.query.filter_by(username="student_syn").one()
        db.session.add(TransferCreditRecord(student_id=student.id))
        db.session.commit()
    assert "抵免進度" in nav_html(client.get("/student/dashboard").get_data(as_text=True))


# 5. 上傳時顯示辨識中
def test_upload_button_says_uploading_while_submitting(client):
    # 辨識改在「辨識中」頁顯示，按鈕只負責上傳
    html = client.get("/student/learning-profile/upload").get_data(as_text=True)

    assert re.search(r'<button[^>]*data-busy-text="上傳中[^"]*"[^>]*>上傳</button>', html)
