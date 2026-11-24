"""資管科小助手：依學校文件回答的內容都要附學生點得到的原檔連結（使用者 2026-11-17 要求）。

- 有學校網址的文件連到學校網站；科辦給的 PDF（school/Documents/）沒有公開網址，連到系統裡的原檔（要登入）。
- 新增「五年規劃」「實習申請與實習履歷」兩份科上文件：問專四要做什麼、實習履歷怎麼填，找得到答案和出處。
- 測試不連真的 AI：沒有金鑰時小助手走「原文節錄＋出處」的備援。
"""
import pytest

from app import create_app
from app.extensions import db
from app.models import User
from app.services import assistant_service
from app.services.knowledge_service import _chunks, school_doc_files, search


@pytest.fixture()
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        student = User(username="stu", display_name="測試生", role="student")
        student.set_password("pw")
        db.session.add(student)
        db.session.commit()
    yield app


def test_every_department_document_has_a_link_students_can_open():
    missing = sorted({chunk["title"] for chunk in _chunks() if not chunk["url"]})
    assert missing == []
    for chunk in _chunks():
        assert chunk["url"].startswith(("https://", "/school-docs/")), chunk["title"]


def test_documents_without_a_school_website_link_to_the_original_pdf(app):
    results = search("畢業門檻要幾張證照")
    graduation = next(r for r in results if "畢業門檻" in r["title"])
    assert graduation["url"].startswith("/school-docs/")
    assert "113-康寧資管科畢業門檻.pdf" in school_doc_files()

    client = app.test_client()
    assert client.get(graduation["url"]).status_code in (302, 401)  # 沒登入看不到
    client.post("/login", data={"username": "stu", "password": "pw"})
    response = client.get(graduation["url"])
    assert response.status_code == 200 and response.mimetype == "application/pdf"
    assert response.data[:4] == b"%PDF"
    # 只開知識庫列出的檔案，不能拿來讀別的東西
    assert client.get("/school-docs/..%2F..%2F.env").status_code == 404
    assert client.get("/school-docs/not-listed.pdf").status_code == 404


@pytest.mark.parametrize("question, title, url, must_have", [
    ("專四要做什麼？", "資管科五年規劃", "https://im.ukn.edu.tw/p/405-1028-609,c82-1.php", "實習"),
    ("專一要修哪些課？", "資管科五年規劃", "https://im.ukn.edu.tw/p/405-1028-609,c82-1.php", "程式設計"),
    ("實習履歷的專業科目怎麼填？", "資管科實習申請與實習履歷", "https://im.ukn.edu.tw/p/412-1028-1193.php?Lang=zh-tw", "及格"),
    ("實習自傳要寫幾頁？", "資管科實習申請與實習履歷", "https://im.ukn.edu.tw/p/412-1028-1193.php?Lang=zh-tw", "一頁"),
])
def test_offline_assistant_answers_school_plan_questions_with_a_source(app, question, title, url, must_have):
    answer, sources = assistant_service.offline_answer(question, "學校的 AI 目前沒有開啟")
    assert must_have in answer
    assert any(source["title"].startswith(title) and source["url"] == url for source in sources)
