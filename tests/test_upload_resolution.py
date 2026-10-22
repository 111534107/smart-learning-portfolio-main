"""上傳成績單時先檢查解析度（合成空白圖片）。

實測（2026-10-20，同一份成績單縮成不同寬度）：原始 3507 像素 85 門有 84 門學分成績齊全；
2800 像素剩 60 門；2000 像素以下時好時壞；1024 像素完全抓不到表格、產生亂字。
"""
import io

import pytest
from PIL import Image

from app import create_app
from app.extensions import db
from app.models import DocumentExtraction, SourceDocument, User
from app.services.upload_quality import (
    TRANSCRIPT_MIN_LONG_SIDE, TRANSCRIPT_RECOMMENDED_LONG_SIDE, resolution_check,
)


def png(width, height):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture()
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "UPLOAD_FOLDER": str(tmp_path), "DOCUMENT_ANALYSIS_PROVIDER": "fake"})
    with app.app_context():
        db.create_all()
        student = User(username="student_syn", display_name="合成學生", role="student")
        student.set_password("pw")
        db.session.add(student)
        db.session.commit()
    return app


@pytest.fixture()
def client(app):
    client = app.test_client()
    client.post("/login", data={"username": "student_syn", "password": "pw"})
    return client


def post(client, document_type, data, name):
    return client.post("/student/learning-profile/documents", content_type="multipart/form-data",
                       data={"document_type": document_type, "file": (io.BytesIO(data), name)})


def test_thresholds_follow_the_measurement():
    assert TRANSCRIPT_MIN_LONG_SIDE == 1600
    assert TRANSCRIPT_RECOMMENDED_LONG_SIDE == 3000


def test_resolution_check_levels():
    assert resolution_check("transcript", png(1024, 703), "a.png")["level"] == "too_small"
    assert resolution_check("transcript", png(703, 1024), "a.png")["level"] == "too_small"  # 直式也看長邊
    assert resolution_check("transcript", png(2400, 1700), "a.png")["level"] == "low"
    assert resolution_check("transcript", png(3507, 2481), "a.png")["level"] == "ok"
    assert resolution_check("transcript", b"%PDF-1.4", "a.pdf") is None      # PDF 會以 300 DPI 轉圖，不檢查
    assert resolution_check("credential", png(1005, 646), "a.png") is None   # 1005 像素的技術士證實測全對


def test_too_small_transcript_image_is_not_stored_and_asks_for_pdf(client, app, tmp_path):
    response = post(client, "transcript", png(1024, 703), "small.png")

    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert "解析度太低" in html and "1024" in html and "PDF" in html
    assert '<input type="hidden" name="document_type" value="transcript">' in html  # 留在成績單上傳頁
    with app.app_context():
        assert SourceDocument.query.count() == 0
    assert not list((tmp_path / "learning-profile").rglob("*.png")) if (tmp_path / "learning-profile").exists() else True


def test_low_resolution_transcript_is_read_with_a_warning(client, app):
    response = post(client, "transcript", png(2400, 1700), "medium.png")

    assert response.status_code == 302
    with app.app_context():
        result = DocumentExtraction.query.one().result_json
    assert any("解析度偏低" in warning and "2400" in warning for warning in result["warnings"])
    assert {"step": "resolution_checked", "long_side": 2400, "level": "low"} in result["processing_steps"]
