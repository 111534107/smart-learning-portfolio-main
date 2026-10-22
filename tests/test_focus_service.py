from datetime import date
from pathlib import Path

import pytest

from app import create_app
from app.extensions import db
from app.models import AdmissionProgram, CredentialRecord, StudentProfile, StudentTarget, User
from app.services.admission_service import import_seed_programs
from app.services.focus_service import FOCUS_MIN_TARGETS, focus_view
from app.services.journey_service import academic_year_of

NATIONAL = Path(__file__).resolve().parents[1] / "app" / "content" / "admission_demo_national_116.csv"


@pytest.fixture()
def app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True})
    with app.app_context():
        db.create_all()
        import_seed_programs()
        import_seed_programs(NATIONAL)
        user = User(username="stu", display_name="stu", role="student")
        user.set_password("pw")
        db.session.add(user)
        db.session.flush()
        db.session.add(StudentProfile(user_id=user.id, student_no="s1",
                                      admission_year=academic_year_of(date.today()) - 2))
        db.session.commit()
        yield app


def student():
    return User.query.filter_by(username="stu").one()


def choose(count):
    user = student()
    for program in AdmissionProgram.query.order_by(AdmissionProgram.id).limit(count):
        db.session.add(StudentTarget(student_id=user.id, rule_version_id=program.id))
    db.session.commit()
    return user


def test_no_focus_with_few_targets(app):
    with app.test_request_context():
        assert focus_view(choose(FOCUS_MIN_TARGETS - 1)) is None


def test_focus_picks_at_most_three_and_ranks_by_weight(app):
    with app.test_request_context():
        view = focus_view(choose(8))

    assert 1 <= len(view["top"]) <= 3
    scores = [item["score"] for item in view["top"]]
    assert scores == sorted(scores, reverse=True)
    assert len(view["pieces"]) > len(view["top"])  # 畫面先堆滿，再聚焦
    for item in view["top"]:
        assert item["href"] and item["label"]
        assert 1 <= item["schools"] <= 8


def test_focus_skips_categories_student_already_has(app):
    with app.test_request_context():
        user = choose(8)
        db.session.add(CredentialRecord(student_id=user.id, credential_name="網頁設計乙級"))
        db.session.commit()
        view = focus_view(user)

    assert "credential" not in [item["key"] for item in view["top"]]


def test_target_page_shows_focus_stage(app):
    client = app.test_client()
    with app.app_context():
        choose(6)
    client.post("/login", data={"username": "stu", "password": "pw"})

    page = client.get("/student/targets").get_data(as_text=True)

    assert "data-focus" in page
    assert page.count("data-focus-top") <= 3


def test_autobiography_counts_when_not_written(app):
    with app.test_request_context():
        view = focus_view(choose(8))

    keys = [item["key"] for item in view["top"]]
    assert "autobiography" in keys
    bio = next(item for item in view["top"] if item["key"] == "autobiography")
    assert "/student/autobiography" in bio["href"]
