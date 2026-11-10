"""各學期預警與教務處檢核日期倒數（2026-11-10）。合成假資料。"""
from datetime import date

from app import create_app
from app.extensions import db
from app.models import AuditLog, LearningCourseRecord, StudentProfile, SystemSetting, User
from app.services import check_dates, semester_warning
from app.services.eligibility_service import normalize_course_name

TODAY = date(2025, 3, 1)  # 113 學年下學期：111 入學是專三下，已結束 5 個學期


def make_app(admission_year=111, today=TODAY):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "WTF_CSRF_ENABLED": False, "TWO_FACTOR_REQUIRED": False})
    with app.app_context():
        db.create_all()
        for username, role in (("stu", "student"), ("admin", "admin")):
            user = User(username=username, display_name=f"合成{role}", role=role)
            user.set_password("pw")
            db.session.add(user)
        db.session.flush()
        student = User.query.filter_by(username="stu").one()
        db.session.add(StudentProfile(user_id=student.id, student_no="111000001", class_name="資三甲",
                                      admission_year=admission_year))
        db.session.add(SystemSetting(key="graduation_check_today", value=today.isoformat()))
        db.session.commit()
    return app


def add_course(student_id, name, credits, score, grade, semester):
    db.session.add(LearningCourseRecord(student_id=student_id, course_name=name,
                                        normalized_course_name=normalize_course_name(name), credits=credits,
                                        score=score, school_year=grade, semester=semester,
                                        confirmation_status="confirmed"))


CURRICULUM = {111: {normalize_course_name("模擬程式"): {"category": "專業必修"},
                    normalize_course_name("模擬資料庫"): {"category": "專業必修"}}}


def seed_terms(student_id):
    add_course(student_id, "模擬程式", 3, 50, 1, "上")   # 專一上不及格 3/5 學分，專一下補及格
    add_course(student_id, "模擬國文", 2, 80, 1, "上")
    add_course(student_id, "模擬程式", 3, 70, 1, "下")
    add_course(student_id, "模擬英文", 3, 90, 1, "下")
    add_course(student_id, "模擬資料庫", 3, 55, 2, "上")  # 必修不及格，還沒補，3/11 未達三分之一
    for name in ("模擬體育", "模擬數學", "模擬歷史"):
        add_course(student_id, name, 8 // 3, 80, 2, "上")
    add_course(student_id, "模擬選修", 2, 50, 3, "上")    # 專二下沒有成績；專三上選修不及格 2/10
    add_course(student_id, "模擬專題", 8, 80, 3, "上")
    db.session.commit()


def test_terms_are_flagged_by_ratio_required_and_missing_data():
    app = make_app()
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        seed_terms(student.id)
        result = semester_warning.build(student, today=TODAY, curriculum=CURRICULUM)
        terms = {t["label"]: t for t in result["terms"]}
        assert [t["label"] for t in result["terms"]] == ["專3上", "專2下", "專2上", "專1下", "專1上"]  # 新到舊
        assert terms["專1上"]["level"] == "high" and terms["專1上"]["recovered"][0]["name"] == "模擬程式"
        assert "一半" in terms["專1上"]["message"]
        assert terms["專1下"]["level"] == "ok"
        assert terms["專2上"]["level"] == "watch" and "必修 模擬資料庫 還沒補及格" in terms["專2上"]["message"]
        assert terms["專2下"]["level"] == "no_data"
        assert terms["專3上"]["level"] == "watch" and terms["專3上"]["still_failed"][0]["required"] is False
        assert result["counts"] == {"high": 1, "watch": 2, "no_data": 1, "ok": 1}
        # 目前的專三下還沒結束，不列入
        assert "專3下" not in terms


def test_exempt_courses_do_not_count_as_attempted_credits():
    app = make_app()
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        add_course(student.id, "模擬抵免", 4, None, 1, "上")
        add_course(student.id, "模擬程式", 3, 40, 1, "上")
        add_course(student.id, "模擬國文", 3, 80, 1, "上")
        db.session.commit()
        term = semester_warning.build(student, today=TODAY, curriculum=CURRICULUM)["terms"][-1]
        assert term["attempted"] == 6 and term["level"] == "high"


def test_student_without_admission_year_gets_reason_not_error():
    app = make_app(admission_year=None)
    with app.app_context():
        result = semester_warning.build(User.query.filter_by(username="stu").one(), today=TODAY, curriculum={})
        assert result["terms"] == [] and "入學年度" in result["reason"]


def test_student_page_shows_semester_warning():
    app = make_app()
    with app.app_context():
        seed_terms(User.query.filter_by(username="stu").one().id)
    client = app.test_client()
    client.post("/login", data={"username": "stu", "password": "pw"})
    html = client.get("/student/graduation-check").get_data(as_text=True)
    assert "data-semester-warning" in html and "各學期預警" in html
    assert 'data-warning-term="high"' in html and 'data-warning-term="no_data"' in html
    assert "僅供提醒" in html


def test_admin_sets_check_dates_and_grade_four_student_sees_countdown():
    app = make_app(admission_year=110)  # 113 下學期是專四下
    admin = app.test_client()
    admin.post("/login", data={"username": "admin", "password": "pw"})
    page = admin.get("/admin/dashboard").get_data(as_text=True)
    assert "data-check-dates" in page
    admin.post("/admin/graduation/check-dates",
               data={"first": "2025-06-09", "second": "2025-12-29", "today": TODAY.isoformat()})
    with app.app_context():
        assert check_dates.dates()["first"] == date(2025, 6, 9)
        assert AuditLog.query.filter_by(action="graduation.check_dates").count() == 1
    student = app.test_client()
    student.post("/login", data={"username": "stu", "password": "pw"})
    html = student.get("/student/graduation-check").get_data(as_text=True)
    assert "第一次檢核（專四下）：2025-06-09，還有 100 天。" in html


def test_bad_date_is_rejected_with_chinese_message():
    app = make_app()
    admin = app.test_client()
    admin.post("/login", data={"username": "admin", "password": "pw"})
    response = admin.post("/admin/graduation/check-dates", data={"first": "明年六月"}, follow_redirects=True)
    assert "日期格式要像 2027-06-07。" in response.get_data(as_text=True)
    with app.app_context():
        assert check_dates.dates()["first"] is None


def test_countdown_rules_by_stage():
    app = make_app()
    with app.app_context():
        db.session.add(SystemSetting(key=check_dates.SECOND_KEY, value="2025-01-10"))
        db.session.commit()
        assert check_dates.countdown({"grade": 3, "semester": "下"}, TODAY) is None
        assert "還沒公布" in check_dates.countdown({"grade": 4, "semester": "上"}, TODAY)["text"]
        assert "已經過了" in check_dates.countdown({"grade": 5, "semester": "上"}, TODAY)["text"]
        assert check_dates.countdown({"grade": 5, "semester": "下"}, TODAY) is None


def test_only_admin_can_set_check_dates():
    app = make_app()
    client = app.test_client()
    client.post("/login", data={"username": "stu", "password": "pw"})
    assert client.post("/admin/graduation/check-dates", data={"first": "2025-06-09"}).status_code == 403


def test_courses_without_semester_get_specific_message():
    app = make_app()
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        add_course(student.id, "模擬國文", 2, 80, 1, None)
        db.session.commit()
        terms = {t["label"]: t for t in semester_warning.build(student, today=TODAY, curriculum=CURRICULUM)["terms"]}
        assert "沒有標上下學期" in terms["專1上"]["message"] and "沒有標上下學期" in terms["專1下"]["message"]
        assert "請先上傳並確認成績單" in terms["專2上"]["message"]
