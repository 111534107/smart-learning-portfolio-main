"""學校 Google 登入：無法登入時，錯誤訊息要說出剛剛登入的是哪個信箱（2026-11-04 實測：看不出要綁哪個）。
另外展示站 run_demo.py 的示範學生改用假學號，不佔用真實學生的學號與學校信箱。"""
import importlib.util
from pathlib import Path

from app.extensions import db
from app.models import SystemSetting
from tests.test_school_google_login import FakeGoogleLogin, school_app, start


def test_unbound_school_account_message_shows_which_email():
    google = FakeGoogleLogin({"sub": "new-sub", "email": "111534199@stu.ukn.edu.tw", "email_verified": True,
                              "hd": "stu.ukn.edu.tw"})
    app, _ = school_app(google)
    with app.app_context():  # 關掉自動建帳號，才會走到「尚未綁定」
        db.session.add(SystemSetting(key="google_login.auto_create_students", value="0"))
        db.session.commit()
    client = app.test_client()

    response = client.get(f"/auth/google/callback?state={start(client)}&code=c")

    assert response.status_code == 403
    assert "111534199@stu.ukn.edu.tw" in response.get_data(as_text=True)
    assert "帳號管理" in response.get_data(as_text=True)


def test_demo_site_students_use_fake_numbers_without_school_email(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "run_demo_for_test", Path(__file__).resolve().parents[1] / "scripts" / "run_demo.py")
    run_demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run_demo)
    from app import create_app
    from app.models import User

    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        run_demo.seed()
        students = User.query.filter_by(role="student").all()
        assert {s.username for s in students} == {"113534901", "113534902", "113534903"}
        assert all(s.email is None for s in students)  # 真的學生用 Google 登入會建自己的帳號
        assert {a["username"] for a in run_demo.DEMO_ACCOUNTS if a["role"] == "student"} == {"113534901", "113534902", "113534903"}
