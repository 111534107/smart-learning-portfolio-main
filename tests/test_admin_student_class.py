"""管理員幫學生填班級（2026-11-18 四角色實測：Google 登入自動建立的學生班級是空的，導師看不到）。合成假資料。"""
from datetime import date

from app import create_app
from app.extensions import db
from app.models import AuditLog, ClassAdvisor, StudentProfile, User
from app.services import teacher_scope
from app.services.journey_service import academic_year_of


def make_app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "WTF_CSRF_ENABLED": False, "TWO_FACTOR_REQUIRED": False})
    with app.app_context():
        db.create_all()
        for username, role in (("adm", "admin"), ("tea", "teacher"), ("stu", "student")):
            user = User(username=username, display_name=f"合成{username}", role=role)
            user.set_password("pw")
            db.session.add(user)
        db.session.flush()
        stu = User.query.filter_by(username="stu").one()
        db.session.add(StudentProfile(user_id=stu.id, student_no="S0001", class_name=None))  # 班級是空的
        tea = User.query.filter_by(username="tea").one()
        db.session.add(ClassAdvisor(teacher_id=tea.id, class_name="資管科三甲",
                                    school_year=academic_year_of(date.today())))
        db.session.commit()
    return app


def client_for(app, username):
    client = app.test_client()
    client.post("/login", data={"username": username, "password": "pw"})
    return client


def _stu_id(app):
    with app.app_context():
        return User.query.filter_by(username="stu").one().id


def test_admin_sets_student_class_and_teacher_sees_student():
    app = make_app()
    with app.app_context():
        assert teacher_scope.students_for_teacher(User.query.filter_by(username="tea").one()) == []
    response = client_for(app, "adm").post(f"/admin/accounts/{_stu_id(app)}/class-name", data={"class_name": "資管科三甲"})
    assert response.status_code == 302
    with app.app_context():
        teacher = User.query.filter_by(username="tea").one()
        assert [s.username for s in teacher_scope.students_for_teacher(teacher)] == ["stu"]
        log = AuditLog.query.filter_by(action="student.class_name.update").one()
        assert log.target_id == _stu_id(app)


def test_non_admin_cannot_set_class():
    app = make_app()
    for username in ("tea", "stu"):
        response = client_for(app, username).post(f"/admin/accounts/{_stu_id(app)}/class-name", data={"class_name": "資管科三甲"})
        assert response.status_code in (302, 403), username
        with app.app_context():
            assert User.query.filter_by(username="stu").one().student_profile.class_name is None


def test_class_name_rejects_blank_and_overlong():
    app = make_app()
    client = client_for(app, "adm")
    for bad in ("", "   ", "甲" * 51):
        response = client.post(f"/admin/accounts/{_stu_id(app)}/class-name", data={"class_name": bad})
        assert response.status_code == 400, repr(bad)
        assert "班級" in response.get_data(as_text=True)
    with app.app_context():
        assert User.query.filter_by(username="stu").one().student_profile.class_name is None


def test_accounts_page_shows_class_form_and_warns_when_missing():
    app = make_app()
    page = client_for(app, "adm").get("/admin/accounts").get_data(as_text=True)
    assert "data-student-class" in page
    assert "未填班級" in page


def test_project_rules_page_says_it_is_not_connected_yet():
    """2026-11-18：專題規則頁目前沒有接到學生端的專題作品，頁首要照實說。"""
    app = make_app()
    page = client_for(app, "adm").get("/admin/project-types").get_data(as_text=True)
    assert "data-planned-notice" in page
    assert "規劃中" in page


def test_accounts_page_has_specific_tour_for_main_operations():
    page = client_for(make_app(), "adm").get("/admin/accounts").get_data(as_text=True)
    for sentence in ("學生缺少入學學年度時，貼上清單匯入。", "新增教職員時，填資料並建立帳號。", "在帳號清單修改班級、信箱或登入狀態。"):
        assert f'data-tour="{sentence}"' in page
