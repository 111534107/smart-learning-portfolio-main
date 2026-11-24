"""自傳貼上圖片：學生在段落裡加入圖片，存成新版時保留；只有本人與班導看得到；備審 Word 帶出圖片。僅為測試資料。"""

import io
import re

import pytest
from docx import Document
from PIL import Image

from app import create_app
from app.extensions import db
from app.models import (AdmissionProgram, AuditLog, ClassAdvisor, LearningProfileOutput, StudentProfile, StudentTarget, User)
from app.services import autobiography_backup, autobiography_service


def png_bytes(color=(200, 30, 30), size=(40, 30)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, "PNG")
    return buffer.getvalue()


@pytest.fixture
def setup(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "UPLOAD_FOLDER": str(tmp_path / "up")})
    with app.app_context():
        db.create_all()
        users = []
        for name, role in [("s1", "student"), ("s2", "student"), ("t1", "teacher"), ("t2", "teacher")]:
            user = User(username=name, display_name=name, role=role)
            user.set_password("pw")
            users.append(user)
        db.session.add_all(users)
        db.session.flush()
        ids = {u.username: u.id for u in users}
        db.session.add_all([
            StudentProfile(user_id=ids["s1"], student_no="D1", class_name="甲班", admission_year=111),
            StudentProfile(user_id=ids["s2"], student_no="D2", class_name="乙班", admission_year=111),
            ClassAdvisor(teacher_id=ids["t1"], class_name="甲班", school_year=115),
        ])
        program = AdmissionProgram(program_code="D1", admission_year=115, school_name="測試大學",
                                   department_name="資管系", status="published")
        db.session.add(program)
        db.session.flush()
        db.session.add(StudentTarget(student_id=ids["s1"], rule_version_id=program.id))
        draft = LearningProfileOutput(
            student_id=ids["s1"], output_type=autobiography_service.OUTPUT_TYPE,
            content_json={"program_id": program.id, "version": 1, "provider": "demo",
                          "paragraphs": [{"title": "段一", "text": "原文"}, {"title": "段二", "text": "第二段"}]},
            source_snapshot_json={})
        db.session.add(draft)
        db.session.commit()
        ids.update(program=program.id, draft=draft.id)
    return app, ids


def login(app, name):
    client = app.test_client()
    path = "/staff/login" if name.startswith("t") else "/login"
    client.post(path, data={"username": name, "password": "pw"})
    return client


def upload(client, data=None, name="a.png"):
    return client.post("/student/autobiography/images", data={"image": (io.BytesIO(data or png_bytes()), name)},
                       content_type="multipart/form-data")


def test_student_uploads_image_and_it_is_recoded(setup):
    app, ids = setup
    client = login(app, "s1")
    response = upload(client)
    assert response.status_code == 200
    info = response.get_json()
    assert re.fullmatch(r"[0-9a-f]{32}", info["id"]) and info["url"].endswith(info["id"])
    shown = client.get(info["url"])
    assert shown.status_code == 200 and shown.mimetype == "image/jpeg"
    Image.open(io.BytesIO(shown.data)).verify()


@pytest.mark.parametrize("payload,name", [(b"not an image", "a.png"), (b"<svg onload=alert(1)/>", "a.svg")])
def test_non_image_rejected(setup, payload, name):
    app, ids = setup
    assert upload(login(app, "s1"), payload, name).status_code == 400


def test_image_visible_only_to_owner_and_class_teacher(setup):
    app, ids = setup
    owner = login(app, "s1")
    url = upload(owner).get_json()["url"]
    assert login(app, "s2").get(url).status_code in (403, 404)
    assert login(app, "t1").get(url).status_code == 200
    assert login(app, "t2").get(url).status_code in (403, 404)
    assert app.test_client().get(url).status_code in (401, 403)


def test_save_keeps_images_in_new_version_and_ignores_foreign_ids(setup):
    app, ids = setup
    s1, s2 = login(app, "s1"), login(app, "s2")
    mine = upload(s1).get_json()["id"]
    foreign = upload(s2).get_json()["id"]
    response = s1.post(f"/student/autobiography/{ids['draft']}/save",
                       data={"paragraph_0": "改過", "paragraph_1": "第二段",
                             "paragraph_0_image": [mine, foreign, "../../etc/passwd"]})
    assert response.status_code == 302
    with app.app_context():
        latest = LearningProfileOutput.query.order_by(LearningProfileOutput.id.desc()).first()
        paragraphs = latest.content_json["paragraphs"]
        assert paragraphs[0]["images"] == [mine]  # 別人的與不合法的編號被丟掉
        assert not paragraphs[1].get("images")
        assert latest.content_json["version"] == 2


def test_editor_page_shows_image_controls_and_thumbnail(setup):
    app, ids = setup
    s1 = login(app, "s1")
    image_id = upload(s1).get_json()["id"]
    s1.post(f"/student/autobiography/{ids['draft']}/save", data={"paragraph_0": "x", "paragraph_1": "y", "paragraph_0_image": [image_id]})
    page = s1.get(f"/student/autobiography?program_id={ids['program']}").get_data(as_text=True)
    assert "data-image-box" in page and f"/student/autobiography-images/" in page and image_id in page


def test_docx_contains_embedded_image(setup):
    app, ids = setup
    s1 = login(app, "s1")
    image_id = upload(s1).get_json()["id"]
    s1.post(f"/student/autobiography/{ids['draft']}/save", data={"paragraph_0": "x", "paragraph_1": "y", "paragraph_0_image": [image_id]})
    with app.app_context():
        latest = LearningProfileOutput.query.order_by(LearningProfileOutput.id.desc()).first()
        student = db.session.get(User, ids["s1"])
        program = db.session.get(AdmissionProgram, ids["program"])
        data = autobiography_backup.build_docx(student, program, latest.content_json)
        assert len(Document(io.BytesIO(data)).inline_shapes) == 1


def test_class_teacher_sees_images_on_student_page(setup):
    app, ids = setup
    s1 = login(app, "s1")
    image_id = upload(s1).get_json()["id"]
    s1.post(f"/student/autobiography/{ids['draft']}/save", data={"paragraph_0": "x", "paragraph_1": "y", "paragraph_0_image": [image_id]})
    page = login(app, "t1").get(f"/teacher/students/{ids['s1']}").get_data(as_text=True)
    assert image_id in page
