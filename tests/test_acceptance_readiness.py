import re
from tests.test_award_certificates import cert_app, client_for
from app.services.upload_quality import resolution_check
from PIL import Image
import io


def test_staff_instructions_name_the_actual_approver(tmp_path):
    app = cert_app(tmp_path)
    client = client_for(app, "assistant")
    for path in ("/staff/dashboard", "/staff/certificates"):
        response = client.get(path)
        assert response.status_code == 200
        instructions = re.findall(r"<p>(.*?)</p>", response.get_data(as_text=True), re.S)
        assert any(re.search(r"主任或副主任.*核准|核准.*由主任或副主任", message) for message in instructions)


def test_welcome_choices_have_explicit_accessible_names(tmp_path):
    app = cert_app(tmp_path)
    client = client_for(app, "stu")
    page = client.get("/student/welcome").get_data(as_text=True)
    choices = re.findall(r'<button[^>]*class="choice[^>]*>', page)
    assert len(choices) == 4
    assert all('aria-label="' in button for button in choices)


def test_readable_image_warning_explains_action_without_pixel_jargon():
    image = io.BytesIO()
    Image.new("RGB", (2400, 1800)).save(image, format="PNG")
    result = resolution_check("transcript", image.getvalue(), "test.png")
    assert result["level"] == "low" and result["long_side"] == 2400
    assert "像素" not in result["message"]
    assert "對照原圖" in result["message"]


def test_preflight_uses_the_mail_settings_read_by_the_app():
    from scripts.preflight_check import RECOMMENDED
    assert {"MAIL_SMTP_HOST", "MAIL_SMTP_PORT", "MAIL_SMTP_USER", "MAIL_SMTP_PASSWORD", "MAIL_SENDER"} <= set(RECOMMENDED)
