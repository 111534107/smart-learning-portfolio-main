from app.models import Portfolio
from app.services import package_exclusion


def test_project_category_is_recognized_without_keywords():
    record = Portfolio(title="學習系統", category="project", status="confirmed")
    assert "project" in package_exclusion.portfolio_keys(record)


def test_project_is_available_as_a_student_record_category():
    from app.services.journey_service import EXPERIENCE_CATEGORIES, CATEGORY_LABELS
    assert "project" in EXPERIENCE_CATEGORIES
    assert CATEGORY_LABELS["project"] == "專題與作品集"


def test_safe_reader_rejects_private_and_unsupported_hosts(monkeypatch):
    import socket
    import pytest
    from app.services.project_link_reader import fetch, ReadError
    with pytest.raises(ReadError):
        fetch("http://127.0.0.1/")
    with pytest.raises(ReadError):
        fetch("https://github.com@127.0.0.1/")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))])
    with pytest.raises(ReadError, match="非公開"):
        fetch("https://github.com/example/repo")


def test_create_project_add_links_and_require_reconfirmation(tmp_path):
    from tests.test_student_portfolio import portfolio_app, login
    from app.extensions import db
    from app.models import PortfolioEvidence
    app = portfolio_app(tmp_path)
    client = app.test_client()
    login(client)
    response = client.post("/student/portfolio", data={"category": "project", "title": "學習系統", "school_year": "3", "confirm": "1"})
    assert response.status_code == 302
    with app.app_context():
        record = Portfolio.query.filter_by(title="學習系統").one()
        record_id = record.id
        assert record.status == "confirmed"
    for url in ("https://github.com/example/example", "https://www.canva.com/design/example"):
        assert client.post(f"/student/portfolio/{record_id}/evidence", data={"external_url": url}).status_code == 302
    with app.app_context():
        assert db.session.get(Portfolio, record_id).status == "draft"
        assert PortfolioEvidence.query.filter_by(portfolio_id=record_id).count() == 2
    edit_page = client.get(f"/student/portfolio/{record_id}/edit").get_data(as_text=True)
    assert "https://github.com/example/example" in edit_page
    with app.app_context():
        link_ids = [item.id for item in PortfolioEvidence.query.filter_by(portfolio_id=record_id).order_by(PortfolioEvidence.id)]
    # 連結不放進檔案格子（沒有檢視、下載），只在作品連結區給「移除連結」
    for link_id in link_ids:
        assert f"/student/evidence/{link_id}/delete" in edit_page
        assert f"/student/evidence/{link_id}/view" not in edit_page
        assert f'/student/evidence/{link_id}"' not in edit_page  # 下載網址
    assert client.get(f"/student/portfolio/{record_id}/analyze").status_code == 200
    assert client.post(f"/student/portfolio/{record_id}/confirm").status_code == 302
    with app.app_context():
        assert db.session.get(Portfolio, record_id).status == "confirmed"


def test_student_can_remove_wrong_project_link(tmp_path):
    from tests.test_student_portfolio import portfolio_app, login
    from app.extensions import db
    from app.models import AuditLog, PortfolioEvidence
    app = portfolio_app(tmp_path)
    client = app.test_client()
    login(client)
    client.post("/student/portfolio", data={"category": "project", "title": "貼錯網址的作品", "school_year": "3", "confirm": "1"})
    with app.app_context():
        record_id = Portfolio.query.filter_by(title="貼錯網址的作品").one().id
    client.post(f"/student/portfolio/{record_id}/evidence", data={"external_url": "https://github.com/wrong/repo", "link_name": "貼錯的"})
    client.post(f"/student/portfolio/{record_id}/evidence", data={"external_url": "https://github.com/right/repo", "link_name": "正確的"})
    client.post(f"/student/portfolio/{record_id}/confirm")
    with app.app_context():
        wrong = PortfolioEvidence.query.filter_by(portfolio_id=record_id, external_url="https://github.com/wrong/repo").one()
        wrong_id = wrong.id
        assert db.session.get(Portfolio, record_id).status == "confirmed"

    response = client.post(f"/student/evidence/{wrong_id}/delete")
    assert response.status_code == 302
    assert "project-links-title" in response.headers["Location"]
    with app.app_context():
        assert db.session.get(PortfolioEvidence, wrong_id).deleted_at is not None  # 只標記，資料列保留
        assert db.session.get(Portfolio, record_id).status == "draft"
        assert AuditLog.query.filter_by(action="evidence.delete", target_id=wrong_id).count() == 1
    page = client.get(f"/student/portfolio/{record_id}/edit").get_data(as_text=True)
    assert "https://github.com/wrong/repo" not in page
    assert "https://github.com/right/repo" in page
    analyze = client.get(f"/student/portfolio/{record_id}/analyze").get_data(as_text=True)
    assert "https://github.com/wrong/repo" not in analyze


def test_project_analysis_requires_owner_and_redacts_before_ai(tmp_path, monkeypatch):
    from tests.test_student_portfolio import portfolio_app, login
    from app.extensions import db
    from app.models import User, PortfolioEvidence
    from app.services import ai_gateway, project_link_reader
    app = portfolio_app(tmp_path)
    with app.app_context():
        student = User.query.filter_by(username="student").one()
        p = Portfolio(student_id=student.id, title="學習系統", category="project", status="confirmed")
        db.session.add(p); db.session.flush()
        e = PortfolioEvidence(portfolio_id=p.id, evidence_type="link", display_name="說明", external_url="https://github.com/example/repo")
        db.session.add(e); db.session.commit(); pid, eid = p.id, e.id
    monkeypatch.setattr(project_link_reader, "fetch", lambda url: "學生 111534199 開發一個能整理學習資料的系統。")
    def fake_ai(prompt, schema, **kwargs):
        assert "111534199" not in prompt
        return {"evidence": "不存在的引文", "summary": "整理資料", "uncertain": "技術尚不清楚"}, "fake"
    monkeypatch.setattr(ai_gateway, "generate_json", fake_ai)
    client = app.test_client(); login(client)
    r = client.post(f"/student/portfolio/{pid}/analyze", data={"evidence_id": eid})
    assert r.status_code == 200
    assert "無法核對模型提供的原文" in r.get_data(as_text=True)
    client.post("/logout"); login(client, "other")
    assert client.get(f"/student/portfolio/{pid}/analyze").status_code == 403


def test_project_readiness_counts_only_confirmed(tmp_path):
    from tests.test_student_portfolio import portfolio_app
    from app.extensions import db
    from app.models import User
    from app.services.gap_service import student_evidence
    app = portfolio_app(tmp_path)
    with app.app_context():
        student = User.query.filter_by(username="student").one()
        item = Portfolio(student_id=student.id, title="學習系統", category="project", status="draft")
        db.session.add(item); db.session.commit()
        assert student_evidence(student)["project_count"] == 0
        item.status = "confirmed"; db.session.commit()
        evidence = student_evidence(student)
        assert evidence["project_count"] == 1
        assert evidence["totals"]["activity"] == 0


def test_reader_refuses_redirects_and_oversized_pages(monkeypatch):
    import socket
    import pytest
    from app.services import project_link_reader as reader
    class FakeSocket:
        def sendall(self, value): pass
        def settimeout(self, value): pass
        def close(self): pass
    class Context:
        def wrap_socket(self, sock, server_hostname): return sock
    class Response:
        status = 302
        def __init__(self, sock): self.count = 0
        def begin(self): pass
        def getheader(self, name, default=""): return "text/html" if name == "Content-Type" else default
        def read1(self, size):
            self.count += 1
            return b"a" * size
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))])
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: FakeSocket())
    monkeypatch.setattr(reader.ssl, "create_default_context", lambda: Context())
    monkeypatch.setattr(reader.http.client, "HTTPResponse", Response)
    with pytest.raises(reader.ReadError, match="302"):
        reader.fetch("https://www.canva.com/design/example")
    Response.status = 200
    with pytest.raises(reader.ReadError, match="大小"):
        reader.fetch("https://www.canva.com/design/example")


def test_public_content_redacts_known_person_and_labeled_details():
    from app.services.project_link_reader import redact_public_text
    from app.services.deidentify import known_values
    text = "姓名：林小美\n聯絡人：王大明\n電話：0912345678\n學號：111534199\n地址：臺北市中正區和平路12號"
    result = redact_public_text(text, known_values(display_name="林小美", student_no="111534199"))
    for value in ("林小美", "王大明", "0912345678", "111534199", "臺北市中正區和平路12號"):
        assert value not in result


def test_teacher_sees_project_under_its_year():
    from tests.test_teacher_journey_map import teacher_journey_app
    from app.extensions import db
    app, student_id = teacher_journey_app()
    with app.app_context():
        db.session.add(Portfolio(student_id=student_id, title="學習系統", category="project", school_year=3,
                                 description="資料整理", status="confirmed"))
        db.session.commit()
    client = app.test_client()
    client.post("/login", data={"username": "journey-teacher", "password": "pw"})
    response = client.get(f"/teacher/students/{student_id}")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "學習系統" in html
    assert "專題與作品集" in html


def test_project_fit_includes_project_requirement(monkeypatch):
    from types import SimpleNamespace
    from app.services.activity_fit import _uses_by_category
    monkeypatch.setattr("app.services.activity_fit.channel_label", lambda program: "測試管道")
    program = SimpleNamespace(school_name="測試學校", department_name="資訊管理系", admission_category="二技")
    gap = {"items": [{"have": [], "missing": [], "documents": ["project"], "weight": 30, "name": "專業成果"}]}
    assert _uses_by_category([(program, gap)])["project"][0]["weight"] == 30
