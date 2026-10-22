"""證照確認頁：每個欄位直接顯示原圖裡被辨識的那一塊（預覽圖），不再只列座標（合成資料）。"""
import io

import pytest
from PIL import Image, ImageDraw

from app import create_app
from app.extensions import db
from app.models import DocumentExtraction, SourceDocument, User

ISSUER_BOX = [100, 50, 300, 150]


@pytest.fixture()
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "UPLOAD_FOLDER": str(tmp_path)})
    image_path = tmp_path / "synthetic_certificate.png"
    image = Image.new("RGB", (400, 200), "white")
    ImageDraw.Draw(image).rectangle(ISSUER_BOX, fill="black")
    image.save(image_path)
    with app.app_context():
        db.create_all()
        users = []
        for username in ("student_syn", "other_syn"):
            user = User(username=username, display_name="合成學生", role="student")
            user.set_password("pw")
            db.session.add(user)
            users.append(user)
        db.session.flush()
        document = SourceDocument(owner_id=users[0].id, document_type="credential", display_name="合成證照.png",
                                  file_path=str(image_path), sha256="0" * 64, status="extracted")
        db.session.add(document)
        db.session.flush()
        db.session.add(DocumentExtraction(source_document_id=document.id, provider="rapidocr", status="extracted",
                                          result_json={
            "draft_revision": "r1", "credentials": [],
            "credential_analyses": [{
                "source_page": 1, "document_kind": "taiwan_technician_certificate",
                "document_label": "中華民國技術士證", "needs_review": False, "steps": [],
                "fields": {"issuer": {"value": "勞動部", "raw_text": "勞動部發", "page": 1,
                                      "bbox": ISSUER_BOX, "confidence": 0.92, "reason": None}},
            }],
        }))
        db.session.commit()
    return app


def login(app, username):
    client = app.test_client()
    client.post("/login", data={"username": username, "password": "pw"})
    return client


def test_review_page_shows_field_preview_image_instead_of_coordinates(app):
    html = login(app, "student_syn").get("/student/learning-profile/documents/1/review").get_data(as_text=True)

    assert 'src="/student/learning-profile/documents/1/credentials/0/fields/issuer/source?revision=r1"' in html
    assert "原圖位置 100" not in html


def test_field_preview_returns_cropped_region_of_original_image(app):
    response = login(app, "student_syn").get(
        "/student/learning-profile/documents/1/credentials/0/fields/issuer/source?revision=r1")

    assert response.status_code == 200
    assert response.mimetype == "image/png"
    crop = Image.open(io.BytesIO(response.data)).convert("RGB")
    assert 200 <= crop.width <= 230 and 100 <= crop.height <= 130   # 欄位範圍，四周留一點邊
    assert crop.getpixel((crop.width // 2, crop.height // 2)) == (0, 0, 0)


def test_other_students_cannot_see_field_preview(app):
    response = login(app, "other_syn").get(
        "/student/learning-profile/documents/1/credentials/0/fields/issuer/source?revision=r1")

    assert response.status_code in {403, 404}


def test_unknown_field_preview_is_not_found(app):
    client = login(app, "student_syn")

    assert client.get("/student/learning-profile/documents/1/credentials/0/fields/level/source").status_code == 404
    assert client.get("/student/learning-profile/documents/1/credentials/5/fields/issuer/source").status_code == 404
