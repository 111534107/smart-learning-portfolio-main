"""年級總覽（評審意見 5b，2026-11-10）：科辦與管理員看專一到專五，只算已確認資料。合成假資料。"""
from datetime import date

from app import create_app
from app.extensions import db
from app.models import CredentialRecord, LearningCourseRecord, Portfolio, SourceDocument, StudentProfile, User
from app.services import grade_overview

TODAY = date(2026, 11, 10)  # 115 學年度：111 入學是專五、115 入學是專一


def make_app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "WTF_CSRF_ENABLED": False, "TWO_FACTOR_REQUIRED": False})
    with app.app_context():
        db.create_all()
        for username, role in (("staff", "staff"), ("adm", "admin"), ("tea", "teacher")):
            user = User(username=username, display_name=username, role=role)
            user.set_password("pw")
            db.session.add(user)
        db.session.commit()
    return app


def student(no, year):
    user = User(username=no, display_name=no, role="student")
    user.set_password("pw")
    db.session.add(user)
    db.session.flush()
    db.session.add(StudentProfile(user_id=user.id, student_no=no, admission_year=year))
    db.session.flush()
    return user


def course(user, score, credits=3, status="confirmed"):
    db.session.add(LearningCourseRecord(student_id=user.id, course_name="國文", normalized_course_name="國文",
                                        credits=credits, score=score, confirmation_status=status))


def test_counts_by_grade_only_confirmed():
    app = make_app()
    with app.app_context():
        senior_a, senior_b = student("111000001", 111), student("111000002", 111)
        freshman = student("115000001", 115)
        student("000000009", None)  # 沒有入學學年度
        course(senior_a, 80)
        course(senior_a, 50)  # 不及格：算平均、不算學分
        course(senior_b, 90)
        course(senior_b, 100, status="draft")  # 未確認不算
        course(freshman, 70, credits=2)
        db.session.add(CredentialRecord(student_id=senior_a.id, credential_name="電腦軟體應用丙級",
                                        confirmation_status="confirmed"))
        db.session.add(CredentialRecord(student_id=senior_b.id, credential_name="網頁設計丙級",
                                        confirmation_status="pending"))
        db.session.add(Portfolio(student_id=senior_a.id, title="資訊競賽佳作", category="competition", status="confirmed"))
        db.session.add(Portfolio(student_id=senior_a.id, title="迎新服務", category="service", status="confirmed"))
        db.session.add(Portfolio(student_id=senior_b.id, title="草稿競賽", category="competition", status="draft"))
        db.session.add(SourceDocument(owner_id=freshman.id, document_type="credential", display_name="a.jpg",
                                      file_path="x", sha256="0" * 64, status="confirmed"))
        db.session.commit()
        result = grade_overview.build(TODAY)
        rows = {row["grade"]: row for row in result["rows"]}
        assert result["total"] == 4 and result["unknown_grade"] == 1
        assert rows[5]["students"] == 2 and rows[5]["average_score"] == round((80 + 50 + 90) / 3, 1)
        assert rows[5]["average_credits"] == 3.0  # 及格 6 學分 / 2 人
        assert rows[5]["credentials"] == 1 and rows[5]["awards"] == 1 and rows[5]["experiences"] == 1
        assert rows[1]["students"] == 1 and rows[1]["uploads"] == 1 and rows[1]["average_score"] == 70
        assert rows[3]["students"] == 0 and rows[3]["average_score"] is None


def test_page_for_staff_and_admin_only():
    app = make_app()
    for username in ("staff", "adm"):
        client = app.test_client()
        client.post("/login", data={"username": username, "password": "pw"})
        page = client.get("/grade-overview")
        assert page.status_code == 200 and "data-grade-overview" in page.get_data(as_text=True)
        assert 'href="/grade-overview"' in client.get("/grade-overview").get_data(as_text=True)
    teacher = app.test_client()
    teacher.post("/login", data={"username": "tea", "password": "pw"})
    assert teacher.get("/grade-overview").status_code == 403
