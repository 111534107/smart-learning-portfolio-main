from datetime import date

from app import create_app
from app.extensions import db
from app.models import ClassAdvisor, Portfolio, StudentProfile, User
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

