"""科辦電子獎狀：學生從獎懲記錄匯入的服務申請 → 科辦編輯內文後核准或退回 → 產出含驗證碼的獎狀。"""
from app import create_app
from app.extensions import db
from app.models import AwardCertificate, ClassAdvisor, Portfolio, StudentProfile, User


def cert_app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        users = {}
        for username, name, role in [("stu", "王小明", "student"), ("other", "林小美", "student"),
                                     ("staff", "林科助", "staff"), ("t1", "陳導師", "teacher"), ("t2", "別班導師", "teacher")]:
            user = User(username=username, display_name=name, role=role)
            user.set_password("pw")
            db.session.add(user)
            users[username] = user
        db.session.flush()
        db.session.add(StudentProfile(user_id=users["stu"].id, student_no="111534105", class_name="資管科三甲", admission_year=111))
        db.session.add(StudentProfile(user_id=users["other"].id, student_no="111534107", class_name="資管科三乙", admission_year=111))
        db.session.add(ClassAdvisor(teacher_id=users["t1"].id, class_name="資管科三甲", school_year=115))
        db.session.add(Portfolio(student_id=users["stu"].id, title="1141學期協助資管科麗山國中社團活動共1次",
                                 category="service", school_year=114, semester=1, source="award_record"))
        db.session.add(Portfolio(student_id=users["stu"].id, title="資訊週志工", category="service"))
        db.session.commit()
    return app


def client_for(app, username):
    client = app.test_client()
    client.post("/login", data={"username": username, "password": "pw"})
    return client


def _record_id(app, title_part):
    with app.app_context():
        return next(p.id for p in Portfolio.query.all() if title_part in p.title)


def _apply(app):
    record_id = _record_id(app, "麗山")
    response = client_for(app, "stu").post(f"/student/portfolio/{record_id}/certificate")
    with app.app_context():
        return response, AwardCertificate.query.one()


def test_student_applies_and_body_is_prefilled(tmp_path):
    app = cert_app(tmp_path)

    response, cert = _apply(app)

    assert response.status_code == 302
    assert cert.status == "pending"
    assert "王小明" in cert.body and "111534105" in cert.body
    assert "114 學年度第一學期" in cert.body
    assert "協助資管科麗山國中社團活動共1次" in cert.body
    assert "1141學期" not in cert.body
    assert cert.verify_code is None


def test_only_award_record_service_can_apply(tmp_path):
    app = cert_app(tmp_path)
    record_id = _record_id(app, "資訊週")

    response = client_for(app, "stu").post(f"/student/portfolio/{record_id}/certificate")

    assert response.status_code == 400
    with app.app_context():
        assert AwardCertificate.query.count() == 0


def test_other_student_cannot_apply_for_my_record(tmp_path):
    app = cert_app(tmp_path)
    record_id = _record_id(app, "麗山")

    response = client_for(app, "other").post(f"/student/portfolio/{record_id}/certificate")

    assert response.status_code == 404


def test_applying_twice_keeps_one_request(tmp_path):
    app = cert_app(tmp_path)
    _apply(app)
    record_id = _record_id(app, "麗山")

    client_for(app, "stu").post(f"/student/portfolio/{record_id}/certificate")

    with app.app_context():
        assert AwardCertificate.query.count() == 1


def test_staff_lists_pending_requests(tmp_path):
    app = cert_app(tmp_path)
    _apply(app)

    html = client_for(app, "staff").get("/staff/certificates").get_data(as_text=True)

    assert "王小明" in html and "麗山國中" in html


def test_students_and_teachers_cannot_open_staff_pages(tmp_path):
    app = cert_app(tmp_path)
    _, cert = _apply(app)

    assert client_for(app, "stu").get("/staff/certificates").status_code == 403
    assert client_for(app, "t1").get(f"/staff/certificates/{cert.id}").status_code == 403


def test_staff_edits_body_and_approves(tmp_path):
    app = cert_app(tmp_path)
    _, cert = _apply(app)

    response = client_for(app, "staff").post(f"/staff/certificates/{cert.id}", data={
        "action": "approve", "title": "服務證明", "issuer": "資訊管理科",
        "body": "茲證明 王小明 同學熱心服務，特此證明。",
    })

    assert response.status_code == 302
    with app.app_context():
        cert = db.session.get(AwardCertificate, cert.id)
        assert cert.status == "approved"
        assert cert.body == "茲證明 王小明 同學熱心服務，特此證明。"
        assert cert.verify_code and len(cert.verify_code) == 8
        assert cert.issued_on is not None
        assert cert.reviewed_by.username == "staff"


def test_return_requires_reason_and_student_can_reapply(tmp_path):
    app = cert_app(tmp_path)
    _, cert = _apply(app)
    staff = client_for(app, "staff")

    missing = staff.post(f"/staff/certificates/{cert.id}", data={"action": "return", "return_reason": "", "body": cert.body})
    returned = staff.post(f"/staff/certificates/{cert.id}", data={"action": "return", "return_reason": "查無這筆紀錄", "body": cert.body})

    assert missing.status_code == 400
    assert returned.status_code == 302
    html = client_for(app, "stu").get(f"/student/portfolio/{_record_id(app, '麗山')}/edit").get_data(as_text=True)
    assert "查無這筆紀錄" in html
    _apply(app)
    with app.app_context():
        assert AwardCertificate.query.one().status == "pending"


def _approved(app):
    _, cert = _apply(app)
    client_for(app, "staff").post(f"/staff/certificates/{cert.id}", data={
        "action": "approve", "title": "服務證明", "issuer": "資訊管理科", "body": cert.body})
    with app.app_context():
        return db.session.get(AwardCertificate, cert.id)


def test_certificate_page_visible_to_owner_staff_and_own_class_teacher(tmp_path):
    app = cert_app(tmp_path)
    cert = _approved(app)
    url = f"/certificates/{cert.id}"

    owner_html = client_for(app, "stu").get(url).get_data(as_text=True)
    assert "服務證明" in owner_html and cert.verify_code in owner_html
    assert client_for(app, "staff").get(url).status_code == 200
    assert client_for(app, "t1").get(url).status_code == 200
    assert client_for(app, "t2").get(url).status_code == 403
    assert client_for(app, "other").get(url).status_code == 403


def test_pending_certificate_cannot_be_viewed_by_student(tmp_path):
    app = cert_app(tmp_path)
    _, cert = _apply(app)

    assert client_for(app, "stu").get(f"/certificates/{cert.id}").status_code == 404


def test_public_verify_page_masks_name(tmp_path):
    app = cert_app(tmp_path)
    cert = _approved(app)

    found = app.test_client().get(f"/verify?code={cert.verify_code}").get_data(as_text=True)
    missing = app.test_client().get("/verify?code=ZZZZZZZZ").get_data(as_text=True)

    assert "王○明" in found and "王小明" not in found and "111534105" not in found
    assert "資訊管理科" in found
    assert "查無" in missing


def test_approved_certificate_becomes_department_source_record(tmp_path):
    app = cert_app(tmp_path)
    _approved(app)

    html = client_for(app, "stu").get("/student/portfolio").get_data(as_text=True)

    assert "科辦電子獎狀" in html


def test_staff_dashboard_shows_pending_certificate_count(tmp_path):
    app = cert_app(tmp_path)
    _apply(app)

    html = client_for(app, "staff").get("/staff/dashboard").get_data(as_text=True)

    assert "待核准電子獎狀" in html and "/staff/certificates" in html


def test_body_converts_grade_back_to_academic_year(tmp_path):
    app = cert_app(tmp_path)
    with app.app_context():
        record = next(p for p in Portfolio.query.all() if "麗山" in p.title)
        record.school_year = 4  # 111 入學的專四 = 114 學年度
        db.session.commit()

    _, cert = _apply(app)

    assert "114 學年度第一學期" in cert.body
