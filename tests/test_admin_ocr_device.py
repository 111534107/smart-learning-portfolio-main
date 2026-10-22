"""系統管理員可切換 OCR 用 CPU 或顯示卡（DirectML）辨識；設定存進資料庫（合成帳號）。"""
import pytest

from app import create_app
from app.extensions import db
from app.models import AuditLog, SystemSetting, User
from app.services import ocr_settings


@pytest.fixture()
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        for username, role in (("admin_syn", "admin"), ("student_syn", "student")):
            user = User(username=username, display_name=f"合成{role}", role=role)
            user.set_password("pw")
            db.session.add(user)
        db.session.commit()
    return app


def login(app, username):
    client = app.test_client()
    client.post("/login", data={"username": username, "password": "pw"})
    return client


def test_admin_page_shows_current_device_and_gpu_availability(app, monkeypatch):
    monkeypatch.setattr(ocr_settings, "directml_available", lambda: True)

    html = login(app, "admin_syn").get("/admin/ocr").get_data(as_text=True)

    assert "OCR 辨識設定" in html
    assert "目前使用：CPU" in html
    assert "可以使用顯示卡加速" in html


def test_admin_switches_to_gpu_and_ocr_reads_it(app, monkeypatch):
    from app.services.ocr_engines import configured_rapidocr_settings

    monkeypatch.setattr(ocr_settings, "directml_available", lambda: True)
    response = login(app, "admin_syn").post("/admin/ocr", data={"device": "dml", "dml_device_id": "1"})

    assert response.status_code == 302
    with app.app_context():
        assert configured_rapidocr_settings() == ("server", "dml", 1)
        assert SystemSetting.query.filter_by(key="ocr_device").one().value == "dml"
        assert AuditLog.query.filter_by(action="system.ocr_device_changed").count() == 1


def test_admin_can_switch_back_to_cpu(app, monkeypatch):
    from app.services.ocr_engines import configured_rapidocr_settings

    monkeypatch.setattr(ocr_settings, "directml_available", lambda: True)
    client = login(app, "admin_syn")
    client.post("/admin/ocr", data={"device": "dml", "dml_device_id": "1"})
    client.post("/admin/ocr", data={"device": "cpu", "dml_device_id": "1"})

    with app.app_context():
        assert configured_rapidocr_settings()[1] == "cpu"


def test_gpu_cannot_be_selected_when_directml_is_not_installed(app, monkeypatch):
    monkeypatch.setattr(ocr_settings, "directml_available", lambda: False)

    response = login(app, "admin_syn").post("/admin/ocr", data={"device": "dml", "dml_device_id": "1"})

    assert response.status_code == 400
    assert "沒有可用的顯示卡加速" in response.get_data(as_text=True)
    with app.app_context():
        assert SystemSetting.query.count() == 0


def test_unknown_device_is_rejected(app):
    response = login(app, "admin_syn").post("/admin/ocr", data={"device": "cuda", "dml_device_id": "0"})

    assert response.status_code == 400


def test_students_cannot_change_ocr_device(app):
    client = login(app, "student_syn")

    assert client.get("/admin/ocr").status_code == 403
    assert client.post("/admin/ocr", data={"device": "dml", "dml_device_id": "1"}).status_code == 403


def test_admin_navigation_links_to_ocr_settings(app):
    html = login(app, "admin_syn").get("/admin/accounts").get_data(as_text=True)

    assert 'href="/admin/ocr"' in html


def test_ocr_settings_fall_back_to_config_when_table_is_missing(tmp_path):
    # 沒有建立資料表（例如離線腳本）時，不可讓 OCR 失敗，改用設定檔的值
    from app.services.ocr_engines import configured_rapidocr_settings

    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "UPLOAD_FOLDER": str(tmp_path), "OCR_DEVICE": "dml", "OCR_DML_DEVICE_ID": 1})
    with app.app_context():
        assert configured_rapidocr_settings() == ("server", "dml", 1)
