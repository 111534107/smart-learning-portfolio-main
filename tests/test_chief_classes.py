"""科主任指派導師班級、導師自傳可選擇看、學生看得到差別（2026-11-18 指導老師三項要求）。僅為測試資料。"""

import pytest

from app import create_app
from app.extensions import db
from app.models import (AdmissionProgram, AuditLog, ClassAdvisor, LearningProfileOutput, PackageReview,
                        StudentProfile, StudentTarget, User)
from app.services import autobiography_service, staff_roles


@pytest.fixture
def setup():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "MIN_REVIEW_GRADE": 1})
    with app.app_context():
        db.create_all()
        rows = [
            ("chief", "staff", "主任"), ("vice", "staff", "副主任"), ("assist", "staff", "科助"),
            ("other_staff", "staff", "其他行政人員"), ("admin", "admin", None),
            ("t1", "teacher", None), ("t2", "teacher", None), ("student", "student", None),
        ]
        users = []
        for name, role, title in rows:
            user = User(username=name, display_name=name, role=role, job_title=title)
            user.set_password("pw")
            users.append(user)
        db.session.add_all(users)
        db.session.flush()
        ids = {u.username: u.id for u in users}
        db.session.add(StudentProfile(user_id=ids["student"], student_no="DEMO-1", class_name="測試甲班", admission_year=110))
        program = AdmissionProgram(program_code="DEMO1", admission_year=115, school_name="測試大學",
                                   department_name="資訊管理系", status="published")
        db.session.add(program)
        db.session.flush()
        db.session.add(StudentTarget(student_id=ids["student"], rule_version_id=program.id))
        db.session.commit()
        ids["program"] = program.id
    return app, ids


def login(app, username):
    client = app.test_client()
    path = "/staff/login" if username not in ("admin", "student") else ("/admin/login" if username == "admin" else "/login")
    assert client.post(path, data={"username": username, "password": "pw"}).status_code == 302
    return client


# ---- 角色判斷集中一處 ----

def test_staff_roles_helpers(setup):
    app, ids = setup
    with app.app_context():
        get = lambda name: db.session.get(User, ids[name])
        assert staff_roles.is_chief(get("chief")) and staff_roles.is_chief(get("vice"))
        assert not staff_roles.is_chief(get("assist")) and not staff_roles.is_chief(get("t1"))
        assert staff_roles.is_assistant(get("assist")) and not staff_roles.is_assistant(get("chief"))
        assert staff_roles.staff_label(get("chief")) == "科主任"
        assert staff_roles.staff_label(get("vice")) == "科主任（副主任）"
        assert staff_roles.staff_label(get("assist")) == "科助"
        assert staff_roles.staff_label(get("other_staff")) == "其他行政人員"


# ---- 科主任指派班級 ----

def test_chief_and_vice_can_assign_assistant_cannot(setup):
    app, ids = setup
    for name in ("chief", "vice"):
        client = login(app, name)
        assert client.get("/staff/classes").status_code == 200
    assistant = login(app, "assist")
    assert assistant.get("/staff/classes").status_code == 403
    assert assistant.post("/staff/classes", data={"teacher_id": ids["t1"], "class_name": "測試甲班", "school_year": 115}).status_code == 403
    assert login(app, "other_staff").get("/staff/classes").status_code == 403
    with app.app_context():
        assert ClassAdvisor.query.count() == 0


def test_chief_assign_logs_and_blocks_duplicate_same_year_but_allows_other_year_and_other_teacher(setup):
    app, ids = setup
    client = login(app, "chief")
    data = {"teacher_id": ids["t1"], "class_name": "測試甲班", "school_year": 115}
    assert client.post("/staff/classes", data=data).status_code == 302
    assert client.post("/staff/classes", data=data).status_code == 400  # 重複
    assert client.post("/staff/classes", data={**data, "school_year": 116}).status_code == 302  # 跨學年度
    assert client.post("/staff/classes", data={**data, "teacher_id": ids["t2"]}).status_code == 302  # 同班多位導師
    assert client.post("/staff/classes", data={**data, "teacher_id": ids["student"]}).status_code == 400  # 不是導師
    with app.app_context():
        assert ClassAdvisor.query.count() == 3
        logs = AuditLog.query.filter_by(action="class_advisor.add").all()
        assert len(logs) == 3 and all(log.user_id == ids["chief"] for log in logs)


def test_chief_remove_logs_and_assistant_cannot_remove(setup):
    app, ids = setup
    with app.app_context():
        advisor = ClassAdvisor(teacher_id=ids["t1"], class_name="測試甲班", school_year=115)
        db.session.add(advisor)
        db.session.commit()
        advisor_id = advisor.id
    assert login(app, "assist").post(f"/staff/classes/{advisor_id}/delete").status_code == 403
    assert login(app, "chief").post(f"/staff/classes/{advisor_id}/delete").status_code == 302
    with app.app_context():
        assert ClassAdvisor.query.count() == 0
        assert AuditLog.query.filter_by(action="class_advisor.remove", user_id=ids["chief"]).count() == 1


def test_admin_keeps_class_permission(setup):
    app, ids = setup
    admin = login(app, "admin")
    assert admin.get("/admin/classes").status_code == 200
    assert admin.post("/admin/classes", data={"teacher_id": ids["t1"], "class_name": "測試甲班", "school_year": 115}).status_code == 302
    with app.app_context():
        assert ClassAdvisor.query.count() == 1


def test_assigned_teacher_sees_only_own_class_students(setup):
    app, ids = setup
    login(app, "chief").post("/staff/classes", data={"teacher_id": ids["t1"], "class_name": "測試甲班", "school_year": 115})
    assert login(app, "t1").get(f"/teacher/students/{ids['student']}").status_code == 200
    assert login(app, "t2").get(f"/teacher/students/{ids['student']}").status_code == 403


# ---- 導師自傳可選擇看 ----

def _draft(ids, text, version):
    return LearningProfileOutput(
        student_id=ids["student"], output_type=autobiography_service.OUTPUT_TYPE,
        content_json={"program_id": ids["program"], "version": version, "provider": "demo",
                      "paragraphs": [{"title": "段一", "text": text}]},
        source_snapshot_json={})


def _submit(app, ids, with_autobiography=True):
    with app.app_context():
        db.session.add(ClassAdvisor(teacher_id=ids["t1"], class_name="測試甲班", school_year=115))
        if with_autobiography:
            db.session.add(_draft(ids, "這是祕密自傳全文ABC", 1))
        db.session.commit()
    student = login(app, "student")
    student.post(f"/student/targets/{ids['program']}/review")
    with app.app_context():
        review = PackageReview.query.one()
        return review.id, review.snapshot_json["taken_at"]


def test_autobiography_collapsed_by_default_and_choice_recorded(setup):
    app, ids = setup
    review_id, taken = _submit(app, ids)
    teacher = login(app, "t1")
    page = teacher.get(f"/teacher/students/{ids['student']}").get_data(as_text=True)
    assert "data-autobiography-optional" in page and "我已查看自傳" in page
    assert "data-autobiography-optional>" in page  # details 沒有 open 屬性＝預設收合
    # 不勾選也能確認，記錄為未檢視
    assert teacher.post(f"/teacher/package-reviews/{review_id}",
                        data={"decision": "confirmed", "taken_at": taken}).status_code == 302
    with app.app_context():
        review = db.session.get(PackageReview, review_id)
        assert review.status == "confirmed" and review.autobiography_viewed is False
        log = AuditLog.query.filter_by(action="package_review.confirm").one()
        assert log.detail_json["autobiography_viewed"] is False


def test_autobiography_viewed_choice_and_student_sees_difference_without_text_in_log(setup):
    app, ids = setup
    review_id, taken = _submit(app, ids)
    teacher = login(app, "t1")
    teacher.post(f"/teacher/package-reviews/{review_id}",
                 data={"decision": "confirmed", "taken_at": taken, "autobiography_viewed": "1"})
    with app.app_context():
        assert db.session.get(PackageReview, review_id).autobiography_viewed is True
        for log in AuditLog.query.all():
            assert "祕密自傳全文ABC" not in str(log.detail_json)
        assert "祕密自傳全文ABC" not in str(db.session.get(PackageReview, review_id).snapshot_json)
    student = login(app, "student")
    assert "導師已確認（已檢視自傳）" in student.get(f"/student/targets/{ids['program']}").get_data(as_text=True)


def test_student_sees_not_viewed_label(setup):
    app, ids = setup
    review_id, taken = _submit(app, ids)
    login(app, "t1").post(f"/teacher/package-reviews/{review_id}", data={"decision": "confirmed", "taken_at": taken})
    student = login(app, "student")
    assert "導師已確認（未檢視自傳）" in student.get(f"/student/targets/{ids['program']}").get_data(as_text=True)


def test_new_autobiography_version_still_blocks_confirm(setup):
    app, ids = setup
    review_id, taken = _submit(app, ids)
    with app.app_context():
        db.session.add(_draft(ids, "新版", 2))
        db.session.commit()
    login(app, "t1").post(f"/teacher/package-reviews/{review_id}",
                          data={"decision": "confirmed", "taken_at": taken, "autobiography_viewed": "1"})
    with app.app_context():
        assert db.session.get(PackageReview, review_id).status == "pending"

def test_class_assignment_tour_explains_both_roles_and_steps(setup):
    app, _ = setup
    for username, url in [('chief', '/staff/classes'), ('admin', '/admin/classes')]:
        page = login(app, username).get(url).get_data(as_text=True)
        assert 'data-tour="選導師、班級和學年度，新增指派。"' in page
        assert 'data-tour="在清單核對指派，需要時可移除。"' in page

def test_chief_student_list_guides_filter_and_read_only_detail(setup):
    app, _ = setup
    page = login(app, 'chief').get('/staff/students').get_data(as_text=True)
    assert 'data-tour="選年級、班級或輸入姓名後篩選。"' in page
    assert 'data-tour="點學生姓名查看唯讀資料與畢業狀態。"' in page
