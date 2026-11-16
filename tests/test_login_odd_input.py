"""登入時輸入中文、亂碼、SQL 字元、超長字串都不能登入，也不會讓伺服器出錯（2026-11-12）。"""
import pytest

from tests.test_login_portals import logged_in_role, make_app, post_login

pytestmark = pytest.mark.real_login_routes

ODD = [
    ("學生", "pw"), ("stu", "密碼"), ("ｓｔｕ", "pw"), ("stu", "ｐｗ"), ("STU", "pw"), (" stu", "pw "),
    ("stu\x00", "pw"), ("stu", "pw\x00"), ("' OR '1'='1", "' OR '1'='1"), ("stu'--", "x"),
    ("stu", ""), ("", "pw"), ("stu", "p" * 100000), ("s" * 5000, "pw"), ("stu", "pw\u200b"),
    ("😀", "😀"), ("stu", "pw\x00zzz"), ("stu", "pw\n"), ("stu", "pw\t"),
]


@pytest.mark.parametrize("path", ["/login", "/staff/login", "/admin/login"])
@pytest.mark.parametrize("username,password", ODD, ids=[str(i) for i in range(len(ODD))])
def test_odd_input_never_logs_in(path, username, password):
    app = make_app()
    client = app.test_client()
    response = post_login(client, path, username, password)
    assert response.status_code in (400, 401, 403, 429)
    with app.app_context():
        assert logged_in_role(client) is None


def test_null_byte_password_cannot_be_set():
    from app.models import User
    with pytest.raises(ValueError):
        User(username="x", display_name="x", role="student").set_password("pw\x00")


def test_chinese_password_still_works_when_it_is_the_real_password():
    from app.extensions import db
    from app.models import User
    app = make_app()
    with app.app_context():
        user = User.query.filter_by(username="stu").one()
        user.set_password("我的密碼123")
        db.session.commit()
    client = app.test_client()
    post_login(client, "/login", "stu", "我的密碼123")
    with app.app_context():
        assert logged_in_role(client) == "student"


@pytest.mark.parametrize("path", ["/login", "/staff/login", "/admin/login"])
def test_every_login_page_has_password_eye(path):
    html = make_app().test_client().get(path).get_data(as_text=True)
    assert "data-password-toggle" in html and 'aria-label="顯示密碼"' in html
