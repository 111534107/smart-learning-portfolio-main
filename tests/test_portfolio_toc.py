"""備審 Word：客製目錄（每章列具體佐證、選放標示）、自傳與讀書計畫分章、自傳段落標題印出來。（僅為測試資料）"""
import io
import re

from docx import Document

from app.models import AdmissionProgram, User
from app.services import package_service
from tests.test_autobiography import ANSWERS, app, choose_target, login, program  # noqa: F401


def _text(app, with_draft=True):
    client = login(app)
    choose_target(app, client)
    if with_draft:
        client.post("/student/autobiography/generate", data={"program_id": program(app), **ANSWERS})
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        prog = AdmissionProgram.query.filter_by(program_code="208003").one()
        document = Document(io.BytesIO(package_service.build_package_docx(student, prog).read()))
        return "\n".join(p.text for p in document.paragraphs)


def test_toc_lists_specific_evidence_under_chapters(app):
    text = _text(app)
    toc = text[text.index("目　錄"):]
    assert re.search(r"\d\.1　", toc)  # 至少有一章底下列了具體佐證
    assert "電腦軟體應用" in toc or "校園黑客松" in toc


def test_autobiography_headings_are_printed_and_plan_is_its_own_chapter(app):
    text = _text(app)
    assert "學習動機" in text  # 自傳段落標題（以前因為欄位名稱不對沒印出來）
    plan_at = text.index("讀書計畫", text.index("目　錄") + 20)
    assert "未來規劃" in text[plan_at:]  # 「未來規劃」段歸讀書計畫章


def test_without_draft_both_chapters_keep_writing_hints(app):
    text = _text(app, with_draft=False)
    assert "請在此撰寫" in text and "請在此撰寫讀書計畫" in text
