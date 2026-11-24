"""證照、成績單照片模糊與歪斜提醒（11-05 評審意見 3，2026-11-10）。只提醒，不擋上傳。合成圖片。"""
import io

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.models import SourceDocument
from app.services import photo_quality
from tests.test_learning_profile_upload import learning_profile_app, login


def _document():
    image = Image.new("RGB", (1600, 1100), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 34)
    except OSError:
        font = ImageFont.load_default(size=34)
    for index in range(18):
        draw.text((120, 90 + index * 52), f"Certificate line {index} Software Application Level C No.{index * 137}",
                  fill="black", font=font)
    return image


def _jpeg(image):
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=90)
    return buffer.getvalue()


def test_sharp_level_photo_has_no_warning():
    result = photo_quality.check(_jpeg(_document()), "cert.jpg")
    assert result["blurry"] is False and result["message"] == ""


def test_blurry_photo_is_flagged():
    result = photo_quality.check(_jpeg(_document().filter(ImageFilter.GaussianBlur(4))), "cert.jpg")
    assert result["blurry"] is True and "模糊" in result["message"] and "建議重拍" in result["message"]


def test_skewed_photo_is_flagged_but_small_tilt_is_not():
    tilted = photo_quality.check(_jpeg(_document().rotate(7, fillcolor="white", expand=True)), "cert.jpg")
    assert abs(abs(tilted["skew"]) - 7) <= 1 and "歪了" in tilted["message"]
    slight = photo_quality.check(_jpeg(_document().rotate(1.5, fillcolor="white", expand=True)), "cert.jpg")
    assert slight["message"] == ""


def test_pdf_and_unreadable_files_are_skipped():
    assert photo_quality.check(b"%PDF-1.4", "cert.pdf") is None
    assert photo_quality.check(b"not an image", "cert.jpg") is None


def test_review_page_shows_warning_but_upload_is_not_blocked(tmp_path):
    app = learning_profile_app(tmp_path)
    client = app.test_client()
    login(client)
    blurry = _jpeg(_document().filter(ImageFilter.GaussianBlur(4)))
    response = client.post("/student/learning-profile/documents",
                           data={"document_type": "credential", "file": (io.BytesIO(blurry), "cert.jpg")},
                           content_type="multipart/form-data")
    assert response.status_code == 302  # 不擋上傳
    with app.app_context():
        document_id = SourceDocument.query.one().id
    page = client.get(f"/student/learning-profile/documents/{document_id}/review").get_data(as_text=True)
    assert "data-photo-check" in page and "建議重拍" in page


def test_review_page_without_problem_has_no_warning(tmp_path):
    app = learning_profile_app(tmp_path)
    client = app.test_client()
    login(client)
    client.post("/student/learning-profile/documents",
                data={"document_type": "credential", "file": (io.BytesIO(_jpeg(_document())), "cert.jpg")},
                content_type="multipart/form-data")
    with app.app_context():
        document_id = SourceDocument.query.one().id
    page = client.get(f"/student/learning-profile/documents/{document_id}/review").get_data(as_text=True)
    assert "data-photo-check" not in page
