"""升學 Agent 自己上網找官方招生來源（使用者 11-04：Agent 要能自行上網找資料，不是人工登記網址）。

搜尋用 Gemini 內建的 Google 搜尋；只收學校與政府網域，自動登記成來源後照原流程檢查與擷取。
擷取出的校系仍是候選，管理員核准後學生才看得到（AGENTS.md §8：AI 不得自行發布招生規則）。
測試一律用假的搜尋與假網路，不真的連線。
"""
import io
import json

import pytest

from app import create_app
from app.extensions import db
from app.models import AgentTask, PublicSource, User
from app.services import admission_agent_service as agent
from app.services import gemini_client
from app.services.gemini_client import AIUnavailable


@pytest.fixture()
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "UPLOAD_FOLDER": str(tmp_path), "AGENT_SOURCE_FOLDER": str(tmp_path / "agent"),
                      "AI_ENABLED": True, "AI_PROVIDER": "gemini", "AI_API_KEY": "test-key"})
    with app.app_context():
        db.create_all()
        db.session.add(User(username="admin", display_name="管理員（僅為測試資料）", role="admin", password_hash="x"))
        db.session.commit()
        yield app


def admin():
    return User.query.filter_by(username="admin").one()


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_search_web_uses_google_search_tool_and_returns_grounded_sources(app):
    sent = {}

    def opener(request, timeout):
        sent["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse(json.dumps({"candidates": [{
            "content": {"parts": [{"text": "找到 115 學年度二技技優甄審簡章。"}]},
            "groundingMetadata": {"groundingChunks": [
                {"web": {"uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc", "title": "jctv.ntut.edu.tw"}},
                {"web": {"uri": "https://example.com/blog", "title": "example.com"}},
            ]},
        }]}).encode("utf-8"))

    result = gemini_client.search_web("115 學年度 二技技優甄審 簡章", opener=opener)

    assert {"google_search": {}} in sent["body"]["tools"]
    assert "115 學年度 二技技優甄審 簡章" in sent["body"]["contents"][0]["parts"][0]["text"]
    assert result["text"].startswith("找到")
    assert result["sources"][0] == {"title": "jctv.ntut.edu.tw",
                                    "uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc"}


@pytest.mark.parametrize("url, ok", [
    ("https://www.jctv.ntut.edu.tw/enter/brochure.pdf", True),
    ("https://admis.ntub.edu.tw/p/403-1028-138.php", True),
    ("https://www.edu.gov.tw/News.aspx", True),
    ("https://edu.tw.example.com/fake.pdf", False),
    ("https://example.com/2tech-guide", False),
    ("ftp://jctv.ntut.edu.tw/file.pdf", False),
])
def test_only_school_and_government_domains_count_as_official(url, ok):
    assert agent.official_url(url) is ok


def test_discover_sources_adds_only_new_official_urls(app):
    db.session.add(PublicSource(name="既有來源", url="https://www.jctv.ntut.edu.tw/old.pdf", source_type="url"))
    db.session.commit()
    resolved = {
        "https://redirect/1": "https://www.jctv.ntut.edu.tw/enter/115-brochure.pdf",
        "https://redirect/2": "https://example.com/copied-brochure",
        "https://redirect/3": "https://www.jctv.ntut.edu.tw/old.pdf",
        "https://redirect/4": "https://www.jctv.ntut.edu.tw/enter/115-brochure.pdf",  # 重複的搜尋結果
    }

    def search(query):
        return {"text": "", "sources": [{"title": f"結果{n}", "uri": f"https://redirect/{n}"} for n in (1, 2, 3, 4)]}

    task = agent.discover_sources(admin(), queries=["二技 簡章"], search=search, resolve=resolved.get)

    assert task.status == "succeeded" and task.task_type == "admission_source_search"
    urls = [s.url for s in PublicSource.query.order_by(PublicSource.id)]
    assert urls == ["https://www.jctv.ntut.edu.tw/old.pdf", "https://www.jctv.ntut.edu.tw/enter/115-brochure.pdf"]
    added = PublicSource.query.filter_by(url="https://www.jctv.ntut.edu.tw/enter/115-brochure.pdf").one()
    assert added.name.startswith("Agent 找到：") and added.source_type == "url"
    assert task.result_json["added"] == ["https://www.jctv.ntut.edu.tw/enter/115-brochure.pdf"]
    # 已知 2 筆：原本就登記的 old.pdf、這次搜尋重複出現的 115-brochure.pdf
    assert task.result_json["skipped_unofficial"] == 1 and task.result_json["already_known"] == 2


def test_discover_sources_without_ai_records_failure_and_adds_nothing(app):
    def search(query):
        raise AIUnavailable("學校的 AI 目前沒有開啟。")

    task = agent.discover_sources(admin(), queries=["二技 簡章"], search=search, resolve=lambda uri: uri)

    assert task.status == "failed" and "AI" in task.error_message
    assert PublicSource.query.count() == 0


def test_default_queries_cover_brochures_and_writing_guides_for_this_and_next_year():
    queries = agent.default_search_queries(roc_year=115)
    text = " ".join(queries)
    assert "115" in text and "116" in text
    assert "技優甄審" in text and "申請入學" in text and "備審資料準備指引" in text
    assert all("資訊管理" in q or "資管" in q for q in queries if "指引" in q)


def test_patrol_searches_before_checking_sources(app):
    from app.services.agent_patrol import run_patrol

    def search(query):
        return {"text": "", "sources": [{"title": "簡章", "uri": "https://www.jctv.ntut.edu.tw/enter/116.pdf"}]}

    def fetch(url):
        return b"%PDF-1.4 brochure", "application/pdf"

    def generate(prompt, schema, **kwargs):
        return {"programs": []}

    result = run_patrol(admin(), decide=None, fetch=fetch, generate=generate, search=search, resolve=lambda uri: uri)

    tools = [step["tool"] for step in result["steps"]]
    assert tools[0] == "search_sources" and tools.index("search_sources") < tools.index("check_sources")
    assert PublicSource.query.filter_by(url="https://www.jctv.ntut.edu.tw/enter/116.pdf").count() == 1
    assert "找到" in result["summary"]


def test_admin_agent_page_lists_search_tasks(app):
    def search(query):
        return {"text": "", "sources": [{"title": "簡章", "uri": "https://www.jctv.ntut.edu.tw/enter/116.pdf"}]}

    agent.discover_sources(admin(), queries=["二技 簡章"], search=search, resolve=lambda uri: uri)
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = admin().id
    html = client.get("/admin/agent").get_data(as_text=True)
    assert "上網找來源" in html and "找到 1 個新的官方來源" in html
    assert "Agent 找到：簡章" in html
