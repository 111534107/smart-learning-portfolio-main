from app import create_app
from app.extensions import db
from app.models import User


def ui_app():
    app = create_app(
        {
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
        }
    )
    with app.app_context():
        db.create_all()
        student = User(username="ui-student", display_name="UI Student", role="student")
        student.set_password("test-password")
        db.session.add(student)
        db.session.commit()
    return app


def test_public_home_uses_the_shared_design_system_and_motion_shell():
    client = ui_app().test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert b'data-page="public-home"' in response.data
    assert b"/static/css/design-system.css" in response.data
    assert b"/static/js/motion.js" in response.data
    assert b"data-scatter" in response.data
    assert b'id="route"' in response.data


def test_public_home_no_longer_hardcodes_admission_program_weights():
    # 首頁不放寫死某一學年度簡章的校系加權表；簡章每年會換，校系資料由管理員在後台維護
    client = ui_app().test_client()

    html = client.get("/").get_data(as_text=True)

    assert 'id="agent"' not in html
    assert "#agent" not in html
    assert "備審加權" not in html
    assert "簡章範例" not in html


def test_public_home_tells_the_six_step_story_in_order():
    client = ui_app().test_client()

    response = client.get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert html.count("data-story-step=") == 6
    story_beats = [
        "把五年，拼成下一站",
        "散落的資料，開始連成一條路",
        "專一到專五，各有一格位置",
        "升學、實習、就業",
        "只留下和目標有關的證明",
        "五年，組成一份能出發的資料包",
    ]
    positions = [html.index(beat) for beat in story_beats]
    assert positions == sorted(positions)
    assert html.count("data-route-branch") == 3


def test_public_home_finishes_with_a_login_call_to_action():
    client = ui_app().test_client()

    response = client.get("/")
    html = response.get_data(as_text=True)

    assert 'href="/login"' in html
    assert ">開始我的路徑<" in html


def test_student_dashboard_exposes_a_personal_journey_layout():
    client = ui_app().test_client()
    login_response = client.post(
        "/login",
        data={"username": "ui-student", "password": "test-password"},
    )

    assert login_response.status_code == 302
    response = client.get("/student/dashboard")

    assert response.status_code == 200
    assert b'data-page="student-dashboard"' in response.data
    assert b"data-folders" in response.data
    assert response.data.count(b"data-year-folder=") == 5


def test_student_portfolio_page_stays_in_the_shared_student_experience():
    client = ui_app().test_client()
    client.post(
        "/login",
        data={"username": "ui-student", "password": "test-password"},
    )

    response = client.get("/student/portfolio")

    assert response.status_code == 200
    assert b'data-page="student-portfolio"' in response.data
    assert b"/static/css/design-system.css" in response.data
