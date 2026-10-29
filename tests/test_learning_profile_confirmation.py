import json

import pytest

from app import create_app
from app.extensions import db
from app.models import (
    CredentialRecord,
    DocumentExtraction,
    LearningCourseRecord,
    SourceDocument,
    User,
)


def learning_profile_app(tmp_path):
    app = create_app({
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "TESTING": True,
        "UPLOAD_FOLDER": str(tmp_path),
    })
    with app.app_context():
        db.create_all()
        for username in ("student_demo", "other_student"):
            user = User(username=username, display_name=username, role="student")
            user.set_password("pw")
            db.session.add(user)
        db.session.commit()
        owner = User.query.filter_by(username="student_demo").one()
        document = SourceDocument(
            owner_id=owner.id,
            document_type="transcript",
            display_name="transcript.pdf",
            file_path=str(tmp_path / "transcript.pdf"),
            sha256="c" * 64,
            status="extracted",
        )
        db.session.add(document)
        db.session.flush()
        db.session.add(DocumentExtraction(
            source_document_id=document.id,
            provider="fake",
            status="extracted",
            result_json={"courses": []},
        ))
        db.session.commit()
        return app, document.id


def login(client, username="student_demo"):
    client.post("/login", data={"username": username, "password": "pw"})


def test_student_confirmation_persists_courses_and_credentials(tmp_path):
    app, document_id = learning_profile_app(tmp_path)
    client = app.test_client()
    login(client)

    response = client.post(
        f"/student/learning-profile/documents/{document_id}/review/confirm",
        data={
            "scores_unlocked": "1",
            "courses_json": json.dumps([
                {"course_name": "程式設計", "credits": 3, "score": 92},
                {"course_name": "資訊管理", "credits": 2, "status_mark": "抵", "grade_level": "二年級"},
            ]),
            "credentials_json": json.dumps([
                {"credential_name": "資訊技術類測試證照", "level": "丙級", "issuing_organization": "測試發證單位"},
            ]),
        },
    )

    assert response.status_code == 302
    with app.app_context():
        courses = LearningCourseRecord.query.order_by(LearningCourseRecord.id).all()
        assert [(course.course_name, course.score, course.status_mark) for course in courses] == [
            ("程式設計", 92, None),
            ("資訊管理", None, "抵"),
        ]
        assert courses[1].grade_level == "二年級"
        assert CredentialRecord.query.one().credential_name == "資訊技術類測試證照"
        extraction = DocumentExtraction.query.one()
        assert extraction.status == "confirmed"
        assert extraction.confirmed_by.username == "student_demo"


def test_credential_review_shows_editable_fields(tmp_path):
    app, document_id = learning_profile_app(tmp_path)
    with app.app_context():
        document = db.session.get(SourceDocument, document_id)
        document.document_type = "credential"
        document.display_name = "certificate.jpg"
        document.extraction.result_json = {
            "courses": [],
            "credentials": [{
                "credential_name": "電腦軟體應用",
                "level": "乙級",
                "issuing_organization": "勞動部",
            }],
        }
        db.session.commit()

    client = app.test_client()
    login(client)
    response = client.get(
        f"/student/learning-profile/documents/{document_id}/review"
    )

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "證照名稱" in page
    assert 'value="電腦軟體應用"' in page
    assert "證照等級" in page
    assert 'value="乙級"' in page
    assert "發證單位" in page
    assert 'value="勞動部"' in page


def test_credential_form_fields_are_saved(tmp_path):
    app, document_id = learning_profile_app(tmp_path)
    with app.app_context():
        document = db.session.get(SourceDocument, document_id)
        document.document_type = "credential"
        db.session.commit()

    client = app.test_client()
    login(client)
    response = client.post(
        f"/student/learning-profile/documents/{document_id}/review/confirm",
        data={
            "courses_json": "[]",
            "credentials_json": "[]",
            "credential_name": "電腦軟體應用",
            "credential_level": "乙級",
            "credential_issuing_organization": "勞動部",
        },
    )

    assert response.status_code == 302
    with app.app_context():
        credential = CredentialRecord.query.one()
        assert (credential.credential_name, credential.level, credential.issuing_organization) == (
            "電腦軟體應用", "乙級", "勞動部"
        )


def test_technician_review_shows_evidence_and_persists_only_confirmed_fields(tmp_path):
    from datetime import date

    app, document_id = learning_profile_app(tmp_path)
    with app.app_context():
        document = db.session.get(SourceDocument, document_id)
        document.document_type = "credential"
        document.extraction.result_json = {
            "courses": [],
            "credentials": [{"credential_name": "電腦軟體應用", "level": "乙級",
                             "issuing_organization": None, "issue_date": "2026-08-21"}],
            "credential_analysis": {
                "document_kind": "taiwan_technician_certificate",
                "document_label": "中華民國技術士證",
                "needs_review": True,
                "steps": ["辨識證照標題", "依版面分區重讀欄位"],
                "fields": {
                    "occupation": {"value": "電腦軟體應用", "raw_text": "電腦軟體應用", "confidence": .95, "reason": None},
                    "level": {"value": "乙級", "raw_text": "乙級", "confidence": .92, "reason": None},
                    "certificate_number": {"value": "118-0186204", "raw_text": "118-0186204", "confidence": .9, "reason": None},
                    "effective_date": {"value": "2026-08-21", "raw_text": "民國115年08月21日", "confidence": .9, "reason": None},
                    "issue_date": {"value": "2026-08-21", "raw_text": "民國115年08月21日", "confidence": .9, "reason": None},
                    "issuer": {"value": None, "raw_text": "", "confidence": None, "reason": "未辨識到欄位值，請對照原圖"},
                },
            },
        }
        db.session.commit()

    client = app.test_client()
    login(client)
    page = client.get(f"/student/learning-profile/documents/{document_id}/review").get_data(as_text=True)
    assert "中華民國技術士證" in page
    assert "需要人工確認" in page
    assert "118-0186204" in page
    assert "未辨識到欄位值，請對照原圖" in page
    assert 'name="credential_issue_date"' in page
    assert 'value="2026-08-21"' in page

    response = client.post(f"/student/learning-profile/documents/{document_id}/review/confirm", data={
        "courses_json": "[]", "credential_name": "電腦軟體應用", "credential_level": "乙級",
        "credential_issuing_organization": "勞動部", "credential_issue_date": "2026-08-22",
    })
    assert response.status_code == 302
    with app.app_context():
        record = CredentialRecord.query.one()
        assert (record.credential_name, record.level, record.issuing_organization, record.issue_date) == (
            "電腦軟體應用", "乙級", "勞動部", date(2026, 8, 22))
        result = DocumentExtraction.query.one().result_json
        assert result["credential_analysis"]["fields"]["certificate_number"]["value"] == "118-0186204"
        assert "certificate_number" not in result["credentials"][0]


def test_older_ocr_draft_offers_traditional_issuer_text_for_confirmation(tmp_path):
    app, document_id = learning_profile_app(tmp_path)
    with app.app_context():
        document = db.session.get(SourceDocument, document_id)
        document.document_type = "credential"
        document.extraction.result_json = {
            "courses": [],
            "credentials": [{"credential_name": "電腦硬體裝修", "level": "丙级",
                             "issuing_organization": "劳助部"}],
            "credential_analysis": {
                "document_kind": "taiwan_technician_certificate",
                "document_label": "中華民國技術士證",
                "fields": {"issuer": {"value": "劳助部", "raw_text": "劳助部發",
                                      "confidence": .75, "reason": "OCR 信心偏低，請核對"},
                           "certificate_number": {"value": None, "raw_text": "-0298233",
                                                  "confidence": .96, "reason": "未辨識到欄位值，請對照原圖"}},
            },
        }
        db.session.commit()
    client = app.test_client()
    login(client)
    page = client.get(f"/student/learning-profile/documents/{document_id}/review").get_data(as_text=True)
    assert "劳" not in page
    assert "丙级" not in page
    assert "OCR 原文（繁體顯示）：勞助部發" in page
    assert 'name="credential_issuing_organization" value="勞動部"' in page
    assert "總編號不完整" in page


def test_invalid_credential_issue_date_is_rejected(tmp_path):
    app, document_id = learning_profile_app(tmp_path)
    with app.app_context():
        db.session.get(SourceDocument, document_id).document_type = "credential"
        db.session.commit()
    client = app.test_client()
    login(client)
    response = client.post(f"/student/learning-profile/documents/{document_id}/review/confirm", data={
        "courses_json": "[]", "credential_name": "電腦軟體應用", "credential_level": "乙級",
        "credential_issuing_organization": "", "credential_issue_date": "2026-13-40",
    })
    assert response.status_code == 400
    with app.app_context():
        assert CredentialRecord.query.count() == 0


def test_unrecognized_credential_review_explains_manual_entry(tmp_path):
    app, document_id = learning_profile_app(tmp_path)
    with app.app_context():
        document = db.session.get(SourceDocument, document_id)
        document.document_type = "credential"
        document.extraction.result_json = {
            "courses": [], "credentials": [],
            "credential_analysis": {"document_kind": "unrecognized_credential",
                                    "document_label": "證照類型未辨識", "needs_review": True,
                                    "steps": ["未取得足夠文字；請對照原圖手動填寫"], "fields": {}},
        }
        db.session.commit()
    client = app.test_client()
    login(client)
    page = client.get(f"/student/learning-profile/documents/{document_id}/review").get_data(as_text=True)
    assert "證照類型未辨識" in page
    assert "需要人工確認" in page
    assert "請對照原圖手動填寫" in page
    assert 'name="credential_name"' in page


def test_credential_field_confirmation_preserves_other_draft_records(tmp_path):
    app, document_id = learning_profile_app(tmp_path)
    with app.app_context():
        document = db.session.get(SourceDocument, document_id)
        document.document_type = "credential"
        document.extraction.result_json = {"courses": [], "credentials": [
            {"credential_name": "第一張", "level": "乙級", "category": "技術士", "source_page": 1},
            {"credential_name": "第二張", "level": "丙級", "category": "其他", "source_page": 2},
        ]}
        db.session.commit()
    client = app.test_client()
    login(client)
    response = client.post(f"/student/learning-profile/documents/{document_id}/review/confirm", data={
        "courses_json": "[]", "credential_name": "第一張已修正", "credential_level": "乙級",
        "credential_issuing_organization": "勞動部", "credential_issue_date": "2026-08-21",
    })
    assert response.status_code == 302
    with app.app_context():
        assert [(item.credential_name, item.category) for item in CredentialRecord.query.order_by(CredentialRecord.id)] == [
            ("第一張已修正", "技術士"), ("第二張", "其他")]
        result = DocumentExtraction.query.one().result_json
        assert [item["source_page"] for item in result["credentials"]] == [1, 2]


def test_credential_advanced_json_mode_saves_all_edited_records(tmp_path):
    app, document_id = learning_profile_app(tmp_path)
    with app.app_context():
        db.session.get(SourceDocument, document_id).document_type = "credential"
        db.session.commit()
    client = app.test_client()
    login(client)
    response = client.post(f"/student/learning-profile/documents/{document_id}/review/confirm", data={
        "courses_json": "[]", "credential_input_mode": "json",
        "credential_name": "表單值不可蓋過 JSON", "credentials_json": json.dumps([
            {"credential_name": "第一張", "level": "乙級"},
            {"credential_name": "第二張", "level": "丙級"},
        ]),
    })
    assert response.status_code == 302
    with app.app_context():
        assert [item.credential_name for item in CredentialRecord.query.order_by(CredentialRecord.id)] == [
            "第一張", "第二張"]


def test_credential_json_mode_requires_the_json_payload(tmp_path):
    app, document_id = learning_profile_app(tmp_path)
    with app.app_context():
        db.session.get(SourceDocument, document_id).document_type = "credential"
        db.session.commit()
    client = app.test_client()
    login(client)
    response = client.post(f"/student/learning-profile/documents/{document_id}/review/confirm", data={
        "courses_json": "[]", "credential_input_mode": "json", "credential_name": "第一張",
    })
    assert response.status_code == 400


def test_multi_page_credential_review_shows_each_analysis_page(tmp_path):
    app, document_id = learning_profile_app(tmp_path)
    with app.app_context():
        document = db.session.get(SourceDocument, document_id)
        document.document_type = "credential"
        first = {"source_page": 1, "document_kind": "taiwan_technician_certificate",
                 "document_label": "第一頁技術士證", "needs_review": True, "fields": {}, "steps": []}
        second = {"source_page": 2, "document_kind": "taiwan_technician_certificate",
                  "document_label": "第二頁技術士證", "needs_review": True, "fields": {}, "steps": []}
        document.extraction.result_json = {"courses": [], "credentials": [
            {"credential_name": "電腦軟體應用", "source_page": 1},
            {"credential_name": "電腦硬體裝修", "source_page": 2}],
            "credential_analysis": first, "credential_analyses": [first, second]}
        db.session.commit()
    client = app.test_client()
    login(client)
    page = client.get(f"/student/learning-profile/documents/{document_id}/review").get_data(as_text=True)
    assert "第 1 頁・第一頁技術士證" in page
    assert "第 2 頁・第二頁技術士證" in page


def test_other_student_cannot_confirm_source_document(tmp_path):
    app, document_id = learning_profile_app(tmp_path)
    client = app.test_client()
    login(client, "other_student")

    response = client.post(
        f"/student/learning-profile/documents/{document_id}/review/confirm",
        data={"courses_json": "[]", "credentials_json": "[]"},
    )

    assert response.status_code == 403


@pytest.mark.skip(reason="刪除與保留政策（M10）待學校決定，本次未搬刪除上傳文件功能")
def test_student_can_delete_owned_source_document_without_erasing_confirmed_records(tmp_path):
    app, document_id = learning_profile_app(tmp_path)
    client = app.test_client()
    login(client)
    with app.app_context():
        document = db.session.get(SourceDocument, document_id)
        db.session.add(LearningCourseRecord(
            student_id=document.owner_id,
            source_document_id=document.id,
            course_name="程式設計",
            normalized_course_name="程式設計",
            credits=3,
            score=92,
        ))
        db.session.commit()

    response = client.post(f"/student/learning-profile/documents/{document_id}/delete")

    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(SourceDocument, document_id) is None
        assert DocumentExtraction.query.count() == 0
        record = LearningCourseRecord.query.one()
        assert record.source_document_id is None


@pytest.mark.parametrize("grade", ["一年級", "二年級", "三年級", "四年級", "五年級", "1年級", "2年級", "3年級", "4年級", "5年級", "1", "5"])
def test_confirmation_accepts_chinese_and_arabic_grades_without_losing_zero(tmp_path, grade):
    app, document_id = learning_profile_app(tmp_path)
    client = app.test_client()
    login(client)
    response = client.post(f"/student/learning-profile/documents/{document_id}/review/confirm", data={
        "scores_unlocked": "1",
        "courses_json": json.dumps([{"course_name": "Zero", "credits": 0, "score": 0, "grade_level": grade},
                                     {"course_name": "Missing", "credits": None, "score": None}]),
        "credentials_json": "[]",
    })
    assert response.status_code == 302
    with app.app_context():
        zero, missing = LearningCourseRecord.query.order_by(LearningCourseRecord.id).all()
        assert (zero.credits, zero.score) == (0, 0)
        assert zero.grade_level == (grade + "年級" if grade.isdigit() else grade)
        assert missing.credits is None and missing.score is None


def test_editable_course_fields_save_without_javascript(tmp_path):
    app, document_id = learning_profile_app(tmp_path)
    with app.app_context():
        DocumentExtraction.query.one().result_json = {"courses": [{"course_name": "Draft", "school_year": 115, "status_mark": "抵"}]}
        db.session.commit()
    client = app.test_client()
    login(client)
    response = client.post(f"/student/learning-profile/documents/{document_id}/review/confirm", data={
        "course_input_mode": "fields", "course_0_course_name": "Edited", "course_0_credits": "0",
        "course_0_score": "", "course_0_semester": "第二學期", "course_0_grade_level": "5年級",
        "courses_json": "[]", "credentials_json": "[]",
    })
    assert response.status_code == 302
    with app.app_context():
        course = LearningCourseRecord.query.one()
        assert (course.course_name, course.credits, course.score, course.semester, course.grade_level) == ("Edited", 0, None, "第二學期", "5年級")
        assert course.school_year == 5 and course.status_mark == "抵"


def test_unconfirmed_document_excluded_from_ai_input(tmp_path):
    """全域規則：未經學生確認的 OCR 資料不得進入 AI 分析；按下確認後才會出現。"""
    from types import SimpleNamespace

    from app.services import agent_file_tool, autobiography_service

    draft_course = "草稿限定課名甲乙丙"
    draft_credential = "草稿限定證照丁戊己"
    app, document_id = learning_profile_app(tmp_path)
    with app.app_context():
        document = db.session.get(SourceDocument, document_id)
        document.extraction.result_json = {
            "courses": [{"course_name": draft_course, "credits": 3, "score": 88, "grade_level": "二年級"}],
            "credentials": [{"credential_name": draft_credential, "level": "乙級"}],
        }
        db.session.commit()

    def ai_inputs():
        """回傳兩個 AI 輸入入口的文字：升學 Agent 取檔工具、自傳事實清單。"""
        student = User.query.filter_by(username="student_demo").one()
        tool = {t.name: t for t in agent_file_tool.document_tools(student)}["get_my_document"]
        agent_text = repr(tool.run(document_id=str(document_id)))
        facts = autobiography_service.build_facts(student, SimpleNamespace(id=1, items=[]))
        return agent_text, repr(facts)

    with app.app_context():
        for text in ai_inputs():
            assert draft_course not in text and draft_credential not in text

    client = app.test_client()
    login(client)
    response = client.post(f"/student/learning-profile/documents/{document_id}/review/confirm", data={
        "scores_unlocked": "1",
        "courses_json": json.dumps([{"course_name": draft_course, "credits": 3, "score": 88, "grade_level": "二年級"}]),
        "credentials_json": json.dumps([{"credential_name": draft_credential, "level": "乙級"}]),
    })
    assert response.status_code == 302

    with app.app_context():
        for text in ai_inputs():
            assert draft_course in text and draft_credential in text
