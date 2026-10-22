"""獎懲記錄：學生從學校系統下載後上傳，AI 逐列讀出並分類，學生確認後才存入。"""
import io

from app.extensions import db
from app.models import Portfolio, SourceDocument
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


def test_draft_skips_punishments_and_revoked_rows():
    draft = service.build_draft(ROWS)

    reasons = [row["reason"] for row in draft["rows"]]
    assert len(reasons) == 3
    assert not any("遲到" in reason for reason in reasons)
    assert not any("永吉" in reason for reason in reasons)
    assert draft["rows"][0]["category"] == "service"
    assert draft["rows"][1]["category"] == "competition"
    assert draft["rows"][0]["school_year"] == 114
    assert any("2 筆" in warning for warning in draft["warnings"])


def test_ai_category_is_used_only_when_rules_do_not_match():
    draft = service.build_draft([
        {"date": "2025/06/11", "name": "嘉獎", "count": 1, "reason": "1132熱心公益", "category": "activity"},
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
    monkeypatch.setattr(service, "extract_rows", lambda path, name: (ROWS, []))
    app = records_app(tmp_path)
    client = app.test_client()
    login(client)

    html = client.get(_upload(client).headers["Location"]).get_data(as_text=True)

    assert "麗山國中" in html
    assert "遲到" not in html
    assert 'value="competition" selected' in html


def test_confirm_creates_records_with_school_source(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "extract_rows", lambda path, name: (ROWS, []))
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


def test_confirm_twice_does_not_duplicate(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "extract_rows", lambda path, name: (ROWS, []))
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
    monkeypatch.setattr(service, "extract_rows", lambda path, name: (ROWS, []))
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
