"""升學 Agent 整理重點（2026-11-10 使用者：小助手要能自己爬資料、整理重點）。

- 擷取簡章時，每個評分項目一起擷取「要繳什麼」與頁碼；每個校系擷取「重點提醒」（特殊表格、字數頁數限制、門檻）。
- 官方網頁更新時，跟著頁面上的簡章 PDF 連結，自動登記成新來源（116 簡章一公布就抓得到）。
- 重點只是候選，管理員核准後學生才在目標校系、備審 Word、小助手看到。
"""
import io

from docx import Document

from app.extensions import db
from app.models import AdmissionProgram, PublicSource, StudentProfile, User
from app.services import admission_agent_service as agent
from app.services.assistant_tools import _gap
from app.services.package_service import build_package_docx
from tests.test_admission_agent import admin, app, fake_fetch, login, make_source  # noqa: F401  (app 是 fixture)

EXTRACTED = {"programs": [
    {"program_code": "208003", "admission_year": 116, "school_name": "國立臺北商業大學", "department_name": "資訊管理系",
     "admission_category": "管理類四",
     "items": [
         {"name": "專業成果", "weight": 30, "categories": ["project"],
          "requirement": "專題製作成果，以資訊系統製作為主。", "source_page": "70"},
         {"name": "學習能力", "weight": 70, "categories": ["grades", "autobiography"],
          "requirement": "", "source_page": ""},
     ],
     "highlights": [
         {"text": "要繳北商官網下載的自我推薦摘要表（表A）與課程學習成果工作內容與貢獻度表（表B），電腦打字並親簽。",
          "source_page": "第 70 頁"},
         {"text": "   ", "source_page": "70"},
         {"text": "書面資料審查所繳交資料不再歸還，請自行留存。", "source_page": "70"},
     ] + [{"text": f"第 {n} 條提醒", "source_page": "70"} for n in range(20)],
     "eligibility_rules": []},
]}


def extract(app):
    source_id = make_source(app)
    with app.app_context():
        source = db.session.get(PublicSource, source_id)
        agent.check_source(source, admin(app), fetch=fake_fetch(b"%PDF brochure"))
        change = agent.PublicSourceChange.query.one()
        agent.extract_programs(change, admin(app), generate=lambda prompt, schema, files: EXTRACTED)
        db.session.commit()
        return AdmissionProgram.query.filter_by(data_origin="agent").one().id


def test_extraction_keeps_requirement_page_and_highlights(app):
    program_id = extract(app)
    with app.app_context():
        program = db.session.get(AdmissionProgram, program_id)
        items = {item.source_item_name: item for item in program.items}
        assert items["專業成果"].requirement == "專題製作成果，以資訊系統製作為主。（PDF 第70頁）"
        assert items["學習能力"].requirement is None
        texts = [h["text"] for h in program.highlights]
        assert "表A" in texts[0] and program.highlights[0]["page"] == "第 70 頁"
        assert "" not in [t.strip() for t in texts]  # 空白的不收
        assert not any("不再歸還" in t for t in texts)  # 每系都有的一般說明不收
        assert len(texts) <= agent.MAX_HIGHLIGHTS


def test_prompt_and_schema_ask_for_key_points():
    prompt = agent._extract_prompt(["資訊管理"])
    assert "requirement" in prompt and "highlights" in prompt and "頁碼" in prompt
    program = agent.EXTRACT_SCHEMA["properties"]["programs"]["items"]["properties"]
    assert "highlights" in program
    assert "requirement" in program["items"]["items"]["properties"]


def test_admin_sees_highlights_and_requirement_changes_before_approving(app):
    program_id = extract(app)
    with app.app_context():
        program = db.session.get(AdmissionProgram, program_id)
        diff = agent.compare_with_published(program)
        row = next(r for r in diff["rows"] if r["name"] == "專業成果")
        assert row["requirement_changed"] is True  # 115 種子資料的說明和這次擷取的不同
    html = login(app, "admin").get("/admin/programs").get_data(as_text=True)
    assert "簡章重點" in html and "表A" in html and "以資訊系統製作為主" in html


def test_html_source_follows_brochure_pdf_links(app):
    page = """<html><body>
      <a href="/downloads/116/skill/116_skill_general.pdf">116學年度二技技優甄審招生簡章</a>
      <a href="https://www.jctv.ntut.edu.tw/downloads/116/skill/116_date.pdf">116 重要日程表 簡章附錄</a>
      <a href="/news/123">最新消息</a>
      <a href="/downloads/115/enter/115_enter_A14.pdf">甄審總成績複查申請表</a>
      <a href="https://evil.example.com/116_skill.pdf">二技招生簡章（非官方）</a>
      <a href="/downloads/116/skill/116_skill_general.pdf">重複的簡章連結</a>
    </body></html>""".encode("utf-8")
    with app.app_context():
        source = agent.add_source("聯招會簡章下載頁", url="https://www.jctv.ntut.edu.tw/enter/contents.php?subId=34")
        task = agent.check_source(source, admin(app), fetch=lambda url: (page, "text/html; charset=utf-8"))
        urls = {s.url for s in PublicSource.query.all()}
        assert "https://www.jctv.ntut.edu.tw/downloads/116/skill/116_skill_general.pdf" in urls
        assert "https://www.jctv.ntut.edu.tw/downloads/116/skill/116_date.pdf" in urls
        assert not any("evil" in url or "/news/" in url for url in urls)
        assert len(task.result_json["linked_sources"]) == 2
        # 頁面沒變就不再找連結，也不會重複登記
        again = agent.check_source(source, admin(app), fetch=lambda url: (page, "text/html; charset=utf-8"))
        assert again.result_json["changed"] is False and PublicSource.query.count() == 3


def test_seed_highlights_reach_student_word_and_assistant(app):
    with app.app_context():
        program = AdmissionProgram.query.filter_by(program_code="208003", data_origin="manual").one()
        assert any("表A" in h["text"] for h in program.highlights)
        student = User.query.filter_by(username="stu").one()
        db.session.add(StudentProfile(user_id=student.id, student_no="111000001", class_name="資五甲", admission_year=111))
        db.session.commit()
        text = "\n".join(p.text for p in Document(io.BytesIO(build_package_docx(student, program).read())).paragraphs)
        assert "重點提醒" in text and "表A" in text
        assert any("表A" in h for h in _gap(student, program)["highlights"])
        program_id = program.id
    html = login(app, "stu").get("/student/targets").get_data(as_text=True)
    assert "data-highlights" in html and "表A" in html


def test_brochure_without_program_code_matches_existing_program_by_name(app):
    """11-11 真實驗收：簡章附錄的志願代碼印成「--」，用學校＋科系對照已有的校系；同學年度已有就不重建。"""
    extracted = {"programs": [{**EXTRACTED["programs"][0], "program_code": "--", "admission_year": 116,
                               "department_name": "資訊管理系(臺北校區)"},
                              {**EXTRACTED["programs"][0], "program_code": "--", "admission_year": 115}]}
    source_id = make_source(app)
    with app.app_context():
        agent.check_source(db.session.get(PublicSource, source_id), admin(app), fetch=fake_fetch(b"%PDF x"))
        task = agent.extract_programs(agent.PublicSourceChange.query.one(), admin(app),
                                      generate=lambda prompt, schema, files: extracted)
        assert task.result_json["created"] == ["208003"]  # 116 新建；115 已有正式版，略過
        assert task.result_json["skipped"] == ["208003"]


def test_made_up_code_is_replaced_and_duplicates_skipped(app):
    """11-11 真實驗收：AI 對同一系多給一個編出來的代碼（108001），要改回已有代碼並略過重複。"""
    made_up = {**EXTRACTED["programs"][0], "program_code": "108001"}
    source_id = make_source(app)
    with app.app_context():
        agent.check_source(db.session.get(PublicSource, source_id), admin(app), fetch=fake_fetch(b"%PDF y"))
        task = agent.extract_programs(agent.PublicSourceChange.query.one(), admin(app),
                                      generate=lambda prompt, schema, files: {"programs": [made_up, EXTRACTED["programs"][0]]})
        assert task.result_json["created"] == ["208003"] and task.result_json["skipped"] == ["208003"]


def test_schedule_keeps_only_dates_in_source_and_merges_duplicates(app):
    """11-11 網頁實測：日程同一件事出現 2～3 筆、還有原文沒有的 116 學年度日期。"""
    page = "<html><body>115學年度重要日程 網路報名 115.4.20(一)10:00起至115.4.23(四)17:00止 ".encode("utf-8") + \
        "放榜 115年5月25日 </body></html>".encode("utf-8")
    schedule = {"channel": "skill_review", "admission_year": 115, "events": [
        {"name": "網路報名", "start": "2026-04-20 00:00", "end": "2026-04-23 23:59"},
        {"name": "考生網路報名", "start": "2026-04-20 10:00", "end": "2026-04-23 17:00"},  # 同一件事，有寫時間
        {"name": "就讀志願序統一分發放榜", "start": "2026-05-25 10:00"},
        {"name": "統一分發放榜", "start": "2026-05-25 10:00"},  # 同一件事
        {"name": "116 網路報名", "start": "2027-05-17 00:00", "end": "2027-05-21 23:59"},  # 原文沒有
    ]}
    with app.app_context():
        source = agent.add_source("聯招會日程", url="https://www.jctv.ntut.edu.tw/enter/date.php")
        agent.check_source(source, admin(app), fetch=lambda url: (page, "text/html"))
        task = agent.extract_programs(agent.PublicSourceChange.query.one(), admin(app),
                                      generate=lambda prompt, schema, files: {"programs": [], "schedule": schedule})
        db.session.commit()
        events = agent.AdmissionScheduleEvent.query.filter_by(status="candidate").order_by("start_at").all()
        assert [(e.name, e.start_at.strftime("%m-%d %H:%M")) for e in events] == [
            ("網路報名", "04-20 10:00"), ("就讀志願序統一分發放榜", "05-25 10:00")]
        assert task.result_json["schedule_skipped"] == 1


def test_date_check_reads_roc_and_western_formats():
    from datetime import datetime as dt
    for text in ("115.4.20", "115/04/20", "115年4月20日", "2026-04-20", "115 . 4 . 20"):
        assert agent._date_in_text(dt(2026, 4, 20), text), text
    assert not agent._date_in_text(dt(2026, 4, 2), "115.4.20")


def test_program_whose_weights_do_not_add_to_100_is_not_created(app):
    """11-11 本機 Ollama 實測：把「書面資料審查 100%」和評分標準都列成項目，合計 200%。"""
    bad = {**EXTRACTED["programs"][0], "items": [
        {"name": "書面資料審查", "weight": 100, "categories": []},
        {"name": "書審資料評分標準", "weight": 100, "categories": []}]}
    source_id = make_source(app)
    with app.app_context():
        agent.check_source(db.session.get(PublicSource, source_id), admin(app), fetch=fake_fetch(b"%PDF z"))
        task = agent.extract_programs(agent.PublicSourceChange.query.one(), admin(app),
                                      generate=lambda prompt, schema, files: {"programs": [bad]})
        assert task.result_json["created"] == [] and task.result_json["skipped"] == ["208003"]
