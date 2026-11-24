"""畢業缺口展示資料。（僅為測試資料）"""
from datetime import date

from app import create_app
from app.demo_graduation import seed_graduation_demo
from app.extensions import db
from app.models import GraduationCase, Notification, User
from app.services import graduation_case_service as svc

TODAY = date(2026, 10, 15)


def _app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite://", "TESTING": True, "SECRET_KEY": "t"})
    with app.app_context():
        db.create_all()
        for role in ("student", "teacher", "staff"):
            user = User(username=f"{role}_demo", display_name=f"合成{role}帳號", role=role)
            user.set_password("demo2026")
            db.session.add(user)
        db.session.commit()
    return app


def _open(username_prefix=None):
    return {(c.student.username, c.case_type, c.item)
            for c in GraduationCase.query.filter(GraduationCase.status != "closed").all()}


def test_seed_produces_expected_overview_and_cases():
    app = _app()
    with app.app_context():
        result = seed_graduation_demo(TODAY)
        teacher = User.query.filter_by(username="teacher_demo").one()
        from app.models import ClassAdvisor, StudentProfile
        classes = [a.class_name for a in ClassAdvisor.query.filter_by(teacher_id=teacher.id)]
        assert result["class_name"] in classes
        students = [p.user for p in StudentProfile.query.filter_by(class_name=result["class_name"])]
        overview = svc.class_overview(students, today=TODAY)
        assert overview["met"] >= 1 and overview["gap"] >= 2 and overview["data"] >= 1
        open_cases = _open()
        assert ("grad_demo_cert", "gap", "certificates") in open_cases
        assert ("grad_demo_fail", "gap", "required_credits") in open_cases
        assert ("grad_demo_data", "data_needed", "credits") in open_cases
        assert not [c for c in open_cases if c[0] == "grad_demo_met"]
        assert Notification.query.count() > 0
        assert all("僅為測試資料" in u.display_name for u in students)


def test_seed_twice_creates_no_duplicates():
    app = _app()
    with app.app_context():
        seed_graduation_demo(TODAY)
        cases, users, notes = GraduationCase.query.count(), User.query.count(), Notification.query.count()
        seed_graduation_demo(TODAY)
        assert (GraduationCase.query.count(), User.query.count(), Notification.query.count()) == (cases, users, notes)
