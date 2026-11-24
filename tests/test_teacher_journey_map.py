from datetime import date
import re

from app import create_app
from app.extensions import db
from app.models import ClassAdvisor, CredentialRecord, LearningCourseRecord, Portfolio, PortfolioEvidence, StudentProfile, User
from app.services.journey_service import academic_year_of


def teacher_journey_app():
    app = create_app(
        {
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
        }
    )
    with app.app_context():
        db.create_all()
        teacher = User(username="journey-teacher", display_name="導師", role="teacher")
        student = User(username="journey-student", display_name="學生", role="student")
        teacher.set_password("pw")
        student.set_password("pw")
        db.session.add_all([teacher, student])
        db.session.flush()

        current_academic_year = academic_year_of(date.today())
        db.session.add(
            StudentProfile(
                user_id=student.id,
                student_no="J0001",
                class_name="資管科三甲",
                admission_year=current_academic_year - 2,
            )
        )
        db.session.add(
            ClassAdvisor(
                teacher_id=teacher.id,
                class_name="資管科三甲",
                school_year=current_academic_year,
            )
        )
        db.session.add_all(
            [
                Portfolio(student_id=student.id, title="專一活動", category="activity", school_year=1),
                Portfolio(student_id=student.id, title="專三活動", category="activity", school_year=3),
                Portfolio(student_id=student.id, title="專三競賽", category="competition", school_year=3),
                Portfolio(student_id=student.id, title="專三服務", category="service", school_year=3),
            ]
        )
        db.session.commit()
        student_id = student.id
    return app, student_id


def test_teacher_student_page_shows_static_five_year_overview_with_correct_counts():
    app, student_id = teacher_journey_app()
    client = app.test_client()
    client.post("/login", data={"username": "journey-teacher", "password": "pw"})

    response = client.get(f"/teacher/students/{student_id}")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert html.count("data-teacher-journey-stop") == 5
    assert 'data-grade="1" data-records="1"' in html
    assert 'data-grade="2" data-records="0"' in html
    assert 'data-grade="3" data-records="3"' in html
    assert 'data-grade="3" data-records="3" data-state="now"' in html
    assert 'data-grade="4" data-records="0" data-state="future"' in html
    assert 'href="#teacher-year-1"' in html
    assert 'href="#teacher-year-3"' in html
    assert 'href="#teacher-year-2"' not in html

    overview = html.split('data-teacher-journey-map', 1)[1].split('</section>', 1)[0]
    assert "<img" not in overview
    assert "photo" not in overview.lower()
    assert "puzzle" not in overview.lower()


def test_teacher_sees_each_student_record_and_attachment_confirmation_state():
    app, student_id = teacher_journey_app()
    with app.app_context():
        records = [
            Portfolio(student_id=student_id, title="草稿活動測試", category="activity", school_year=1, status="draft"),
            Portfolio(student_id=student_id, title="確認活動測試", category="activity", school_year=1, status="confirmed"),
        ]
        db.session.add_all(records)
        db.session.flush()
        for record in records:
            db.session.add(PortfolioEvidence(portfolio_id=record.id, evidence_type="image", display_name="測試.png", file_path="test.png"))
        db.session.add_all([
            LearningCourseRecord(student_id=student_id, course_name="草稿課程測試", normalized_course_name="草稿課程測試", school_year=1, confirmation_status="draft"),
            LearningCourseRecord(student_id=student_id, course_name="確認課程測試", normalized_course_name="確認課程測試", school_year=1, confirmation_status="confirmed"),
            CredentialRecord(student_id=student_id, credential_name="草稿證照測試", issue_date=date.today(), confirmation_status="draft"),
            CredentialRecord(student_id=student_id, credential_name="確認證照測試", issue_date=date.today(), confirmation_status="confirmed"),
        ])
        db.session.commit()

    client = app.test_client()
    client.post("/login", data={"username": "journey-teacher", "password": "pw"})
    response = client.get(f"/teacher/students/{student_id}")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    for name, state in [("草稿活動測試", "草稿"), ("確認活動測試", "學生已確認"),
                        ("草稿課程測試", "草稿"), ("確認課程測試", "學生已確認"),
                        ("草稿證照測試", "草稿"), ("確認證照測試", "學生已確認")]:
        assert any(name in item and state in item for item in re.findall(r"<li\b[^>]*>.*?</li>", html, re.S))
    for name, state in [("草稿活動測試", "草稿"), ("確認活動測試", "學生已確認")]:
        assert any(name in heading and state in heading for heading in re.findall(r"<h3\b[^>]*>.*?</h3>", html, re.S))
    assert "以下是學生已確認的資料" not in html
    roster = client.get("/teacher/roster").get_data(as_text=True)   # 2026-11-21 工作台拆頁：這段說明在學生名單頁
    assert "各類資料筆數包含草稿與學生已確認資料" in roster


def test_teacher_can_filter_visible_year_records_and_use_quick_links():
    app, student_id = teacher_journey_app()
    with app.app_context():
        db.session.add(Portfolio(student_id=student_id, title="已確認項目測試", category="activity", school_year=1, status="confirmed"))
        db.session.add(Portfolio(student_id=student_id, title="未歸年級草稿測試", category="activity", status="draft"))
        db.session.commit()
    client = app.test_client()
    client.post("/login", data={"username": "journey-teacher", "password": "pw"})
    response = client.get(f"/teacher/students/{student_id}?record_status=draft")
    html = response.get_data(as_text=True)
    records = html.split('id="teacher-records"', 1)[1].split('</section>\n</section>', 1)[0]
    assert response.status_code == 200
    assert "專一活動" in records
    assert "已確認項目測試" not in records
    assert 'href="#teacher-graduation"' in html
    assert 'href="#teacher-targets"' in html
    assert 'href="#teacher-evidence"' in html
    assert 'id="teacher-records"' in html
    assert "尚未歸入年級" in html
    assert "草稿 5 筆" in html
    assert "學生已確認 1 筆" in html
    assert "未歸年級草稿測試" in records

    confirmed_html = client.get(f"/teacher/students/{student_id}?record_status=confirmed").get_data(as_text=True)
    confirmed_records = confirmed_html.split('id="teacher-records"', 1)[1].split('</section>\n</section>', 1)[0]
    assert "已確認項目測試" in confirmed_records
    assert "專一活動" not in confirmed_records



def test_teacher_dashboard_filters_only_assigned_classes():
    app, first_id = teacher_journey_app()
    with app.app_context():
        teacher = User.query.filter_by(username="journey-teacher").one()
        second = User(username="other-class", display_name="另一班學生", role="student")
        second.set_password("pw")
        db.session.add(second)
        db.session.flush()
        db.session.add(StudentProfile(user_id=second.id, student_no="J0002", class_name="資管科三乙"))
        db.session.add(ClassAdvisor(teacher_id=teacher.id, class_name="資管科三乙", school_year=115))
        db.session.commit()
    client = app.test_client()
    client.post("/login", data={"username": "journey-teacher", "password": "pw"})
    # 2026-11-21 工作台拆頁：學生列在「學生名單」頁；四個分頁都有班級篩選，不是負責的班級一律 400
    page = client.get("/teacher/roster?class_name=資管科三乙").get_data(as_text=True)
    assert "另一班學生" in page
    assert "J0001" not in page
    assert "班級篩選" in page
    assert "班級篩選" in client.get("/teacher/dashboard?class_name=資管科三乙").get_data(as_text=True)
    for path in ("/teacher/dashboard", "/teacher/graduation", "/teacher/roster", "/teacher/targets"):
        assert client.get(f"{path}?class_name=非負責班級").status_code == 400, path


def test_student_search_only_shows_own_records_and_function_links():
    app, student_id = teacher_journey_app()
    with app.app_context():
        other = User(username="other-search", display_name="另一位", role="student")
        other.set_password("pw")
        db.session.add(other)
        db.session.flush()
        db.session.add_all([
            Portfolio(student_id=student_id, title="獨有搜尋活動", category="activity", school_year=1),
            Portfolio(student_id=other.id, title="他人搜尋活動", category="activity", school_year=1),
        ])
        db.session.commit()
    client = app.test_client()
    client.post("/login", data={"username": "journey-student", "password": "pw"})
    response = client.get("/student/search?q=搜尋活動")
    assert response.status_code == 200
    assert "獨有搜尋活動" in response.get_data(as_text=True)
    assert "他人搜尋活動" not in response.get_data(as_text=True)
    assert "畢業門檻" in client.get("/student/search?q=畢業").get_data(as_text=True)
    assert client.get("/student/search", query_string={"q": "搜尋活動", "kind": "證照", "format": "json"}).json == {"results": []}
    response = client.get("/student/search", query_string={"q": "搜尋活動", "kind": "經歷", "format": "json"})
    assert [(kind, title) for kind, title, _ in response.json["results"]] == [("經歷", "獨有搜尋活動")]


def test_teacher_summary_rejects_class_outside_teacher_scope():
    app, _ = teacher_journey_app()
    client = app.test_client()
    client.post("/login", data={"username": "journey-teacher", "password": "pw"})
    assert client.post("/teacher/class-summary", data={"class_name": "不是負責的班"}).status_code == 403
    response = client.post("/teacher/class-summary", data={"class_name": "資管科三甲"})
    assert response.status_code == 200
    assert "人數較少" in response.get_data(as_text=True)

def test_teacher_student_summary_only_for_own_student():
    app, student_id = teacher_journey_app()
    with app.app_context():
        outsider = User(username="other-summary", display_name="別班學生", role="student")
        outsider.set_password("pw")
        db.session.add(outsider)
        db.session.flush()
        db.session.add(StudentProfile(user_id=outsider.id, student_no="OTHER", class_name="別班"))
        db.session.commit()
        outsider_id = outsider.id
    client = app.test_client()
    client.post("/login", data={"username": "journey-teacher", "password": "pw"})
    assert client.post(f"/teacher/students/{outsider_id}/summary").status_code == 403
    response = client.post(f"/teacher/students/{student_id}/summary")
    assert response.status_code == 200
    assert "本機統計" in response.get_data(as_text=True)
