"""2026-11-18 四角色實走（管理員、導師、科辦、學生）發現的小問題，修正後的回歸測試。

帳號、學號都是假資料（僅為測試資料）。
"""
from pathlib import Path

from app import create_app
from app.extensions import db
from app.models import AdmissionProgram, AuditLog, ClassAdvisor, User

ROOT = Path(__file__).resolve().parents[1]


def walk_app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "WTF_CSRF_ENABLED": False})
    with app.app_context():
        db.create_all()
        admin = User(username="walk-admin", display_name="測試管理員", role="admin")
        staff = User(username="walk-staff", display_name="測試科助", role="staff", job_title="科助")
        teacher = User(username="walk-teacher", display_name="測試導師", role="teacher")
        for user in (admin, staff, teacher):
            user.set_password("test-password")
            db.session.add(user)
        db.session.add(AdmissionProgram(program_code="999001", admission_year=115, school_name="測試科技大學",
                                        department_name="資訊管理系", admission_category="管理類四"))
        db.session.commit()
    return app


def admin_client(app):
    client = app.test_client()
    client.post("/login", data={"username": "walk-admin", "password": "test-password"})
    return client


def user_id(app, username):
    with app.app_context():
        return User.query.filter_by(username=username).one().id


def actions(app):
    with app.app_context():
        return [log.action for log in AuditLog.query.order_by(AuditLog.id)]


def test_form_mistake_shows_chinese_page_with_reason_and_back_link_instead_of_bad_request():
    app = walk_app()
    client = admin_client(app)
    staff_id = user_id(app, "walk-staff")

    response = client.post(f"/admin/accounts/{staff_id}/school-email", data={"school_email": "someone@gmail.com"},
                           headers={"Referer": "http://localhost/admin/accounts"})

    body = response.get_data(as_text=True)
    assert response.status_code == 400
    assert "Bad Request" not in body
    assert "資料沒有存" in body
    assert "教職員信箱須為 @" in body
    assert 'href="http://localhost/admin/accounts"' in body and "回上一頁" in body


def test_english_or_default_400_reason_falls_back_to_chinese_message():
    app = walk_app()
    client = admin_client(app)
    admin_id = user_id(app, "walk-admin")

    own = client.post(f"/admin/accounts/{admin_id}/toggle-active").get_data(as_text=True)
    assert "不能停用自己正在使用的管理員帳號" in own and "Administrators cannot" not in own

    # 外部網址當上一頁時不放連結，避免被帶到別的網站
    bad = client.post("/admin/course-rules", data={"school_year": "abc"}, headers={"Referer": "https://evil.example/"})
    text = bad.get_data(as_text=True)
    assert bad.status_code == 400
    assert "evil.example" not in text and "回上一頁" not in text


def test_admin_route_400_reasons_are_all_written_in_chinese():
    source = (ROOT / "app/routes/admin.py").read_text(encoding="utf-8")
    import re
    english = re.findall(r'abort\(400, description="([A-Za-z][^"]*)"', source)
    assert english == []


def test_key_admin_actions_leave_operation_logs():
    app = walk_app()
    client = admin_client(app)
    staff_id, teacher_id = user_id(app, "walk-staff"), user_id(app, "walk-teacher")
    with app.app_context():
        program_id = AdmissionProgram.query.one().id

    client.post(f"/admin/accounts/{staff_id}/toggle-active")
    client.post(f"/admin/accounts/{staff_id}/toggle-active")
    client.post(f"/admin/programs/{program_id}/toggle-status")
    client.post("/admin/classes", data={"teacher_id": teacher_id, "class_name": "資管科三甲", "school_year": "115"})
    with app.app_context():
        advisor_id = ClassAdvisor.query.one().id
    client.post(f"/admin/classes/{advisor_id}/delete")

    assert actions(app)[-5:] == ["account.deactivate", "account.activate", "program.publish",
                                 "class_advisor.add", "class_advisor.remove"]
    logs_page = client.get("/admin/audit-logs").get_data(as_text=True)
    for label in ("停用帳號", "重新啟用帳號", "校系核准為正式", "指派導師班級", "移除導師班級"):
        assert label in logs_page


def test_admin_pages_do_not_show_a_real_student_number_as_example():
    app = walk_app()
    client = admin_client(app)
    for path in ("/admin/accounts", "/admin/google-workspace"):
        assert "111534105" not in client.get(path).get_data(as_text=True)
    from app.services.certificate_batch_service import SAMPLE
    assert "111534105" not in SAMPLE


def test_program_list_has_search_box_and_cards_carry_search_text():
    app = walk_app()
    body = admin_client(app).get("/admin/programs").get_data(as_text=True)
    assert "data-program-query" in body and "data-program-todo" in body
    assert 'data-program-text="測試科技大學 資訊管理系 999001 管理類四 115"' in body


def test_staff_certificate_pages_say_assistant_can_return_but_only_chief_approves():
    for name in ("staff_certificates.html", "dashboard.html"):
        text = (ROOT / "app/templates" / name).read_text(encoding="utf-8")
        assert "核准或退回由主任或副主任按" not in text
        assert "修改內文或退回；核准要由主任或副主任按" in text


def test_student_review_timeline_uses_taipei_date():
    text = (ROOT / "app/templates/student_gap.html").read_text(encoding="utf-8")
    assert "requested_at.strftime" not in text
    assert "item.requested_at|taipei_time('%Y-%m-%d')" in text


def test_assistant_launcher_is_placed_again_after_mobile_tab_bar_exists():
    script = (ROOT / "app/static/js/assistant-window.js").read_text(encoding="utf-8")
    assert "document.addEventListener('DOMContentLoaded', viewport)" in script
    assert "addEventListener('load', viewport)" in script
