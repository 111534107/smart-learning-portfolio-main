"""升學 Agent 依檔案編號取檔：只能拿自己的檔案、只回需要的欄位、送 AI 前去識別化；AI 不直接碰 Drive。

帳號、學號、證號都是合成資料。
"""
import pytest

from app import create_app
from app.extensions import db
from app.models import DocumentExtraction, SourceDocument, StudentProfile, User
from app.services import agent_file_tool, deidentify
from app.services.agent_engine import Tool, ToolError

FAKE_NAME = "林合成"
FAKE_NO = "199000123"
FAKE_ID = "A123456789"


@pytest.fixture()
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        owner = User(username="syn_owner", display_name=FAKE_NAME, role="student", email="syn.owner@example.test")
        other = User(username="syn_other", display_name="陳合成", role="student")
        for user in (owner, other):
            user.set_password("pw")
            db.session.add(user)
        db.session.flush()
        db.session.add(StudentProfile(user_id=owner.id, student_no=FAKE_NO, admission_year=113))
        transcript = SourceDocument(owner_id=owner.id, document_type="transcript",
                                    display_name=f"{FAKE_NAME}_{FAKE_NO}_成績單.png",
                                    file_path="drive:file9/abc_成績單.png", sha256="0" * 64, status="confirmed")
        credential = SourceDocument(owner_id=owner.id, document_type="credential", display_name="證照.png",
                                    file_path=str(tmp_path / "x.png"), sha256="1" * 64, status="extracted")
        pending = SourceDocument(owner_id=owner.id, document_type="transcript", display_name="p.png",
                                 file_path=str(tmp_path / "p.png"), sha256="2" * 64, status="queued")
        db.session.add_all([transcript, credential, pending])
        db.session.flush()
        db.session.add(DocumentExtraction(source_document_id=transcript.id, provider="fake", status="confirmed",
                                          result_json={
                                              "courses": [{"school_year": 113, "semester": "一", "course_name": "程式設計",
                                                           "credits": 3, "score": 92, "source_bbox": [1, 2, 3, 4]}],
                                              "raw_text": f"{FAKE_NAME} {FAKE_NO} 程式設計 3 92",
                                              "source": {"file_name": "abc_成績單.png"}}))
        db.session.add(DocumentExtraction(source_document_id=credential.id, provider="fake", status="extracted",
                                          result_json={"credentials": [{
                                              "credential_name": "電腦軟體應用", "level": "丙級",
                                              "issuing_organization": "測試機構",
                                              "certificate_no": FAKE_ID, "holder_name": FAKE_NAME}]}))
        db.session.commit()
    return app


def tools_for(username):
    student = User.query.filter_by(username=username).one()
    return student, {tool.name: tool for tool in agent_file_tool.document_tools(student)}


def test_tools_are_read_only_agent_tools(app):
    with app.app_context():
        _, tools = tools_for("syn_owner")
        assert set(tools) == {"list_my_documents", "get_my_document"}
        assert all(isinstance(tool, Tool) for tool in tools.values())
        assert tools["get_my_document"].params == {"document_id": tools["get_my_document"].params["document_id"]}


def test_owner_gets_only_needed_fields(app):
    with app.app_context():
        _, tools = tools_for("syn_owner")
        document = SourceDocument.query.filter_by(document_type="transcript", status="confirmed").one()

        result = tools["get_my_document"].run(document_id=str(document.id))

        assert result["document_id"] == str(document.id)
        assert result["document_type"] == "transcript"
        assert result["status"] == "confirmed"
        assert result["courses"] == [{"school_year": 113, "semester": "一", "course_name": "程式設計",
                                      "credits": 3, "score": 92}]
        assert "summary" in result
        text = repr(result)
        # 不回原始檔、檔案位置、OCR 原文與座標
        for forbidden in ("drive:", "file9", "raw_text", "source_bbox", "file_path", "成績單.png"):
            assert forbidden not in text


def test_result_is_deidentified(app):
    with app.app_context():
        _, tools = tools_for("syn_owner")
        document = SourceDocument.query.filter_by(document_type="credential").one()
        document.status = "confirmed"  # 未確認的檔案不回內容，去識別化要用確認後的檔案測

        result = tools["get_my_document"].run(document_id=str(document.id))

        text = repr(result)
        assert FAKE_NAME not in text and FAKE_NO not in text and FAKE_ID not in text
        assert result["credentials"][0]["credential_name"] == "電腦軟體應用"
        assert result["credentials"][0]["level"] == "丙級"


def test_other_student_and_missing_document_get_same_refusal(app):
    with app.app_context():
        document = SourceDocument.query.filter_by(document_type="transcript", status="confirmed").one()
        _, other_tools = tools_for("syn_other")

        with pytest.raises(ToolError) as denied:
            other_tools["get_my_document"].run(document_id=str(document.id))
        with pytest.raises(ToolError) as missing:
            other_tools["get_my_document"].run(document_id="99999")
        assert str(denied.value) == str(missing.value)  # 不透露別人的檔案存不存在

        with pytest.raises(ToolError):
            other_tools["get_my_document"].run(document_id="abc")


def test_pending_document_is_not_returned_yet(app):
    with app.app_context():
        _, tools = tools_for("syn_owner")
        document = SourceDocument.query.filter_by(status="queued").one()
        with pytest.raises(ToolError) as error:
            tools["get_my_document"].run(document_id=str(document.id))
        assert "辨識" in str(error.value)


def test_get_document_never_reads_storage(app, monkeypatch):
    """AI 不直接瀏覽 Drive，也不拿原始檔：這個工具只讀系統資料庫裡確認流程的欄位。"""
    from app.services import storage_service

    def boom(*args, **kwargs):
        raise AssertionError("不應該讀原始檔")

    for name in ("read_bytes", "local_path", "local_path_or_none", "exists"):
        monkeypatch.setattr(storage_service, name, boom)
    with app.app_context():
        _, tools = tools_for("syn_owner")
        document = SourceDocument.query.filter_by(document_type="transcript", status="confirmed").one()
        assert tools["get_my_document"].run(document_id=str(document.id))["courses"]


def test_list_my_documents_only_lists_own_without_file_names(app):
    with app.app_context():
        _, tools = tools_for("syn_owner")
        result = tools["list_my_documents"].run()
        assert len(result["documents"]) == 3
        assert {item["document_type"] for item in result["documents"]} == {"transcript", "credential"}
        text = repr(result)
        assert FAKE_NAME not in text and FAKE_NO not in text and "drive:" not in text and ".png" not in text

        _, other_tools = tools_for("syn_other")
        assert other_tools["list_my_documents"].run()["documents"] == []


def test_advisor_has_document_tools():
    from app.services import agent_advisor

    names = {tool.name for tool in agent_advisor._tools(object(), generate=None)}
    assert {"list_my_documents", "get_my_document"} <= names


# ---------- 去識別化 ----------

def test_redact_known_values_and_patterns():
    known = deidentify.known_values(display_name=FAKE_NAME, student_no=FAKE_NO, username="syn_owner",
                                    email="syn.owner@example.test")
    text = (f"{FAKE_NAME}（{FAKE_NO}）證號 {FAKE_ID}、居留證 AB12345678，電話 0912-345-678，"
            "信箱 someone@example.test，帳號 syn_owner，成績 92 分，113 學年")
    redacted = deidentify.redact(text, known)

    for value in (FAKE_NAME, FAKE_NO, FAKE_ID, "AB12345678", "0912-345-678", "someone@example.test", "syn_owner"):
        assert value not in redacted
    assert "[姓名]" in redacted and "[學號]" in redacted and "[證號]" in redacted
    assert "92 分" in redacted and "113 學年" in redacted  # 一般數字不能被誤刪


def test_redact_walks_nested_structures_and_keeps_numbers():
    known = deidentify.known_values(display_name=FAKE_NAME)
    data = {"a": [f"{FAKE_NAME}的作品", {"b": FAKE_NAME}], "n": 3, "none": None}
    assert deidentify.redact(data, known) == {"a": ["[姓名]的作品", {"b": "[姓名]"}], "n": 3, "none": None}


def test_single_character_name_is_not_used_as_pattern():
    known = deidentify.known_values(display_name="王")
    assert deidentify.redact("王牌程式", known) == "王牌程式"
