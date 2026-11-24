"""獎懲記錄：學生從學校系統下載後上傳，AI 逐列讀出並分類，學生確認後才存入。"""
import io

from app.extensions import db
from app.models import Portfolio, SchoolAwardRecord, SourceDocument
from app.services import award_record_service as service
from tests.test_student_records import login, records_app


ROWS = [
    {"date": "2025/12/30", "name": "嘉獎", "count": 1, "reason": "1141學期協助資管科麗山國中社團活動共1次", "revoked": ""},
    {"date": "2025/12/22", "name": "嘉獎", "count": 1,
     "reason": "1141學期參加2025第36屆AERC亞洲智慧型機器人大賽B05機器人向前衝高中高職A組獲得佳作", "revoked": ""},
    {"date": "2025/06/10", "name": "嘉獎", "count": 1, "reason": "1132學期JAVA程式語言小老師表現優異", "revoked": ""},
    {"date": "2025/03/01", "name": "警告", "count": 1, "reason": "1132學期上課遲到", "revoked": ""},
    {"date": "2024/06/12", "name": "嘉獎", "count": 2, "reason": "1122學期協助資管科永吉國中社團共5次", "revoked": "已銷"},
]


def test_classify_uses_editable_rules():
    assert service.classify("1141學期協助資管科麗山國中社團活動共1次") == "service"
    assert service.classify("參加AERC亞洲機器人運動競技大賽獲得佳作") == "competition"
    assert service.classify("1132學期JAVA程式語言小老師表現優異") == "leadership"
    assert service.classify("無法判斷的事由") is None


def test_semester_is_read_from_reason_prefix():
    assert service.parse_semester("1141學期協助資管科") == (114, 1)
    assert service.parse_semester("1132熱心班級事務") == (113, 2)
    assert service.parse_semester("協助活動") == (None, None)
    # 學校系統偶爾寫成括號或橫線格式
    assert service.parse_semester("111(1)協助科上活動") == (111, 1)
    assert service.parse_semester("111（2）參加比賽") == (111, 2)
    assert service.parse_semester("111-1熱心公益") == (111, 1)


def test_draft_skips_punishments_and_revoked_rows():
    draft = service.build_draft(ROWS)

    reasons = [row["reason"] for row in draft["rows"]]
    assert len(reasons) == 3
    assert not any("遲到" in reason for reason in reasons)
    assert not any("永吉" in reason for reason in reasons)
    assert draft["rows"][0]["category"] == "service"
    assert draft["rows"][1]["category"] == "competition"
    assert draft["rows"][0]["school_year"] == 114
    assert any("已略過 1 筆已銷過" in warning for warning in draft["warnings"])
    # 懲處不進活動與經歷，但要保存
    assert [p["name"] for p in draft["punishments"]] == ["警告"]
    assert draft["punishments"][0]["reason"] == "1132學期上課遲到"


def test_ai_category_is_used_only_when_rules_do_not_match():
    draft = service.build_draft([
        {"date": "2025/06/11", "name": "嘉獎", "count": 1, "reason": "1132參與校園活動", "category": "activity"},
        {"date": "2025/06/11", "name": "嘉獎", "count": 1, "reason": "1132協助國中社團", "category": "activity"},
        {"date": "2025/06/11", "name": "嘉獎", "count": 1, "reason": "1132其他", "category": "不存在"},
    ])

    assert [row["category"] for row in draft["rows"]] == ["activity", "service", ""]


def _upload(client, name="award.pdf"):
    return client.post("/student/award-records", data={
        "file": (io.BytesIO(b"%PDF-1.4 award"), name),
    }, content_type="multipart/form-data")


def test_upload_without_ai_goes_to_review_with_blank_rows(tmp_path):
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)

    response = _upload(client)

    assert response.status_code == 302
    assert "/review" in response.headers["Location"]
    html = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "尚未接上 AI" in html
    assert 'name="reason"' in html
    with app.app_context():
        assert SourceDocument.query.one().document_type == "award_record"


def test_upload_with_ai_shows_classified_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "extract_rows", lambda path, name, known=(): (ROWS, []))
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)

    html = client.get(_upload(client).headers["Location"]).get_data(as_text=True)

    assert "麗山國中" in html
    assert 'value="competition" selected' in html
    # 懲處顯示在獨立的懲處區塊，不混進可勾選的經歷列
    assert "懲處紀錄（會保存，不放進活動與經歷）" in html
    assert 'name="reason" value="1132學期上課遲到"' not in html


def test_confirm_creates_records_with_school_source(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "extract_rows", lambda path, name, known=(): (ROWS, []))
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    review_url = _upload(client).headers["Location"]

    response = client.post(review_url.replace("/review", "/confirm"), data={
        "include": ["0", "1"],
        "reason": [ROWS[0]["reason"], ROWS[1]["reason"], ROWS[2]["reason"]],
        "category": ["service", "competition", "leadership"],
        "school_year": ["114", "114", "113"],
        "semester": ["1", "1", "2"],
        "detail": ["2025/12/30 嘉獎1次", "2025/12/22 嘉獎1次", "2025/06/10 嘉獎1次"],
    })

    assert response.status_code == 302
    with app.app_context():
        records = Portfolio.query.order_by(Portfolio.id).all()
        assert [r.category for r in records] == ["service", "competition"]
        assert records[0].source == "award_record"
        assert records[0].source_label == "學校獎懲記錄"
        assert records[0].source_document_id == SourceDocument.query.one().id
        assert (records[0].school_year, records[0].semester) == (4, 1)  # 111 入學，114 學年度是專四
        # 懲處保存在獎懲表，但不進活動與經歷
        assert not any("遲到" in r.title for r in records)
        punishments = SchoolAwardRecord.query.filter_by(record_type="punishment").all()
        assert [(p.name, p.reason) for p in punishments] == [("警告", "1132學期上課遲到")]


def test_confirm_twice_does_not_duplicate(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "extract_rows", lambda path, name, known=(): (ROWS, []))
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    confirm_url = _upload(client).headers["Location"].replace("/review", "/confirm")
    data = {"include": ["0"], "reason": [ROWS[0]["reason"]], "category": ["service"],
            "school_year": ["114"], "semester": ["1"], "detail": [""]}

    client.post(confirm_url, data=data)
    client.post(confirm_url, data=data)

    with app.app_context():
        assert Portfolio.query.count() == 1


def test_confirm_rejects_row_without_valid_category(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "extract_rows", lambda path, name, known=(): (ROWS, []))
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    confirm_url = _upload(client).headers["Location"].replace("/review", "/confirm")

    response = client.post(confirm_url, data={
        "include": ["0"], "reason": ["某事由"], "category": [""],
        "school_year": [""], "semester": [""], "detail": [""],
    })

    assert response.status_code == 400
    assert "請選擇類別" in response.get_data(as_text=True)
    with app.app_context():
        assert Portfolio.query.count() == 0


def test_other_student_cannot_open_review(tmp_path):
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    review_url = _upload(client).headers["Location"]
    with app.app_context():
        from app.models import User
        other = User(username="other", display_name="別人", role="student")
        other.set_password("pw")
        db.session.add(other)
        db.session.commit()
    other_client = app.test_client()
    other_client.post("/login", data={"username": "other", "password": "pw"})

    assert other_client.get(review_url).status_code == 403


def test_portfolio_shows_source_and_award_entry(tmp_path):
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    with app.app_context():
        from app.models import User
        student = User.query.filter_by(username="stu").one()
        db.session.add(Portfolio(student_id=student.id, title="協助國中社團", category="service",
                                 source="award_record"))
        db.session.commit()

    html = client.get("/student/portfolio").get_data(as_text=True)

    assert "/student/award-records" in html
    assert "學校獎懲記錄" in html


def test_award_documents_are_not_listed_with_transcripts(tmp_path):
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    _upload(client, "獎懲記錄.pdf")

    html = client.get("/student/learning-profile").get_data(as_text=True)

    assert "獎懲記錄.pdf" not in html


def test_autobiography_facts_mention_school_source(tmp_path):
    app = records_app(tmp_path)
    with app.app_context():
        from app.models import User
        from app.services.autobiography_service import build_facts
        student = User.query.filter_by(username="stu").one()
        db.session.add(Portfolio(student_id=student.id, title="協助國中社團", category="service", source="award_record",
                                 status="confirmed"))
        db.session.commit()

        class Program:
            items = []

        facts = build_facts(student, Program())

    assert any("來源：學校獎懲記錄" in item["text"] for item in facts["items"])


def test_perfect_attendance_is_default_off_but_other_rewards_stay_on():
    draft = service.build_draft([
        {"date": "2025/06/30", "name": "嘉獎", "count": 1, "reason": "1132學期全勤", "revoked": ""},
        {"date": "2025/06/10", "name": "嘉獎", "count": 1, "reason": "1132學期JAVA程式語言小老師表現優異", "revoked": ""},
    ])

    assert [row["include"] for row in draft["rows"]] == [False, True]
    assert any("全勤" in warning and "預設不勾選" in warning for warning in draft["warnings"])


def test_same_reason_in_different_terms_is_not_treated_as_duplicate(tmp_path, monkeypatch):
    rows = [
        {"date": "2025/06/30", "name": "嘉獎", "count": 1, "reason": "全勤", "revoked": ""},
        {"date": "2025/12/30", "name": "嘉獎", "count": 1, "reason": "全勤", "revoked": ""},
    ]
    monkeypatch.setattr(service, "extract_rows", lambda path, name, known=(): (rows, []))
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    confirm_url = _upload(client).headers["Location"].replace("/review", "/confirm")

    client.post(confirm_url, data={
        "include": ["0", "1"], "reason": ["全勤", "全勤"], "category": ["activity", "activity"],
        "school_year": ["114", "114"], "semester": ["1", "2"], "detail": ["2025/06/30 嘉獎1次", "2025/12/30 嘉獎1次"],
    })

    with app.app_context():
        assert Portfolio.query.count() == 2
        assert SchoolAwardRecord.query.filter_by(record_type="reward").count() == 2


def test_same_row_is_saved_once_even_after_student_deletes_portfolio(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "extract_rows", lambda path, name, known=(): (ROWS, []))
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    confirm_url = _upload(client).headers["Location"].replace("/review", "/confirm")
    draft_key = service.build_draft(ROWS)["rows"][0]["key"]
    data = {"include": ["0"], "reason": [ROWS[0]["reason"]], "category": ["service"],
            "school_year": ["114"], "semester": ["1"], "detail": ["2025/12/30 嘉獎1次"], "key": [draft_key]}

    client.post(confirm_url, data=data)
    with app.app_context():
        Portfolio.query.delete()
        db.session.commit()
    client.post(confirm_url, data=data)

    with app.app_context():
        assert Portfolio.query.count() == 0  # 刪掉的不會冒回來


def test_punishments_are_saved_with_revoked_flag_and_listed_on_their_own_page(tmp_path, monkeypatch):
    rows = [
        {"date": "2025/03/01", "name": "警告", "count": 1, "reason": "1132學期上課遲到", "revoked": ""},
        {"date": "2024/06/12", "name": "小過", "count": 1, "reason": "1122學期未繳交作業", "revoked": "已銷"},
    ]
    monkeypatch.setattr(service, "extract_rows", lambda path, name, known=(): (rows, []))
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    review_url = _upload(client).headers["Location"]
    confirm_url = review_url.replace("/review", "/confirm")

    client.post(confirm_url, data={"include": [], "reason": [""], "category": [""],
                                   "school_year": [""], "semester": [""], "detail": [""]})

    with app.app_context():
        saved = SchoolAwardRecord.query.filter_by(record_type="punishment").order_by(SchoolAwardRecord.id).all()
        assert [(s.name, s.revoked) for s in saved] == [("警告", ""), ("小過", "已銷")]
        assert Portfolio.query.count() == 0
    html = client.get("/student/discipline-records").get_data(as_text=True)
    assert "上課遲到" in html
    assert "未繳交作業" in html
    assert "不會出現在「活動與經歷」" in html


def test_punishments_are_not_shown_in_portfolio_or_autobiography(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "extract_rows", lambda path, name, known=(): (ROWS, []))
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    confirm_url = _upload(client).headers["Location"].replace("/review", "/confirm")
    client.post(confirm_url, data={"include": [], "reason": [""], "category": [""],
                                   "school_year": [""], "semester": [""], "detail": [""]})

    html = client.get("/student/portfolio").get_data(as_text=True)
    assert "上課遲到" not in html


# ---- 貼上學校獎懲表格（組員 111534107/smart-learning-portfolio-main 7282998 移入；不送 AI） ----

PASTED = "\n".join("\t".join(cells) for cells in [
    ["學號", "姓名", "獎懲日期", "獎懲名稱", "數量", "獎懲事由", "銷過"],
    ["111534100", "測試學生", "2025/12/22", "嘉獎", "1", "1141學期參加測試機器人大賽獲得佳作", ""],
    ["111534100", "測試學生", "2025/06/13", "嘉獎", "1", "1132學期協助資管科國中入班宣導活動", ""],
    ["111534100", "測試學生", "2023/05/30", "小功", "1", "1112學期升旗全勤(個人)", ""],
    ["111534100", "測試學生", "2023/03/01", "警告", "1", "1112學期未到", "已銷過"],
])


def test_parse_pasted_table_reads_rows_without_ai():
    rows = service.parse_pasted_table(PASTED, "111534100")

    assert len(rows) == 4
    assert rows[0] == {"date": "2025/12/22", "name": "嘉獎", "count": 1,
                       "reason": "1141學期參加測試機器人大賽獲得佳作", "revoked": ""}
    assert rows[3]["revoked"] == "已銷過"


def test_parse_pasted_table_accepts_extra_columns_without_losing_revoked_status():
    table = "\n".join(line + "\t備註" for line in PASTED.split("\n"))
    rows = service.parse_pasted_table(table, "111534100")
    assert len(rows) == 4
    assert rows[3]["revoked"] == "已銷過"


def test_parse_pasted_table_rejects_other_students_and_bad_header():
    import pytest
    with pytest.raises(ValueError, match="學號與目前帳號不一致"):
        service.parse_pasted_table(PASTED, "111534199")
    with pytest.raises(ValueError, match="表頭"):
        service.parse_pasted_table("隨便\t一段\t文字\n1\t2\t3", "111534100")
    with pytest.raises(ValueError, match="1000 筆"):
        service.parse_pasted_table(PASTED.split("\n")[0] + "\n" + "\n".join([PASTED.split("\n")[1]] * 1001), "111534100")


def test_paste_route_builds_draft_without_calling_gemini(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("貼上不可以呼叫 AI")
    monkeypatch.setattr(service.gemini_client, "generate_json", boom)
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)

    response = client.post("/student/award-records/paste", data={"pasted_table": PASTED})

    assert response.status_code == 302 and "/review" in response.headers["Location"]
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "你貼上的獎懲記錄" in page and "測試機器人大賽" in page
    assert "AI 讀的字" not in page
    with app.app_context():
        document = SourceDocument.query.filter_by(document_type="award_record").one()
        assert document.extraction.provider == "paste"


def test_paste_route_shows_error_and_keeps_text(tmp_path):
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)

    response = client.post("/student/award-records/paste", data={"pasted_table": "亂貼的內容"})

    assert response.status_code == 400
    page = response.get_data(as_text=True)
    assert "表頭" in page and "亂貼的內容" in page


def test_upload_page_recommends_paste_and_warns_pdf_goes_to_gemini(tmp_path):
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)

    page = client.get("/student/award-records").get_data(as_text=True)

    assert "data-award-paste" in page and "不會送給 AI" in page and "Google Gemini" in page
    assert 'href="/student/discipline-records"' in page
    assert "查看已保存的懲處紀錄" in page


def test_enthusiastic_class_service_suggests_leadership():
    draft = service.build_draft([
        {"date": "2025/06/30", "name": "嘉獎", "count": 1, "reason": "1132熱心班級事務", "revoked": ""}
    ])
    assert draft["rows"][0]["category"] == "leadership"


def test_enthusiastic_charity_is_not_mistaken_for_leadership():
    assert service.classify("1132熱心公益") == "service"
    assert service.classify("1132熱心服務") == "service"
    assert service.classify("1132熱心") is None


def test_award_paste_routes_school_attendance_to_review_without_saving_source(tmp_path):
    from app.models import AttendanceSummary

    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    text = "114/10/03\t病假\t病假\n項目\t曠課\t病假\n合計\t0\t2"

    response = client.post("/student/award-records/paste", data={"pasted_table": text})
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "核對學期合計" in html and 'name="病假" value="2"' in html
    assert 'action="/student/attendance-records/confirm"' in html
    assert "114/10/03" not in html
    assert response.headers["Cache-Control"] == "no-store"
    with app.app_context():
        assert AttendanceSummary.query.count() == 0
        assert SourceDocument.query.count() == 0


def test_award_paste_explains_how_to_import_attendance_daily_rows(tmp_path):
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)

    response = client.post("/student/award-records/paste",
                           data={"pasted_table": "114/10/03\t病假\t病假"})
    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert "缺曠" in html and "底部" in html and "無法辨識表格欄位" not in html
    assert html.count('action="/student/attendance-records"') == 2
    assert "114/10/03" not in html


def test_unconfirmed_award_import_can_be_deleted_and_returns_to_award_page(tmp_path):
    """2026-11-19 刪除原則：還沒確認的獎懲匯入可以刪，刪完回獎懲頁；已確認的不能刪。"""
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    client.post("/student/award-records/paste", data={"pasted_table": PASTED})
    with app.app_context():
        document_id = SourceDocument.query.filter_by(document_type="award_record").one().id
    page = client.get("/student/award-records").get_data(as_text=True)
    assert f"/student/learning-profile/documents/{document_id}/delete" in page

    response = client.post(f"/student/learning-profile/documents/{document_id}/delete",
                           data={"next": "/student/award-records"})

    assert response.status_code == 302 and response.headers["Location"].endswith("/student/award-records")
    with app.app_context():
        assert SourceDocument.query.filter_by(document_type="award_record").count() == 0


def test_confirmed_award_import_cannot_be_deleted(tmp_path):
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    client.post("/student/award-records/paste", data={"pasted_table": PASTED})
    with app.app_context():
        document = SourceDocument.query.filter_by(document_type="award_record").one()
        document.status = "confirmed"
        db.session.commit()
        document_id = document.id
    assert f"/documents/{document_id}/delete" not in client.get("/student/award-records").get_data(as_text=True)
    client.post(f"/student/learning-profile/documents/{document_id}/delete")
    with app.app_context():
        assert db.session.get(SourceDocument, document_id) is not None


def test_external_next_is_ignored_after_delete(tmp_path):
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)
    client.post("/student/award-records/paste", data={"pasted_table": PASTED})
    with app.app_context():
        document_id = SourceDocument.query.filter_by(document_type="award_record").one().id
    response = client.post(f"/student/learning-profile/documents/{document_id}/delete", data={"next": "https://evil.example"})
    assert response.headers["Location"].endswith("/student/files")
