"""自傳產生後自動放到學生自己的 Google 雲端硬碟（使用者 2026-11-13）。

Google 一律用假物件，不連線；帳號、校系皆僅為測試資料。
"""
from app.models import AutobiographyGoogleDoc
from app.services import google_docs_service as gdocs
from tests.autobio_helpers import FOCUS_ANSWERS
from tests.test_autobiography_google_docs import (ANSWERS, app, authorize, csrf, fake_google,  # noqa: F401
                                                  login_with_draft, program_id)


def _generate(app, client):
    with app.app_context():  # 共用的測試學生是專三；自傳要專五才能產生
        from datetime import date
        from app.extensions import db
        from app.models import StudentProfile
        from app.services.journey_service import academic_year_of
        StudentProfile.query.filter_by(student_no="111534100").one().admission_year = academic_year_of(date.today()) - 4
        db.session.commit()
    return client.post("/student/autobiography/generate",
                       data={"program_id": program_id(app), "csrf_token": csrf(client), **ANSWERS, **FOCUS_ANSWERS})


def _links(app):
    with app.app_context():
        return AutobiographyGoogleDoc.query.count()


def test_generation_creates_google_doc_when_student_already_connected(app, fake_google):
    client, _ = login_with_draft(app)
    authorize(client)

    response = _generate(app, client)

    assert response.status_code == 302 and "google=auto_created" in response.headers["Location"]
    assert len(fake_google.created) == 1 and _links(app) == 1
    assert "已自動放到你的 Google 雲端硬碟" in client.get(response.headers["Location"]).get_data(as_text=True)


def test_generation_without_google_connection_creates_nothing(app, fake_google):
    client, _ = login_with_draft(app)

    response = _generate(app, client)

    assert response.status_code == 302 and "google=" not in response.headers["Location"]
    assert fake_google.created == [] and _links(app) == 0


def test_existing_google_doc_is_not_replaced(app, fake_google):
    client, output_id = login_with_draft(app)
    authorize(client)
    client.post(f"/student/autobiography/{output_id}/google/open", data={"csrf_token": csrf(client)})
    assert len(fake_google.created) == 1

    response = _generate(app, client)

    assert response.status_code == 302
    assert len(fake_google.created) == 1  # 學生可能正在 Google 改，不自動換掉


def test_google_failure_does_not_block_generation(app, fake_google):
    client, _ = login_with_draft(app)
    authorize(client)
    fake_google.fail = gdocs.GoogleDocsError("假的 Google 失敗")

    response = _generate(app, client)

    assert response.status_code == 302 and "google=" not in response.headers["Location"]
    assert _links(app) == 0
