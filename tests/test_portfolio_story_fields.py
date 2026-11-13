"""經歷多四個欄位：我負責的部分、數字成果、學到什麼、相關領域（設計書 D-1）。

各校備審指引一再要求「團體作品寫個人貢獻」「說明成果與反思」；使用者的範例自傳也靠這些細節撐起來。
"""
from datetime import date

import pytest
from sqlalchemy import inspect

from app import create_app
from app.extensions import db
from app.models import AdmissionProgram, Portfolio, StudentProfile, User
from app.services.admission_service import import_seed_programs
from app.services.autobiography_service import build_facts
from app.services.journey_service import academic_year_of

FIELDS = {
    "role": "負責後端 API 與資料庫設計（僅為測試資料）",
    "achievement": "三人一組、兩週完成，報名人數 120 人",
    "learned": "需求要先跟使用者確認，再動手寫",
    "domain_tags": "系統開發, 資料庫、 活動規劃",
}


@pytest.fixture()
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        import_seed_programs()
        user = User(username="stu", display_name="測試學生（僅為測試資料）", role="student")
        user.set_password("pw")
        db.session.add(user)
        db.session.flush()
        db.session.add(StudentProfile(user_id=user.id, student_no="TEST-0002", class_name="資管科五甲",
                                      admission_year=academic_year_of(date.today()) - 4))
        db.session.commit()
    yield app


def login(app):
    client = app.test_client()
    client.post("/login", data={"username": "stu", "password": "pw"})
    return client


def test_new_record_saves_story_fields_and_normalizes_tags(app):
    client = login(app)
    response = client.post("/student/portfolio", data={"category": "competition", "title": "校園黑客松",
                                                      "school_year": "3", "confirm": "1", **FIELDS})
    assert response.status_code == 302
    with app.app_context():
        record = Portfolio.query.one()
        assert record.role == FIELDS["role"] and record.achievement == FIELDS["achievement"]
        assert record.learned == FIELDS["learned"]
        assert record.domain_tags == "系統開發、資料庫、活動規劃"


def test_form_asks_the_four_guiding_questions(app):
    html = login(app).get("/student/portfolio/new").get_data(as_text=True)
    for name in ("role", "achievement", "learned", "domain_tags"):
        assert f'name="{name}"' in html
    assert "我負責的部分" in html and "數字成果" in html


def test_edit_keeps_story_fields(app):
    client = login(app)
    client.post("/student/portfolio", data={"category": "activity", "title": "資訊週", **FIELDS})
    with app.app_context():
        record_id = Portfolio.query.one().id
    html = client.get(f"/student/portfolio/{record_id}/edit").get_data(as_text=True)
    assert FIELDS["achievement"] in html
    client.post(f"/student/portfolio/{record_id}/edit", data={"category": "activity", "title": "資訊週",
                                                            **dict(FIELDS, learned="")})
    with app.app_context():
        record = db.session.get(Portfolio, record_id)
        assert record.learned is None and record.role == FIELDS["role"]


def test_facts_for_autobiography_include_story_fields(app):
    with app.app_context():
        user = User.query.filter_by(username="stu").one()
        db.session.add(Portfolio(student_id=user.id, title="校園黑客松", category="competition", status="confirmed",
                                 role=FIELDS["role"], achievement=FIELDS["achievement"], learned=FIELDS["learned"],
                                 domain_tags="系統開發、資料庫"))
        db.session.commit()
        program = AdmissionProgram.query.filter_by(program_code="208003").one()
        text = next(f["text"] for f in build_facts(user, program)["items"] if "校園黑客松" in f["text"])
    assert "我負責：" + FIELDS["role"] in text
    assert "成果：" + FIELDS["achievement"] in text and "學到：" in text and "領域：系統開發、資料庫" in text


def test_overlong_story_fields_are_rejected_with_a_message(app):
    client = login(app)
    response = client.post("/student/portfolio", data={"category": "activity", "title": "太長",
                                                      "achievement": "字" * 301})
    assert response.status_code == 400
    assert "數字成果最多 300 字" in response.get_data(as_text=True)


def test_migration_adds_story_columns(tmp_path):
    import sqlite3

    path = (tmp_path / "m.db").as_posix()
    connection = sqlite3.connect(path)
    connection.execute("create table portfolios (id integer primary key, title varchar(150))")
    connection.commit()
    connection.close()
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{path}", "TESTING": True})
    runner = app.test_cli_runner()
    assert runner.invoke(args=["db", "stamp", "b20261102e01"]).exit_code == 0
    assert runner.invoke(args=["db", "upgrade"]).exit_code == 0
    with app.app_context():
        columns = {c["name"] for c in inspect(db.engine).get_columns("portfolios")}
        tables = set(inspect(db.engine).get_table_names())
    assert {"role", "achievement", "learned"} <= columns
    # 相關領域 2026-11-13 正規化後改存獨立資料表（一個領域一列）
    assert "domain_tags" not in columns and "portfolio_domain_tags" in tables
