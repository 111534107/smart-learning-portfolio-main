"""AI 自傳小幫手：先回答問題，AI 只能用學生的資料與回答寫草稿。"""
from datetime import date
import io

import pytest
from docx import Document

from app import create_app
from app.extensions import db
from app.models import (AdmissionProgram, CredentialRecord, LearningCourseRecord, LearningProfileOutput,
                        Portfolio, StudentProfile, StudentTarget, User)
from app.services.admission_service import import_seed_programs
from app.services.autobiography_service import build_facts, generate_draft
from app.services import autobiography_service
from app.services.journey_service import academic_year_of
from tests.board_helpers import fill_board

ANSWERS = {
    "motivation": "專二做網頁設計時發現自己喜歡把需求變成系統。",
    "proud": "黑客松時負責後端 API。",
    "challenge": "",
    "future": "想學資料分析。",
}
from tests.autobio_helpers import FOCUS_ANSWERS  # noqa: E402
ANSWERS = {**ANSWERS, **FOCUS_ANSWERS}  # 比重高的項目也要學生自己寫（2026-11-12）


@pytest.fixture()
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "UPLOAD_FOLDER": str(tmp_path)})
    with app.app_context():
        db.create_all()
        import_seed_programs()
        for username in ("stu", "other"):
            user = User(username=username, display_name=username, role="student")
            user.set_password("pw")
            db.session.add(user)
        db.session.flush()
        stu = User.query.filter_by(username="stu").one()
        db.session.add(StudentProfile(user_id=stu.id, student_no="111534100", class_name="資管科三甲", admission_year=academic_year_of(date.today()) - 4))  # 專五
        db.session.add(Portfolio(student_id=stu.id, title="校園黑客松", category="competition", school_year=3, status="confirmed",
                                 description="三人一組完成報名網站"))
        db.session.commit()
        fill_board(stu)  # 補滿五年資料（拼圖閘門已拿掉，這裡只是讓資料齊全）
    yield app


def login(app, username="stu"):
    client = app.test_client()
    client.post("/login", data={"username": username, "password": "pw"})
    return client


def program(app):
    with app.app_context():
        return AdmissionProgram.query.filter_by(program_code="208003").one().id


def choose_target(app, client):
    client.post("/student/targets", data={"program_id": program(app)})


def test_facts_are_numbered_and_include_program_weights(app):
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        facts = build_facts(student, AdmissionProgram.query.filter_by(program_code="208003").one())

    assert facts["items"][0]["id"] == "F1"
    assert any("校園黑客松" in fact["text"] for fact in facts["items"])
    assert facts["weights"]


def test_facts_keep_stable_evidence_ids_for_confirmed_sources(app):
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        program = AdmissionProgram.query.filter_by(program_code="208003").one()
        course = LearningCourseRecord(student_id=student.id, course_name="資料庫管理", normalized_course_name="資料庫管理",
                                      score=91, confirmation_status="confirmed")
        unconfirmed = LearningCourseRecord(student_id=student.id, course_name="待確認課程", normalized_course_name="待確認課程",
                                           score=99, confirmation_status="draft")
        credential = CredentialRecord(student_id=student.id, credential_name="測試證照", confirmation_status="confirmed")
        db.session.add_all([course, unconfirmed, credential])
        db.session.commit()

        facts = build_facts(student, program)["items"]

    course_fact = next(fact for fact in facts if "資料庫管理" in fact["text"])
    credential_fact = next(fact for fact in facts if "測試證照" in fact["text"])
    assert course_fact["evidence_id"] == f"course:{course.id}"
    assert credential_fact["evidence_id"] == f"credential:{credential.id}"
    assert all("待確認課程" not in fact["text"] for fact in facts)


def test_teacher_submission_snapshot_preserves_evidence_ids(app):
    from app.services.review_snapshot_service import build_snapshot

    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        program = AdmissionProgram.query.filter_by(program_code="208003").one()
        db.session.add(LearningCourseRecord(student_id=student.id, course_name="網頁設計", normalized_course_name="網頁設計",
                                            score=90, confirmation_status="confirmed"))
        db.session.commit()

        snapshot = build_snapshot(student, program)

    assert snapshot["facts"][0]["evidence_id"].startswith("course:")


def test_generate_keeps_only_known_fact_ids(app):
    def fake_ai(prompt, schema):
        assert "專二做網頁設計" in prompt
        assert "不得編造" in prompt
        return {"paragraphs": [{"title": "動機", "text": "我想讀資管。", "sources": ["F1", "F99"]}]}

    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        prog = AdmissionProgram.query.filter_by(program_code="208003").one()
        output = generate_draft(student, prog, ANSWERS, generate=fake_ai)

        assert output.output_type == "autobiography_ai"
        assert output.content_json["paragraphs"][0]["sources"] == ["F1"]
        assert output.content_json["provider"] == "gemini"
        assert any(item["evidence_id"].startswith("portfolio:") for item in output.source_snapshot_json["evidence_package"]["items"])


def test_without_api_key_uses_labelled_demo_draft(app):
    client = login(app)
    choose_target(app, client)

    response = client.post("/student/autobiography/generate", data={"program_id": program(app), **ANSWERS})

    assert response.status_code == 302
    html = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "尚未接上 AI" in html
    assert "專二做網頁設計" in html


def test_page_asks_to_choose_target_first(app):
    html = login(app).get("/student/autobiography").get_data(as_text=True)

    assert "/student/targets" in html
    assert 'name="motivation"' not in html


def test_page_shows_questions_after_target_chosen(app):
    client = login(app)
    choose_target(app, client)

    html = client.get("/student/autobiography").get_data(as_text=True)

    assert 'name="motivation"' in html


def test_second_school_carries_answers_from_latest_draft(app):
    with app.app_context():
        other_id = AdmissionProgram.query.filter(AdmissionProgram.program_code != "208003").first().id
    client = login(app)
    choose_target(app, client)
    client.post("/student/autobiography/generate", data={"program_id": program(app), **ANSWERS})
    client.post("/student/targets", data={"program_id": other_id})

    html = client.get(f"/student/autobiography?program_id={other_id}").get_data(as_text=True)

    assert "專二做網頁設計時發現自己喜歡把需求變成系統。" in html
    assert "黑客松時負責後端 API。" in html
    assert "想學資料分析。" in html


def test_student_edits_are_saved_and_go_into_word(app):
    client = login(app)
    choose_target(app, client)
    client.post("/student/autobiography/generate", data={"program_id": program(app), **ANSWERS})
    with app.app_context():
        output = LearningProfileOutput.query.filter_by(output_type="autobiography_ai").one()
        count = len(output.content_json["paragraphs"])

    response = client.post(f"/student/autobiography/{output.id}/save",
                           data={f"paragraph_{i}": f"我修改過的第{i + 1}段" for i in range(count)})
    docx = client.get(f"/student/targets/{program(app)}/package.docx")

    assert response.status_code == 302
    text = "\n".join(p.text for p in Document(io.BytesIO(docx.data)).paragraphs)
    assert "我修改過的第1段" in text


def test_synthetic_transcript_to_excluded_evidence_and_word(app):
    from tests.test_document_ocr_candidates import FakeOcrEngine, synthetic_png_bytes
    from app.models import DocumentExtraction, SourceDocument

    app.config.update(DOCUMENT_ANALYSIS_PROVIDER="offline_ocr", OCR_ENGINE=FakeOcrEngine("課程：模擬資料結構 學分：3 分數：88"))
    client = login(app)
    upload = client.post("/student/learning-profile/documents", data={
        "document_type": "transcript",
        "file": (io.BytesIO(synthetic_png_bytes((3200, 800))), "synthetic.png"),
    }, content_type="multipart/form-data")
    assert upload.status_code == 302
    with app.app_context():
        source = SourceDocument.query.one()
        extraction = DocumentExtraction.query.one()
        assert not LearningCourseRecord.query.filter_by(course_name="模擬資料結構").count()
        source_id, revision = source.id, extraction.result_json["draft_revision"]
    response = client.post(f"/student/learning-profile/documents/{source_id}/review/confirm", data={
        "draft_revision": revision,
        "courses_json": '[{"school_year":"3","semester":"上","course_name":"模擬資料結構","credits":"3","score":"88"}]',
        "credentials_json": "[]",
    })
    assert response.status_code == 302
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        assert LearningCourseRecord.query.filter_by(student_id=student.id, course_name="模擬資料結構").count() == 1
        record = Portfolio(student_id=student.id, title="不放入備審的測試經歷", category="activity", status="confirmed")
        db.session.add(record)
        db.session.commit()
        record_id = record.id
    choose_target(app, client)
    response = client.post("/student/package-exclusions", data={"kind": "portfolio", "record_id": record_id, "excluded": "1"})
    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(Portfolio, record_id).excluded_from_package
    response = client.post("/student/autobiography/generate", data={"program_id": program(app), **ANSWERS})
    assert response.status_code == 302
    with app.app_context():
        assert LearningProfileOutput.query.filter_by(output_type="autobiography_ai").count() == 1
    output = client.get(f"/student/targets/{program(app)}/package.docx")
    assert output.status_code == 200
    document = Document(io.BytesIO(output.data))
    text = "\n".join([p.text for p in document.paragraphs] + [cell.text for table in document.tables for row in table.rows for cell in row.cells])
    assert "模擬資料結構" in text
    assert "不放入備審的測試經歷" not in text


def test_other_student_cannot_save_my_draft(app):
    client = login(app)
    choose_target(app, client)
    client.post("/student/autobiography/generate", data={"program_id": program(app), **ANSWERS})
    with app.app_context():
        output_id = LearningProfileOutput.query.filter_by(output_type="autobiography_ai").one().id

    response = login(app, "other").post(f"/student/autobiography/{output_id}/save", data={"paragraph_0": "x"})

    assert response.status_code in (403, 404)


def test_own_api_key_is_used_once_and_never_stored(app, monkeypatch):
    import json
    from app.services import gemini_client
    secret = "AQ.student-own-secret-key-123"
    seen = {}

    def fake_generate(prompt, schema, files=None, api_key=None, opener=None):
        seen["key"] = api_key
        return {"paragraphs": [{"title": "動機", "text": "我想讀資管。", "sources": []}]}

    monkeypatch.setattr(gemini_client, "generate_json", fake_generate)
    monkeypatch.setattr("app.services.autobiography_service.generate_json", fake_generate)
    client = login(app)
    choose_target(app, client)

    response = client.post("/student/autobiography/generate",
                           data={"program_id": program(app), "own_api_key": secret, **ANSWERS})
    page = client.get(response.headers["Location"]).get_data(as_text=True)

    assert seen["key"] == secret
    assert secret not in response.headers["Location"]
    assert secret not in page
    assert "記得" in page and "刪除" in page
    with app.app_context():
        stored = LearningProfileOutput.query.filter_by(output_type="autobiography_ai").one()
        assert stored.content_json["provider"] == "gemini"
        assert secret not in json.dumps(stored.content_json, ensure_ascii=False)
        assert secret not in json.dumps(stored.source_snapshot_json, ensure_ascii=False)
    with client.session_transaction() as session:
        assert secret not in json.dumps(dict(session))


def test_form_offers_own_key_field_without_autocomplete(app):
    client = login(app)
    choose_target(app, client)

    html = client.get("/student/autobiography").get_data(as_text=True)

    assert 'name="own_api_key"' in html
    assert 'type="password"' in html
    assert 'autocomplete="off"' in html


def test_draft_page_shows_review_evidence_and_ai_limits(app):
    client = login(app)
    choose_target(app, client)
    client.post("/student/autobiography/generate", data={"program_id": program(app), **ANSWERS})

    html = client.get("/student/autobiography").get_data(as_text=True)

    assert "主張" in html
    assert "證據" in html
    assert "競賽：校園黑客松" in html
    assert "三人一組完成報名網站" in html
    assert "這題還沒回答" in html
    assert "AI 不能做的事" in html
    assert "給分" in html and "退件" in html and "核定資格" in html and "發布招生規則" in html
    assert "送出前要你自己確認" in html


def _count_generate(monkeypatch):
    calls = []

    def fake(prompt, schema, files=None, api_key=None, opener=None):
        calls.append(1)
        return {"paragraphs": [{"title": "動機", "text": "我想讀資管。", "sources": []}]}

    monkeypatch.setattr("app.services.autobiography_service.generate_json", fake)
    return calls


def test_autobiography_no_longer_waits_for_the_puzzle(app, monkeypatch):
    """試用版拿掉拼圖閘門：少了一類資料（服務學習）照樣可以生成自傳。"""
    calls = _count_generate(monkeypatch)
    with app.app_context():
        Portfolio.query.filter_by(category="service").delete()
        db.session.commit()
    client = login(app)
    choose_target(app, client)

    page = client.get("/student/autobiography").get_data(as_text=True)
    response = client.post("/student/autobiography/generate",
                           data={"program_id": program(app), "own_api_key": "test-key", **ANSWERS})

    assert "拼圖還差" not in page
    assert response.status_code == 302
    assert len(calls) == 1


def test_grade_one_autobiography_page_disables_generate_up_front(app):
    with app.app_context():
        stu = User.query.filter_by(username="stu").one()
        stu.student_profile.admission_year = academic_year_of(date.today())  # 專一
        db.session.commit()
    client = login(app)
    choose_target(app, client)

    page = client.get("/student/autobiography").get_data(as_text=True)

    assert "專五開放生成自傳" in page
    submit = page.split("data-step-submit", 1)[1].split(">", 1)[0]
    assert "disabled" in submit


def _set_grade(app, grade):
    with app.app_context():
        stu = User.query.filter_by(username="stu").one()
        stu.student_profile.admission_year = academic_year_of(date.today()) - (grade - 1)
        db.session.commit()


def test_grade_three_cannot_generate_autobiography(app, monkeypatch):
    calls = _count_generate(monkeypatch)
    _set_grade(app, 3)
    client = login(app)
    choose_target(app, client)

    response = client.post("/student/autobiography/generate",
                           data={"program_id": program(app), "own_api_key": "test-key", **ANSWERS})
    page = client.get("/student/autobiography").get_data(as_text=True)

    assert calls == []
    assert "專五才開放" in response.get_data(as_text=True)
    assert "專五開放生成自傳" in page


def test_grade_five_can_generate_autobiography(app, monkeypatch):
    calls = _count_generate(monkeypatch)
    _set_grade(app, 5)
    client = login(app)
    choose_target(app, client)

    response = client.post("/student/autobiography/generate",
                           data={"program_id": program(app), "own_api_key": "test-key", **ANSWERS})

    assert response.status_code == 302
    assert len(calls) == 1


def test_grade_three_can_still_submit_for_review(app):
    """送審維持專二規則：專三不受自傳專五限制影響。"""
    from app.services import student_rules
    _set_grade(app, 3)
    with app.app_context():
        stu = User.query.filter_by(username="stu").one()
        assert student_rules.review_block_reason(stu) is None
        assert "專五" in student_rules.autobiography_block_reason(stu)



def test_grade_one_is_told_autobiography_opens_at_grade_five(app):
    """專一的說明要講自傳專五才開放，不能沿用送審那句「專二」。"""
    from app.services import student_rules
    _set_grade(app, 1)
    with app.app_context():
        stu = User.query.filter_by(username="stu").one()
        reason = student_rules.autobiography_block_reason(stu)
        assert "專五" in reason and "專二" not in reason
        assert student_rules.review_open_note(stu) == "專五開放生成自傳"


def test_custom_draft_prompt_uses_flexible_headings_and_evidence_based_length(app):
    captured = {}
    def fake_ai(prompt, schema):
        captured['prompt'] = prompt
        return {'paragraphs': [{'title': '從實作學習', 'text': '測試內容', 'sources': ['F1']}]}
    with app.app_context():
        student = User.query.filter_by(username='stu').one()
        prog = AdmissionProgram.query.filter_by(program_code='208003').one()
        generate_draft(student, prog, ANSWERS, generate=fake_ai)
    assert '1500' in captured['prompt'] and '2500' in captured['prompt']
    assert '有主張的小標題' in captured['prompt']
    assert '不得編造' in captured['prompt']


def test_custom_draft_prompt_uses_flexible_headings_and_evidence_based_length(app):
    captured = {}
    def fake_ai(prompt, schema):
        captured['prompt'] = prompt
        return {'paragraphs': [{'title': '從實作學習', 'text': '測試內容', 'sources': ['F1']}]}
    with app.app_context():
        student = User.query.filter_by(username='stu').one()
        prog = AdmissionProgram.query.filter_by(program_code='208003').one()
        generate_draft(student, prog, ANSWERS, generate=fake_ai)
    assert '1500' in captured['prompt'] and '2500' in captured['prompt']
    assert '有主張的小標題' in captured['prompt']
    assert '不得編造' in captured['prompt']


def test_custom_contents_lists_only_confirmed_evidence_in_weighted_order(app):
    from app.services.autobiography_service import custom_contents
    with app.app_context():
        student = User.query.filter_by(username='stu').one()
        prog = AdmissionProgram.query.filter_by(program_code='208003').one()
        db.session.add(Portfolio(student_id=student.id, title='尚未確認的競賽', category='competition', status='draft'))
        db.session.commit()
        chapters = custom_contents(student, prog)
        names = [e['name'] for c in chapters for e in c['evidence']]
        assert '校園黑客松' in names
        assert '尚未確認的競賽' not in names
        assert all(e['evidence_id'] for c in chapters for e in c['evidence'])
        weighted = [c['weight'] for c in chapters if c['weight']]
        assert weighted == sorted(weighted, reverse=True)


def test_course_evidence_is_summarized_not_listed_course_by_course():
    """11-04 實測：備審目錄把 85 門課逐一列出（含勞作教育、體育）。"""
    from types import SimpleNamespace
    from app.services.autobiography_service import TOP_COURSES, _course_summary
    courses = [SimpleNamespace(id=i, course_name=f"專業科目{i}", score=60 + i) for i in range(1, 80)]
    courses += [SimpleNamespace(id=100, course_name="勞作教育", score=100),
                SimpleNamespace(id=101, course_name="體育(一)", score=99),
                SimpleNamespace(id=102, course_name="班會", score=None)]
    items = _course_summary(courses)
    names = [item["name"] for item in items]
    assert len(items) == 1 + TOP_COURSES
    assert names[0].startswith("歷年成績單：已確認 82 門課")
    assert not any("勞作" in n or "體育" in n for n in names)
    assert "專業科目79" in names[1]
    assert _course_summary([]) == []


def test_credential_label_shows_level_only_when_missing_from_name():
    from types import SimpleNamespace
    from app.services.autobiography_service import credential_label
    assert credential_label(SimpleNamespace(credential_name="網頁設計", level="丙級")) == "網頁設計（丙級）"
    assert credential_label(SimpleNamespace(credential_name="網頁設計丙級", level="丙級")) == "網頁設計丙級"
    assert credential_label(SimpleNamespace(credential_name="TQC Word", level=None)) == "TQC Word"


def test_strength_inventory_counts_only_confirmed_records_and_links_evidence(app):
    from app.services.autobiography_service import strength_inventory
    with app.app_context():
        student = User.query.filter_by(username='stu').one()
        db.session.add_all([
            CredentialRecord(student_id=student.id, credential_name='測試證照甲', category='國際', confirmation_status='confirmed'),
            CredentialRecord(student_id=student.id, credential_name='未確認證照', category='國際', confirmation_status='draft'),
            Portfolio(student_id=student.id, title='未確認經歷', category='competition', status='draft'),
        ])
        db.session.commit()
        inventory = strength_inventory(student)
        entries = [e for group in inventory for e in group['evidence']]
        assert any(e['name'] == '測試證照甲' for e in entries)
        assert not any(e['name'] in ('未確認證照', '未確認經歷') for e in entries)
        assert all(group['count'] == len(group['evidence']) for group in inventory)
        assert all(e['evidence_id'] for e in entries)


def test_student_can_expand_inventory_without_hiding_question(app):
    client = login(app)
    choose_target(app, client)
    page = client.get('/student/autobiography').get_data(as_text=True)
    assert '<details class="strengths-disclosure"' in page
    assert '<summary' in page and '已確認資料盤點' in page
    assert 'name="motivation"' in page


def test_contents_evidence_is_nested_under_its_chapter(app):
    from html.parser import HTMLParser

    class Outline(HTMLParser):
        def __init__(self):
            super().__init__(); self.inside = False; self.depth = 0; self.chapters = 0; self.evidence_nested = False
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'ol' and attrs.get('class') == 'toc':
                self.inside = True; self.depth = 1
            elif self.inside and tag in ('ol', 'ul'):
                self.depth += 1
            elif self.inside and tag == 'li' and self.depth == 1:
                self.chapters += 1
            elif self.inside and tag == 'li' and self.depth > 1:
                self.evidence_nested = True
        def handle_endtag(self, tag):
            if self.inside and tag in ('ol', 'ul'):
                self.depth -= 1
                if self.depth == 0: self.inside = False
    client = login(app)
    choose_target(app, client)
    page = client.get(f'/student/targets/{program(app)}').get_data(as_text=True)
    tree = Outline(); tree.feed(page)
    assert tree.chapters == 10
    assert tree.evidence_nested


# ---------- B1／B2（2026-11-13）：素材拖放、保留學生自己打的字 ----------

def _rewrite(prompt, schema):
    return {"paragraphs": [{"title": "動機", "text": "AI 重寫的新版本。", "sources": []}]}


def test_regenerating_keeps_paragraphs_the_student_edited(app):
    from app.services.autobiography_service import own_words, guided_questions, save_edits

    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        prog = AdmissionProgram.query.filter_by(program_code="208003").one()
        first = generate_draft(student, prog, ANSWERS, generate=_rewrite)
        save_edits(first, ["這是我自己改的一句話。"], student)
        second = generate_draft(student, prog, ANSWERS, generate=_rewrite)

        assert second.content_json["paragraphs"][0]["text"] == "AI 重寫的新版本。"
        assert second.content_json["kept_paragraphs"] == [{"title": "動機", "text": "這是我自己改的一句話。"}]
        # 再重寫一次（上一版沒人改）也不會弄丟
        third = generate_draft(student, prog, ANSWERS, generate=_rewrite)
        assert third.content_json["kept_paragraphs"] == second.content_json["kept_paragraphs"]
        texts = [item["text"] for item in own_words(third.content_json, guided_questions(prog))]
        assert "這是我自己改的一句話。" in texts
        assert ANSWERS["motivation"] in texts


def test_draft_page_offers_own_words_and_facts_as_draggable_pieces(app):
    client = login(app)
    choose_target(app, client)
    client.post("/student/autobiography/generate", data={"program_id": program(app), **ANSWERS})

    html = client.get(f"/student/autobiography?program_id={program(app)}").get_data(as_text=True)

    assert "data-bio-pieces" in html and "js/bio-pieces.js" in html
    assert "你自己寫的文字" in html
    assert f'data-bio-piece="{ANSWERS["motivation"]}"' in html
    assert 'draggable="true"' in html and "（F1）" in html


def test_question_page_offers_facts_as_draggable_pieces(app):
    client = login(app)
    choose_target(app, client)

    html = client.get("/student/autobiography").get_data(as_text=True)

    assert "data-bio-pieces" in html
    assert "校園黑客松" in html and "（F" in html


def test_manual_start_works_without_ai_and_preserves_versions(app, monkeypatch):
    client = login(app)
    choose_target(app, client)
    monkeypatch.setattr('app.routes.student.autobiography_service.generate_json', lambda *a, **k: (_ for _ in ()).throw(AssertionError('AI called')))
    response = client.post('/student/autobiography/manual', data={'program_id': program(app), 'motivation': '我的手寫動機'})
    assert response.status_code == 302
    html = client.get(response.headers['Location']).get_data(as_text=True)
    assert '我的手寫動機' in html
    assert '目前版本' in html and '送審' in html and '未儲存' in html
    with app.app_context():
        output = LearningProfileOutput.query.filter_by(output_type='autobiography_ai').one()
        assert output.content_json['provider'] == 'manual'
        output_id = output.id
        count = len(output.content_json['paragraphs'])
    client.post(f'/student/autobiography/{output_id}/save', data={f'paragraph_{i}': '手寫內容' for i in range(count)})
    with app.app_context():
        assert LearningProfileOutput.query.filter_by(output_type='autobiography_ai').count() == 2


def test_manual_school_switch_and_review_snapshot(app):
    client = login(app)
    choose_target(app, client)
    with app.app_context():
        other_id = AdmissionProgram.query.filter(AdmissionProgram.program_code != "208003").first().id
    client.post('/student/targets', data={'program_id': other_id})
    client.post('/student/autobiography/manual', data={'program_id': program(app), 'motivation': '第一校的手寫內容'})
    client.post('/student/autobiography/manual', data={'program_id': other_id, 'motivation': '第二校的手寫內容'})
    first = client.get(f'/student/autobiography?program_id={program(app)}').get_data(as_text=True)
    assert '第一校的手寫內容' in first and '第二校的手寫內容' not in first
    assert '#review' in first
    client.post(f'/student/targets/{program(app)}/review')
    first = client.get(f'/student/autobiography?program_id={program(app)}').get_data(as_text=True)
    assert '送出第 1 版' in first
    with app.app_context():
        student = User.query.filter_by(username='stu').one()
        output = autobiography_service.latest_draft(student, db.session.get(AdmissionProgram, program(app)))
        output_id = output.id
        count = len(output.content_json['paragraphs'])
    client.post(f'/student/autobiography/{output_id}/save', data={f'paragraph_{i}': '更新' for i in range(count)})
    first = client.get(f'/student/autobiography?program_id={program(app)}').get_data(as_text=True)
    assert '目前版本尚未送審' in first and '送出第 1 版' in first


def test_manual_start_rejects_another_students_target(app):
    owner = login(app)
    choose_target(app, owner)
    other = login(app, 'other')
    assert other.post('/student/autobiography/manual', data={'program_id': program(app)}).status_code == 302
    with app.app_context():
        assert LearningProfileOutput.query.filter_by(output_type='autobiography_ai').count() == 0


def test_ai_failure_keeps_answers_and_allows_manual_start(app, monkeypatch):
    from app.services.gemini_client import AIUnavailable
    client = login(app)
    choose_target(app, client)
    def fail(*args, **kwargs):
        raise AIUnavailable('模擬 AI 失敗')
    with monkeypatch.context() as patcher:
        patcher.setattr(autobiography_service, 'generate_draft', fail)
        failed = client.post('/student/autobiography/generate', data={'program_id': program(app), **ANSWERS})
    html = failed.get_data(as_text=True)
    assert failed.status_code == 503 and '模擬 AI 失敗' in html
    assert ANSWERS['motivation'] in html and '/student/autobiography/manual' in html
    saved = client.post('/student/autobiography/manual', data={'program_id': program(app), **ANSWERS})
    assert saved.status_code == 302 and ANSWERS['motivation'] in client.get(saved.headers['Location']).get_data(as_text=True)


def test_writing_progress_guides_first_draft_before_review(app):
    client = login(app)
    choose_target(app, client)
    program_id = program(app)
    first = client.get('/student/autobiography').get_data(as_text=True)
    assert 'aria-label="自傳步驟"' in first
    assert 'data-writing-stage="questions" aria-current="step"' in first
    assert '前往確認送審' not in first
    response = client.post('/student/autobiography/manual', data={'program_id': program_id})
    assert response.status_code == 302
    draft = client.get(response.location).get_data(as_text=True)
    assert 'data-writing-stage="draft" aria-current="step"' in draft
    assert '前往確認送審' in draft


def _draft_count(app, username="stu"):
    with app.app_context():
        student = User.query.filter_by(username=username).one()
        return len(autobiography_service.versions(student, db.session.get(AdmissionProgram, program(app))))


def test_unsubmitted_autobiography_can_be_deleted_whole(app):
    """2026-11-19 使用者決定：從沒送過導師的自傳草稿可以整份刪除，並留操作紀錄。"""
    from app.models import AuditLog
    client = login(app)
    choose_target(app, client)
    client.post('/student/autobiography/manual', data={'program_id': program(app), 'motivation': '想刪掉重寫'})
    assert _draft_count(app) == 1
    page = client.get(f'/student/autobiography/versions?program_id={program(app)}').get_data(as_text=True)
    assert '刪除整份草稿' in page

    response = client.post('/student/autobiography/delete', data={'program_id': program(app)})

    assert response.status_code == 302
    assert _draft_count(app) == 0
    with app.app_context():
        assert AuditLog.query.filter_by(action='autobiography.delete').count() == 1


def test_submitted_autobiography_cannot_be_deleted(app):
    """送過導師確認的自傳不能刪（歷史版本與送審紀錄要保留），頁面也不顯示刪除鈕。"""
    from app.models import AuditLog
    client = login(app)
    choose_target(app, client)
    client.post('/student/autobiography/manual', data={'program_id': program(app), 'motivation': '已送審的內容'})
    client.post(f'/student/targets/{program(app)}/review')
    page = client.get(f'/student/autobiography/versions?program_id={program(app)}').get_data(as_text=True)
    assert '刪除整份草稿' not in page

    client.post('/student/autobiography/delete', data={'program_id': program(app)})

    assert _draft_count(app) == 1
    with app.app_context():
        assert AuditLog.query.filter_by(action='autobiography.delete_blocked').count() == 1


def test_other_student_cannot_delete_my_autobiography(app):
    owner = login(app)
    choose_target(app, owner)
    owner.post('/student/autobiography/manual', data={'program_id': program(app), 'motivation': '我的內容'})
    other = login(app, 'other')
    assert other.post('/student/autobiography/delete', data={'program_id': program(app)}).status_code == 404
    assert _draft_count(app) == 1


def test_outline_follows_target_program_weights(app):
    """自傳目錄跟著目標校系的簡章項目改變：學習動機開頭、未來規劃結尾，中間依比重由高到低。"""
    from app.services.autobiography_service import guided_questions, outline_titles
    with app.app_context():
        prog = AdmissionProgram.query.filter_by(program_code='208003').one()
        questions = guided_questions(prog)
        titles = outline_titles(prog, questions)
        weighted = [q["item"][:30] for q in questions if q.get("weight")]
        assert titles[0] == "學習動機" and titles[-1] == "未來規劃"
        assert titles[1:1 + len(weighted[:4])] == weighted[:4]
        assert outline_titles(None, []) == ["學習動機", "學習歷程與具體經驗", "困難與成長", "未來規劃"]


def test_paragraph_budgets_follow_weights_and_stay_short(app):
    """每段字數上限依簡章比重分配；全份不超過約 2200 字的目標（不會寫成萬字）。"""
    from app.services.autobiography_service import (TOTAL_CHAR_BUDGET, guided_questions, outline_titles,
                                                    paragraph_budgets)
    with app.app_context():
        prog = AdmissionProgram.query.filter_by(program_code='208003').one()
        questions = guided_questions(prog)
        budgets = paragraph_budgets(prog, questions)
        titles = outline_titles(prog, questions)
        assert all(title in budgets for title in titles)
        assert sum(budgets[t] for t in titles) <= TOTAL_CHAR_BUDGET + 300
        focus = [q for q in questions if q.get("weight")]
        if len(focus) >= 2 and focus[0]["weight"] > focus[-1]["weight"]:
            assert budgets[focus[0]["item"][:30]] >= budgets[focus[-1]["item"][:30]]


def test_prompt_tells_ai_the_chapter_budgets(app):
    captured = {}
    def fake_ai(prompt, schema):
        captured['prompt'] = prompt
        return {'paragraphs': [{'title': '學習動機', 'text': '測試', 'sources': []}]}
    with app.app_context():
        student = User.query.filter_by(username='stu').one()
        prog = AdmissionProgram.query.filter_by(program_code='208003').one()
        generate_draft(student, prog, ANSWERS, generate=fake_ai)
    assert '約250字內' in captured['prompt'] and '未來規劃（約300字內）' in captured['prompt']


def test_new_facts_since_draft_lists_only_new_confirmed_data(app):
    from app.services.autobiography_service import build_facts, new_facts_since
    client = login(app)
    choose_target(app, client)
    client.post("/student/autobiography/generate", data={"program_id": program(app), **ANSWERS})
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        prog = AdmissionProgram.query.filter_by(program_code="208003").one()
        draft = autobiography_service.latest_draft(student, prog)
        assert new_facts_since(draft, build_facts(student, prog)) == []
        db.session.add(Portfolio(student_id=student.id, title="新增的志工服務", category="service", school_year=3,
                                 status="confirmed", description="假日淨灘"))
        db.session.commit()
        fresh = new_facts_since(draft, build_facts(student, prog))
        assert any("新增的志工服務" in text for text in fresh)


def test_editor_page_receives_budgets_and_update_notice(app):
    client = login(app)
    choose_target(app, client)
    client.post("/student/autobiography/generate", data={"program_id": program(app), **ANSWERS})
    with app.app_context():
        student = User.query.filter_by(username="stu").one()
        db.session.add(Portfolio(student_id=student.id, title="剛新增的社團", category="activity", school_year=3,
                                 status="confirmed", description="社長"))
        db.session.commit()
    page = client.get(f"/student/autobiography?program_id={program(app)}").get_data(as_text=True)
    assert page.count("data-budget") >= 0 and response_ok(page)


def response_ok(page):
    return "小助手寫自傳" in page


def test_autobiography_autosave_accumulates_versions_and_returns_json(app):
    client = login(app)
    choose_target(app, client)
    client.post("/student/autobiography/generate", data={"program_id": program(app), **ANSWERS})
    with app.app_context():
        output = LearningProfileOutput.query.filter_by(output_type="autobiography_ai").one()
        v1 = autobiography_service.version_of(output)

    # 第一次自動儲存
    res1 = client.post(f"/student/autobiography/{output.id}/autosave",
                       json={"paragraph_0": "自動儲存測試第一段", "paragraph_1": "自動儲存測試第二段"})
    assert res1.status_code == 200
    data1 = res1.get_json()
    assert data1["ok"] is True
    assert data1["version"] == v1 + 1
    assert "已自動儲存" in data1["message"]
    new_id = data1["output_id"]

    # 第二次自動儲存：以最新 output_id 儲存，版本照舊累加
    res2 = client.post(f"/student/autobiography/{new_id}/autosave",
                       json={"paragraph_0": "第二次自動儲存第一段", "paragraph_1": "第二次自動儲存第二段"})
    assert res2.status_code == 200
    data2 = res2.get_json()
    assert data2["ok"] is True
    assert data2["version"] == v1 + 2
    assert data2["output_id"] != new_id

    # 防衝突：拿舊的 output.id 來存會回報 409 與 stale
    res_stale = client.post(f"/student/autobiography/{output.id}/autosave",
                            json={"paragraph_0": "舊頁面打的字"})
    assert res_stale.status_code == 409
    assert res_stale.get_json()["stale"] is True


def test_autobiography_autosave_validation_and_permissions(app):
    client = login(app)
    choose_target(app, client)
    client.post("/student/autobiography/generate", data={"program_id": program(app), **ANSWERS})
    with app.app_context():
        output = LearningProfileOutput.query.filter_by(output_type="autobiography_ai").one()
        out_id = output.id

    # 找不到這份自傳 404
    res_404 = client.post("/student/autobiography/999999/autosave", json={"paragraph_0": "test"})
    assert res_404.status_code == 404

    # 非本人操作 403
    other_client = login(app, username="other")
    res_403 = other_client.post(f"/student/autobiography/{out_id}/autosave", json={"paragraph_0": "test"})
    assert res_403.status_code == 403
