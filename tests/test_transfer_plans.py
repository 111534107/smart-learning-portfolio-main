"""B18 插大自填目標、B19／B20 升學路線比較頁。資料僅為測試資料。"""
from datetime import date, timedelta

import pytest

from app import create_app
from app.extensions import db
from app.models import AuditLog, ClassAdvisor, StudentProfile, TransferPlan, TransferPlanSubject, User
from app.services.journey_service import academic_year_of
from app.services.transfer_plan import readiness, split_subjects, target_year


@pytest.fixture()
def app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "WTF_CSRF_ENABLED": False})
    with app.app_context():
        db.create_all()
        year = academic_year_of(date.today())
        student = User(username="tp-stu", display_name="測試學生（僅為測試資料）", role="student")
        other = User(username="tp-other", display_name="別班學生", role="student")
        teacher = User(username="tp-teacher", display_name="測試導師", role="teacher")
        for user in (student, other, teacher):
            user.set_password("pw")
        db.session.add_all([student, other, teacher])
        db.session.flush()
        db.session.add_all([
            StudentProfile(user_id=student.id, student_no="T0001", class_name="資管科五甲", admission_year=year - 4),
            StudentProfile(user_id=other.id, student_no="T0002", class_name="資管科五乙", admission_year=year - 4),
            ClassAdvisor(teacher_id=teacher.id, class_name="資管科五甲", school_year=year),
        ])
        db.session.commit()
        yield app


def login(app, username):
    client = app.test_client()
    client.post("/login", data={"username": username, "password": "pw"})
    return client


def student_id(name):
    return User.query.filter_by(username=name).one().id


def new_plan(**kw):
    values = dict(school_name="測試大學", department_name="資訊管理學系", admission_year=target_year())
    values.update(kw)
    plan = TransferPlan(student_id=student_id("tp-stu"), **values)
    db.session.add(plan)
    db.session.commit()
    return plan


# ---------- 準備度計算 ----------

def test_split_subjects_drops_weights_and_notes():
    assert split_subjects("微積分Ａ×1、計算機概論×1.5、英文×1（臺大共同）") == ["微積分Ａ", "計算機概論", "英文"]
    assert split_subjects("不考筆試；書面審查 100%") == []


def test_readiness_averages_subjects_and_warns_when_exam_is_close(app):
    plan = new_plan(exam_date=date.today() + timedelta(days=20))
    plan.subjects = [TransferPlanSubject(name="英文", progress=40), TransferPlanSubject(name="計概", progress=80)]
    db.session.commit()

    result = readiness(plan)

    assert result["score"] == 60
    assert result["level"] == "urgent"
    assert result["weakest"].name == "英文"
    assert not result["stale"]


def test_readiness_flags_last_years_brochure(app):
    plan = new_plan(admission_year=academic_year_of(date.today()))

    result = readiness(plan)

    assert result["stale"]
    assert "已考完" in result["stale_message"]
    assert result["level"] == "nodate"


# ---------- 學生頁 ----------

def test_student_adds_plan_and_saves_subject_progress(app):
    client = login(app, "tp-stu")
    response = client.post("/student/transfer-plans", data={
        "school_name": "測試大學", "department_name": "資訊管理學系", "entry_grade": "3",
        "admission_year": str(target_year()), "brochure_url": "https://exam.test.edu.tw/116.pdf",
        "exam_date": (date.today() + timedelta(days=200)).isoformat(), "subjects": "計算機概論、英文",
    })
    assert response.status_code == 302

    plan = TransferPlan.query.one()
    assert [s.name for s in plan.subjects] == ["計算機概論", "英文"]
    subject = plan.subjects[0]
    client.post(f"/student/transfer-plans/{plan.id}/progress", data={f"progress_{subject.id}": "150"})
    db.session.refresh(subject)
    assert subject.progress == 100  # 超過 100 會被夾回

    page = client.get("/student/transfer-plans").get_data(as_text=True)
    assert "測試大學 資訊管理學系" in page
    assert "準備度 50%" in page


def test_student_cannot_touch_someone_elses_plan(app):
    plan = TransferPlan(student_id=student_id("tp-other"), school_name="別校", department_name="資工",
                        admission_year=target_year())
    db.session.add(plan)
    db.session.commit()

    client = login(app, "tp-stu")
    assert client.post(f"/student/transfer-plans/{plan.id}/progress", data={}).status_code == 404
    assert client.post(f"/student/transfer-plans/{plan.id}/archive").status_code == 404


def test_archive_keeps_the_row(app):
    plan = new_plan()
    client = login(app, "tp-stu")
    client.post(f"/student/transfer-plans/{plan.id}/archive")

    db.session.refresh(plan)
    assert plan.archived
    assert TransferPlan.query.count() == 1


def test_bad_date_order_shows_error(app):
    client = login(app, "tp-stu")
    response = client.post("/student/transfer-plans", data={
        "school_name": "測試大學", "department_name": "資管", "admission_year": str(target_year()),
        "apply_start": "2027-05-20", "apply_end": "2027-05-01",
    })
    assert response.status_code == 200
    assert "報名開始日不能晚於報名截止日" in response.get_data(as_text=True)
    assert TransferPlan.query.count() == 0


# ---------- 導師 ----------

def test_teacher_sees_plan_and_corrects_it_with_audit_log(app):
    plan = new_plan(note="學生自己的備註")
    plan.subjects = [TransferPlanSubject(name="英文", progress=30)]
    db.session.commit()

    client = login(app, "tp-teacher")
    page = client.get(f"/teacher/students/{plan.student_id}").get_data(as_text=True)
    assert "插大準備" in page and "測試大學" in page

    response = client.post(f"/teacher/students/{plan.student_id}/transfer-plans/{plan.id}", data={
        "school_name": "測試大學", "department_name": "資訊管理學系", "admission_year": str(target_year()),
        "exam_date": "2027-07-10", "subjects": "英文、計算機概論", "teacher_note": "考期請再對一次簡章",
    })
    assert response.status_code == 302

    db.session.refresh(plan)
    assert plan.exam_date == date(2027, 7, 10)
    assert plan.teacher_note == "考期請再對一次簡章"
    assert plan.note == "學生自己的備註"  # 導師修改不會蓋掉學生備註
    assert plan.subjects[0].progress == 30  # 原本的科目保留進度
    assert AuditLog.query.filter_by(action="transfer_plan.teacher_update").count() == 1


def test_teacher_of_other_class_cannot_edit(app):
    other_plan = TransferPlan(student_id=student_id("tp-other"), school_name="別校", department_name="資工",
                              admission_year=target_year())
    db.session.add(other_plan)
    db.session.commit()

    client = login(app, "tp-teacher")
    response = client.post(f"/teacher/students/{other_plan.student_id}/transfer-plans/{other_plan.id}", data={
        "school_name": "改掉", "department_name": "改掉", "admission_year": "116"})
    assert response.status_code == 403


# ---------- 升學路線比較 ----------

def test_pathways_page_states_leave_of_absence_rule_and_sources(app):
    page = login(app, "tp-stu").get("/student/pathways").get_data(as_text=True)

    assert "休學或退學滿一年" in page
    assert "law.moj.gov.tw" in page
    assert "會計學、經濟學" in page
    assert 'value="y5" checked' in page  # 五年級學生預設選五年級
