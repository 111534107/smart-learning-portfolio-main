"""從頭到尾的主線測試（V1 規格第 9 節）：一個假學生從第一次登入走到導師確認。

只用 Flask 測試用戶端與記憶體 SQLite；OCR 用 fake 擷取（不連外部服務），自傳用假的 AI 函式。
每一步都用頁面回應或資料庫確認結果；全部是合成資料。
"""
import io
import json
import re
import zipfile
from datetime import date

import pytest
from PIL import Image

from app import create_app
from app.extensions import db
from app.models import (
    AdmissionProgram,
    ClassAdvisor,
    LearningCourseRecord,
    LearningProfileOutput,
    PackageReview,
    Portfolio,
    PortfolioEvidence,
    SourceDocument,
    StudentProfile,
    StudentTarget,
    User,
)
from app.services import autobiography_service
from app.services.admission_service import import_seed_programs
from app.services.gap_service import ALL_LABELS, analyze_gap
from app.services.journey_service import academic_year_of
from tests.board_helpers import fill_board

# 讓學生不論哪一年跑測試都是專三（送導師確認、AI 自傳要二年級以上）
GRADE3_ADMISSION_YEAR = academic_year_of(date.today()) - 2
GRADE5_ADMISSION_YEAR = academic_year_of(date.today()) - 4  # 自傳到專五才開放生成
PROGRAM_CODE = "208003"
ANSWERS = {
    "motivation": "修程式設計時發現自己喜歡把流程整理清楚。",
    "proud": "資訊週擔任志工，負責報到系統的測試。",
    "challenge": "資料庫查詢常寫錯，後來每天練習題目。",
    "future": "想學資料分析，之後做系統分析師。",
}


@pytest.fixture()
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True,
                      "UPLOAD_FOLDER": str(tmp_path), "DOCUMENT_ANALYSIS_PROVIDER": "fake"})
    with app.app_context():
        db.create_all()
        import_seed_programs()
        for username, role in (("e2e_stu", "student"), ("e2e_other", "student"),
                               ("e2e_teacher", "teacher"), ("e2e_stranger", "teacher")):
            user = User(username=username, display_name=f"合成{username}", role=role)
            user.set_password("pw")
            db.session.add(user)
        db.session.flush()
        stu = User.query.filter_by(username="e2e_stu").one()
        other = User.query.filter_by(username="e2e_other").one()
        db.session.add(StudentProfile(user_id=stu.id, student_no="SYN9001", class_name="資管科三甲",
                                      admission_year=GRADE5_ADMISSION_YEAR))
        db.session.add(StudentProfile(user_id=other.id, student_no="SYN9002", class_name="資管科三乙",
                                      admission_year=GRADE5_ADMISSION_YEAR))
        db.session.add(ClassAdvisor(teacher_id=User.query.filter_by(username="e2e_teacher").one().id,
                                    class_name="資管科三甲", school_year=GRADE3_ADMISSION_YEAR + 2))
        db.session.add(ClassAdvisor(teacher_id=User.query.filter_by(username="e2e_stranger").one().id,
                                    class_name="資管科三乙", school_year=GRADE3_ADMISSION_YEAR + 2))
        db.session.commit()
        yield app


@pytest.fixture()
def fake_ai(monkeypatch):
    """假的 AI：從提示詞讀出事實編號，每段都引用至少一個 F 編號。不連網路。"""
    prompts = []

    def generate_json(prompt, schema, api_key=None):
        prompts.append(prompt)
        ids = re.findall(r"^(F\d+)\. ", prompt, re.M)
        assert len(ids) >= 3, "提示詞裡應該有成績與經歷的事實編號"
        return {"paragraphs": [
            {"title": "學習動機", "text": ANSWERS["motivation"], "sources": [ids[0]]},
            {"title": "學習歷程與具體經驗", "text": ANSWERS["proud"], "sources": [ids[-1]]},
            {"title": "困難與成長", "text": ANSWERS["challenge"], "sources": [ids[1]]},
            {"title": "未來規劃", "text": ANSWERS["future"], "sources": [ids[0], ids[1]]},
        ]}

    monkeypatch.setattr(autobiography_service, "ai_ready", lambda: True)
    monkeypatch.setattr(autobiography_service, "generate_json", generate_json)
    return prompts


def login(app, username):
    client = app.test_client()
    response = client.post("/login", data={"username": username, "password": "pw"})
    return client, response


def tiny_pdf():
    """測試內產生的一頁 PDF（假的成績單；內容由 fake 擷取決定）。"""
    buffer = io.BytesIO()
    Image.new("RGB", (1240, 1754), "white").save(buffer, format="PDF")
    return buffer.getvalue()


def tiny_png():
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 220, 240)).save(buffer, format="PNG")
    return buffer.getvalue()


def text(response):
    return response.get_data(as_text=True)


def test_one_student_walks_the_whole_main_line(app, fake_ai):
    with app.app_context():
        stu_id = User.query.filter_by(username="e2e_stu").one().id
        program = AdmissionProgram.query.filter_by(program_code=PROGRAM_CODE).one()
        pid, school_name = program.id, program.school_name

    # 1. 第一次登入進新生引導；完成後到「我的五年」
    stu, response = login(app, "e2e_stu")
    assert response.headers["Location"].endswith("/student/welcome")
    assert "data-welcome-step=" in text(stu.get("/student/welcome"))
    response = stu.post("/student/welcome/done", data={"to": ""})
    assert response.headers["Location"].endswith("/student/dashboard")
    home = stu.get("/student/dashboard")
    assert home.status_code == 200
    assert "我的五年" in text(home)

    # 2. 上傳假的成績單 → 辨識中 → 確認擷取資料頁
    response = stu.post("/student/learning-profile/documents", content_type="multipart/form-data",
                        data={"document_type": "transcript", "file": (io.BytesIO(tiny_pdf()), "synthetic.pdf")})
    assert response.status_code == 302
    with app.app_context():
        document = SourceDocument.query.filter_by(owner_id=stu_id).one()
        document_id = document.id
        assert document.status == "extracted"
        result = document.extraction.result_json
    processing = stu.get(response.headers["Location"])
    assert processing.headers["Location"].endswith(f"/student/learning-profile/documents/{document_id}/review")
    review_page = text(stu.get(processing.headers["Location"]))
    assert "確認並儲存" in review_page
    assert f'name="draft_revision" value="{result["draft_revision"]}"' in review_page
    assert "程式設計" in review_page

    # 3. 確認前沒有正式成績；改一門分數、加一門課後按「確認並儲存」才寫入
    with app.app_context():
        assert LearningCourseRecord.query.filter_by(student_id=stu_id).count() == 0
    courses = [dict(course) for course in result["courses"]]
    courses[0].pop("school_year", None)
    courses[0].update(score=95, grade_level="三年級")
    courses.append({"course_name": "資料庫管理", "credits": 3, "score": 88, "grade_level": "二年級"})
    response = stu.post(f"/student/learning-profile/documents/{document_id}/review/confirm", data={
        "draft_revision": result["draft_revision"], "course_input_mode": "json", "scores_unlocked": "1",
        "courses_json": json.dumps(courses, ensure_ascii=False), "credentials_json": "[]",
    })
    assert response.status_code == 302, text(response)
    with app.app_context():
        saved = {c.course_name: c for c in LearningCourseRecord.query.filter_by(student_id=stu_id)}
        assert set(saved) == {"程式設計", "資料庫管理"}
        assert saved["程式設計"].score == 95
        assert saved["資料庫管理"].score == 88
        assert all(c.confirmation_status == "confirmed" for c in saved.values())
        assert db.session.get(SourceDocument, document_id).status == "confirmed"
    assert "程式設計" in text(stu.get("/student/learning-profile"))

    # 4. 新增活動經歷並確認；上傳一個佐證檔案
    response = stu.post("/student/portfolio", data={
        "title": "資訊週志工", "category": "activity", "school_year": "2", "semester": "1",
        "description": "負責報到系統測試"})
    assert response.status_code == 302
    with app.app_context():
        record = Portfolio.query.filter_by(student_id=stu_id, title="資訊週志工").one()
        record_id = record.id
        assert record.status == "draft"
    assert stu.post(f"/student/portfolio/{record_id}/confirm").status_code == 302
    response = stu.post(f"/student/portfolio/{record_id}/evidence", content_type="multipart/form-data",
                        data={"file": (io.BytesIO(tiny_png()), "volunteer.png")})
    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(Portfolio, record_id).status == "confirmed"
        evidence = PortfolioEvidence.query.filter_by(portfolio_id=record_id).one()
        evidence_id = evidence.id
        assert evidence.display_name == "volunteer.png"
    assert "volunteer.png" in text(stu.get(f"/student/portfolio/{record_id}/edit"))
    assert stu.get(f"/student/evidence/{evidence_id}").status_code == 200

    # 5. 推薦排序頁看得到校系；設為目標校系
    matching = stu.get("/student/matching")
    assert matching.status_code == 200
    assert school_name in text(matching)
    response = stu.post("/student/targets", data={"program_id": pid})
    assert response.headers["Location"].endswith(f"/student/targets/{pid}")
    with app.app_context():
        assert StudentTarget.query.filter_by(student_id=stu_id).one().rule_version_id == pid

    # 6. 備審缺件頁：加權項目、已有與缺少的資料；下載 Word
    gap_page = text(stu.get(f"/student/targets/{pid}"))
    with app.app_context():
        gap = analyze_gap(db.session.get(User, stu_id), db.session.get(AdmissionProgram, pid))
    assert gap["items"], "這個校系應該有評分項目"
    for item in gap["items"]:
        assert f"{item['name']}（佔 {item['weight']}%）" in gap_page
    have = [key for item in gap["items"] for key in item["have"]]
    missing = [key for item in gap["items"] for key in item["missing"]]
    assert have and missing, "要同時有已有與缺少的資料"
    assert "piece--have" in gap_page and "piece--missing" in gap_page
    for key in set(have) | set(missing):
        assert ALL_LABELS[key] in gap_page
    package = stu.get(f"/student/targets/{pid}/package.docx")
    assert package.status_code == 200
    assert package.mimetype == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert ".docx" in package.headers["Content-Disposition"]
    with zipfile.ZipFile(io.BytesIO(package.data)) as docx:
        assert "word/document.xml" in docx.namelist()

    # 7. 自傳小幫手：拼圖要先完成；回答 4 題 → 假 AI 產生草稿，每段都有 F 編號；改一段存成第 2 版
    with app.app_context():
        fill_board(db.session.get(User, stu_id))
    assert 'name="motivation"' in text(stu.get(f"/student/autobiography?program_id={pid}"))
    response = stu.post("/student/autobiography/generate", data={"program_id": pid, **ANSWERS})
    assert response.status_code == 302, text(response)
    assert len(fake_ai) == 1
    with app.app_context():
        draft = autobiography_service.latest_draft(db.session.get(User, stu_id), db.session.get(AdmissionProgram, pid))
        first_id, content = draft.id, draft.content_json
    assert content["provider"] == "gemini" and content["version"] == 1
    known = {fact["id"] for fact in content["facts"]}
    assert len(content["paragraphs"]) == 4
    for paragraph in content["paragraphs"]:
        assert paragraph["sources"] and set(paragraph["sources"]) <= known
    draft_page = text(stu.get(f"/student/autobiography?program_id={pid}"))
    for paragraph in content["paragraphs"]:
        for source in paragraph["sources"]:
            assert f'<span class="mono">{source}</span>' in draft_page
    texts = [p["text"] for p in content["paragraphs"]]
    texts[1] = "資訊週擔任志工時，我負責報到系統的測試，整理出十個問題回報給組長。"
    response = stu.post(f"/student/autobiography/{first_id}/save",
                        data={f"paragraph_{i}": value for i, value in enumerate(texts)})
    assert response.status_code == 302
    with app.app_context():
        second = autobiography_service.latest_draft(db.session.get(User, stu_id), db.session.get(AdmissionProgram, pid))
        second_id = second.id
        assert second.content_json["version"] == 2
        assert second.content_json["paragraphs"][1]["text"] == texts[1]
        assert db.session.get(LearningProfileOutput, first_id).content_json["paragraphs"][1]["text"] == ANSWERS["proud"]
    versions_page = text(stu.get(f"/student/autobiography/versions?program_id={pid}"))
    assert "第 1 版" in versions_page and "第 2 版" in versions_page

    # 8. 送導師確認，固定一份快照
    response = stu.post(f"/student/targets/{pid}/review")
    assert response.status_code == 302
    with app.app_context():
        review = PackageReview.query.filter_by(student_id=stu_id).one()
        review_id, snapshot = review.id, review.snapshot_json
        assert review.status == "pending"
    assert snapshot["autobiography"] == {"output_id": second_id, "version": 2}
    fact_texts = [fact["text"] for fact in snapshot["facts"]]
    assert any("程式設計" in fact and "95" in fact for fact in fact_texts)
    assert any("資訊週志工" in fact for fact in fact_texts)
    assert "等待導師確認" in text(stu.get(f"/student/targets/{pid}"))

    # 9. 學生再改自傳（第 3 版），快照與第 2 版內容都不變
    texts[3] = "進二技後想學資料分析與系統設計，之後做系統分析師。"
    response = stu.post(f"/student/autobiography/{second_id}/save",
                        data={f"paragraph_{i}": value for i, value in enumerate(texts)})
    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(PackageReview, review_id).snapshot_json == snapshot
        frozen = db.session.get(LearningProfileOutput, second_id).content_json
        assert frozen["version"] == 2
        assert frozen["paragraphs"][3]["text"] == ANSWERS["future"]

    # 10. 導師在本班看到這位學生與待確認 1 份，選「內容合理，確認」；學生端看到已確認
    teacher, _ = login(app, "e2e_teacher")
    dashboard = text(teacher.get("/teacher/dashboard"))
    assert "SYN9001" in dashboard and "SYN9002" not in dashboard
    assert '<span class="tag tag--warn">1 份</span>' in dashboard
    detail = text(teacher.get(f"/teacher/students/{stu_id}"))
    assert "自傳依據第 2 版（目前第 3 版）" in detail
    assert "內容合理，確認" in detail
    assert f'name="taken_at" value="{snapshot["taken_at"]}"' in detail
    response = teacher.post(f"/teacher/package-reviews/{review_id}",
                            data={"decision": "confirmed", "comment": "", "taken_at": snapshot["taken_at"]})
    assert response.status_code == 302
    assert "notice=" not in response.headers["Location"]
    with app.app_context():
        review = db.session.get(PackageReview, review_id)
        assert review.status == "confirmed"
        assert review.teacher.username == "e2e_teacher"
        assert review.snapshot_json == snapshot
    assert "導師已確認" in text(stu.get(f"/student/targets/{pid}"))

    # 11. 另一位學生與非本班導師看不到這位學生的資料
    other, _ = login(app, "e2e_other")
    other.post("/student/welcome/done", data={"to": ""})
    assert other.get(f"/student/learning-profile/documents/{document_id}/review").status_code == 403
    assert other.get(f"/student/portfolio/{record_id}/edit").status_code in (403, 404)
    assert other.get(f"/student/evidence/{evidence_id}").status_code in (403, 404)
    assert other.post(f"/student/autobiography/{second_id}/save", data={"paragraph_0": "偷改"}).status_code == 403
    assert other.get(f"/student/targets/{pid}/package.docx").status_code == 404
    assert other.get(f"/teacher/students/{stu_id}").status_code == 403
    stranger, _ = login(app, "e2e_stranger")
    assert stranger.get(f"/teacher/students/{stu_id}").status_code == 403
    assert stranger.get(f"/teacher/evidence/{evidence_id}/view").status_code == 403
    assert stranger.get(f"/teacher/documents/{document_id}/view").status_code == 403
    assert stranger.post(f"/teacher/package-reviews/{review_id}",
                         data={"decision": "needs_revision", "comment": "不該能送"}).status_code == 403
    assert "SYN9001" not in text(stranger.get("/teacher/dashboard"))
    with app.app_context():
        assert db.session.get(PackageReview, review_id).status == "confirmed"
        assert LearningProfileOutput.query.filter_by(student_id=stu_id).count() == 3
