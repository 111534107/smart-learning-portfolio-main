import pytest

from app.security import validate_upload_filename


def test_upload_validation_rejects_unsafe_or_unapproved_files():
    with pytest.raises(ValueError):
        validate_upload_filename("../../secret.exe", {"pdf", "png"})
    with pytest.raises(ValueError):
        validate_upload_filename("notes.exe", {"pdf", "png"})


def test_upload_validation_returns_safe_name():
    assert validate_upload_filename("作品 1.PDF", {"pdf", "png"}) == "作品_1.PDF"
