"""OCR 實測結果頁：把驗收紀錄放進系統，老師、科辦、管理員、學生登入後都看得到（合成帳號）。"""
from pathlib import Path

import pytest

from app import create_app
from app.extensions import db
from app.models import User


@pytest.fixture()
def app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        for role in ("student", "teacher", "staff", "admin"):
            user = User(username=f"{role}_syn", display_name=f"合成{role}", role=role)
            user.set_password("pw")
            db.session.add(user)
        db.session.commit()
    return app


def login(app, role):
    client = app.test_client()
    client.post("/login", data={"username": f"{role}_syn", "password": "pw"})
    return client


@pytest.mark.parametrize("role", ["student", "teacher", "staff", "admin"])
def test_every_role_can_read_the_acceptance_results(app, role):
    response = login(app, role).get("/ocr/acceptance")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "OCR 實測結果" in html
    assert "24／24" in html            # 證照修正後全部欄位
    assert "74／85" in html            # 成績單課程名稱校正前完全正確
    assert "課程名稱（清單校正後）" in html  # 校正後的結果要和校正前分開寫
    assert "同一份成績單" in html      # 清單來源與限制要寫清楚
    assert "不是正確率" in html
    assert "合計概論" in html          # 錯在哪裡要寫出來，不只寫總數


def test_acceptance_page_requires_login(app):
    assert app.test_client().get("/ocr/acceptance").status_code in {302, 401, 403}


def test_acceptance_content_has_no_personal_data():
    from app.content.ocr_acceptance import ACCEPTANCE
    text = repr(ACCEPTANCE)
    for forbidden in ("A123456789", "111534", "王大名", "劉小美", "118-0186204", "149-0685006"):
        assert forbidden not in text


def test_admin_ocr_page_and_credential_review_link_to_the_results(app):
    html = login(app, "admin").get("/admin/ocr").get_data(as_text=True)
    assert 'href="/ocr/acceptance"' in html
    review = (Path(__file__).resolve().parents[1] / "app" / "templates" / "learning_profile_review.html").read_text(encoding="utf-8")
    assert "url_for('main.ocr_acceptance')" in review


def test_acceptance_page_explains_image_processing_and_resolution(app):
    html = login(app, "teacher").get("/ocr/acceptance").get_data(as_text=True)

    assert "圖片怎麼處理" in html
    assert "300 DPI" in html and "框線" in html and "標籤" in html
    assert "解析度實測" in html and "3507" in html and "1024" in html
    assert "1600" in html and "3000" in html  # 上傳時的兩個門檻
