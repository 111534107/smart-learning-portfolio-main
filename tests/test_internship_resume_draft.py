"""實習履歷編輯頁：學生自己填欄位、貼圖、存草稿、下載 Word、導師唯讀查看（2026-11-18）。僅為測試資料。"""
import io
from datetime import date
from io import BytesIO

import pytest
from docx import Document
from PIL import Image

from app import create_app
from app.extensions import db
from app.models import AuditLog, ClassAdvisor, CredentialRecord, LearningProfileOutput, Portfolio, StudentProfile, User
from app.services import internship_resume_draft as drafts
from app.services.journey_service import academic_year_of


def png():
    buffer = io.BytesIO()
    Image.new("RGB", (60, 40), (20, 90, 200)).save(buffer, "PNG")
    return buffer.getvalue()


@pytest.fixture
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "TESTING": True, "UPLOAD_FOLDER": str(tmp_path / "up")})
    with app.app_context():
        db.create_all()
        rows = {}
        for name, role in [("stu", "student"), ("other", "student"), ("t1", "teacher"), ("t2", "teacher")]:
            user = User(username=name, display_name=name, role=role, email=f"{name}@example.test")
            user.set_password("pw")
            db.session.add(user)
            rows[name] = user
        db.session.flush()
        year = academic_year_of(date.today()) - 3
        db.session.add(StudentProfile(user_id=rows["stu"].id, student_no="s1", class_name="甲班", admission_year=year))
        db.session.add(StudentProfile(user_id=rows["other"].id, student_no="s2", class_name="乙班", admission_year=year))
        db.session.add(ClassAdvisor(teacher_id=rows["t1"].id, class_name="甲班", school_year=115))
        db.session.add(AuditLog(user_id=rows["stu"].id, action="student.welcome_done"))
        db.session.add(Portfolio(student_id=rows["stu"].id, title="校內程式競賽佳作", category="competition", school_year=3, status="confirmed"))
        db.session.add(CredentialRecord(student_id=rows["stu"].id, credential_name="電腦軟體應用", level="丙級", issue_date=date.today()))
        db.session.commit()
    return app


def login(app, name):
    client = app.test_client()
    client.post("/staff/login" if name.startswith("t") else "/login", data={"username": name, "password": "pw"})
    return client


def upload(client):
    response = client.post("/student/autobiography/images", data={"image": (BytesIO(png()), "a.png")},
                           content_type="multipart/form-data")
    return response.get_json()["id"]


FIELDS = {
    "period": "115年2月23日至6月26日", "birth_0": "95", "birth_1": "1", "birth_2": "2", "gender": "女",
    "phone": "0900-000-000", "addr_0": "臺北", "addr_1": "信義", "addr_2": "測試路1號",
    "conduct": "甲", "lang_en": "中等", "lang_ja": "略懂", "lang_tw": "略懂", "lang_hk": "略懂",
    "abs_range": "1132至1141", "abs_0": "0", "abs_3": "4",
}


def all_text(document):
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return "\n".join(parts)


def test_resume_accepts_pdf_pages_and_persists_address_and_free_bio(app):
    client = login(app, "stu")
    pdf = BytesIO()
    first = Image.new("RGB", (200, 300), "white")
    first.save(pdf, "PDF", save_all=True, append_images=[Image.new("RGB", (240, 320), "blue")])
    response = client.post("/student/internship-resume/pdf",
                           data={"pdf": (BytesIO(pdf.getvalue()), "fixture.pdf")})
    assert response.status_code == 200
    pages = response.json["pages"]
    assert len(pages) == 2
    assert all(client.get(page["url"]).status_code == 200 for page in pages)
    assert login(app, "other").get(pages[0]["url"]).status_code in (403, 404)
    docx = client.post("/student/internship-resume", data={
        **FIELDS, "addr_kind_0": "市", "addr_kind_1": "區",
        "bio_mode": "free", "text_free": "我的自訂自傳", "text_family": "建議段落不應匯出",
        "transcript_image": [page["id"] for page in pages],
        "certimg_image_0": pages[0]["id"], "contest_image_0": pages[1]["id"],
        "abs_image": pages[1]["id"],
    })
    assert docx.status_code == 200
    document = Document(BytesIO(docx.data))
    content = all_text(document)
    assert "臺北市信義區測試路1號" in content
    assert "我的自訂自傳" in content and "建議段落不應匯出" not in content
    assert len(document.inline_shapes) >= 5
    html = client.get("/student/internship-resume").get_data(as_text=True)
    assert 'value="free" selected' in html and "我的自訂自傳" in html
    assert client.post("/student/internship-resume/pdf",
                       data={"pdf": (BytesIO(b"%PDF-broken"), "bad.pdf")}).status_code == 400


def test_save_draft_then_reload_shows_values_and_logs(app):
    client = login(app, "stu")
    response = client.post("/student/internship-resume", data={**FIELDS, "action": "save"})
    assert response.status_code == 302
    page = client.get("/student/internship-resume").get_data(as_text=True)
    for value in ("115年2月23日至6月26日", "0900-000-000", "測試路1號"):
        assert value in page
    with app.app_context():
        assert LearningProfileOutput.query.filter_by(output_type=drafts.OUTPUT_TYPE).count() == 1
        assert AuditLog.query.filter_by(action="student.internship_resume_save").count() == 1


def test_download_fills_fields_images_and_competition_page(app):
    client = login(app, "stu")
    cert_image, contest_image, transcript_image = upload(client), upload(client), upload(client)
    data = {**FIELDS, "certimg_name_0": "電腦軟體應用丙級", "certimg_image_0": cert_image,
            "contest_caption_0": "校內程式競賽佳作", "contest_image_0": contest_image,
            "transcript_image": [transcript_image], "photo": upload(client), "abs_image": upload(client)}
    response = client.post("/student/internship-resume", data=data)
    assert response.status_code == 200
    document = Document(BytesIO(response.data))
    text = all_text(document)
    for expected in ("實習期間：115年2月23日至6月26日", "出生日期： 95 年 1 月 2 日", "■女", "0900-000-000", "臺北 信義",
                     "測試路1號", "■甲", "英語 □精通　■中等　□略懂", "（查詢區間：1132至1141）", "4節", "電腦軟體應用丙級", "校內程式競賽佳作", "競賽"):
        assert expected in text, expected
    baseline = len(Document(BytesIO(login(app, "stu").post("/student/internship-resume", data={}).data)).inline_shapes)
    # 成績單、證照圖片、競賽、缺曠截圖是文件裡的圖；照片則填在學校格式「照片」方框裡（不算內嵌圖）
    assert len(document.inline_shapes) == baseline + 4
    assert _photo_box_has_picture(document) and not _photo_box_has_picture(Document(BytesIO(client.post("/student/internship-resume", data={}).data)))


def test_foreign_image_ids_are_dropped(app):
    foreign = upload(login(app, "other"))
    client = login(app, "stu")
    response = client.post("/student/internship-resume", data={**FIELDS, "certimg_image_0": foreign, "photo": foreign,
                                                               "transcript_image": [foreign, "../../x"]})
    assert response.status_code == 200
    baseline = len(Document(BytesIO(client.post("/student/internship-resume", data={}).data)).inline_shapes)
    assert len(Document(BytesIO(response.data)).inline_shapes) == baseline  # 別人的圖不進履歷
    with app.app_context():
        content = (LearningProfileOutput.query.filter_by(output_type=drafts.OUTPUT_TYPE)
                   .order_by(LearningProfileOutput.id).first().content_json)  # 第一筆＝帶別人圖片那次
        assert content["photo"] == "" and content["certimg"][0]["image"] == "" and content["transcript"] == []


def test_experience_can_be_dragged_into_chosen_autobiography_section(app):
    client = login(app, "stu")
    page = client.get("/student/internship-resume").get_data(as_text=True)
    import re
    exp_id = re.search(r'name="exp" value="(portfolio-\d+)"', page).group(1)
    response = client.post("/student/internship-resume", data={"exp": [exp_id], f"expsec_{exp_id}": "future"})
    document = Document(BytesIO(response.data))
    cell_text = document.tables[1].rows[0].cells[0].text
    assert "未來生涯規劃" in cell_text and "校內程式競賽佳作" in cell_text
    assert "【" not in cell_text  # 小標用粗體，不加括號（照學校 PDF）


def test_class_teacher_can_view_draft_read_only_others_cannot(app):
    client = login(app, "stu")
    client.post("/student/internship-resume", data={**FIELDS, "action": "save"})
    with app.app_context():
        student_id = User.query.filter_by(username="stu").one().id
    teacher = login(app, "t1")
    page = teacher.get(f"/teacher/students/{student_id}/internship-resume")
    assert page.status_code == 200 and "測試路1號" in page.get_data(as_text=True)
    html = page.get_data(as_text=True)
    assert "data-resume-form" not in html and 'name="period"' not in html  # 唯讀，沒有可編輯欄位
    assert login(app, "t2").get(f"/teacher/students/{student_id}/internship-resume").status_code == 403
    assert app.test_client().get(f"/teacher/students/{student_id}/internship-resume").status_code in (401, 403)


def test_rotate_endpoint_swaps_size_and_rejects_other_students_image(app):
    client = login(app, "stu")
    buffer = io.BytesIO()
    Image.new("RGB", (60, 40), (10, 10, 10)).save(buffer, "PNG")
    info = client.post("/student/autobiography/images", data={"image": (BytesIO(buffer.getvalue()), "t.png")},
                       content_type="multipart/form-data").get_json()
    assert (info["width"], info["height"]) == (60, 40)
    turned = client.post(f"/student/autobiography/images/{info['id']}/rotate").get_json()
    assert (turned["width"], turned["height"]) == (40, 60) and turned["id"] != info["id"]
    foreign = upload(login(app, "other"))
    assert client.post(f"/student/autobiography/images/{foreign}/rotate").status_code == 404


def test_autobiography_paragraphs_are_prefilled_into_matching_sections_and_family_stays_empty(app):
    with app.app_context():
        user = User.query.filter_by(username="stu").one()
        db.session.add(LearningProfileOutput(student_id=user.id, output_type="autobiography_ai", source_snapshot_json={},
                                             content_json={"program_id": 1, "version": 1, "paragraphs": [
                                                 {"title": "學習動機", "text": "動機文字甲"},
                                                 {"title": "專題與專長", "text": "專長文字乙"},
                                                 {"title": "未來規劃", "text": "未來文字丙"}]}))
        db.session.commit()
    page = login(app, "stu").get("/student/internship-resume").get_data(as_text=True)
    import re
    texts = dict(re.findall(r'<textarea id="text-(\w+)"[^>]*>(.*?)</textarea>', page, flags=re.S))
    assert "動機文字甲" in texts["study"] and "專長文字乙" in texts["skill"] and "未來文字丙" in texts["future"]
    assert texts["family"].strip() == ""
    assert page.count('data-card="para"') == 3


def test_many_certificates_and_contests_can_be_added_beyond_eight(app):
    client = login(app, "stu")
    data = {"certimg_count": "12", "contest_count": "11"}
    for i in range(12):
        data[f"certimg_name_{i}"] = f"證照{i}"
        data[f"certimg_image_{i}"] = upload(client)
    for i in range(11):
        data[f"contest_caption_{i}"] = f"競賽{i}"
        data[f"contest_image_{i}"] = upload(client)
    baseline = len(Document(BytesIO(client.post("/student/internship-resume", data={}).data)).inline_shapes)
    response = client.post("/student/internship-resume", data=data)
    document = Document(BytesIO(response.data))
    text = all_text(document)
    for i in (0, 7, 8, 11):
        assert f"證照{i}" in text
    for i in (0, 10):
        assert f"競賽{i}" in text
    assert len(document.inline_shapes) == baseline + 12 + 11
    page = client.get("/student/internship-resume").get_data(as_text=True)
    assert 'name="certimg_count" value="12"' in page and 'name="contest_count" value="11"' in page
    assert 'name="certimg_name_11"' in page and 'name="contest_caption_10"' in page


def test_grid_count_is_clamped(app):
    client = login(app, "stu")
    client.post("/student/internship-resume", data={"certimg_count": "9999", "contest_count": "-5", "action": "save"})
    with app.app_context():
        content = LearningProfileOutput.query.filter_by(output_type=drafts.OUTPUT_TYPE).one().content_json
        assert len(content["certimg"]) == drafts.MAX_GRID and len(content["contest"]) == 0  # 上限夾 40、負數夾 0（拿光＝整張表不放）


def test_family_assistant_returns_text_and_falls_back_to_raw_without_ai(app):
    client = login(app, "stu")
    assert client.post("/student/internship-resume/family", data={"raw": ""}).status_code == 400
    response = client.post("/student/internship-resume/family", data={"raw": "我家有四個人，爸媽做小生意。"})
    assert response.status_code == 200
    body = response.get_json()
    assert "爸媽做小生意" in body["text"] and body["note"]
    assert login(app, "t1").post("/student/internship-resume/family", data={"raw": "x"}).status_code == 403


def test_family_assistant_uses_ai_result_when_available(app, monkeypatch):
    from app.services import ai_gateway
    seen = {}

    def fake(prompt, schema, documents=(), known=(), callers=None):
        seen["prompt"] = prompt
        return {"text": "我來自一個互相支持的家庭。"}, "fake"

    monkeypatch.setattr(ai_gateway, "generate_json", fake)
    body = login(app, "stu").post("/student/internship-resume/family", data={"raw": "爸媽做生意"}).get_json()
    assert body["text"] == "我來自一個互相支持的家庭。" and "爸媽做生意" in seen["prompt"]


def test_course_missing_from_the_year_table_is_left_blank(app):
    from app.models import CurriculumCourse, CurriculumVersion
    with app.app_context():
        year = User.query.filter_by(username="stu").one().student_profile.admission_year
        version = CurriculumVersion(admission_year=year, status="published", source_url="https://example.test", file_sha256="x" * 64)
        version.courses.append(CurriculumCourse(name="資訊科技", credits=2, sort_order=1))
        db.session.add(version)
        db.session.commit()
    document = Document(BytesIO(login(app, "stu").post("/student/internship-resume", data={}).data))
    cells = {}
    for row in document.tables[0].rows[5:15]:
        texts = []
        for cell in row.cells:
            if not texts or cell.text != texts[-1]:
                texts.append(cell.text)
        for i in range(0, len(texts) - 1, 2):
            cells[texts[i].strip()] = texts[i + 1].strip()
    assert cells.get("資訊科技") == "2"     # 年度科目表有：照學校格式填
    assert cells.get("管理學") == ""         # 年度科目表沒有：學分留白


def test_typed_certificate_cells_are_used_instead_of_cards(app):
    client = login(app, "stu")
    data = {"certcells_present": "1", "cert_international_0": "Google AI | Explore ML Beginner Track",
            "cert_labor_0": "電腦軟體應用丙級", "cert_domestic_0": "中文看打輸入丙級", "cred": ["1", "2"]}
    document = Document(BytesIO(client.post("/student/internship-resume", data=data).data))
    text = all_text(document)
    for name in ("Google AI | Explore ML Beginner Track", "電腦軟體應用丙級", "中文看打輸入丙級"):
        assert name in text, name
    assert "ITS" not in text  # 沒有在格子裡的卡片不會被帶進去
    with app.app_context():
        content = LearningProfileOutput.query.filter_by(output_type=drafts.OUTPUT_TYPE).one().content_json
        assert content["certcells"]["international"][0] == "Google AI | Explore ML Beginner Track"
    page = client.get("/student/internship-resume").get_data(as_text=True)
    assert 'name="cert_international_0" value="Google AI | Explore ML Beginner Track"' in page


def test_pages_can_be_left_out_of_the_word_file(app):
    client = login(app, "stu")
    full = Document(BytesIO(client.post("/student/internship-resume", data={}).data))
    assert any("缺曠記錄" in p.text for p in full.paragraphs)
    assert any(t.rows[0].cells[0].text.strip() == "成績單" for t in full.tables)
    only_contest = {"inc_present": "1", "inc_contest": "1"}
    trimmed = Document(BytesIO(client.post("/student/internship-resume", data=only_contest).data))
    assert not any("缺曠記錄" in p.text for p in trimmed.paragraphs)
    assert not any(t.rows[0].cells[0].text.strip() == "成績單" for t in trimmed.tables)
    assert not any(p.text.strip() == "證照" for p in trimmed.paragraphs)
    assert any("履歷" in p.text for p in trimmed.paragraphs)  # 其他頁還在
    page = client.get("/student/internship-resume").get_data(as_text=True)
    assert page.count('data-include="') == 4


def test_my_uploaded_file_can_be_imported_as_an_image_but_only_by_the_owner(app, tmp_path):
    from hashlib import sha256
    from app.models import SourceDocument
    from app.services import storage_service
    with app.app_context():
        owner = User.query.filter_by(username="stu").one()
        data = png()
        location = storage_service.save(data, owner.id, "learning-profile", "成績單.png")
        doc = SourceDocument(owner_id=owner.id, document_type="transcript", display_name="成績單.png", file_path=location,
                             sha256=sha256(data).hexdigest(), status="confirmed")
        bad = SourceDocument(owner_id=owner.id, document_type="transcript", display_name="說明.txt", file_path=location,
                             sha256="0" * 64, status="confirmed")
        db.session.add_all([doc, bad])
        db.session.commit()
        doc_id, bad_id = doc.id, bad.id
    client = login(app, "stu")
    page = client.get("/student/internship-resume").get_data(as_text=True)
    assert f'data-doc-import="{doc_id}"' in page and f'data-doc-import="{bad_id}"' not in page
    body = client.post(f"/student/internship-resume/import/{doc_id}").get_json()
    assert body["width"] == 60 and body["height"] == 40
    assert client.get(body["url"]).status_code == 200
    assert client.post(f"/student/internship-resume/import/{bad_id}").status_code == 400
    assert login(app, "other").post(f"/student/internship-resume/import/{doc_id}").status_code == 404


def _photo_box_has_picture(document):
    """學校格式的照片方框（畫在格子裡的 wps 圖形）有沒有被填上照片。"""
    wps = "{http://schemas.microsoft.com/office/word/2010/wordprocessingShape}"
    a = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    return any(shape.find(wps + "spPr") is not None and shape.find(wps + "spPr").find(a + "blipFill") is not None
               for shape in document.element.body.iter(wps + "wsp"))


def _cert_image_table(document):
    return next((t for t in document.tables if t.rows and t.rows[0].cells[0].text.strip() == "證照圖片"), None)


def test_student_can_remove_certificate_cells_down_to_what_they_have(app):
    client = login(app, "stu")
    full = _cert_image_table(Document(BytesIO(client.post("/student/internship-resume", data={}).data)))
    assert len(full.rows) == 8                      # 預設 8 格＝4 組（圖片列＋名稱列）
    two = Document(BytesIO(client.post("/student/internship-resume", data={
        "certimg_count": "3", "certimg_name_0": "電腦軟體應用丙級", "certimg_name_1": "電腦硬體裝修丙級",
        "certimg_name_2": "第三張"}).data))
    table = _cert_image_table(two)
    assert len(table.rows) == 4                     # 3 格＝2 組；單數最後一格空的不留字樣
    text = "\n".join(c.text for r in table.rows for c in r.cells)
    assert "第三張" in text and text.count("證照圖片") == 3
    assert "證照名稱" not in text  # 有名稱的格子只寫名稱（照學校 PDF），單數時最後空的那格什麼字樣都不留
    none = Document(BytesIO(client.post("/student/internship-resume", data={"certimg_count": "0"}).data))
    assert _cert_image_table(none) is None
    assert not any(p.text.strip() == "證照" for p in none.paragraphs)


def test_related_certificate_table_rows_follow_the_students_choice(app):
    client = login(app, "stu")

    def rows(count):
        data = {"certcells_present": "1", "certrows": str(count), "cert_labor_0": "電腦軟體應用丙級"}
        doc = Document(BytesIO(client.post("/student/internship-resume", data=data).data))
        sheet = doc.tables[0]
        header = next(i for i, r in enumerate(sheet.rows) if r.cells[0].text.strip() == "勞動部")
        end = next(i for i, r in enumerate(sheet.rows) if r.cells[0].text.strip() == "語文能力")
        return end - header - 1, all_text(doc)

    assert rows(6)[0] == 6
    three, text = rows(3)
    assert three == 3 and "電腦軟體應用丙級" in text
    assert rows(9)[0] == 9
    page = client.get("/student/internship-resume").get_data(as_text=True)
    assert 'name="certrows" value="9"' in page and 'name="cert_labor_8"' in page


def test_resume_can_be_saved_to_the_students_cloud_folder(app, monkeypatch):
    from app.services import storage_service
    seen = {}

    def fake_save(data, owner_id, folder, filename):
        seen.update(data=data, owner=owner_id, folder=folder, filename=filename)
        return "drive:abc123/" + filename

    monkeypatch.setattr(storage_service, "save", fake_save)
    client = login(app, "stu")
    response = client.post("/student/internship-resume", data={**FIELDS, "action": "cloud"})
    assert response.status_code == 302 and "cloud=drive" in response.headers["Location"]
    assert seen["folder"] == "internship-resume" and seen["filename"].startswith("實習履歷-") and seen["filename"].endswith(".docx")
    assert Document(BytesIO(seen["data"])) and "0900-000-000" in all_text(Document(BytesIO(seen["data"])))
    page = client.get("/student/internship-resume?cloud=drive").get_data(as_text=True)
    assert "存到你的 Google 雲端硬碟" in page and "存到我的雲端" in page
    with app.app_context():
        assert AuditLog.query.filter_by(action="student.internship_resume_cloud", user_id=seen["owner"]).count() == 1


def test_cloud_save_falls_back_to_local_and_says_so(app, monkeypatch):
    from app.services import storage_service
    monkeypatch.setattr(storage_service, "save", lambda data, owner_id, folder, filename: f"{folder}/{owner_id}/{filename}")
    client = login(app, "stu")
    response = client.post("/student/internship-resume", data={"action": "cloud"})
    assert "cloud=local" in response.headers["Location"]
    assert "還沒連線" in client.get("/student/internship-resume?cloud=local").get_data(as_text=True)
    monkeypatch.setattr(storage_service, "save", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    assert "cloud=fail" in client.post("/student/internship-resume", data={"action": "cloud"}).headers["Location"]


def test_email_is_filled_in_the_page_not_after_download(app):
    client = login(app, "stu")
    page = client.get("/student/internship-resume").get_data(as_text=True)
    assert 'name="email"' in page and 'value="stu@example.test"' in page and "下載後自己填" not in page
    document = Document(BytesIO(client.post("/student/internship-resume", data={"email": "me@school.example.test"}).data))
    assert "me@school.example.test" in all_text(document)
    saved = client.get("/student/internship-resume").get_data(as_text=True)
    assert 'value="me@school.example.test"' in saved


def test_lines_around_the_photo_are_hidden_like_the_school_pdf(app):
    from docx.oxml.ns import qn
    document = Document(BytesIO(login(app, "stu").post("/student/internship-resume", data={}).data))
    sheet = document.tables[0]
    from app.services import internship_resume as resume
    contact, photo = resume._unique_cells(sheet.rows[1])[:2]
    address = resume._unique_cells(sheet.rows[2])[0]

    def hidden(cell, side):
        borders = cell._tc.tcPr.find(qn("w:tcBorders"))
        node = borders.find(qn(f"w:{side}")) if borders is not None else None
        return node is not None and node.get(qn("w:val")) == "nil"

    assert hidden(contact, "right") and hidden(contact, "bottom")
    assert hidden(photo, "left") and hidden(photo, "bottom")
    assert hidden(address, "top")
    order = [child.tag.split("}")[1] for child in contact._tc.tcPr.find(qn("w:tcBorders"))]
    assert order == sorted(order, key=["top", "left", "bottom", "right"].index)  # 子項順序符合結構定義


def test_side_panel_is_a_collapsible_drawer_with_per_page_blocks(app):
    page = login(app, "stu").get("/student/internship-resume").get_data(as_text=True)
    assert "data-side-toggle" in page and 'aria-expanded="false"' in page
    for key in ("basic", "bio", "transcript", "cert", "contest", "absence"):
        assert f'data-focus-page="{key}"' in page, key
    assert page.count("data-for=") >= 4  # 小助手、證照卡、經歷卡、收納匣（有系統自傳、原始檔時還有兩塊）各標明哪幾頁用得到


# ---------- 用 Word 實際轉 PDF 檢查後修的版面問題（2026-11-19）----------

def _body_blocks(document):
    return [child for child in document.element.body if not child.tag.endswith("}sectPr")]


def test_absence_page_sample_screenshot_is_replaced_or_removed(app):
    """學校空白檔在缺曠記錄放了別人的範例截圖：學生貼了自己的就換掉（同一位置），沒貼就拿掉，不能留別人的資料。"""
    client = login(app, "stu")

    def inline_paragraphs(document):
        return [p for p in document.paragraphs if p._p.xpath(".//wp:inline")]

    blank = Document(BytesIO(client.post("/student/internship-resume", data={}).data))
    assert inline_paragraphs(blank) == []            # 範例截圖拿掉
    shot = upload(client)
    mine = Document(BytesIO(client.post("/student/internship-resume", data={"abs_image": shot, "abs_range": "1132至1141"}).data))
    found = inline_paragraphs(mine)
    assert len(found) == 1                           # 只有學生自己的一張
    texts = [p.text for p in mine.paragraphs]
    assert texts.index(found[0].text) >= 0 and any("查詢區間：1132至1141" in t for t in texts)
    order = [p._p for p in mine.paragraphs]
    caption = next(p._p for p in mine.paragraphs if "查詢區間" in p.text)
    assert order.index(found[0]._p) > order.index(caption)   # 在「查詢區間」下面（學校 PDF 的位置），不是接在文件最後面


def test_contest_page_starts_on_its_own_page_and_looks_like_the_certificate_page(app):
    client = login(app, "stu")
    image = upload(client)
    document = Document(BytesIO(client.post("/student/internship-resume", data={
        "certimg_count": "2", "certimg_image_0": image, "certimg_name_0": "證照甲",
        "contest_count": "2", "contest_image_0": image, "contest_caption_0": "競賽甲"}).data))
    blocks = _body_blocks(document)

    from docx.text.paragraph import Paragraph

    def text(el):
        return Paragraph(el, document._body).text.strip() if el.tag.endswith("}p") else "".join(el.itertext()).strip()

    index = {name: next(i for i, b in enumerate(blocks) if b.tag.endswith("}p") and text(b) == name) for name in ("證照", "競賽")}
    assert index["證照"] < index["競賽"]
    previous = blocks[index["競賽"] - 1]
    assert previous.tag.endswith("}p") and previous.xpath('.//w:br[@w:type="page"]')   # 競賽前面有換頁
    assert blocks[index["競賽"] + 1].tag.endswith("}tbl")                              # 標題後面接表格
    assert "競賽甲" in text(blocks[index["競賽"] + 1]) and "證照名稱" not in text(blocks[index["競賽"] + 1])
    absence = next(i for i, b in enumerate(blocks) if b.tag.endswith("}p") and text(b) == "缺曠記錄")
    assert blocks[absence - 1].xpath('.//w:br[@w:type="page"]')                        # 缺曠記錄前面也換頁


def test_no_blank_trailing_blocks_after_pages_are_left_out(app):
    client = login(app, "stu")
    document = Document(BytesIO(client.post("/student/internship-resume", data={
        "certimg_count": "0", "contest_count": "0", "inc_present": "1"}).data))   # 成績單、證照、缺曠都不放
    blocks = _body_blocks(document)
    tail = blocks[-1]
    assert tail.tag.endswith("}p") and not "".join(tail.itertext()).strip()          # 極小的收尾段落
    assert tail.xpath('./w:pPr/w:spacing[@w:line="20"]')
    before = blocks[-2]
    assert before.tag.endswith("}tbl") and "自傳" in "".join(before.itertext())       # 前面緊接自傳表格，沒有空段落或換頁
    assert not any(b.xpath('.//w:br[@w:type="page"]') for b in blocks[blocks.index(before) + 1:])


def test_biography_keeps_its_title_and_drops_the_guide_lines(app):
    client = login(app, "stu")
    document = Document(BytesIO(client.post("/student/internship-resume", data={"text_family": "我來自一個家庭。"}).data))
    cell = document.tables[1].rows[0].cells[0]
    assert cell.paragraphs[0].text.strip() == "自傳"                                  # 框裡最上面的「自傳」標題還在
    assert "我來自一個家庭。" in cell.text
    assert not any(p.text.strip().startswith("自傳下列各項內容請參酌使用") for p in document.paragraphs)
    blank = Document(BytesIO(client.post("/student/internship-resume", data={}).data))
    assert any(p.text.strip().startswith("自傳下列各項內容請參酌使用") for p in blank.paragraphs)   # 沒內容時保留學校的提示


def test_more_related_certificate_rows_are_squeezed_so_the_table_stays_on_one_page(app):
    client = login(app, "stu")
    data = {"certcells_present": "1", "certrows": "9", "cert_labor_0": "電腦軟體應用丙級"}
    document = Document(BytesIO(client.post("/student/internship-resume", data=data).data))
    sheet = document.tables[0]
    header = next(i for i, r in enumerate(sheet.rows) if r.cells[0].text.strip() == "勞動部")
    heights = {sheet.rows[i].height for i in range(header + 1, header + 10)}
    assert len(heights) == 1 and None not in heights and heights.pop() < 360000        # 每列都縮矮（小於 1 公分）


def test_reset_starts_blank_and_keeps_previous_versions(app):
    """清空重填：畫面回到空白，之前存的版本保留（不實體刪除），並留操作紀錄。"""
    client = login(app, "stu")
    client.post("/student/internship-resume", data={**FIELDS, "action": "save"})
    assert "0900-000-000" in client.get("/student/internship-resume").get_data(as_text=True)

    response = client.post("/student/internship-resume/reset")

    assert response.status_code == 302 and "reset=1" in response.headers["Location"]
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "已清空" in page and "0900-000-000" not in page and "測試路1號" not in page
    with app.app_context():
        assert LearningProfileOutput.query.filter_by(output_type=drafts.OUTPUT_TYPE).count() == 2
        assert AuditLog.query.filter_by(action="student.internship_resume_reset").count() == 1
