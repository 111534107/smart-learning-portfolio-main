"""科辦直接開立電子獎狀（2026-11-09 使用者決定）：科上要開「曾擔任某某輔導班小老師、某課 TA」時，
不必等學生申請。開立後直接核准、有驗證碼，同時在學生的經歷多一筆「科辦電子獎狀」。合成資料。"""
from app.extensions import db
from app.models import AuditLog, AwardCertificate, Notification, Portfolio
from tests.test_award_certificates import cert_app, client_for


def issue(app, **form):
    data = {"student_no": "111534105", "kind": "service", "event": "協助資管科課輔班擔任小老師",
            "school_year": "114", "semester": "1"}
    data.update(form)
    return client_for(app, "staff").post("/staff/certificates/new", data=data)


def test_staff_list_has_issue_button(tmp_path):
    app = cert_app(tmp_path)
    page = client_for(app, "staff").get("/staff/certificates").get_data(as_text=True)
    assert 'href="/staff/certificates/new"' in page and "開立電子獎狀" in page
    form = client_for(app, "staff").get("/staff/certificates/new").get_data(as_text=True)
    assert 'name="student_no"' in form and "111534105" in form  # 學號清單可以選


def test_staff_issues_service_certificate_directly(tmp_path):
    app = cert_app(tmp_path)
    response = issue(app)
    assert response.status_code == 302
    with app.app_context():
        cert = AwardCertificate.query.one()
        assert response.headers["Location"].endswith(f"/certificates/{cert.id}")
        assert cert.status == "approved" and cert.verify_code and cert.issued_on
        assert cert.kind == "service" and cert.title == "服務證明"
        assert "王小明" in cert.body and "111534105" in cert.body
        assert "114 學年度第一學期" in cert.body and "協助資管科課輔班擔任小老師" in cert.body
        record = cert.portfolio
        assert record.source == "department_certificate" and record.category == "service"
        assert record.student.username == "stu" and record.school_year == 4  # 111 入學，114 學年度是專四
        assert Notification.query.filter_by(recipient_id=cert.student_id).count() == 1
        assert AuditLog.query.filter_by(action="certificate.issue").count() == 1


def test_staff_issues_ta_certificate_with_course_name(tmp_path):
    app = cert_app(tmp_path)
    issue(app, kind="ta", event="", course="資料庫系統", school_year="114", semester="2")
    with app.app_context():
        cert = AwardCertificate.query.one()
        assert cert.title == "TA 證明"
        assert "擔任「資料庫系統」課程 TA（教學助理）" in cert.body and "114 學年度第二學期" in cert.body


def test_staff_can_write_own_body(tmp_path):
    app = cert_app(tmp_path)
    issue(app, body="茲證明 王小明 同學協助本科迎新活動，特此證明。")
    with app.app_context():
        assert AwardCertificate.query.one().body == "茲證明 王小明 同學協助本科迎新活動，特此證明。"


def test_issue_validates_input(tmp_path):
    app = cert_app(tmp_path)
    assert issue(app, student_no="999999999").status_code == 400
    assert issue(app, event="").status_code == 400
    assert issue(app, kind="ta", course="").status_code == 400
    assert issue(app, kind="club").status_code == 400  # 科學會證明由學務處辦
    with app.app_context():
        assert AwardCertificate.query.count() == 0 and Portfolio.query.filter_by(source="department_certificate").count() == 0


def test_only_staff_can_issue(tmp_path):
    app = cert_app(tmp_path)
    for username in ("stu", "t1"):
        assert client_for(app, username).post("/staff/certificates/new", data={"student_no": "111534105"}).status_code == 403


def test_student_sees_issued_certificate(tmp_path):
    app = cert_app(tmp_path)
    issue(app)
    with app.app_context():
        cert_id = AwardCertificate.query.one().id
    page = client_for(app, "stu").get(f"/certificates/{cert_id}")
    assert page.status_code == 200 and "協助資管科課輔班擔任小老師" in page.get_data(as_text=True)
