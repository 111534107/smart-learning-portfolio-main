"""修業科目表代理（11-09）：抓網頁 → 解析 PDF → 檢查 → 候選版本 → 管理員確認才生效。全部用假的下載函式，不連網路。"""
from pathlib import Path

import pytest
from sqlalchemy import inspect

from app import create_app
from app.extensions import db
from app.models import AuditLog, CurriculumVersion, User
from app.services import curriculum_agent_service as agent
from app.services import curriculum_parser

FIXTURES = Path(__file__).parent / "fixtures" / "curriculum"
INDEX = agent.INDEX_URL
PDF_URLS = {
    110: "https://im.ukn.edu.tw/var/file/28/1028/img/519/781166206.pdf",
    111: "https://im.ukn.edu.tw/var/file/28/1028/img/519/369604849.pdf",
    114: "https://im.ukn.edu.tw/var/file/28/1028/img/519/800645289.pdf",
}


def fake_fetch(url):
    if url == INDEX:
        return (FIXTURES / "index.html").read_bytes(), "text/html"
    for year, pdf_url in PDF_URLS.items():
        if url == pdf_url:
            return (FIXTURES / f"{year}.pdf").read_bytes(), "application/pdf"
    raise AssertionError(f"不該下載 {url}")


@pytest.fixture()
def app():
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "WTF_CSRF_ENABLED": False, "CURRICULUM_FETCH": fake_fetch})
    with app.app_context():
        db.create_all()
        for username, role in (("adm", "admin"), ("stf", "staff"), ("stu", "student")):
            user = User(username=username, display_name=username, role=role)
            user.set_password("pw")
            db.session.add(user)
        db.session.commit()
        yield app


def admin():
    return User.query.filter_by(username="adm").one()


def run(years=(110, 111, 114)):
    return agent.check_updates(admin(), fetch=fake_fetch, years=years)


def test_check_creates_candidates_that_students_do_not_use_yet(app):
    result = run()
    assert sorted(result["created"]) == [110, 111, 114]
    versions = CurriculumVersion.query.order_by(CurriculumVersion.admission_year).all()
    assert [v.status for v in versions] == ["candidate"] * 3
    assert versions[2].required_credits == 181 and versions[2].checks_ok
    assert len(versions[2].courses) == 105
    # 還沒確認：畢業門檻不用 114 的規則
    assert agent.credit_rule(114) is None
    assert AuditLog.query.filter_by(action="curriculum.check").count() == 1


def test_second_check_with_same_files_creates_nothing(app):
    run()
    assert run() == {"created": [], "unchanged": [110, 111, 114], "failed": [], "errors": []}
    assert CurriculumVersion.query.count() == 3


def test_diff_compares_with_hand_checked_csv_for_same_year(app):
    run(years=(111,))
    version = CurriculumVersion.query.one()
    assert version.diff_json == {"added": [], "removed": [], "changed": []}
    assert "新增 0 門、刪除 0 門" in version.summary


def test_year_without_csv_compares_with_nearest_earlier_year(app):
    run(years=(114,))
    version = CurriculumVersion.query.one()
    assert "113 學年度科目表" in version.summary and version.diff_json is not None


def test_numbers_that_do_not_add_up_become_check_failed(app, monkeypatch):
    original = curriculum_parser.parse_pdf

    def broken(content):
        result = original(content)
        result["courses"][0]["credits"] += 5
        return result

    monkeypatch.setattr(curriculum_parser, "parse_pdf", broken)
    result = run(years=(114,))
    version = CurriculumVersion.query.one()
    assert result["failed"] == [114] and version.status == "check_failed" and not version.checks_ok
    with pytest.raises(agent.CurriculumError):
        agent.publish(version, admin())


def test_publish_makes_graduation_check_use_the_new_rules(app):
    from app.services import graduation_check_service as check
    run(years=(114,))
    version = CurriculumVersion.query.one()
    agent.publish(version, admin())
    db.session.commit()
    assert version.status == "published" and version.reviewed_by_id == admin().id
    assert agent.credit_rule(114) == {"total": 220, "required": 181, "elective": 39,
                                      "source": "114 學年度入學五專修業科目表（管理員確認版）",
                                      "source_url": PDF_URLS[114]}
    assert check.credit_rule(114)["required"] == 181
    table = check.load_curriculum()[114]
    assert table[check.normalize_course_name("生成式人工智慧之應用")]["category"] == "專業必修"
    # CSV 的 111、113 仍在
    assert 111 in check.load_curriculum() and 113 in check.load_curriculum()


def test_new_publish_supersedes_old_one_and_reject_works(app, monkeypatch):
    run(years=(114,))
    first = CurriculumVersion.query.one()
    agent.publish(first, admin())
    db.session.commit()
    # 網站換了新檔：內容一樣但雜湊不同時也會產生新候選
    original = agent._sha256
    monkeypatch.setattr(agent, "_sha256", lambda content: "x" * 64)
    run(years=(114,))
    monkeypatch.setattr(agent, "_sha256", original)
    second = CurriculumVersion.query.filter_by(status="candidate").one()
    agent.publish(second, admin())
    db.session.commit()
    assert db.session.get(CurriculumVersion, first.id).status == "superseded"
    run_again = CurriculumVersion(admission_year=113, status="candidate", source_url="u", file_sha256="y" * 64)
    db.session.add(run_again)
    db.session.flush()
    agent.reject(run_again, admin())
    assert run_again.status == "rejected"


def test_admin_page_and_buttons(app):
    client = app.test_client()
    client.post("/login", data={"username": "adm", "password": "pw"})
    page = client.get("/admin/curriculum").get_data(as_text=True)
    assert "修業科目表" in page and "檢查網站更新" in page
    assert client.post("/admin/curriculum/check").status_code == 302
    page = client.get("/admin/curriculum").get_data(as_text=True)
    assert "114" in page and "待確認" in page and "各區段學分加總等於小計" in page
    version = CurriculumVersion.query.filter_by(admission_year=114).one()
    assert client.post(f"/admin/curriculum/{version.id}/publish").status_code == 302
    assert db.session.get(CurriculumVersion, version.id).status == "published"


def test_only_admin_can_open_curriculum_pages(app):
    for username in ("stf", "stu"):
        client = app.test_client()
        client.post("/login", data={"username": username, "password": "pw"})
        assert client.get("/admin/curriculum").status_code in (302, 403)
        assert client.post("/admin/curriculum/check").status_code in (302, 403)
    assert CurriculumVersion.query.count() == 0


def test_admin_todo_counts_candidates(app):
    from app.services.admin_todos import admin_todos
    run(years=(114,))
    with app.test_request_context():
        todo = next(item for item in admin_todos() if item["key"] == "curriculum")
    assert todo["count"] == 1 and todo["href"].endswith("/admin/curriculum")


def test_migration_creates_curriculum_tables(tmp_path):
    migrated = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'c.db'}", "TESTING": True})
    runner = migrated.test_cli_runner()
    assert runner.invoke(args=["db", "upgrade"]).exit_code == 0
    with migrated.app_context():
        assert {"curriculum_versions", "curriculum_courses"} <= set(inspect(db.engine).get_table_names())
    assert runner.invoke(args=["db", "downgrade", "b20261108f01"]).exit_code == 0
    with migrated.app_context():
        assert not inspect(db.engine).has_table("curriculum_versions")
