"""學期照片：學生上傳這學期最快樂的照片，當成首頁拼圖的圖。只有本人看得到。"""
import io
import struct
import zlib
from datetime import date
from pathlib import Path

import pytest
from PIL import Image

from app import create_app
from app.extensions import db
from app.models import AuditLog, StudentProfile, User
from app.services.journey_service import academic_year_of
from app.services.photo_service import current_semester


@pytest.fixture()
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        for name in ("stu", "other"):
            user = User(username=name, display_name=name, role="student")
            user.set_password("pw")
            db.session.add(user)
            db.session.flush()
            db.session.add(StudentProfile(user_id=user.id, student_no=name, admission_year=academic_year_of(date.today()) - 2))
            db.session.add(AuditLog(user_id=user.id, action="student.welcome_done"))
        teacher = User(username="tch", display_name="tch", role="teacher")
        teacher.set_password("pw")
        db.session.add(teacher)
        db.session.commit()
    app.tmp = tmp_path
    return app


def login(app, name="stu"):
    client = app.test_client()
    client.post("/login", data={"username": name, "password": "pw"})
    return client


def jpeg_with_gps(size=(1200, 600)):
    image = Image.new("RGB", size, (200, 120, 40))
    exif = Image.Exif()
    exif[0x8825] = {2: (25.0, 2.0, 0.0)}  # GPS 資訊
    out = io.BytesIO()
    image.save(out, "JPEG", exif=exif)
    out.seek(0)
    return out


def png_declaring_size(width, height):
    """只改 1×1 PNG 的 IHDR，讓檔案很小但宣告尺寸很大。"""
    source = io.BytesIO()
    Image.new("RGB", (1, 1), (1, 2, 3)).save(source, "PNG")
    data = source.getvalue()
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    crc = zlib.crc32(b"IHDR" + ihdr) & 0xFFFFFFFF
    return io.BytesIO(data[:8] + struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr + struct.pack(">I", crc) + data[33:])


def test_current_semester():
    assert current_semester(date(2026, 10, 10)) == 1
    assert current_semester(date(2027, 1, 15)) == 1
    assert current_semester(date(2027, 3, 1)) == 2
    assert current_semester(date(2027, 7, 31)) == 2


def test_upload_replaces_puzzle_picture_and_strips_metadata(app):
    client = login(app)
    response = client.post("/student/photo", data={"photo": (jpeg_with_gps(), "happy.jpg")},
                           content_type="multipart/form-data")
    assert response.status_code == 302

    saved = list(app.tmp.rglob("*.jpg"))
    assert len(saved) == 1
    with Image.open(saved[0]) as image:
        assert image.format == "JPEG"
        assert abs(image.width / image.height - 1.5) < 0.01  # 裁成拼圖的 3:2
        assert 0x8825 not in image.getexif()  # 定位資訊已移除

    page = client.get("/student/dashboard").get_data(as_text=True)
    assert "/student/photo/3/" in page  # 拼圖改用照片
    photo_url = page.split('href="/student/photo/3/', 1)[1].split('"', 1)[0]
    assert client.get(f"/student/photo/3/{photo_url}").status_code == 200


def test_only_owner_can_see_photo(app):
    client = login(app)
    client.post("/student/photo", data={"photo": (jpeg_with_gps(), "happy.jpg")}, content_type="multipart/form-data")
    semester = current_semester(date.today())
    with app.app_context():
        owner_id = User.query.filter_by(username="stu").one().id

    assert client.get(f"/student/photo/3/{semester}").status_code == 200
    assert login(app, "other").get(f"/student/photo/3/{semester}").status_code == 404
    assert login(app, "tch").get(f"/student/photo/3/{semester}").status_code == 403
    assert app.test_client().get(f"/student/photo/3/{semester}").status_code == 401
    assert owner_id  # 檔案用學生編號分資料夾


def test_rejects_non_image(app):
    client = login(app)
    response = client.post("/student/photo", data={"photo": (io.BytesIO(b"not an image"), "x.jpg")},
                           content_type="multipart/form-data")
    assert response.status_code == 400
    assert not list(app.tmp.rglob("*.jpg"))


def test_rejects_oversized_png_and_keeps_existing_photo(app):
    client = login(app)
    client.post("/student/photo", data={"photo": (jpeg_with_gps(), "old.jpg")},
                content_type="multipart/form-data")
    semester = current_semester(date.today())
    old_photo = client.get(f"/student/photo/3/{semester}").data

    app.config["PROPAGATE_EXCEPTIONS"] = False
    response = client.post(
        "/student/photo",
        data={"photo": (png_declaring_size(10_000, 4_001), "huge.png")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert "照片太大了，請換一張或先縮小再上傳。" in response.get_data(as_text=True)
    assert client.get(f"/student/photo/3/{semester}").data == old_photo
    assert not list(app.tmp.rglob("*.tmp"))


def test_failed_atomic_replace_keeps_existing_photo_and_removes_temporary_file(app, monkeypatch):
    client = login(app)
    client.post("/student/photo", data={"photo": (jpeg_with_gps(), "old.jpg")},
                content_type="multipart/form-data")
    semester = current_semester(date.today())
    old_photo = client.get(f"/student/photo/3/{semester}").data

    def fail_replace(self, target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        client.post("/student/photo", data={"photo": (jpeg_with_gps((600, 400)), "new.jpg")},
                    content_type="multipart/form-data")

    assert client.get(f"/student/photo/3/{semester}").data == old_photo
    assert not list(app.tmp.rglob("*.tmp"))


def test_failed_temporary_save_keeps_existing_photo_and_removes_partial_file(app, monkeypatch):
    client = login(app)
    client.post("/student/photo", data={"photo": (jpeg_with_gps(), "old.jpg")},
                content_type="multipart/form-data")
    semester = current_semester(date.today())
    old_photo = client.get(f"/student/photo/3/{semester}").data
    new_photo = jpeg_with_gps((600, 400))

    def fail_after_partial_write(self, target, *args, **kwargs):
        Path(target).write_bytes(b"partial jpeg")
        raise OSError("simulated save failure")

    monkeypatch.setattr(Image.Image, "save", fail_after_partial_write)
    with pytest.raises(OSError, match="simulated save failure"):
        client.post("/student/photo", data={"photo": (new_photo, "new.jpg")},
                    content_type="multipart/form-data")

    assert client.get(f"/student/photo/3/{semester}").data == old_photo
    assert not list(app.tmp.rglob("*.tmp"))


def test_valid_upload_atomically_replaces_existing_photo(app):
    client = login(app)
    client.post("/student/photo", data={"photo": (jpeg_with_gps(), "old.jpg")},
                content_type="multipart/form-data")
    semester = current_semester(date.today())
    old_photo = client.get(f"/student/photo/3/{semester}").data

    response = client.post("/student/photo", data={"photo": (jpeg_with_gps((600, 400)), "new.jpg")},
                           content_type="multipart/form-data")
    new_photo = client.get(f"/student/photo/3/{semester}").data

    assert response.status_code == 302
    assert new_photo != old_photo
    with Image.open(io.BytesIO(new_photo)) as image:
        assert image.format == "JPEG"
    assert not list(app.tmp.rglob("*.tmp"))


def test_without_photo_shows_illustration_and_upload_prompt(app):
    page = login(app).get("/student/dashboard").get_data(as_text=True)
    assert 'id="year-scene"' in page
    assert "最快樂的照片" in page
    assert "/student/photo/3/" not in page


def test_photo_is_not_cached(app):
    client = login(app)
    client.post("/student/photo", data={"photo": (jpeg_with_gps(), "happy.jpg")}, content_type="multipart/form-data")
    response = client.get(f"/student/photo/3/{current_semester(date.today())}")
    assert response.headers["Cache-Control"] == "no-store"
