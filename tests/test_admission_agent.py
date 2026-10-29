"""招生資料 Agent：第二階段偵測官方來源更新、第三階段擷取加權成候選版本。"""
import io

import pytest

from app import create_app
from app.extensions import db
from app.models import AdmissionProgram, AgentTask, PublicSource, PublicSourceChange, User
from app.services import admission_agent_service as agent
from app.services.admission_service import import_seed_programs

EXTRACTED = {"programs": [
    {"program_code": "208003", "admission_year": 116, "school_name": "國立臺北商業大學", "department_name": "資訊管理系",
     "admission_category": "管理類四", "items": [
         {"name": "歷年成績", "weight": 30, "categories": ["grades"]},
         {"name": "專題實作", "weight": 70, "categories": ["project", "不存在的類別"]},
     ]},
    {"program_code": "301001", "admission_year": 116, "school_name": "某科大", "department_name": "機械工程系",
     "admission_category": "工程類", "items": [{"name": "歷年成績", "weight": 100, "categories": ["grades"]}]},
]}


@pytest.fixture()
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "UPLOAD_FOLDER": str(tmp_path), "AGENT_SOURCE_FOLDER": str(tmp_path / "agent")})
    with app.app_context():
        db.create_all()
        import_seed_programs()
        for username, role in (("admin", "admin"), ("stu", "student")):
            user = User(username=username, display_name=username, role=role)
            user.set_password("pw")
            db.session.add(user)
        db.session.commit()
    yield app


def admin(app):
    with app.app_context():
        return User.query.filter_by(username="admin").one()


def login(app, username):
    client = app.test_client()
    client.post("/login", data={"username": username, "password": "pw"})
    return client


def make_source(app):
    with app.app_context():
        source = agent.add_source("技專校院招生委員會", url="https://example.edu.tw/brochure.pdf")
        return source.id


def fake_fetch(content):
    return lambda url: (content, "application/pdf")


def test_only_http_urls_are_allowed(app):
    with app.app_context():
        for url in ("file:///etc/passwd", "ftp://x/y", "javascript:alert(1)"):
            with pytest.raises(ValueError):
                agent.add_source("壞的", url=url)


def test_first_check_records_change_then_same_content_does_not(app):
    source_id = make_source(app)
    with app.app_context():
        source = db.session.get(PublicSource, source_id)
        first = agent.check_source(source, admin(app), fetch=fake_fetch(b"%PDF v1"))
        second = agent.check_source(source, admin(app), fetch=fake_fetch(b"%PDF v1"))

        assert first.status == "succeeded" and first.result_json["changed"] is True
        assert second.result_json["changed"] is False
        assert PublicSourceChange.query.count() == 1


def test_new_content_creates_a_change(app):
    source_id = make_source(app)
    with app.app_context():
        source = db.session.get(PublicSource, source_id)
        agent.check_source(source, admin(app), fetch=fake_fetch(b"%PDF v1"))
        task = agent.check_source(source, admin(app), fetch=fake_fetch(b"%PDF v2"))

        assert task.result_json["changed"] is True
        assert PublicSourceChange.query.order_by(PublicSourceChange.id.desc()).first().change_type == "changed"


def test_fetch_failure_is_recorded_not_raised(app):
    source_id = make_source(app)

    def broken(url):
        raise OSError("timeout")

    with app.app_context():
        task = agent.check_source(db.session.get(PublicSource, source_id), admin(app), fetch=broken)

        assert task.status == "failed"
        assert AgentTask.query.count() == 1


def test_extract_creates_candidates_for_keyword_programs_only(app):
    source_id = make_source(app)
    with app.app_context():
        source = db.session.get(PublicSource, source_id)
        agent.check_source(source, admin(app), fetch=fake_fetch(b"%PDF v1"))
        change = PublicSourceChange.query.one()
        task = agent.extract_programs(change, admin(app), generate=lambda prompt, schema, files: EXTRACTED)

        candidates = AdmissionProgram.query.filter_by(data_origin="agent").all()
        assert task.status == "succeeded"
        assert [p.program_code for p in candidates] == ["208003"]
        program = candidates[0]
        assert program.status == "candidate" and program.admission_year == 116
        assert program.items[1].category_keys == ["project"]
        assert all(item.mapping_status == "pending" for item in program.items)
        assert change.status == "extracted"


def test_extract_twice_does_not_duplicate(app):
    source_id = make_source(app)
    with app.app_context():
        agent.check_source(db.session.get(PublicSource, source_id), admin(app), fetch=fake_fetch(b"%PDF v1"))
        change = PublicSourceChange.query.one()
        agent.extract_programs(change, admin(app), generate=lambda p, s, f: EXTRACTED)
        agent.extract_programs(change, admin(app), generate=lambda p, s, f: EXTRACTED)

        assert AdmissionProgram.query.filter_by(data_origin="agent").count() == 1


def test_diff_against_previous_published_version(app):
    source_id = make_source(app)
    with app.app_context():
        agent.check_source(db.session.get(PublicSource, source_id), admin(app), fetch=fake_fetch(b"%PDF v1"))
        agent.extract_programs(PublicSourceChange.query.one(), admin(app), generate=lambda p, s, f: EXTRACTED)
        candidate = AdmissionProgram.query.filter_by(data_origin="agent").one()

        diff = agent.compare_with_published(candidate)

        assert diff["previous"].admission_year == 115
        assert any(row["name"] == "專題實作" and row["old"] is None for row in diff["rows"])


def test_extract_without_api_key_gives_chinese_message(app):
    source_id = make_source(app)
    with app.app_context():
        agent.check_source(db.session.get(PublicSource, source_id), admin(app), fetch=fake_fetch(b"%PDF v1"))
        task = agent.extract_programs(PublicSourceChange.query.one(), admin(app))

        assert task.status == "failed"
        assert "沒有開啟" in task.error_message


def test_admin_page_and_upload_source(app):
    client = login(app, "admin")

    response = client.post("/admin/agent/sources", data={
        "name": "116 簡章（手動上傳）", "file": (io.BytesIO(b"%PDF upload"), "brochure.pdf"),
    }, content_type="multipart/form-data")
    page = client.get("/admin/agent").get_data(as_text=True)

    assert response.status_code == 302
    assert "116 簡章（手動上傳）" in page
    with app.app_context():
        assert PublicSourceChange.query.count() == 1


def test_students_cannot_open_agent_page(app):
    assert login(app, "stu").get("/admin/agent").status_code in (302, 403)


def test_students_see_only_newest_year_after_approval(app):
    from app.services.admission_service import published_programs
    source_id = make_source(app)
    with app.app_context():
        agent.check_source(db.session.get(PublicSource, source_id), admin(app), fetch=fake_fetch(b"%PDF v1"))
        agent.extract_programs(PublicSourceChange.query.one(), admin(app), generate=lambda p, s, f: EXTRACTED)
        candidate = AdmissionProgram.query.filter_by(data_origin="agent").one()
        candidate.status = "published"
        db.session.commit()

        years = [p.admission_year for p in published_programs() if p.program_code == "208003"]

        assert years == [116]
