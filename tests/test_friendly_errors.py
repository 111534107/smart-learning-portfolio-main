"""10-27 照手冊實測發現的錯誤畫面：上傳錯檔、未登入、帳號停用都要用中文說明。"""
import io

from app.extensions import db
from app.models import AuditLog, User
from tests.test_student_records import login, records_app


def test_wrong_file_type_stays_on_upload_page_with_chinese_message(tmp_path):
    client = records_app(tmp_path).test_client()
    login(client)

    response = client.post("/student/learning-profile/documents", data={
        "document_type": "transcript", "file": (io.BytesIO(b"hello"), "test.txt"),
    }, content_type="multipart/form-data")

    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert "只接受 PNG、JPG 圖片或 PDF 檔" in html and "上傳成績單" in html
    assert "file type is not allowed" not in html


def test_logged_out_page_explains_in_chinese_and_links_back_after_login(tmp_path):
    app = records_app(tmp_path)
    with app.app_context():  # 已經看過歡迎頁的學生；第一次登入仍會先去歡迎頁
        db.session.add(AuditLog(user_id=User.query.filter_by(username="stu").one().id, action="student.welcome_done"))
        db.session.commit()
    client = app.test_client()

    response = client.get("/student/portfolio")

    html = response.get_data(as_text=True)
    assert response.status_code == 401
    assert "請先登入" in html and "Unauthorized" not in html
    assert "/login?next=/student/portfolio" in html
    after = client.post("/login", data={"username": "stu", "password": "pw", "next": "/student/portfolio"})
    assert after.headers["Location"].endswith("/student/portfolio")


def test_login_next_only_accepts_paths_inside_the_site(tmp_path):
    client = records_app(tmp_path).test_client()

    after = client.post("/login", data={"username": "stu", "password": "pw", "next": "https://evil.example/"})

    assert "evil.example" not in after.headers["Location"]


def test_forbidden_and_missing_pages_are_chinese(tmp_path):
    client = records_app(tmp_path).test_client()
    login(client)

    assert "沒有權限" in client.get("/admin/dashboard").get_data(as_text=True)
    assert "找不到這一頁" in client.get("/student/agent/runs/999").get_data(as_text=True)


def test_disabled_account_is_told_only_after_the_right_password(tmp_path):
    app = records_app(tmp_path)
    with app.app_context():
        User.query.filter_by(username="stu").one().is_active = False
        db.session.commit()
    client = app.test_client()

    wrong = client.post("/login", data={"username": "stu", "password": "nope"}).get_data(as_text=True)
    right = client.post("/login", data={"username": "stu", "password": "pw"})

    assert "帳號或密碼錯誤" in wrong and "停用" not in wrong
    assert right.status_code == 403 and "這個帳號已停用" in right.get_data(as_text=True)
