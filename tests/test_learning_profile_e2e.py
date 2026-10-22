import io
import json

from app import create_app
from app.extensions import db
from app.models import LearningProfileOutput, SourceDocument, User


def p0_app(tmp_path):
    app = create_app({
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "TESTING": True,
        "UPLOAD_FOLDER": str(tmp_path),
        "DOCUMENT_ANALYSIS_PROVIDER": "fake",
    })
    with app.app_context():
        db.create_all()
        for username, role in (("student_demo", "student"), ("admin_demo", "admin")):
            user = User(username=username, display_name="測試學生甲" if role == "student" else "測試管理員", role=role)
            user.set_password("pw")
            db.session.add(user)
        db.session.commit()
    return app


def login(client, username):
    client.post("/login", data={"username": username, "password": "pw"})


def test_anonymous_p0_demo_flow_from_upload_to_word_download(tmp_path):
    app = p0_app(tmp_path)
    client = app.test_client()
    login(client, "student_demo")
    for document_type, filename in (("transcript", "demo-transcript.pdf"), ("credential", "demo-credential.pdf")):
        response = client.post("/student/learning-profile/documents", data={
            "document_type": document_type,
            "file": (io.BytesIO(b"anonymous demo"), filename),
        }, content_type="multipart/form-data")
        assert response.status_code == 302
    with app.app_context():
        transcript_id = SourceDocument.query.filter_by(document_type="transcript").one().id
        credential_id = SourceDocument.query.filter_by(document_type="credential").one().id
        transcript_revision = db.session.get(SourceDocument, transcript_id).extraction.result_json["draft_revision"]
        credential_revision = db.session.get(SourceDocument, credential_id).extraction.result_json["draft_revision"]
    assert client.post(f"/student/learning-profile/documents/{transcript_id}/review/confirm", data={
        "draft_revision": transcript_revision,
        "scores_unlocked": "1",
        "courses_json": json.dumps([{"course_name": "程式設計", "credits": 3, "score": 92}]),
        "credentials_json": "[]",
    }).status_code == 302
    assert client.post(f"/student/learning-profile/documents/{credential_id}/review/confirm", data={
        "draft_revision": credential_revision,
        "courses_json": "[]",
        "credentials_json": json.dumps([{"credential_name": "資訊技術類測試證照", "level": "丙級"}]),
    }).status_code == 302

    client.post("/logout")
    login(client, "admin_demo")
    assert client.post("/admin/course-rules", data={
        "school_year": "115", "course_name": "程式設計", "category": "專業課程",
        "requirement_type": "required", "credits": "3", "ability_domain": "程式智能開發",
    }).status_code == 302

    client.post("/logout")
    login(client, "student_demo")
    assert client.post("/student/learning-profile/generate", data={"school_year": "115"}).status_code == 302
    with app.app_context():
        output_id = LearningProfileOutput.query.filter_by(output_type="profile_summary").one().id
    response = client.get(f"/student/learning-profile/outputs/{output_id}/docx")
    assert response.status_code == 200
    assert response.data.startswith(b"PK")
