from datetime import datetime, timedelta, timezone

import pytest

from app import create_app
from app.extensions import db
from app.models import LearningCourseRecord, StudentProfile, StudentTarget, User
from app.services.admission_service import import_seed_programs
from app.services.guide_service import MAX_CARDS, SNOOZE_HOURS, guide_cards


@pytest.fixture()
def app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "WTF_CSRF_ENABLED": False})
    with app.app_context():
        db.create_all()
        import_seed_programs()
        yield app


def make_student(grade_year_offset=0, username="s1"):
    """admission_year 讓學生落在指定年級（以今天算）。"""
    from app.services.journey_service import academic_year_of
    from datetime import date

    admission = academic_year_of(date.today()) - grade_year_offset
    user = User(username=username, display_name=username, role="student")
    user.set_password("pw")
    db.session.add(user)
    db.session.flush()
    db.session.add(StudentProfile(user_id=user.id, student_no=username, class_name="甲", admission_year=admission))
    db.session.commit()
    return user


def ids(cards):
    return [card["id"] for card in cards]


def test_first_year_student_sees_welcome_cards(app):
    with app.test_request_context():
        cards = guide_cards(make_student(0))

    assert ids(cards)[0] == "welcome"
    assert len(cards) <= MAX_CARDS


def test_never_more_than_three_cards(app):
    with app.test_request_context():
        for offset in range(5):
            assert len(guide_cards(make_student(offset, username=f"s{offset}"))) <= MAX_CARDS


def test_cards_are_short_and_have_one_button(app):
    with app.test_request_context():
        for offset in range(5):
            for card in guide_cards(make_student(offset, username=f"s{offset}")):
                assert len(card["text"]) <= 40, card
                assert card["button"] and card["href"]


def test_card_disappears_when_done(app):
    with app.test_request_context():
        user = make_student(0)
        assert "first-save" in ids(guide_cards(user))
        db.session.add(LearningCourseRecord(student_id=user.id, school_year=1, course_name="程式",
                                            normalized_course_name="程式", score=90))
        db.session.commit()
        assert "first-save" not in ids(guide_cards(user))


def test_target_card_disappears_after_choosing_target(app):
    from app.models import AdmissionProgram

    with app.test_request_context():
        user = make_student(0)
        assert "meet-schools" in ids(guide_cards(user))
        db.session.add(StudentTarget(student_id=user.id, rule_version_id=AdmissionProgram.query.first().id))
        db.session.commit()
        assert "meet-schools" not in ids(guide_cards(user))


def test_snoozed_card_hidden_until_time_passes(app):
    with app.test_request_context():
        user = make_student(0)
        now = datetime.now(timezone.utc)
        snoozed = {"welcome": (now - timedelta(hours=1)).isoformat()}
        assert "welcome" not in ids(guide_cards(user, snoozed=snoozed, now=now))
        later = now + timedelta(hours=SNOOZE_HOURS + 1)
        assert "welcome" in ids(guide_cards(user, snoozed=snoozed, now=later))


def test_fifth_year_student_gets_apply_cards(app):
    with app.test_request_context():
        cards = guide_cards(make_student(4))

    assert "target-five" in ids(cards) or "grad-next" in ids(cards)


def test_dashboard_shows_cards_and_snooze_hides_one(app):
    client = app.test_client()
    with app.app_context():
        make_student(0, username="stu")
    client.post("/login", data={"username": "stu", "password": "pw"})

    page = client.get("/student/dashboard").get_data(as_text=True)
    assert 'data-guide-card="welcome"' in page

    response = client.post("/student/guide/snooze", data={"card": "welcome"})
    assert response.status_code in (200, 204, 302)
    page = client.get("/student/dashboard").get_data(as_text=True)
    assert 'data-guide-card="welcome"' not in page


def test_snooze_rejects_unknown_card(app):
    client = app.test_client()
    with app.app_context():
        make_student(0, username="stu")
    client.post("/login", data={"username": "stu", "password": "pw"})

    assert client.post("/student/guide/snooze", data={"card": "../x"}).status_code == 400


def test_snooze_requires_student(app):
    assert app.test_client().post("/student/guide/snooze", data={"card": "welcome"}).status_code == 401
